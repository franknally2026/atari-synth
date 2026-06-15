"""Quantitative & property-based verification — the synth doesn't just make
*a* sound, it makes the *exact* sound/pitch/timing we designed. These replace
'present/relative' acoustic checks with measured Hz / ms / cents / monotonic
sweeps over full parameter ranges.
"""
import numpy as np
from .. import dsp, notes
from ..harness import PH_ATTACK, PH_DECAY, PH_SUSTAIN, PH_RELEASE

LFO_LEVEL_U = 0x0665
LFO_OFFSET = 0x0668


def _hold(s, idx, mode=notes.MODE_NORMAL, wave=1, volume=13):
    s.set("clock15", mode); s.poke(0x0689, mode)
    s.set("wave", wave); s.set("volume", volume); s.set("sus", 14)
    s.set("lfod", 0); s.set("detune", 0); s.poke(0x06B6, 0)   # porta off
    s.poke(LFO_LEVEL_U, 0); s.poke(LFO_OFFSET, 0)
    for i in range(4):
        s.set("vlevel", 0, i); s.set("vphase", 0, i)
    s.set("vnote", idx, 0); s.set("vlevel", volume, 0)
    s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)


def tuning_sweep_16bit(s, rep):
    """Every note across the 65-note table renders within a few cents of its
    designed pitch in 16-bit mode (the in-tune mode). The literal 'what we
    tuned is what sounds', swept over the whole range — not one note."""
    rep.section("quant: full-range 16-bit tuning sweep (<5 cents everywhere)")
    worst = (0, 0.0)
    with s.frozen("trigger_voices"):
        for idx in (*range(0, 61, 6), 62, 64):         # C2..E7, 13 points
            _hold(s, idx, mode=notes.MODE_16BIT)
            clip = s.capture(f"tune16_{idx}", 22)
            f = dsp.median_pitch(clip)
            exp = notes.predicted_freq(idx, notes.MODE_16BIT)
            c = notes.cents(f, exp) if f > 0 else 999
            if abs(c) > abs(worst[1]):
                worst = (idx, c)
    rep.check("every 16-bit note in tune to <5 cents",
              abs(worst[1]) <= 5, f"worst idx{worst[0]}={worst[1]:+.1f}c")


def octave_sweep(s, rep):
    """An octave up doubles the frequency, everywhere across the keyboard (not
    just one pair). 16-bit for clean resolution."""
    rep.section("quant: octave-doubling across the whole range")
    worst = (0, 0.0)
    with s.frozen("trigger_voices"):
        for idx in range(0, 49, 8):
            _hold(s, idx, mode=notes.MODE_16BIT)
            lo = dsp.median_pitch(s.capture(f"oct_lo_{idx}", 20))
            _hold(s, idx + 12, mode=notes.MODE_16BIT)
            hi = dsp.median_pitch(s.capture(f"oct_hi_{idx}", 20))
            if lo > 0 and hi > 0:
                c = notes.cents(hi, 2 * lo)
                if abs(c) > abs(worst[1]):
                    worst = (idx, c)
    rep.check("octave up doubles freq everywhere (<20 cents)",
              abs(worst[1]) <= 20, f"worst idx{worst[0]}={worst[1]:+.0f}c")


def volume_monotonic(s, rep):
    """RMS rises monotonically across ALL 16 volume levels (not just 3 points);
    level 0 is silent."""
    rep.section("quant: loudness monotonic across all 16 levels")
    rms = []
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 15)
        for lvl in range(16):
            # hold an EXACT emitted level: RELEASE phase with a long count keeps
            # voice_level at our poke (SUSTAIN would overwrite it with sus_clamp)
            s.set("vnote", 24, 0); s.set("vlevel", lvl, 0)
            s.set("vphase", PH_RELEASE, 0); s.set("vcount", 200, 0); s.set("held", 0)
            rms.append(dsp.rms(s.capture(f"vol_{lvl}", 18)))
    # allow a tiny epsilon for measurement noise; require overall strong increase
    drops = sum(1 for i in range(1, 16) if rms[i] < rms[i - 1] - 0.004)
    rep.check("level 0 is silent", rms[0] < 1.5e-3, f"rms0={rms[0]:.5f}")
    rep.check("RMS rises monotonically over 0..15",
              drops == 0 and rms[15] > rms[1] * 3, f"drops={drops} rms15/rms1={rms[15]/max(rms[1],1e-6):.1f}")


def adsr_frame_timing(s, rep):
    """The envelope advances exactly one level step every (rate+1) frames, for
    ATTACK, DECAY and RELEASE — verified over the per-frame level timeline for
    several rates. (The exact rate->time law, never quantitatively checked.)"""
    rep.section("quant: ADSR steps every (rate+1) frames")

    def step_spacing(levels):
        chg = [i for i in range(1, len(levels)) if levels[i] != levels[i - 1]]
        return [chg[i + 1] - chg[i] for i in range(len(chg) - 1)]

    with s.frozen("trigger_voices"):
        for r in (1, 3, 6):
            # ATTACK
            s.set("clock15", 0); s.poke(0x0689, 0); s.set("volume", 15)
            s.set("atk", r); s.set("vnote", 24, 0); s.set("vlevel", 0, 0)
            s.set("vphase", PH_ATTACK, 0); s.set("vcount", 1, 0); s.set("held", 0)
            sp = step_spacing(s.timeline(8 * (r + 1) + 4, voices=(0,)).level(0))
            ok = sp and all(x == r + 1 for x in sp[:6])
            rep.check(f"ATTACK rate {r}: 1 step / {r+1} frames", ok, f"spacings={sp[:6]}")
            # RELEASE
            s.set("rel", r); s.set("vlevel", 15, 0); s.set("vphase", PH_RELEASE, 0)
            s.set("vcount", 1, 0); s.set("held", 0xFF)
            sp = step_spacing(s.timeline(8 * (r + 1) + 4, voices=(0,)).level(0))
            ok = sp and all(x == r + 1 for x in sp[:6])
            rep.check(f"RELEASE rate {r}: 1 step / {r+1} frames", ok, f"spacings={sp[:6]}")
        s.set("held", 0)


def sustain_clamp(s, rep):
    """Sustain level = min(sus_level, volume), and it tracks a live change to
    either while the voice is sustaining."""
    rep.section("quant: sustain = min(sus, volume), tracks live changes")
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0)
        s.set("volume", 8); s.set("sus", 15); s.set("dec", 0); s.set("atk", 0)  # sus>vol -> 8
        s.set("vnote", 24, 0); s.set("vlevel", 0, 0)
        s.set("vphase", PH_ATTACK, 0); s.set("vcount", 1, 0); s.set("held", 0)
        s.frame(30)
        rep.check("sus_level>volume clamps to volume (8)", s.get("vlevel", 0) == 8,
                  f"level={s.get('vlevel', 0)}")
        s.set("sus", 4); s.frame(8)
        rep.check("sustain follows sus_level lowered to 4", s.get("vlevel", 0) == 4,
                  f"level={s.get('vlevel', 0)}")
        s.set("volume", 3); s.frame(8)
        rep.check("sustain follows volume lowered to 3 (min)", s.get("vlevel", 0) == 3,
                  f"level={s.get('vlevel', 0)}")


def lfo_depth_monotonic(s, rep):
    """The vibrato (AUDF) depth grows monotonically with the LFO DEPTH param
    across its range, and is ~2*(depth>>1) AUDF peak-to-peak."""
    rep.section("quant: LFO depth scales monotonically (AUDF swing)")
    swings = {}
    with s.frozen("trigger_voices"):
        for lfod in (0, 4, 8, 12, 14):
            s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 12)
            s.poke(LFO_LEVEL_U, 0); s.poke(LFO_OFFSET, 0)
            s.set("detune", 0); s.set("lfod", lfod); s.set("lfor", 14)   # fast -> full cycles
            s.set("vnote", 0, 0); s.set("vlevel", 12, 0)
            s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
            af = s.timeline(120, voices=(0,)).audf(0)
            swings[lfod] = max(af) - min(af)
        s.poke(LFO_LEVEL_U, 0); s.poke(LFO_OFFSET, 0)
    seq = [swings[d] for d in (0, 4, 8, 12, 14)]
    rep.check("depth 0 -> no AUDF swing", swings[0] <= 1, f"swing0={swings[0]}")
    rep.check("AUDF swing monotonic non-decreasing with depth",
              all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1)), f"swings={seq}")
    rep.check("swing ~ 2*(depth>>1) at depth 14", abs(swings[14] - 2 * (14 >> 1)) <= 2,
              f"swing14={swings[14]} want ~{2*(14>>1)}")


def _audf16(s, v):
    """16-bit AUDF of voice v: lo on channel 2v+1, hi (audible) on channel 2v+2."""
    return s.chan(2 * v + 2)[0] * 256 + s.chan(2 * v + 1)[0]


def lfo_vibrato_16bit(s, rep):
    """REGRESSION: LFO and DETUNE must be audible in 16-bit too. 16-bit notes use
    a large AUDF, so the raw +-7 offset was inaudible (0% swing); the engine now
    scales the offset to the note (offset * AUDF16>>6), giving a fixed-% vibrato
    that also never wraps a high note."""
    rep.section("quant: LFO vibrato + detune work in 16-bit (scaled to the note)")
    s.set("clock15", 2); s.poke(0x0689, 2)          # stable 16-bit (vlimit=2, no clear)
    s.frame(2)

    def swing(depth):
        with s.frozen("trigger_voices"):
            s.set("wave", 1); s.set("volume", 12); s.set("detune", 0)
            s.poke(LFO_LEVEL_U, 0); s.poke(LFO_OFFSET, 0)
            s.set("lfod", depth); s.set("lfor", 14)
            s.set("vnote", 24, 0); s.set("vlevel", 12, 0)
            s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
            vals = [_audf16(s, 0) for _ in range(120) if not s.frame(1)]
            return max(vals) - min(vals)

    off, on = swing(0), swing(15)
    rep.check("16-bit LFO off -> no vibrato", off <= 2, f"swing={off}")
    rep.check("16-bit LFO on -> audible vibrato (was 0 before the scale fix)",
              on >= 50, f"swing={on}")

    # detune: voice 1's 16-bit AUDF must differ from voice 0's (a beat); off -> equal
    def spread(det):
        with s.frozen("trigger_voices"):
            s.set("wave", 1); s.set("volume", 12); s.set("lfod", 0)
            s.poke(LFO_LEVEL_U, 0); s.poke(LFO_OFFSET, 0); s.set("detune", det)
            for i in range(2):
                s.set("vnote", 24, i); s.set("vlevel", 12, i)
                s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
            s.set("held", 0); s.frame(4)
            return abs(_audf16(s, 0) - _audf16(s, 1))

    d0, d15 = spread(0), spread(15)
    rep.check("16-bit detune 0 -> voices in unison", d0 == 0, f"spread={d0}")
    rep.check("16-bit detune 15 -> voices spread apart (audible beat)", d15 >= 8,
              f"spread={d15}")
    s.set("clock15", 0); s.poke(0x0689, 0); s.frame(2)


def detune_beat_hz(s, rep):
    """Two detuned voices beat at the frequency predicted by their actual AUDF
    difference (measured, not just 'a beat exists')."""
    rep.section("quant: detune beat frequency matches the AUDF spread")
    results = []
    with s.frozen("trigger_voices"):
        for det in (8, 12, 15):
            s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 11)
            s.poke(LFO_LEVEL_U, 0); s.poke(LFO_OFFSET, 0); s.set("lfod", 0)
            s.set("sustain_ped", 1); s.set("detune", det)
            for i in range(2):
                s.set("vnote", 0, i); s.set("vlevel", 12, i)
                s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
            s.set("held", 0); s.frame(6)
            f1, f2 = s.chan(1)[0], s.chan(2)[0]          # the two AUDFs the engine set
            predicted = abs(notes.pokey_freq_8bit(f1) - notes.pokey_freq_8bit(f2))
            beat = dsp.beat_freq(s.capture(f"detbeat_{det}", 55))
            results.append((det, predicted, beat))
        s.set("sustain_ped", 0)
    ok = True
    detail = []
    for det, pred, beat in results:
        detail.append(f"det{det}:{beat:.1f}~{pred:.1f}Hz")
        if not (pred * 0.6 <= beat <= pred * 1.5 + 1):
            ok = False
    rep.check("measured beat matches predicted AUDF-difference Hz", ok, " ".join(detail))


def waveform_harmonics(s, rep):
    """SQUARE is odd-harmonic dominant; SQUARE and PURE are the same pure-tone
    distortion (near-identical spectra); BUZZ/NOISE are the poly distortions."""
    rep.section("quant: waveform harmonic identity (odd_even, SQUARE==PURE)")
    feats = {}
    with s.frozen("trigger_voices"):
        for wave, name in [(0, "SQUARE"), (1, "PURE"), (2, "BUZZ"), (3, "NOISE")]:
            _hold(s, 12, wave=wave)               # idx 12: mid pitch, harmonics resolvable
            c = s.capture(f"harm_{name}", 26)
            feats[name] = (dsp.spectral_features(c), dsp.median_pitch(c))
    sq, pu = feats["SQUARE"][0], feats["PURE"][0]
    rep.check("SQUARE is odd-harmonic dominant (odd_even>3)",
              sq["odd_even"] is not None and sq["odd_even"] > 3,
              f"odd_even={sq['odd_even']}")
    rep.check("SQUARE and PURE are the same pure-tone distortion (close flatness)",
              abs(sq["flatness"] - pu["flatness"]) < 0.03,
              f"SQ={sq['flatness']:.3f} PU={pu['flatness']:.3f}")
    rep.check("BUZZ/NOISE poly distortions differ from PURE",
              feats["BUZZ"][0]["flatness"] > pu["flatness"] * 1.5
              and feats["NOISE"][0]["flatness"] > pu["flatness"] * 1.5,
              f"BUZZ={feats['BUZZ'][0]['flatness']:.3f} NOISE={feats['NOISE'][0]['flatness']:.3f}")


SCENARIOS = [
    tuning_sweep_16bit,
    octave_sweep,
    volume_monotonic,
    adsr_frame_timing,
    sustain_clamp,
    lfo_depth_monotonic,
    lfo_vibrato_16bit,
    detune_beat_hz,
    waveform_harmonics,
]
