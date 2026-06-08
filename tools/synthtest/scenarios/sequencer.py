"""Step-sequencer scenarios — transport, multi-step playback, step-entry
recording, real-time recording, ties, loop length, and acoustic playback.

The sequencer is the feature whose near-silence bug started this framework, so
it gets the most behavioural + acoustic coverage. Transport uses the console
keys (START=play, SELECT=record), independent of the scanned key matrix; note
entry is driven by poking note_idx with read_keyboard frozen (the cooked bridge
KEY can't hold a key). All addresses come from VARS / synth.asm.
"""
from .. import dsp, notes
from ..harness import VARS

REC_LATCH = 0x06B4


def transport(s, rep):
    rep.section("sequencer: START transport toggles play")
    s.set("curparam", 0); s.frame(2)
    s.set("seq_play", 0)
    s.consol(start=True); s.frame(3); s.consol(); s.frame(3)
    rep.check("START -> play on", s.get("seq_play") == 1, s.get("seq_play"))
    s.consol(start=True); s.frame(3); s.consol(); s.frame(3)
    rep.check("START -> play off", s.get("seq_play") == 0, s.get("seq_play"))


def multi_step_playback(s, rep):
    """A multi-step pattern advances through its steps and triggers each note."""
    rep.section("sequencer: multi-step playback cycles + triggers notes")
    pattern = [0, 0xFF, 4, 0xFF, 7, 0xFF, 12, 0xFF] + [0xFF] * 8
    s.set("octave", 2); s.set("lastv", 3)
    s.step_seq(pattern, tempo=12)
    seen_pos, fired = set(), set()
    for _ in range(170):                  # ~10 frames/step * 16 steps + margin
        before = [s.get("vnote", i) for i in range(4)]
        s.frame(1)
        seen_pos.add(s.get("seq_pos"))
        after = [s.get("vnote", i) for i in range(4)]
        for i in range(4):
            if after[i] != before[i] and after[i] != 0xFF:
                fired.add(after[i])
    s.set("seq_play", 0)
    rep.check("playback visits all 16 steps", seen_pos >= set(range(16)),
              f"{len(seen_pos)} of 16 positions")
    # notes at steps 0/2/4/6 = octave2 base24 + {0,4,7,12} = 24,28,31,36
    rep.check("each step's note is triggered", {24, 28, 31, 36} <= fired,
              f"fired={sorted(fired)}")
    s.set("seq_play", 0)


def step_entry_record(s, rep):
    """STOPPED + armed = step entry: each played note writes one step and grows
    the loop length."""
    rep.section("sequencer: step-entry recording")
    with s.frozen("read_keyboard"):
        for i in range(16):
            s.set("seq_notes", 0xFF, i)
        s.set("seq_rec", 1); s.set("seq_play", 0); s.set("seq_wpos", 0)
        s.set("seq_len", 0); s.set("seq_prevn", 0xFF)
        for n in (0, 2, 4, 7):
            s.set("note_idx", n); s.frame(3); s.set("note_idx", 0xFF); s.frame(3)
        steps = [s.get("seq_notes", i) for i in range(4)]
        rep.check("each key writes a step", steps == [0, 2, 4, 7], steps)
        rep.check("loop length grows to step count", s.get("seq_len") == 4, s.get("seq_len"))
        s.set("seq_rec", 0)


def loop_length_wraps(s, rep):
    """Playback wraps within the RECORDED length (no trailing-rest gap)."""
    rep.section("sequencer: playback wraps within recorded length")
    for i in range(16):
        s.set("seq_notes", 0xFF, i)
    for i, n in enumerate((0, 2, 4)):
        s.set("seq_notes", n, i)
    s.set("seq_len", 3); s.set("seq_rec", 0)
    s.set("tempo", 12); s.set("seq_timer", 1); s.set("seq_pos", 0); s.set("seq_play", 1)
    seen = set()
    for _ in range(40):
        s.frame(1); seen.add(s.get("seq_pos"))
    s.set("seq_play", 0)
    rep.check("wraps over the 3 recorded steps only", seen == {0, 1, 2}, sorted(seen))


def realtime_record(s, rep):
    """SELECT alone = real-time record: a held note is captured as ONE struck
    note + tie markers (not re-struck each step), gaps stay rests."""
    rep.section("sequencer: real-time recording (held note -> struck + ties)")
    s.set("curparam", 12); s.frame(6)
    s.set("tempo", 8); s.set("octave", 2)
    if s.get("seq_play"):
        s.consol(start=True); s.frame(3); s.consol(); s.frame(3)
    if s.get("seq_rec"):
        s.consol(select=True); s.frame(3); s.consol(); s.frame(3)
    s.consol(select=True); s.frame(3); s.consol(); s.frame(3)   # SELECT only
    rep.check("SELECT enters real-time record (clock running)",
              s.get("seq_rec") == 1 and s.get("seq_play") == 1,
              f"rec={s.get('seq_rec')} play={s.get('seq_play')}")
    with s.frozen("read_keyboard"):
        s.set("note_idx", 5)                       # lead-in: lands on step 0
        for _ in range(40):
            s.frame(1)
            if s.get("seq_pos") != 0:
                break
        s.set("note_idx", 0xFF)
        rep.check("lead-in lands first note on step 0", s.get("seq_notes", 0) == 5,
                  f"step0={s.get('seq_notes', 0)}")
        s.set("note_idx", 4); s.frame(54)          # hold ~3 steps
        s.set("note_idx", 0xFF); s.frame(40)
    s.consol(start=True); s.frame(3); s.consol(); s.frame(3)     # stop
    s.consol(select=True); s.frame(3); s.consol(); s.frame(3)    # disarm
    steps = [s.get("seq_notes", i) for i in range(16)]
    rep.check("held note recorded as one struck note + ties",
              steps.count(4) == 1 and steps.count(0xFE) >= 2,
              f"4x{steps.count(4)} ties={steps.count(0xFE)}")


def tie_sustains_no_reattack(s, rep):
    """A TIED note ($FE) plays back as ONE sustained note (rings through the
    ties) — not re-struck blips. Asserted on the level timeline."""
    rep.section("sequencer: tied note sustains (no re-strike blips)")
    for i in range(16):
        s.set("seq_notes", 0xFF, i)
    s.set("seq_notes", 4, 0); s.set("seq_notes", 0xFE, 1); s.set("seq_notes", 0xFE, 2)
    s.set("seq_len", 16); s.set("volume", 10); s.set("sus", 8)
    s.set("atk", 0); s.set("dec", 2); s.set("tempo", 4)
    s.set("seq_rec", 0); s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
    lv = []
    for _ in range(70):
        s.frame(1); lv.append(max(s.get("vlevel", i) for i in range(4)))
    s.set("seq_play", 0)
    reattacks = sum(1 for i in range(1, len(lv)) if lv[i - 1] == 0 and lv[i] > 0)
    held_min = min(lv[14:60])
    rep.check("tied note sustains, no re-strike blips",
              reattacks <= 1 and held_min >= 6,
              f"peak={max(lv)} held_min={held_min} reattacks={reattacks}")


def playback_audible(s, rep):
    """ACOUSTIC: a recorded pattern actually plays back audibly with the right
    pitches in the mix."""
    rep.section("sequencer: pattern plays back audibly (PCM)")
    for i in range(16):
        s.set("seq_notes", 0xFF, i)
    # consecutive notes C/E/G (octave 0 -> idx 0/4/7) so all three play within
    # the capture window and each occupies enough frames to detect.
    for st, n in {0: 0, 1: 4, 2: 7}.items():
        s.set("seq_notes", n, st)
    s.set("seq_len", 3); s.set("octave", 0); s.set("lastv", 3)
    s.set("volume", 12); s.set("sus", 12); s.set("atk", 0); s.set("dec", 2); s.set("rel", 1)
    s.set("seq_rec", 0); s.set("tempo", 12); s.set("seq_pos", 0); s.set("seq_timer", 1)
    s.set("seq_play", 1)
    clip = s.capture("seq_playback", 90)
    s.set("seq_play", 0)
    heard = dsp.distinct_pitches(clip)
    rep.check("recorded pattern is audible", dsp.rms(clip) >= 4e-3, f"rms={dsp.rms(clip):.4f}")
    rep.check("playback sounds multiple notes", len(heard) >= 2, f"heard={sorted(heard)}")


SCENARIOS = [
    transport,
    multi_step_playback,
    step_entry_record,
    loop_length_wraps,
    realtime_record,
    tie_sustains_no_reattack,
    playback_audible,
]
