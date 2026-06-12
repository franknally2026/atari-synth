"""Scenario framework: timelines, a result reporter, acoustic + timeline
assertion helpers, and the effect-combination matrix generator.

The "DSL" is intentionally thin: a scenario is a plain function
``def scenario(s: Synth, rep: Reporter)`` that drives the synth and records
checks via ``rep``. The leverage is in:

  Timeline        - frame-by-frame POKEY/level capture with trajectory queries
                    (this is what catches "register looked fine but it went
                    silent" bugs the static peeks missed).
  assert_*        - acoustic intent expressed once (audible & sustained, pitch
                    in Hz, modulated at a rate, octave relationship, timbre).
  combo matrix    - curated musical presets + automated pairwise coverage of
                    every effect pair, so "SUS=3 + LFO=7 + ARP=2: still sounds
                    right?" is generated, not hand-written.
"""
import itertools
import numpy as np

from . import dsp, notes


# ===========================================================================
# Timeline
# ===========================================================================
class Timeline:
    """Frame-by-frame capture of POKEY + per-voice envelope state."""

    def __init__(self, rows, voices):
        self.rows = rows
        self.voices = list(voices)

    def __len__(self):
        return len(self.rows)

    def audf(self, voice):
        return [r["audf"][voice] for r in self.rows]

    def audc(self, voice):
        return [r["audc"][voice] for r in self.rows]

    def level(self, voice):
        i = self.voices.index(voice)
        return [r["level"][i] for r in self.rows]

    def phase(self, voice):
        i = self.voices.index(voice)
        return [r["phase"][i] for r in self.rows]

    def var(self, name):
        return [r[name] for r in self.rows]

    def active_count(self):
        """Per-frame count of channels with non-zero AUDC."""
        return [sum(1 for c in r["audc"] if c) for r in self.rows]

    def any_active(self):
        return [c > 0 for c in self.active_count()]

    # trajectory queries ----------------------------------------------------
    def max_level(self, voice):
        s = self.level(voice)
        return max(s) if s else 0

    def min_level_after_onset(self, voice, onset_thresh=1):
        """Lowest level once the voice has started sounding (catches a voice
        that attacks then collapses to near-silence — the sequencer bug)."""
        s = self.level(voice)
        started = [i for i, v in enumerate(s) if v >= onset_thresh]
        if not started:
            return 0
        return min(s[started[0]:])

    def audf_span(self, voice):
        """(min, max) AUDF over frames where the voice is audible."""
        af, lv = self.audf(voice), self.level(voice)
        vals = [a for a, l in zip(af, lv) if l > 0]
        return (min(vals), max(vals)) if vals else (0, 0)

    def sustained_level(self, voice, frac=0.5):
        """Median level over the second half of the audible region."""
        s = self.level(voice)
        nz = [i for i, v in enumerate(s) if v > 0]
        if not nz:
            return 0
        seg = s[nz[0] + int(len(nz) * frac):nz[-1] + 1]
        return float(np.median(seg)) if seg else 0


# ===========================================================================
# Reporter
# ===========================================================================
class Reporter:
    def __init__(self):
        self.results = []     # (group, name, ok, detail)
        self.group = "?"

    def section(self, name):
        self.group = name
        print(f"\n[{name}]")

    def check(self, name, ok, detail=""):
        self.results.append((self.group, name, bool(ok), str(detail)))
        flag = "  PASS " if ok else "  FAIL "
        print(flag + name + (f"  [{detail}]" if detail else ""))
        return bool(ok)

    @property
    def npass(self):
        return sum(1 for *_, ok, _ in self.results if ok)

    @property
    def nfail(self):
        return len(self.results) - self.npass

    def failures(self):
        return [(g, n, d) for g, n, ok, d in self.results if not ok]


# ===========================================================================
# Acoustic + timeline assertion helpers
#   Each takes the reporter and records one (or a few) checks.
# ===========================================================================
def assert_audible_sustained(rep, clip, name, min_rms=4e-3, min_voiced=0.5):
    """The clip carries a real, sustained tone — not silence, not a 1-frame
    blip that collapses. This is the acoustic form of the sequencer-bug guard."""
    r = dsp.rms(clip)
    t, f = dsp.pitch_track(clip)
    voiced_frac = float(np.mean(f > 0)) if len(f) else 0.0
    rep.check(f"{name}: audible (rms>{min_rms})", r >= min_rms, f"rms={r:.4f}")
    rep.check(f"{name}: sustained (voiced>{min_voiced:.0%})",
              voiced_frac >= min_voiced, f"voiced={voiced_frac:.0%}")
    return r >= min_rms and voiced_frac >= min_voiced


def assert_silent(rep, clip, name):
    rep.check(f"{name}: silent", dsp.is_silent(clip), f"rms={dsp.rms(clip):.5f}")


def assert_pitch_hz(rep, clip, name, expect_hz, tol_cents=60):
    """Measured fundamental matches an expected Hz within a cents tolerance.
    (POKEY's 8-bit divider quantises pitch, so the tolerance is generous for
    high notes; pass a tighter tol for low notes / 16-bit mode.)"""
    f = dsp.median_pitch(clip)
    if f <= 0:
        return rep.check(f"{name}: pitch ~{expect_hz:.1f}Hz", False, "no pitch detected")
    err = notes.cents(f, expect_hz)
    ok = abs(err) <= tol_cents
    rep.check(f"{name}: pitch ~{expect_hz:.1f}Hz ({notes.nearest_et(expect_hz)[0]})",
              ok, f"got {f:.1f}Hz {err:+.0f}c")
    return f


def assert_octave_up(rep, clip_lo, clip_hi, name, tol_cents=80):
    """clip_hi is one octave above clip_lo (frequency doubles)."""
    flo, fhi = dsp.median_pitch(clip_lo), dsp.median_pitch(clip_hi)
    if flo <= 0 or fhi <= 0:
        return rep.check(f"{name}: octave doubles", False, f"lo={flo:.1f} hi={fhi:.1f}")
    err = notes.cents(fhi, 2 * flo)
    rep.check(f"{name}: octave up doubles freq", abs(err) <= tol_cents,
              f"{flo:.1f}->{fhi:.1f}Hz ({err:+.0f}c vs 2x)")


def assert_engine_faithful_via_state(rep, s, name, voice=0, idx=None,
                                     audf=None, mode=notes.MODE_NORMAL,
                                     tol_cents=1.0):
    """Engine faithfulness without an audio capture: the emulator-reported
    output frequency on the voice's channel (AUDIO_STATE.freq_hz, exposed
    by ilmenit/AltirraSDL#71) matches the divider->Hz prediction.

    Use for 8-bit modes (NORMAL / 15 kHz), where the prediction formula
    ``clock / (2*(audf+1))`` is exact. In 16-bit mode the joined-pair
    timing has a small offset that the +1 form doesn't capture (the
    sweep showed up to ~30c at the top of the table), so this helper is
    not appropriate for 16-BIT until the prediction is recalibrated.

    Returns the reported Hz, or None on failure."""
    if idx is not None:
        expect = notes.predicted_freq(idx, mode)
    else:
        expect = notes.audf_freq(audf, mode)
    reported = s.channel_freq_hz(voice)
    if reported is None:
        rep.check(f"{name}: engine reports a freq_hz", False,
                  f"reported=None (channel idle?)")
        return None
    err = notes.cents(reported, expect)
    ok = abs(err) <= tol_cents
    rep.check(f"{name}: reported Hz == predicted ({expect:.2f}Hz)",
              ok, f"reported={reported:.3f}Hz {err:+.2f}c")
    return reported


def assert_engine_faithful(rep, clip, name, audf=None, mode=notes.MODE_NORMAL,
                           idx=None, tol_cents=70):
    """The audio engine renders what the registers command: measured pitch
    matches the POKEY divider->Hz prediction. Catches clock-mode / 16-bit /
    rendering bugs that register peeks alone cannot."""
    if idx is not None:
        expect = notes.predicted_freq(idx, mode)
    else:
        expect = notes.audf_freq(audf, mode)
    f = dsp.median_pitch(clip)
    if f <= 0:
        return rep.check(f"{name}: engine renders commanded pitch", False, "no pitch")
    err = notes.cents(f, expect)
    rep.check(f"{name}: engine renders commanded pitch ({expect:.1f}Hz)",
              abs(err) <= tol_cents, f"got {f:.1f}Hz {err:+.0f}c")
    return f


def assert_modulated(rep, clip, name, expect_present=True, rate_range=None):
    """Pitch is (or is not) periodically modulated — vibrato / LFO."""
    m = dsp.vibrato(clip)
    if not expect_present:
        return rep.check(f"{name}: no pitch modulation", not m["present"],
                         f"depth={m['depth']:.1f}Hz rate={m['rate_hz']:.1f}")
    ok = m["present"]
    detail = f"rate={m['rate_hz']:.1f}Hz depth={m['depth']:.1f}Hz"
    if ok and rate_range:
        lo, hi = rate_range
        ok = lo <= m["rate_hz"] <= hi
        detail += f" (want {lo}-{hi})"
    rep.check(f"{name}: vibrato present", ok, detail)
    return m


def spectral_fingerprint(clip):
    """A compact, comparable timbre signature for golden/regression checks."""
    f = dsp.spectral_features(clip)
    return dict(centroid=f["centroid"], flatness=f["flatness"],
                rolloff85=f["rolloff85"], pitch=dsp.median_pitch(clip),
                rms=dsp.rms(clip))


def assert_fingerprint_close(rep, clip, name, golden, tol=None):
    """Assert a clip's spectral fingerprint matches a stored golden signature
    within tolerances (relative for centroid/rolloff/rms, absolute for flatness,
    cents for pitch). Catches timbre/tuning regressions a presence check misses."""
    tol = tol or {}
    fp = spectral_fingerprint(clip)
    bad = []
    def rel(k, t):
        g = golden.get(k)
        if g is None:
            return
        if g == 0:
            if abs(fp[k]) > t:
                bad.append(f"{k}={fp[k]:.3f} vs 0")
        elif abs(fp[k] - g) / abs(g) > t:
            bad.append(f"{k}={fp[k]:.1f} vs {g:.1f} ({100*(fp[k]-g)/g:+.0f}%)")
    rel("centroid", tol.get("centroid", 0.20))
    rel("rolloff85", tol.get("rolloff85", 0.25))
    rel("rms", tol.get("rms", 0.30))
    if golden.get("flatness") is not None and abs(fp["flatness"] - golden["flatness"]) > tol.get("flatness", 0.06):
        bad.append(f"flatness={fp['flatness']:.3f} vs {golden['flatness']:.3f}")
    if golden.get("pitch"):
        if fp["pitch"] <= 0 or abs(notes.cents(fp["pitch"], golden["pitch"])) > tol.get("cents", 60):
            bad.append(f"pitch={fp['pitch']:.0f} vs {golden['pitch']:.0f}Hz")
    rep.check(f"{name}: matches golden fingerprint", not bad,
              "ok" if not bad else "; ".join(bad))
    return fp


def assert_timbre(rep, clip, name, kind):
    """Coarse waveform-identity check from the spectrum.
      'tonal' - a clear pitched tone (low spectral flatness)
      'noise' - broadband / unpitched (high flatness, no stable pitch)
    """
    feat = dsp.spectral_features(clip)
    flat = feat["flatness"]
    f0 = dsp.median_pitch(clip)
    if kind == "noise":
        ok = flat > 0.25 or f0 == 0
        rep.check(f"{name}: noisy timbre", ok, f"flatness={flat:.2f} pitch={f0:.0f}")
    else:  # tonal
        ok = flat < 0.2 and f0 > 0
        rep.check(f"{name}: tonal timbre", ok, f"flatness={flat:.3f} pitch={f0:.0f}")
    return feat


def assert_no_collapse(rep, timeline, voice, name, floor=5):
    """The voice's envelope never collapses to near-silence after it starts
    sounding (the register-timeline form of the sequencer near-silence bug)."""
    mn = timeline.min_level_after_onset(voice)
    pk = timeline.max_level(voice)
    rep.check(f"{name}: level holds (no collapse)", pk >= floor and mn >= floor // 2 or pk == 0,
              f"peak={pk} min-after-onset={mn}")


# ===========================================================================
# Effect-combination matrix
# ===========================================================================
# Each axis: (param_name, [values]). Values are joystick/poke-settable work
# vars. Keep value sets small; pairwise keeps the combo count tractable.
DEFAULT_AXES = [
    ("wave", [0, 1, 2]),          # SQUARE, PURE, BUZZ (NOISE handled separately)
    ("octave", [1, 3]),           # low / high register
    ("clock15", [0, 2]),          # NORMAL / 16-bit
    ("sus", [2, 8, 14]),
    ("lfod", [0, 7, 15]),
    ("detune", [0, 8, 15]),
]

# Curated, musically-meaningful patches the user actually cares about. Each is
# a dict of work-var -> value; the matrix runner adds invariants on top.
CURATED_PRESETS = [
    {"name": "pad",      "wave": 1, "sus": 14, "rel": 8, "lfod": 5, "lfor": 4, "detune": 6},
    {"name": "lead",     "wave": 0, "sus": 10, "rel": 3, "lfod": 8, "lfor": 9, "detune": 0},
    {"name": "fat-arp",  "wave": 0, "sus": 8,  "rel": 4, "lfod": 0, "detune": 12, "arp": 9},
    {"name": "buzzy",    "wave": 2, "sus": 12, "rel": 5, "lfod": 3, "detune": 4},
    {"name": "user-case","wave": 0, "sus": 3,  "rel": 4, "lfod": 7, "detune": 0, "arp": 2},
]


def all_pairs(axes):
    """Greedy all-pairs (pairwise) combination cover. Returns a list of dicts
    {param: value}. Guarantees every value-pair across any two axes appears in
    at least one returned combo, with far fewer rows than the full product."""
    names = [a[0] for a in axes]
    values = [a[1] for a in axes]
    # all uncovered (i<j, vi, vj) pairs
    needed = set()
    for i in range(len(axes)):
        for j in range(i + 1, len(axes)):
            for vi in values[i]:
                for vj in values[j]:
                    needed.add((i, vi, j, vj))
    combos = []
    full = list(itertools.product(*values))  # candidate pool
    while needed:
        # pick the candidate covering the most still-needed pairs
        best, best_cov = None, -1
        for cand in full:
            cov = 0
            for i in range(len(cand)):
                for j in range(i + 1, len(cand)):
                    if (i, cand[i], j, cand[j]) in needed:
                        cov += 1
            if cov > best_cov:
                best, best_cov = cand, cov
        if best_cov <= 0:
            break
        for i in range(len(best)):
            for j in range(i + 1, len(best)):
                needed.discard((i, best[i], j, best[j]))
        combos.append(dict(zip(names, best)))
    return combos
