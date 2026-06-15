"""Timing / rhythm verification — measured from the actual rendered audio
(inter-onset intervals) and from exact per-frame register timelines. Confirms
the sequencer/arp/drum-machine play at the tempo we designed, not just that
events occur.

PAL = 50 frames/s (20 ms/frame). Sequencer step = (16-tempo)*2+2 frames.
Arp step = 16-arp_rate frames. Drum-beat period = (16-RHYTHM) tempo beats.
"""
import numpy as np
from .. import dsp

DRUM = 0x06BD
RHYTHM = 0x06C9


def seq_rhythm_from_audio(s, rep):
    """Record-free: load a pattern with notes on alternating steps, play at two
    tempos, and measure the inter-onset interval IN THE RENDERED AUDIO. The IOI
    (2 steps) must match (16-tempo)*2+2 frames x 20ms, and the two tempos' IOIs
    must be in the right ratio."""
    rep.section("timing: sequencer tempo -> audible inter-onset interval")
    # clean slate: no residual modulation/auto-drum/arp that would add spurious
    # amplitude pulses (false onsets) on top of the sequenced notes
    s.set("arp", 0); s.poke(RHYTHM, 0); s.poke(DRUM, 0); s.poke(0x06BE, 0)
    s.set("lfod", 0); s.set("detune", 0); s.poke(0x06B6, 0); s.set("sustain_ped", 0)
    s.poke(0x0665, 0); s.poke(0x0668, 0)
    for i in range(16):
        s.set("seq_notes", 0xFF, i)
    for st in (0, 4):                             # one note every 4 steps (3 rests
        s.set("seq_notes", 0, st)                 # between -> full decay -> clean onsets)
    s.set("seq_len", 8); s.set("octave", 0); s.set("lastv", 3)
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.set("volume", 13); s.set("sus", 12); s.set("atk", 0); s.set("dec", 0); s.set("rel", 0)
    s.set("seq_rec", 0)

    def ioi(tempo, frames):
        step_frames = (16 - tempo) * 2 + 2
        s.set("tempo", tempo); s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
        clip = s.capture(f"seq_rhythm_{tempo}", frames)
        s.set("seq_play", 0)
        gaps = dsp.inter_onset_intervals(clip, min_gap_ms=150)
        return (float(np.median(gaps)) if gaps else 0.0), step_frames

    ioi12, sf12 = ioi(12, 150)   # 10 fr/step -> 4 steps = 40 fr = 800 ms
    ioi4, sf4 = ioi(4, 280)      # 26 fr/step -> 4 steps = 104 fr = 2080 ms
    exp12 = 4 * sf12 / 50.0
    exp4 = 4 * sf4 / 50.0
    # exact frame timing is pinned deterministically by seq_tempo_exact_frames;
    # this audio cross-check uses a generous band (onset detection has slop).
    rep.check("tempo 12: audible IOI ~ 4 steps (800ms)", abs(ioi12 - exp12) < exp12 * 0.20,
              f"{ioi12*1000:.0f}ms vs {exp12*1000:.0f}ms")
    rep.check("tempo 4: audible IOI ~ 4 steps (2080ms)", abs(ioi4 - exp4) < exp4 * 0.20,
              f"{ioi4*1000:.0f}ms vs {exp4*1000:.0f}ms")
    rep.check("slower tempo -> proportionally longer IOI", ioi4 > ioi12 * 2.0,
              f"ratio={ioi4/max(ioi12,1e-3):.2f} (want ~2.6)")


def seq_tempo_exact_frames(s, rep):
    """The step interval is exactly (16-tempo)*2+2 frames — pinned at both
    extremes (tempo 0 = 34 frames, tempo 15 = 4 frames; never 0/hang)."""
    rep.section("timing: sequencer step interval exact frame count")
    for i in range(16):
        s.set("seq_notes", (i % 5), i)            # any notes; we watch seq_pos
    s.set("seq_len", 16); s.set("seq_rec", 0); s.set("octave", 0)

    def frames_per_step(tempo):
        s.set("tempo", tempo); s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
        tl = s.timeline(((16 - tempo) * 2 + 2) * 3 + 6, extra=["seq_pos"])
        s.set("seq_play", 0)
        pos = tl.var("seq_pos")
        # frames between successive seq_pos increments
        chg = [i for i in range(1, len(pos)) if pos[i] != pos[i - 1]]
        return [chg[i + 1] - chg[i] for i in range(len(chg) - 1)]

    for tempo, exp in ((0, 34), (15, 4), (8, 18)):
        sp = frames_per_step(tempo)
        ok = sp and all(x == exp for x in sp)
        rep.check(f"tempo {tempo}: {exp} frames/step", ok, f"spacings={sp}")


def arp_rate_exact(s, rep):
    """Arpeggiator step interval is exactly (16-arp_rate) frames — a DIFFERENT
    curve from the sequencer's. Measured from the per-frame held-voice changes."""
    rep.section("timing: arp step interval = 16 - arp_rate frames")
    s.set("clock15", 0); s.poke(0x0689, 0); s.set("octave", 2)
    s.set("volume", 13); s.set("sus", 10); s.set("atk", 0); s.set("rel", 1); s.poke(0x06B6, 0)
    with s.frozen("read_keyboard"):
        for rate, exp in ((6, 10), (12, 4)):
            s.set("note_idx", 0); s.set("lastv", 3)
            s.set("arp_step", 0); s.set("arp_timer", 1); s.set("arp", rate)
            tl = s.timeline(exp * 4 + 6, extra=["held"])
            held = tl.var("held")
            chg = [i for i in range(1, len(held)) if held[i] != held[i - 1]]
            sp = [chg[i + 1] - chg[i] for i in range(len(chg) - 1)]
            ok = sp and all(x == exp for x in sp[:4])
            rep.check(f"arp_rate {rate}: arp step every {exp} frames", ok, f"spacings={sp[:4]}")
        s.set("arp", 0); s.set("note_idx", 0xFF)


def drumbeat_period_exact(s, rep):
    """Auto drum-beat fires every (16-RHYTHM) tempo beats — exact frame gap
    between channel-4 hits, verified for two RHYTHM values."""
    rep.section("timing: RHYTHM auto period = (16-RHYTHM) tempo beats")
    s.set("clock15", 0); s.poke(0x0689, 0); s.poke(DRUM, 6); s.set("tempo", 13)
    beat = (16 - 13) * 2 + 2                       # 8 frames per tempo beat

    def hit_gaps(rhythm):
        s.poke(RHYTHM, rhythm); s.poke(0x06BE, 0)         # drum_level
        s.poke(0x06CA, 1); s.poke(0x06CB, 1)                 # dbeat_timer, dbeat_cnt
        tl = s.timeline((16 - rhythm) * beat * 3 + 10, voices=(3,))
        c4 = [r["audc"][3] & 0x0F for r in tl.rows]
        # a hit is an UPWARD jump in level (the drum only rises on a re-strike;
        # otherwise it decays) — robust even when it re-fires before fully decaying
        hits = [i for i in range(1, len(c4)) if c4[i] > c4[i - 1]]
        return [hits[i + 1] - hits[i] for i in range(len(hits) - 1)]

    for rhythm in (15, 13):
        exp = (16 - rhythm) * beat               # rh15 -> 1*8=8; rh13 -> 3*8=24
        gaps = hit_gaps(rhythm)
        ok = gaps and all(abs(g - exp) <= 1 for g in gaps)
        rep.check(f"RHYTHM {rhythm}: hits every {exp} frames", ok, f"gaps={gaps}")
    s.poke(RHYTHM, 0); s.poke(DRUM, 0); s.poke(0x06BE, 0)


SCENARIOS = [
    seq_rhythm_from_audio,
    seq_tempo_exact_frames,
    arp_rate_exact,
    drumbeat_period_exact,
]
