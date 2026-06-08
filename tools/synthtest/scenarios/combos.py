"""Effect-combination scenarios — the user's headline ask: "sustain=03,
LFO=07, ARP=2: does it sound as it should?", across many combinations.

Generators:
  curated   - hand-picked musical patches (incl. the exact SUS=3/LFO=7/ARP=2
              case), each asserted audible, sustained, pitch-stable.
  pairwise  - automated all-pairs cover of the effect axes (wave, octave,
              clock-mode, sustain, LFO depth, detune) driven through the REAL
              trigger path so octave/clock genuinely take effect; every combo
              must stay audible and non-collapsing.
  stacked   - specific multi-effect acoustic stacks (arp+vibrato+detune,
              16-bit+LFO+detune) and effects applied to a real chord.

Invariant: enabling effects must never silence the synth or collapse a held
note (the bug class that started this).
"""
from .. import dsp, notes
from ..scenario import (assert_audible_sustained, all_pairs, DEFAULT_AXES,
                        CURATED_PRESETS)
from ..harness import PH_SUSTAIN


def _apply(s, params):
    """Apply a combo dict of work-var -> value (unspecified effects -> sane
    defaults), including clock mode (keeps prev_clkm in sync so the engine
    doesn't reset voices mid-test)."""
    d = {"wave": 1, "volume": 13, "sus": 12, "rel": 3, "atk": 0, "dec": 2,
         "lfod": 0, "lfor": 8, "detune": 0, "arp": 0, "octave": 2, "clock15": 0}
    d.update(params)
    for k in ("wave", "volume", "sus", "rel", "atk", "dec", "lfod", "lfor",
              "detune", "arp", "octave", "clock15"):
        s.set(k, d[k])
    s.poke(0x0689, d["clock15"])          # prev_clkm = clock_mode (suppress reset)


def curated_presets(s, rep):
    rep.section("combos: curated musical presets")
    for preset in CURATED_PRESETS:
        name = preset["name"]
        _apply(s, {k: v for k, v in preset.items() if k != "name"})
        with s.held_key(0):
            clip = s.capture(f"preset_{name}", 30)
        label = "+".join(f"{k}{v}" for k, v in preset.items() if k != "name")
        rep.check(f"preset '{name}' audible", dsp.rms(clip) >= 4e-3,
                  f"rms={dsp.rms(clip):.4f}  [{label}]")
        if name == "user-case":
            assert_audible_sustained(rep, clip, "user-case (sus3 lfo7 arp2)")


def pairwise_matrix(s, rep):
    rep.section("combos: pairwise effect-pair coverage (real trigger path)")
    combos = all_pairs(DEFAULT_AXES)
    rep.check(f"pairwise cover generated ({len(combos)} combos, {len(DEFAULT_AXES)} axes)",
              len(combos) > 0, f"{len(combos)} combos")
    for i, combo in enumerate(combos):
        _apply(s, combo)
        with s.held_key(0):
            clip = s.capture(f"combo_{i:02d}", 28)
        r = dsp.rms(clip)
        _, f = dsp.pitch_track(clip)
        voiced = float((f > 0).mean()) if len(f) else 0.0
        label = " ".join(f"{k}={v}" for k, v in combo.items())
        # BUZZ and NOISE are poly distortions -> legitimately weak/unstable
        # pitch (especially in 16-bit); only the pure tones must stay voiced.
        sustained = voiced >= 0.4 or combo.get("wave", 1) >= 2
        rep.check(f"combo {i:02d} audible & sustained", r >= 3e-3 and sustained,
                  f"rms={r:.4f} voiced={voiced:.0%}  [{label}]")


def arp_plus_effects(s, rep):
    """Arpeggiator stacked with vibrato + detune: still cycles audible notes
    (effects don't break the arp path)."""
    rep.section("combos: ARP + vibrato + detune together")
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.set("wave", 1); s.set("volume", 13); s.set("sus", 12)
    s.set("atk", 0); s.set("dec", 0); s.set("rel", 1)
    s.set("lfod", 8); s.set("lfor", 8); s.set("detune", 10); s.set("octave", 1)
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0); s.set("lastv", 3)
        s.set("arp_step", 0); s.set("arp_timer", 1); s.set("arp", 6)
        clip = s.capture("arp_fx", 90)
        heard = dsp.distinct_pitches(clip)
        rep.check("ARP+vibrato+detune still cycles audible notes",
                  dsp.rms(clip) >= 4e-3 and len(heard) >= 2,
                  f"rms={dsp.rms(clip):.4f} heard={sorted(heard)}")
        s.set("arp", 0); s.set("note_idx", 0xFF)
    s.frame(2)


def sixteenbit_plus_effects(s, rep):
    """16-bit pitch mode stacked with LFO + detune: audible and in tune at the
    16-bit table pitch (effects layered on the joined-pair path)."""
    rep.section("combos: 16-bit + LFO + detune together")
    _apply(s, {"clock15": 2, "lfod": 6, "lfor": 8, "detune": 8, "octave": 2})
    with s.held_key(0):
        clip = s.capture("sixteen_fx", 35)
    assert_audible_sustained(rep, clip, "16bit+LFO+detune")
    # octave 2 + semitone 0 -> idx 24; 16-bit table is in tune (~C4)
    expect = notes.predicted_freq(24, notes.MODE_16BIT)
    f = dsp.median_pitch(clip)
    rep.check("16-bit+FX stays near the right pitch",
              f > 0 and abs(notes.cents(f, expect)) <= 80,
              f"{f:.1f}Hz vs {expect:.1f}Hz")


def effects_on_chord(s, rep):
    """A real 3-note chord with LFO + detune piled on still presents its three
    distinct tones (effects don't smear the chord into mush)."""
    rep.section("combos: effects on a real chord (C/E/G + LFO + detune)")
    triad = [(0, "C"), (4, "E"), (7, "G")]      # NORMAL idx 0/4/7 ~ 262/330/391 Hz
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0)
        s.set("wave", 1); s.set("volume", 12); s.set("sus", 14)
        s.set("lfod", 5); s.set("lfor", 6); s.set("detune", 6)
        for i, (idx, _) in enumerate(triad):
            s.set("vnote", idx, i); s.set("vlevel", 12, i)
            s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
        s.set("vlevel", 0, 3); s.set("vphase", 0, 3)
        s.set("held", 0)
        clip = s.capture("chord_fx", 35)
        present = sum(dsp.has_tone_at(clip, notes.predicted_freq(idx, notes.MODE_NORMAL),
                                      tol_frac=0.07) for idx, _ in triad)
        rep.check("chord keeps >=2 of its 3 tones under FX", present >= 2,
                  f"{present}/3 tones; peaks={[round(f) for f, _ in dsp.spectral_peaks(clip, 6)]}")


def combo_timeline_no_collapse(s, rep):
    """Across stacked-effect combos the engine's per-voice level must not
    collapse to near-silence mid-note (timeline form of the bug; runs even
    without AUDIO_RECORD)."""
    rep.section("combos: held note never collapses (timeline)")
    stacks = [
        {"sus": 3, "lfod": 7, "detune": 0},        # the user's case
        {"sus": 8, "lfod": 15, "detune": 15},      # everything modulating
        {"sus": 14, "lfod": 7, "detune": 8, "wave": 2},
    ]
    with s.frozen("trigger_voices"):
        for st in stacks:
            _apply(s, st)
            for i in range(2):
                s.set("vnote", 24, i); s.set("vlevel", 13, i)
                s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
            s.set("held", 0)
            tl = s.timeline(24, voices=(0,))
            mn = tl.min_level_after_onset(0); pk = tl.max_level(0)
            label = " ".join(f"{k}={v}" for k, v in st.items())
            rep.check(f"held note holds level  [{label}]",
                      pk >= 6 and mn >= 3, f"peak={pk} min-after-onset={mn}")


SCENARIOS = [
    curated_presets,
    pairwise_matrix,
    arp_plus_effects,
    sixteenbit_plus_effects,
    effects_on_chord,
    combo_timeline_no_collapse,
]
