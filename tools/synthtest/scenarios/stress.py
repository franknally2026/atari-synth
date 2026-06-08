"""Unusual / widest-scenario tests: boundary values, numerical overflow,
rapid state-thrashing, conflicting-effect combinations, and integrity
guarantees. These exercise behaviour that normal feature tests don't —
the kind of thing that breaks synths in the wild.
"""
import numpy as np
from .. import dsp, notes
from ..harness import PH_ATTACK, PH_SUSTAIN, PH_RELEASE, PH_IDLE

PORTA = 0x06B6
DRUM = 0x06BD
HPF = 0x06C0
DRUM_LEVEL = 0x06BE


def note_range_extremes(s, rep):
    """The very lowest and highest chromatic notes, and the trigger clamp at
    idx 64 (notes beyond the table must not run off the end)."""
    rep.section("stress: note-range extremes + chromatic clamp")
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 13)
        s.set("sus", 14); s.set("lfod", 0); s.set("detune", 0); s.poke(PORTA, 0)
        s.poke(0x0665, 0); s.poke(0x0668, 0)   # zero LFO counter+offset (clean AUDF)
        for idx in (0, 64):
            for i in range(4):
                s.set("vlevel", 0, i); s.set("vphase", 0, i)
            s.set("vnote", idx, 0); s.set("vlevel", 13, 0)
            s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
            s.frame(2)
            f, c = s.chan(1)
            audf = notes.chromatic()[idx]
            rep.check(f"idx {idx} emits its AUDF ({audf}) and sounds",
                      f == audf and c != 0, f"AUDF={f} AUDC={c:#x}")
    # clamp: octave 4 (base 48) + a high semitone must clamp the absolute note
    # to 64 (the last table entry), not index past it. Set octave BEFORE the
    # note triggers (held_key triggers on entry).
    s.set("octave", 4)
    with s.held_key(20):                      # 48 + 20 = 68 -> clamp to 64
        s.frame(4)
        held = s.get("held")
        vn = s.get("vnote", held) if held != 0xFF else -1
        rep.check("note past the table clamps to idx 64", vn == 64, f"vnote={vn}")
    s.set("octave", 2)


def lfo_audf_overflow(s, rep):
    """A deep LFO on a very high note pushes AUDF below 0; POKEY's AUDF is an
    8-bit byte so it WRAPS (a documented glitch, not a crash). Verify the wrap
    happens AND that turning the LFO off cleanly restores the right pitch (no
    permanent corruption)."""
    rep.section("stress: LFO AUDF 8-bit wraparound on a high note (+ recovery)")
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 13)
        s.set("sus", 14); s.set("detune", 0)
        s.set("vnote", 60, 0); s.set("vlevel", 13, 0)   # AUDF ~3 (very high)
        s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
        s.set("lfod", 15); s.set("lfor", 12)
        af = s.timeline(40, voices=(0,)).audf(0)
        lo, hi = min(af), max(af)
        # base AUDF 3, offset down -> wraps to ~250s: span must straddle the wrap
        rep.check("deep LFO on a high note wraps AUDF (8-bit)",
                  lo < 16 and hi > 200, f"AUDF {lo}..{hi}")
        rep.check("AUDF always a valid byte (no crash/garbage)",
                  all(0 <= v <= 255 for v in af), f"{lo}..{hi}")
        # turn the LFO fully off: lfod=0 alone leaves the triangle counter to
        # decay slowly, so zero it directly (and the offset) for a clean state
        s.set("lfod", 0); s.poke(0x0665, 0); s.poke(0x0668, 0); s.frame(4)
        rep.check("LFO off restores the exact note AUDF (no corruption)",
                  s.chan(1)[0] == 3, f"AUDF={s.chan(1)[0]}")


def rapid_clock_switch(s, rep):
    """Thrash the clock mode (NORMAL/15kHz/16-bit) every frame while voices are
    active, then confirm the engine is still sane: voice levels valid, and a
    fresh note plays correctly afterward (the NORMAL<->16-bit vlimit wrap)."""
    rep.section("stress: rapid clock-mode switching while playing")
    with s.frozen("trigger_voices"):
        s.set("wave", 1); s.set("volume", 13); s.set("sus", 14); s.set("lastv", 3)
        for i in range(4):
            s.set("vnote", 24, i); s.set("vlevel", 12, i)
            s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
        s.set("held", 0)
        for k in range(30):
            s.set("clock15", k % 3); s.poke(0x0689, (k + 1) % 3)  # force resets
            s.frame(1)
        levels = [s.get("vlevel", i) for i in range(4)]
        rep.check("voice levels stay valid bytes through the storm",
                  all(0 <= v <= 15 for v in levels), f"levels={levels}")
        last = s.peek(0x0619)
        rep.check("last_voice stays in range", 0 <= last <= 3, f"last_voice={last}")
    # after the storm, settle to NORMAL and play a fresh note -> must sound
    s.set("clock15", 0); s.poke(0x0689, 0)
    with s.held_key(0):
        clip = s.capture("after_clock_storm", 24)
    rep.check("a fresh note still sounds after the storm", dsp.rms(clip) >= 4e-3,
              f"rms={dsp.rms(clip):.4f}")


def porta_plus_arp(s, rep):
    """Two effects that both want voice 0 (portamento glide + arpeggiator):
    they should coexist — the arp still cycles audible notes (no crash/stuck)."""
    rep.section("stress: portamento + arpeggiator together")
    s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 13)
    s.set("sus", 12); s.set("lfod", 0); s.set("detune", 0); s.set("octave", 1)
    s.set("atk", 0); s.set("rel", 1)
    s.poke(PORTA, 6)
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0); s.set("lastv", 3)
        s.set("arp_step", 0); s.set("arp_timer", 1); s.set("arp", 6)
        clip = s.capture("porta_arp", 90)
        heard = dsp.distinct_pitches(clip)
        rep.check("porta+arp stays audible and cycles notes",
                  dsp.rms(clip) >= 4e-3 and len(heard) >= 2,
                  f"rms={dsp.rms(clip):.4f} heard={sorted(heard)}")
        s.set("arp", 0); s.set("note_idx", 0xFF)
    s.poke(PORTA, 0); s.frame(2)


def mega_combo(s, rep):
    """Everything 8-bit-compatible at once: BUZZ wave + detune + deep LFO +
    HP filter + sustain pedal, two voices. Must stay audible and not collapse."""
    rep.section("stress: maximal effect stack (wave+detune+LFO+HP+sustain)")
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0)
        s.set("wave", 2); s.set("volume", 13); s.set("sus", 14)
        s.set("detune", 12); s.set("lfod", 10); s.set("lfor", 8)
        s.poke(HPF, 5); s.set("sustain_ped", 1)
        for i in range(2):
            s.set("vnote", 0, i); s.set("vlevel", 13, i)
            s.set("vphase", PH_SUSTAIN, i); s.set("vcount", 8, i)
        s.set("held", 0)
        tl = s.timeline(40, voices=(0, 1))
        clip = s.capture("mega", 30)
        pk = tl.max_level(0); mn = tl.min_level_after_onset(0)
        rep.check("mega-stack stays audible", dsp.rms(clip) >= 4e-3, f"rms={dsp.rms(clip):.4f}")
        rep.check("mega-stack level never collapses", pk >= 6 and mn >= 3,
                  f"peak={pk} min={mn}")
        s.poke(HPF, 0); s.set("sustain_ped", 0)


def sequencer_edge_patterns(s, rep):
    """Degenerate sequencer patterns: all drums, all ties, all rests."""
    rep.section("stress: degenerate sequencer patterns")

    def run(fill, frames=60, setup=None):
        for i in range(16):
            s.set("seq_notes", fill, i)
        if setup:
            setup()
        s.set("seq_len", 16); s.set("seq_rec", 0); s.set("tempo", 12)
        s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
        out = []
        for _ in range(frames):
            s.frame(1); out.append(s.nactive())
        s.set("seq_play", 0); s.frame(2)
        return out

    s.set("clock15", 0); s.poke(0x0689, 0); s.set("volume", 12); s.set("sus", 10)
    # all drums -> channel 4 keeps firing (drum active), no crash
    s.poke(DRUM, 8)
    act = run(0xFD)
    drum_on = max(act) > 0
    rep.check("all-drum pattern fires without crashing", drum_on, f"max active={max(act)}")
    s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)
    # all ties -> nothing is ever struck -> stays silent (no stuck note)
    for i in range(4):
        s.set("vlevel", 0, i); s.set("vphase", 0, i)
    s.set("held", 0xFF); s.frame(4)
    act = run(0xFE)
    rep.check("all-tie pattern never strikes a note", max(act) == 0, f"max active={max(act)}")
    # all rests -> silence
    act = run(0xFF)
    rep.check("all-rest pattern is silent", max(act) == 0, f"max active={max(act)}")


def extreme_envelopes(s, rep):
    """Degenerate ADSR settings: instant blip (atk0/dec0/sus0) and ultra-slow
    attack (atk15)."""
    rep.section("stress: extreme ADSR settings")
    with s.frozen("trigger_voices"):
        # instant attack, sustain 0 -> peaks then immediately falls to 0
        s.set("volume", 12); s.set("atk", 0); s.set("dec", 0); s.set("sus", 0)
        s.set("vnote", 24, 0); s.set("vlevel", 0, 0)
        s.set("vphase", PH_ATTACK, 0); s.set("vcount", 1, 0); s.set("held", 0)
        # attack ramps up one step/frame to the peak (12), then decays to sus=0;
        # needs ~12+12 frames to complete, so sample 30
        lv = s.timeline(30, voices=(0,)).level(0)
        rep.check("sus=0 blip peaks (12) then falls to 0", max(lv) == 12 and lv[-1] == 0,
                  f"peak={max(lv)} end={lv[-1]}")
        # ultra-slow attack: barely rises over many frames
        s.set("atk", 15); s.set("sus", 12)
        s.set("vlevel", 0, 0); s.set("vphase", PH_ATTACK, 0); s.set("vcount", 16, 0)
        lv = s.timeline(16, voices=(0,)).level(0)
        rep.check("atk=15 attack is very gradual (<=2 steps in 16 frames)",
                  max(lv) <= 2, f"reached {max(lv)}")


def silence_after_chaos(s, rep):
    """The integrity guarantee: after a chaotic burst of input (notes, arp,
    drum, sequencer, mode switches, effects), shutting everything off returns
    the synth to TRUE silence — no stuck voice or channel anywhere."""
    rep.section("stress: true silence returns after chaos")
    # --- chaos ---
    with s.frozen("read_keyboard"):
        s.set("octave", 2); s.set("volume", 13); s.set("sus", 12)
        s.set("lfod", 12); s.set("detune", 10); s.poke(HPF, 6); s.poke(DRUM, 8)
        s.set("note_idx", 3); s.set("arp", 7); s.set("arp_timer", 1)
        for i in range(16):
            s.set("seq_notes", (0xFD if i % 4 == 0 else i % 13), i)
        s.set("seq_len", 16); s.set("tempo", 14); s.set("seq_pos", 0)
        s.set("seq_timer", 1); s.set("seq_play", 1)
        for k in range(40):
            s.set("clock15", (k // 4) % 2)        # also flip NORMAL<->15kHz
            s.frame(1)
        s.set("note_idx", 0xFF)
    # --- shut everything off ---
    s.set("seq_play", 0); s.set("seq_rec", 0); s.set("arp", 0)
    s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0); s.set("sustain_ped", 0)
    s.set("lfod", 0); s.set("detune", 0); s.poke(HPF, 0)
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.set("held", 0xFF); s.set("prevheld", 0xFF)
    for i in range(4):
        s.set("vlevel", 0, i); s.set("vphase", PH_IDLE, i)
    for _ in range(60):
        s.frame(1)
        if s.nactive() == 0:
            break
    clip = s.capture("after_chaos", 20)
    rep.check("all channels silent after chaos", s.nactive() == 0, f"{s.nactive()} active")
    rep.check("audio is truly silent after chaos", dsp.is_silent(clip),
              f"rms={dsp.rms(clip):.5f}")


def rapid_retrigger(s, rep):
    """Machine-gun retriggering: hammer new notes far faster than they decay,
    then release — voices must cycle round-robin and all fall silent (none
    stuck on)."""
    rep.section("stress: rapid retriggering then clean release")
    s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 13)
    s.set("sus", 10); s.set("atk", 0); s.set("rel", 1); s.set("arp", 0)
    s.poke(PORTA, 0)
    seen = set()
    with s.frozen("read_keyboard"):
        for n in range(24):
            s.set("note_idx", (n % 12)); s.frame(1)   # new note almost every frame
            seen.add(s.get("held"))
            s.set("note_idx", 0xFF); s.frame(1)
        s.set("note_idx", 0xFF)
    rep.check("retriggering cycles across all voices", seen >= {0, 1, 2, 3},
              f"voices used={sorted(v for v in seen if v != 0xFF)}")
    for _ in range(80):
        s.frame(1)
        if s.nactive() == 0:
            break
    rep.check("all voices fall silent after the burst", s.nactive() == 0,
              f"{s.nactive()} active")


def octave_shift_while_ringing(s, rep):
    """Changing the OCTAVE knob must NOT repitch notes that are already ringing
    (octave only affects the next trigger; a sounding voice keeps its absolute
    note). Documented behaviour — guard it."""
    rep.section("stress: octave change leaves ringing voices' pitch alone")
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 13)
        s.set("sus", 14); s.set("lfod", 0); s.set("detune", 0); s.set("octave", 2)
        s.poke(0x0665, 0); s.poke(0x0668, 0)   # force LFO fully off (no residual offset)
        s.set("vnote", 24, 0); s.set("vlevel", 13, 0)
        s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
        s.frame(4); before = s.chan(1)[0]
        s.set("octave", 4); s.frame(4); after = s.chan(1)[0]
        rep.check("ringing voice keeps its pitch when OCTAVE changes",
                  before == after, f"AUDF {before} -> {after}")
    s.set("octave", 2)


def porta_in_16bit(s, rep):
    """Portamento is an 8-bit-path effect; in 16-bit mode it must be ignored
    cleanly (note plays at the correct in-tune 16-bit pitch, no glide/corruption)."""
    rep.section("stress: portamento is a clean no-op in 16-bit mode")
    s.set("clock15", 2); s.poke(0x0689, 2); s.set("wave", 1); s.set("volume", 13)
    s.set("sus", 14); s.set("lfod", 0); s.set("detune", 0); s.set("octave", 2)
    s.poke(PORTA, 10)
    with s.held_key(0):                        # idx 24 in 16-bit
        clip = s.capture("porta_16bit", 30)
    expect = notes.predicted_freq(24, notes.MODE_16BIT)
    f = dsp.median_pitch(clip)
    rep.check("16-bit note with PORTA on is audible and in tune",
              dsp.rms(clip) >= 4e-3 and f > 0 and abs(notes.cents(f, expect)) <= 60,
              f"{f:.1f}Hz vs {expect:.1f}Hz, rms={dsp.rms(clip):.4f}")
    s.poke(PORTA, 0); s.set("clock15", 0); s.poke(0x0689, 0)


def drum_plus_hpfilter(s, rep):
    """Drum (channel 4) and HP filter (channel 3 = cutoff clock, filters ch1)
    both reach into the channel allocation — they must coexist."""
    rep.section("stress: drum + HP filter share the channels cleanly")
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 13)
        s.set("sus", 14); s.set("lfod", 0); s.set("detune", 0)
        s.set("vnote", 0, 0); s.set("vlevel", 13, 0)
        s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
        s.poke(HPF, 8); s.frame(8)             # engage HP (settle)
        s.poke(DRUM, 8); s.poke(DRUM_LEVEL, 15); s.poke(0x06BF, 8); s.frame(3)
        rep.check("HP filter engaged (AUDCTL bit2)", (s.audctl() & 0x04) != 0, hex(s.audctl()))
        rep.check("drum ringing on channel 4", (s.chan(4)[1] & 0x0F) > 0, f"AUDC4={s.chan(4)[1]:#x}")
        rep.check("voice 0 still sounding on channel 1", s.chan(1)[1] != 0, f"AUDC1={s.chan(1)[1]:#x}")
    s.poke(HPF, 0); s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)


def seq_plus_arp(s, rep):
    """Sequencer playback AND the arpeggiator running at once — both drive
    trigger_note. It should stay audible (chaotic but not broken), and shutting
    both off must return to silence."""
    rep.section("stress: sequencer + arpeggiator simultaneously")
    s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 13)
    s.set("sus", 10); s.set("atk", 0); s.set("rel", 1); s.set("octave", 2); s.poke(PORTA, 0)
    for i in range(16):
        s.set("seq_notes", (0xFF if i % 2 else (i % 12)), i)
    s.set("seq_len", 16); s.set("seq_rec", 0); s.set("tempo", 12)
    s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0); s.set("arp", 6); s.set("arp_timer", 1)
        clip = s.capture("seq_arp", 70)
        rep.check("sequencer + arp together stays audible", dsp.rms(clip) >= 4e-3,
                  f"rms={dsp.rms(clip):.4f}")
        s.set("arp", 0); s.set("note_idx", 0xFF)
    s.set("seq_play", 0); s.set("held", 0xFF); s.set("prevheld", 0xFF)
    for i in range(4):
        s.set("vlevel", 0, i); s.set("vphase", PH_IDLE, i)
    for _ in range(60):
        s.frame(1)
        if s.nactive() == 0:
            break
    rep.check("silence returns after seq+arp are switched off", s.nactive() == 0,
              f"{s.nactive()} active")


SCENARIOS = [
    note_range_extremes,
    lfo_audf_overflow,
    rapid_clock_switch,
    porta_plus_arp,
    mega_combo,
    sequencer_edge_patterns,
    extreme_envelopes,
    rapid_retrigger,
    octave_shift_while_ringing,
    porta_in_16bit,
    drum_plus_hpfilter,
    seq_plus_arp,
    silence_after_chaos,
]
