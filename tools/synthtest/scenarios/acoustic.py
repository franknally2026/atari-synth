"""Acoustic scenarios — these RECORD real PCM from POKEY and assert on the
sound itself. This is the layer the user asked for: "does it actually sound
as it should". Skipped gracefully if the build lacks AUDIO_RECORD.

To get a steady tone to analyse we freeze trigger_voices (RTS) and hold a
voice in SUSTAIN at a known note, then capture ~0.5 s of audio while the
engine renders it. Each frame is 20 ms (PAL), so `frames=30` ~= 0.6 s.
"""
from .. import dsp, notes
from ..scenario import (assert_audible_sustained, assert_silent, assert_pitch_hz,
                        assert_octave_up, assert_engine_faithful, assert_modulated,
                        assert_timbre)
from ..harness import PH_SUSTAIN, PH_ATTACK


def _hold_and_capture(s, name, idx, frames=30, mode=notes.MODE_NORMAL,
                      wave=1, volume=12, lfod=0, lfor=8, detune=0):
    """Hold one voice on absolute chromatic index `idx` and capture audio."""
    s.set("clock15", mode); s.set("clock_mode", mode); s.poke(0x0689, mode)
    s.set("wave", wave); s.set("volume", volume); s.set("sus", 14)
    s.set("lfod", lfod); s.set("lfor", lfor); s.set("detune", detune)
    s.set("vnote", idx, 0); s.set("vlevel", 14, 0)
    s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
    return s.capture(name, frames)


def silence_is_silent(s, rep):
    rep.section("acoustic: silence")
    s.reset_voices()
    clip = s.capture("silence", 20)
    assert_silent(rep, clip, "at rest")


def real_pitch_normal(s, rep):
    rep.section("acoustic: real pitch (NORMAL clock) + engine fidelity")
    with s.frozen("trigger_voices"):
        # C4-labelled (idx 24). NORMAL clock renders 2 octaves above the label
        # (table is tuned for 15kHz) -> ~1055 Hz. We assert the engine renders
        # exactly what the divider commands (faithfulness), independent of the
        # naming question.
        clip = _hold_and_capture(s, "normal_c4", 24, wave=1)
        assert_audible_sustained(rep, clip, "idx24 NORMAL")
        f = assert_engine_faithful(rep, clip, "idx24 NORMAL", idx=24, mode=notes.MODE_NORMAL)
        if f:
            rep.check("  (reported) NORMAL idx24 measured pitch",
                      True, f"{f:.1f}Hz = {notes.nearest_et(f)[0]}")


def octave_relationship(s, rep):
    rep.section("acoustic: octave up doubles frequency")
    with s.frozen("trigger_voices"):
        lo = _hold_and_capture(s, "oct_lo", 24, wave=1)
        hi = _hold_and_capture(s, "oct_hi", 36, wave=1)   # +12 semitones
        assert_octave_up(rep, lo, hi, "idx24->idx36")


def semitone_in_tune(s, rep):
    """Adjacent semitones differ by the equal-tempered ratio (~1.0595).
    Tested in 16-bit mode, where POKEY's divider has the resolution to be in
    tune (NORMAL mode at high notes can't — its tiny 8-bit AUDF quantises the
    semitone badly, which is itself a finding the framework surfaces)."""
    rep.section("acoustic: semitone ratio (16-bit, where POKEY has resolution)")
    with s.frozen("trigger_voices"):
        a = _hold_and_capture(s, "semi_a", 24, mode=notes.MODE_16BIT, wave=1)
        b = _hold_and_capture(s, "semi_b", 25, mode=notes.MODE_16BIT, wave=1)
        fa, fb = dsp.median_pitch(a), dsp.median_pitch(b)
        if fa > 0 and fb > 0:
            err = notes.cents(fb / fa, 2 ** (1 / 12))
            rep.check("one semitone up = +100 cents", abs(err) <= 20,
                      f"{fa:.1f}->{fb:.1f}Hz ratio={fb/fa:.4f} ({err:+.0f}c vs 100c)")
        else:
            rep.check("one semitone up = +100 cents", False, f"fa={fa} fb={fb}")


def sixteen_bit_real_pitch(s, rep):
    """16-bit mode: register peeks cannot report output Hz (AUDIO_STATE limit),
    but PCM can. The 16-bit table is tuned in-tune, so idx24 should be ~C4
    (261.6 Hz) within a tight tolerance."""
    rep.section("acoustic: 16-bit mode real output pitch")
    with s.frozen("trigger_voices"):
        clip = _hold_and_capture(s, "sixteen_c4", 24, mode=notes.MODE_16BIT, wave=1)
        assert_audible_sustained(rep, clip, "16bit idx24")
        expect = notes.predicted_freq(24, notes.MODE_16BIT)
        assert_pitch_hz(rep, clip, "16bit idx24", expect, tol_cents=40)
        f = dsp.median_pitch(clip)
        if f:
            rep.check("  (reported) 16-bit idx24 measured pitch", True,
                      f"{f:.1f}Hz = {notes.nearest_et(f)[0]}")


def label_matches_pitch(s, rep):
    """The displayed note name must equal the note you actually HEAR — the
    label is valid. For several notes in NORMAL and 16-bit modes, the nearest
    equal-tempered note of the measured pitch must match the name draw_note
    shows (notes.displayed_note)."""
    rep.section("acoustic: displayed label == sounding pitch")
    with s.frozen("trigger_voices"):
        cases = [(24, notes.MODE_NORMAL), (36, notes.MODE_NORMAL),
                 (24, notes.MODE_16BIT), (28, notes.MODE_16BIT)]
        for idx, mode in cases:
            clip = _hold_and_capture(s, f"label_{idx}_{mode}", idx, mode=mode, wave=1)
            f = dsp.median_pitch(clip)
            heard = notes.nearest_et(f)[0] if f > 0 else "?"
            shown = notes.displayed_note(idx, mode)
            modename = {0: "NORMAL", 1: "15K", 2: "16BIT"}[mode]
            rep.check(f"idx{idx} {modename}: label '{shown}' == heard '{heard}'",
                      heard == shown, f"{f:.1f}Hz heard={heard} shown={shown}")


def clock_switch_voice_wrap(s, rep):
    """Regression: switching NORMAL->16-bit drops the voice limit 4->2. A stale
    last_voice of 2/3 must still wrap when the next note triggers, or the
    trigger writes a non-existent voice and the note is SILENT (and corrupts
    voice RAM). Set up the exact stale state, then play in 16-bit."""
    rep.section("regression: NORMAL->16-bit voice-limit wrap (was silent)")
    s.set("wave", 1); s.set("volume", 13); s.set("sus", 12); s.set("octave", 3)
    # 16-bit mode with the reset SUPPRESSED (prev_clkm == clock15) and a stale
    # last_voice of 3 from a 4-voice session: the trigger must wrap 4->0 itself.
    s.set("clock15", 2); s.poke(0x0689, 2); s.set("lastv", 3); s.frame(2)
    with s.held_key(0):
        clip = s.capture("clk_switch_16bit", 30)
    assert_audible_sustained(rep, clip, "16-bit note after NORMAL")
    s.set("clock15", 0)


def waveform_timbre(s, rep):
    """Each waveform has its expected spectral character. POKEY's "NOISE" is a
    poly-counter pattern (semi-tonal), not white noise, so we assert NOISE is
    markedly *noisier* (flatter spectrum) than the pure tones rather than
    broadband. SQUARE/PURE/BUZZ are periodic (low flatness)."""
    rep.section("acoustic: waveform timbres")
    feats = {}
    with s.frozen("trigger_voices"):
        for wave, label in [(0, "SQUARE"), (1, "PURE"), (2, "BUZZ"), (3, "NOISE")]:
            clip = _hold_and_capture(s, f"wave_{label.lower()}", 24, wave=wave)
            f = dsp.spectral_features(clip)
            f["pitch"] = dsp.median_pitch(clip)
            feats[label] = f
            rep.check(f"  (reported) {label}", True,
                      f"flatness={f['flatness']:.3f} centroid={f['centroid']:.0f}Hz "
                      f"pitch={f['pitch']:.0f}Hz")
    # SQUARE and PURE are POKEY's pure-tone distortions: clearly periodic.
    for label in ("SQUARE", "PURE"):
        rep.check(f"{label}: pure tone (low flatness, stable pitch)",
                  feats[label]["flatness"] < 0.08 and feats[label]["pitch"] > 0,
                  f"flatness={feats[label]['flatness']:.3f} pitch={feats[label]['pitch']:.0f}")
    # BUZZ is a richer (poly) distortion: harmonically fuller than the pure tone.
    rep.check("BUZZ richer than PURE (more harmonic content)",
              feats["BUZZ"]["flatness"] > feats["PURE"]["flatness"] * 1.5,
              f"BUZZ={feats['BUZZ']['flatness']:.3f} PURE={feats['PURE']['flatness']:.3f}")
    # NOISE is a poly distortion too — noticeably noisier than the pure tones
    # (in POKEY it is not necessarily flatter than BUZZ; both are non-pure).
    rep.check("NOISE noisier than the pure tones (poly distortion)",
              feats["NOISE"]["flatness"] > 3 * feats["PURE"]["flatness"],
              f"NOISE={feats['NOISE']['flatness']:.3f} PURE={feats['PURE']['flatness']:.3f}")
    # the four waveforms are mutually distinct timbres (not all the same sound)
    flats = sorted(feats[w]["flatness"] for w in ("SQUARE", "PURE", "BUZZ", "NOISE"))
    rep.check("four waveforms are distinct timbres",
              flats[-1] - flats[0] > 0.05,
              f"flatness span {flats[0]:.3f}..{flats[-1]:.3f}")


def vibrato_audible(s, rep):
    """LFO depth produces audible vibrato; depth 0 produces a steady pitch."""
    rep.section("acoustic: LFO vibrato")
    with s.frozen("trigger_voices"):
        clip = _hold_and_capture(s, "vib_on", 24, wave=1, lfod=15, lfor=12, frames=45)
        assert_modulated(rep, clip, "LFO depth 15", expect_present=True)
        clip0 = _hold_and_capture(s, "vib_off", 24, wave=1, lfod=0, frames=45)
        assert_modulated(rep, clip0, "LFO depth 0", expect_present=False)


def detune_beating(s, rep):
    """Detuned voices on the same note beat against each other (audible
    chorusing) — a steady amplitude beat in the envelope."""
    rep.section("acoustic: detune beating / chorus")
    # Use a LOW note (idx 0, large AUDF) so a per-voice detune offset produces
    # a small Hz difference -> a slow, audible beat. At high notes the tiny
    # AUDF makes detune jump by tens of Hz (no clean beat).
    def arm_two_voices(detune):
        # Re-arm BOTH voices on idx 0 and hold them with the sustain pedal so
        # neither decays across the 50-frame capture (only one voice can be the
        # "held" voice; the pedal keeps the rest sounding).
        s.set("clock15", 0); s.poke(0x0689, 0)
        s.set("wave", 1); s.set("volume", 10); s.set("sus", 14)
        s.set("lfod", 0); s.set("detune", detune); s.set("sustain_ped", 1)
        for i in range(2):
            s.set("vnote", 0, i); s.set("vlevel", 12, i)
            s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
        s.set("held", 0); s.frame(6)

    with s.frozen("trigger_voices"):
        arm_two_voices(15)
        beat = dsp.beat_freq(s.capture("detune_beat", 50))
        # detune 0 -> baseline: two identical tones still show a little DSP
        # phase ripple, so this is a RELATIVE check — detuning raises the beat.
        arm_two_voices(0)
        beat0 = dsp.beat_freq(s.capture("detune_none", 50))
        s.set("sustain_ped", 0)
        rep.check("detuned voices beat (chorus)", beat > 3.0, f"beat={beat:.2f}Hz")
        rep.check("detuning clearly increases beating", beat > 2.5 * max(beat0, 0.5),
                  f"detuned={beat:.2f}Hz vs detune0={beat0:.2f}Hz")


def clock_15khz(s, rep):
    """15 kHz clock mode (CLOCK=1): audible and at the table's tuned pitch
    (the chromatic table is tuned for this clock, ~in tune at the label)."""
    rep.section("acoustic: 15 kHz clock mode")
    with s.frozen("trigger_voices"):
        clip = _hold_and_capture(s, "clk15_c4", 24, mode=notes.MODE_15K, wave=1)
        assert_audible_sustained(rep, clip, "15kHz idx24")
        assert_engine_faithful(rep, clip, "15kHz idx24", idx=24, mode=notes.MODE_15K,
                               tol_cents=50)


def octave_knob_pitch(s, rep):
    """Turning the OCTAVE knob actually shifts the played note by an octave —
    tested through the real trigger path (octave_base), not a poked AUDF."""
    rep.section("acoustic: OCTAVE knob shifts pitch by an octave")
    def play_at_octave(octv, name):
        # reset_voices idles every voice so the previous note (fast release)
        # can't bleed into this capture and fool the pitch detector.
        s.reset_voices(volume=13)
        s.set("clock15", 0); s.poke(0x0689, 0)
        s.set("wave", 1); s.set("sus", 12); s.set("rel", 0); s.set("arp", 0)
        s.set("octave", octv)
        with s.held_key(0):
            return s.capture(name, 30)
    lo = play_at_octave(1, "oct_knob_1")
    hi = play_at_octave(2, "oct_knob_2")
    assert_octave_up(rep, lo, hi, "octave knob 1->2")


def volume_loudness(s, rep):
    """The VOLUME parameter scales loudness: higher VOLUME -> larger RMS."""
    rep.section("acoustic: VOLUME scales loudness")
    # The emitted channel volume IS the envelope level, so to exercise the
    # VOLUME *param* we let the level equal it (ceiling high, level = vol).
    levels = {}
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 15)
        for vol in (4, 9, 15):
            s.set("vnote", 24, 0); s.set("vlevel", vol, 0)
            s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
            clip = s.capture(f"vol_{vol}", 30)
            levels[vol] = dsp.rms(clip)
            rep.check(f"  (reported) level {vol}", True, f"rms={levels[vol]:.4f}")
    rep.check("louder VOLUME -> larger RMS (4<9<15)",
              levels[4] < levels[9] < levels[15],
              f"{levels[4]:.4f} < {levels[9]:.4f} < {levels[15]:.4f}")


def envelope_timing_audible(s, rep):
    """ATTACK / RELEASE rate parameters change the audible envelope timing:
    a bigger ATTACK lengthens the fade-in; a bigger RELEASE lengthens the tail.
    Measured from the recorded amplitude envelope (dsp.adsr)."""
    rep.section("acoustic: ATTACK / RELEASE timing scales with the rate param")
    with s.frozen("trigger_voices"):
        def attack_audio(atk):
            s.set("clock15", 0); s.poke(0x0689, 0)
            s.set("wave", 1); s.set("volume", 14); s.set("sus", 12)
            s.set("atk", atk); s.set("dec", 0)
            s.set("vnote", 24, 0); s.set("vlevel", 0, 0)
            s.set("vphase", PH_ATTACK, 0)
            s.set("vcount", 1, 0); s.set("held", 0)
            return dsp.adsr(s.capture(f"atk_{atk}", 45))["attack_s"]
        fast = attack_audio(0)
        slow = attack_audio(9)
        rep.check("slower ATTACK -> longer audible fade-in", slow > fast + 0.05,
                  f"atk0={fast*1000:.0f}ms atk9={slow*1000:.0f}ms")

        def release_fall(rel):
            s.set("wave", 1); s.set("volume", 14); s.set("sus", 12)
            s.set("vnote", 24, 0); s.set("vlevel", 12, 0)
            s.set("vphase", 4, 0)            # RELEASE
            s.set("vcount", 1, 0); s.set("rel", rel); s.set("held", 0xFF)
            # measure how long the amplitude takes to fall to 30% of its peak
            return dsp.fall_time(s.capture(f"rel_{rel}", 45), frac=0.3)
        rfast = release_fall(0)
        rslow = release_fall(9)
        rep.check("slower RELEASE -> longer audible decay", rslow > rfast + 0.05,
                  f"rel0={rfast*1000:.0f}ms rel9={rslow*1000:.0f}ms")


def lfo_rate_scales(s, rep):
    """A higher LFO RATE produces faster vibrato (higher modulation rate)."""
    rep.section("acoustic: LFO RATE scales vibrato speed")
    # Measure the LFO from the AUDF register wobble per frame (deterministic) —
    # far more reliable than tracking deep vibrato through pitch detection.
    # The LFO triangle period is 4*(depth/2)*(16-rate) frames, so a small depth
    # keeps cycles short enough to fit the capture window and resolve the rate.
    import numpy as np
    def lfo_rate(lfor):
        s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 12)
        s.set("lfod", 2); s.set("lfor", lfor)               # depth 2 -> short triangle
        s.set("vnote", 0, 0); s.set("vlevel", 12, 0)        # idx 0: big AUDF -> clean wobble
        s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
        af = s.timeline(100, voices=(0,)).audf(0)
        t = np.arange(len(af)) / 50.0                       # PAL: 50 frames/s
        return dsp.modulation(t, af, rate_band=(0.3, 25.0))
    with s.frozen("trigger_voices"):
        slow = lfo_rate(3)
        fast = lfo_rate(12)
        rep.check("higher LFO RATE -> faster AUDF wobble (vibrato)",
                  fast["present"] and slow["present"] and fast["rate_hz"] > slow["rate_hz"] + 0.3,
                  f"lfor3={slow['rate_hz']:.2f}Hz lfor12={fast['rate_hz']:.2f}Hz")


def arpeggiator(s, rep):
    """The arpeggiator cycles a chord (root,+4,+7,+12) from the held note:
    asserted both on the per-voice note state AND acoustically (several
    distinct pitches heard over time)."""
    rep.section("acoustic: arpeggiator cycles a chord")
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.set("wave", 1); s.set("volume", 13); s.set("sus", 10)
    s.set("lfod", 0); s.set("detune", 0); s.set("octave", 2)
    s.set("atk", 0); s.set("dec", 0); s.set("rel", 2)
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0); s.set("lastv", 3)
        s.set("arp_step", 0); s.set("arp_timer", 1); s.set("arp", 15)
        # behavioural: across steps the four voices take the chord notes
        seen = set()
        for _ in range(24):
            s.frame(1)
            for v in range(4):
                seen.add(s.get("vnote", v))
        chord = {24, 28, 31, 36}
        rep.check("ARP visits chord notes 24/28/31/36", chord <= seen,
                  f"seen={sorted(n for n in seen if n != 0xFF)}")
        # acoustic: a slower arp rate (each note rings long enough to detect)
        # at a lower octave (mid-range pitches track cleanly). Confirm several
        # distinct pitches actually sound over time.
        s.set("octave", 1); s.set("arp", 6); s.set("sus", 12); s.set("rel", 1)
        s.set("atk", 0); s.set("arp_step", 0); s.set("arp_timer", 1)
        clip = s.capture("arp_cycle", 90)
        pitches = dsp.distinct_pitches(clip)
        rep.check("ARP sounds several distinct pitches", len(pitches) >= 2,
                  f"heard={sorted(pitches)}")
        s.set("arp", 0); s.set("note_idx", 0xFF)
    s.frame(2)


def chord_distinct_pitches(s, rep):
    """A real simultaneous chord: three voices on C/E/G must produce three
    distinct tones in the mix (polyphony was only ever checked at the register
    level before)."""
    rep.section("acoustic: simultaneous chord = distinct tones in the mix")
    triad = [(0, "C"), (4, "E"), (7, "G")]   # NORMAL idx 0/4/7 = ~262/330/391 Hz
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0)
        s.set("wave", 1); s.set("volume", 12); s.set("sus", 14)
        s.set("lfod", 0); s.set("detune", 0)
        for i, (idx, _) in enumerate(triad):
            s.set("vnote", idx, i); s.set("vlevel", 12, i)
            s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
        for i in range(len(triad), 4):
            s.set("vlevel", 0, i); s.set("vphase", 0, i)
        s.set("held", 0)
        clip = s.capture("chord_ceg", 35)
        for idx, name in triad:
            hz = notes.predicted_freq(idx, notes.MODE_NORMAL)
            rep.check(f"chord tone {name} (~{hz:.0f}Hz) present",
                      dsp.has_tone_at(clip, hz, tol_frac=0.05),
                      f"peaks={[round(f) for f, _ in dsp.spectral_peaks(clip, 5)]}")


SCENARIOS = [
    silence_is_silent,
    real_pitch_normal,
    label_matches_pitch,
    clock_15khz,
    octave_knob_pitch,
    volume_loudness,
    envelope_timing_audible,
    lfo_rate_scales,
    arpeggiator,
    chord_distinct_pitches,
    octave_relationship,
    semitone_in_tune,
    sixteen_bit_real_pitch,
    waveform_timbre,
    vibrato_audible,
    detune_beating,
]
