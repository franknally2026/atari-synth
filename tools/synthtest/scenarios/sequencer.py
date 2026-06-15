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
SEQ_DIRTY = 0x06AA
PREV_SPOS = 0x06A7      # last-drawn head cache (invalidate to force a head redraw)
DRUM_LEVEL = 0x06BE
SCAN_GRID = 56          # step-cell scanline
SCAN_HEAD = 48          # play/write-head scanline


def _cell_col(step):
    """Framebuffer byte-column of step `step`'s grid cell (col = 4 + step*2)."""
    return 4 + step * 2


def _clear_pattern(s):
    for i in range(16):
        s.set("seq_notes", 0xFF, i)


def _show_seq_page(s):
    """Land on the sequencer page (internal page 1) and force a full grid + head
    redraw from the current seq state. cur_param drives the page, but `page`
    catches up a few frames later (input auto-repeat lag), so poll until page==1
    before invalidating the grid/head caches and re-blitting."""
    s.set("curparam", 12)                       # TEMPO -> sequencer page
    for _ in range(24):
        s.frame(1)
        if s.get("page") == 1:
            break
    s.poke(SEQ_DIRTY, 1); s.poke(PREV_SPOS, 0xFF); s.frame(4)


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


def realtime_arm_clears_and_runs(s, rep):
    """SELECT arms real-time record: it CLEARS the pattern, starts the clock
    (seq_play=1), and records from step 0. Disarming punches out but keeps the
    loop playing."""
    rep.section("sequencer: SELECT arms real-time record (clears + runs clock)")
    s.set("curparam", 12); s.frame(2)
    # the first console edge after an idle console is swallowed, so prime it with a
    # throwaway SELECT cycle, then force a clean disarmed start.
    s.consol(); s.frame(3)
    s.consol(select=True); s.frame(4); s.consol(); s.frame(4)        # prime
    s.set("seq_play", 0); s.set("seq_rec", 0)
    for i, n in enumerate((1, 2, 3, 4)):                             # notes to wipe
        s.set("seq_notes", n, i)
    s.consol(select=True); s.frame(4); s.consol(); s.frame(4)        # arm for real
    rep.check("arming starts the clock (play=1, rec=1)",
              s.get("seq_play") == 1 and s.get("seq_rec") == 1,
              f"play={s.get('seq_play')} rec={s.get('seq_rec')}")
    cleared = [s.get("seq_notes", i) for i in range(4)]
    rep.check("arming clears the existing pattern", cleared == [0xFF] * 4, cleared)
    s.consol(select=True); s.frame(4); s.consol(); s.frame(4)        # disarm
    rep.check("disarming keeps the loop playing", s.get("seq_play") == 1, s.get("seq_play"))
    s.set("seq_play", 0); s.set("seq_rec", 0)


def realtime_record_monitors_pattern(s, rep):
    """REGRESSION (overdub monitoring): while armed (play=1, rec=1) with no live
    key down, the EXISTING recorded notes must still play back audibly — the
    stepped note has to sustain its whole step, not get force-released after one
    frame (the old bug made record-mode playback near-silent)."""
    rep.section("sequencer: armed record still plays back the pattern (monitoring)")
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0xFF)
        _clear_pattern(s)
        s.set("seq_notes", 4, 0)                 # one sustained note, rest is empty
        s.set("seq_len", 8); s.set("octave", 2)
        s.set("volume", 12); s.set("atk", 0); s.set("dec", 2); s.set("sus", 10); s.set("rel", 6)
        s.set("tempo", 2)                        # slow: step 0 spans ~30 frames
        s.set("seq_rec", 1); s.set("seq_play", 1)
        s.set("seq_pos", 0); s.set("seq_timer", 1)
        s.poke(REC_LATCH, 0xFF); s.set("seq_prevn", 0xFF)
        levels = []
        for _ in range(22):                      # all within step 0's window
            s.frame(1)
            levels.append(max(s.get("vlevel", v) for v in range(4)))
        s.set("seq_play", 0); s.set("seq_rec", 0)
    sustained = sum(1 for v in levels if v >= 6)
    rep.check("recorded note is audibly monitored while armed (not force-released)",
              sustained >= 10, f"sustained={sustained}/22 levels={levels}")


def realtime_overdub_keeps_existing(s, rep):
    """Within one armed session, playing a note on a later pass overdubs it WITHOUT
    erasing notes already captured this session."""
    rep.section("sequencer: overdub adds notes without erasing earlier ones")
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0xFF)
        _clear_pattern(s)
        s.set("seq_len", 8); s.set("octave", 2); s.set("tempo", 10)
        s.set("seq_rec", 1); s.set("seq_play", 1)
        s.set("seq_pos", 0); s.set("seq_timer", 1)
        s.poke(REC_LATCH, 0xFF); s.set("seq_prevn", 0xFF)
        # capture note 4 at step 0
        s.set("note_idx", 4)
        for _ in range(30):
            s.frame(1)
            if s.get("seq_pos") != 0:
                break
        s.set("note_idx", 0xFF)
        # advance to step 4, overdub note 7 there
        for _ in range(80):
            s.frame(1)
            if s.get("seq_pos") == 4:
                break
        s.set("note_idx", 7)
        for _ in range(30):
            s.frame(1)
            if s.get("seq_pos") == 5:
                break
        s.set("note_idx", 0xFF); s.frame(4)
        steps = [s.get("seq_notes", i) for i in range(16)]
        s.set("seq_play", 0); s.set("seq_rec", 0)
    rep.check("overdubbed note is recorded", 7 in steps, f"steps={steps}")
    rep.check("the earlier note is NOT erased by the overdub", 4 in steps, f"steps={steps}")


def realtime_record_drum_tap(s, rep):
    """REGRESSION (drum lane, real-time): tapping '1' ($FD) while armed records a
    $FD drum step, and that step fires the drum on playback."""
    rep.section("sequencer: real-time drum tap records + plays a $FD drum step")
    s.set("clock15", 0); s.set("clock_mode", 0); s.set("drum_dec", 8); s.poke(DRUM_LEVEL, 0)
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0xFF)
        _clear_pattern(s)
        s.set("seq_len", 8); s.set("tempo", 8)
        s.set("seq_rec", 1); s.set("seq_play", 1)
        s.set("seq_pos", 0); s.set("seq_timer", 1)
        s.poke(REC_LATCH, 0xFF); s.set("seq_prevn", 0xFF)
        # tap the drum repeatedly so at least one step boundary captures an onset
        for _ in range(50):
            s.set("note_idx", 0xFD); s.frame(1)
            s.set("note_idx", 0xFF); s.frame(1)
        s.set("seq_rec", 0)
        steps = [s.get("seq_notes", i) for i in range(16)]
    ndrum = steps.count(0xFD)
    rep.check("real-time drum taps record at least one $FD step", ndrum >= 1, f"steps={steps}")
    # play the first drum step back -> channel 4 fires
    pos = steps.index(0xFD) if 0xFD in steps else 0
    s.set("seq_len", 8); s.set("tempo", 12)
    s.set("seq_pos", pos); s.set("seq_timer", 1); s.set("seq_play", 1)
    peak = 0
    for _ in range(6):
        s.frame(1); peak = max(peak, s.chan(4)[1] & 0x0F)
    s.set("seq_play", 0); s.set("drum_dec", 0); s.poke(DRUM_LEVEL, 0)
    rep.check("a recorded drum step fires the drum on playback", peak >= 12, f"ch4 peak={peak}")


def realtime_held_drum_no_tie(s, rep):
    """REGRESSION: a HELD '1' is a one-shot, not a sustain — it records exactly one
    $FD and must NOT smear into tie steps (the old bug rewrote it as $FE, so the
    drum step went silent on later loops)."""
    rep.section("sequencer: held drum key records one $FD, never smears into ties")
    s.set("clock15", 0); s.set("clock_mode", 0); s.set("drum_dec", 8); s.poke(DRUM_LEVEL, 0)
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0xFF)
        _clear_pattern(s)
        s.set("seq_len", 8); s.set("tempo", 10)
        s.set("seq_rec", 1); s.set("seq_play", 1)
        s.set("seq_pos", 0); s.set("seq_timer", 1)
        s.poke(REC_LATCH, 0xFF); s.set("seq_prevn", 0xFF)
        s.set("note_idx", 0xFD)                  # hold '1' across several loops
        for _ in range(2 * 8 * 14):
            s.frame(1)
        s.set("note_idx", 0xFF); s.frame(4)
        steps = [s.get("seq_notes", i) for i in range(16)]
        s.set("seq_play", 0); s.set("seq_rec", 0)
    s.set("drum_dec", 0); s.poke(DRUM_LEVEL, 0)
    rep.check("held drum records exactly one $FD (no auto-repeat)",
              steps.count(0xFD) == 1, f"steps={steps}")
    rep.check("held drum never becomes a tie ($FE)", steps.count(0xFE) == 0, f"steps={steps}")


def drum_step_sounds_during_record(s, rep):
    """A $FD step already in the pattern fires the drum even while armed (the head
    passing the drum field hits it during record, not only in pure playback)."""
    rep.section("sequencer: drum step sounds while the clock runs in record mode")
    s.set("clock15", 0); s.set("clock_mode", 0); s.set("drum_dec", 8); s.poke(DRUM_LEVEL, 0)
    with s.frozen("read_keyboard"):
        s.set("note_idx", 0xFF)
        _clear_pattern(s)
        s.set("seq_notes", 0xFD, 2)
        s.set("seq_len", 8); s.set("tempo", 12)
        s.set("seq_rec", 1); s.set("seq_play", 1)
        s.set("seq_pos", 0); s.set("seq_timer", 1)
        s.poke(REC_LATCH, 0xFF); s.set("seq_prevn", 0xFF)
        peak = 0
        for _ in range(60):
            s.frame(1); peak = max(peak, s.chan(4)[1] & 0x0F)
        s.set("seq_play", 0); s.set("seq_rec", 0)
    s.set("drum_dec", 0); s.poke(DRUM_LEVEL, 0)
    rep.check("$FD step fires the drum during record", peak >= 12, f"ch4 peak={peak}")


def rest_releases_note_on_playback(s, rep):
    """A rest step ($FF) silences the prior note during playback: the gate opens
    on a note step and closes on the following rest."""
    rep.section("sequencer: a rest step releases the held note (silent gap)")
    _clear_pattern(s)
    s.set("seq_notes", 4, 0)                     # note ... then rests
    s.set("seq_len", 8); s.set("octave", 2)
    s.set("volume", 12); s.set("atk", 0); s.set("dec", 2); s.set("sus", 10); s.set("rel", 1)
    s.set("seq_rec", 0); s.set("tempo", 6)
    s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
    lv = []
    for _ in range(60):
        s.frame(1); lv.append(max(s.get("vlevel", v) for v in range(4)))
    s.set("seq_play", 0)
    rep.check("note sounds on its step", max(lv[:20]) >= 8, f"peak={max(lv[:20])}")
    rep.check("note is silenced over the following rests", min(lv[40:]) == 0,
              f"tail_min={min(lv[40:])} lv={lv}")


def grid_glyphs(s, rep):
    """The step grid uses four distinct glyphs — '.'=rest, block=note, '-'=tie,
    '*'=drum — so the drum lane is readable (a drum is NOT a plain note block)."""
    rep.section("sequencer: step grid glyphs (rest / note / tie / drum)")
    _clear_pattern(s)
    s.set("seq_notes", 5, 0)        # note
    s.set("seq_notes", 0xFE, 1)     # tie
    s.set("seq_notes", 0xFD, 2)     # drum
    # step 3 stays rest
    s.set("seq_play", 0); s.set("seq_rec", 0); s.set("seq_pos", 0); s.set("seq_wpos", 0)
    _show_seq_page(s)
    note = s.cell(_cell_col(0), SCAN_GRID)
    tie = s.cell(_cell_col(1), SCAN_GRID)
    drum = s.cell(_cell_col(2), SCAN_GRID)
    rest = s.cell(_cell_col(3), SCAN_GRID)
    rep.check("note step renders a solid block ($80)", note == s.glyph(0x80), "note")
    rep.check("tie step renders '-' ($0D)", tie == s.glyph(0x0D), "tie")
    rep.check("drum step renders '*' ($0A)", drum == s.glyph(0x0A), "drum")
    rep.check("rest step renders '.' ($0E)", rest == s.glyph(0x0E), "rest")
    rep.check("drum glyph is distinct from a note block", drum != note,
              "drum and note look identical")


def head_marks_active_step(s, rep):
    """The ↓ head marker ($5D, scanline 48) sits above the active step and only
    there (it moves as the play head advances)."""
    rep.section("sequencer: play-head marker tracks the active step")
    _clear_pattern(s)
    s.set("seq_play", 0); s.set("seq_rec", 0); s.set("seq_wpos", 0)
    s.set("seq_pos", 3)
    _show_seq_page(s)
    arrow = s.glyph(0x5D)
    at3 = s.cell(_cell_col(3), SCAN_HEAD)
    at0 = s.cell(_cell_col(0), SCAN_HEAD)
    rep.check("head marker ↓ sits over the active step (pos 3)", at3 == arrow, "no head at 3")
    rep.check("no head marker over an inactive step (pos 0)", at0 != arrow, "stray head at 0")


SCENARIOS = [
    transport,
    realtime_arm_clears_and_runs,
    multi_step_playback,
    step_entry_record,
    loop_length_wraps,
    realtime_record,
    realtime_record_monitors_pattern,
    realtime_overdub_keeps_existing,
    realtime_record_drum_tap,
    realtime_held_drum_no_tie,
    drum_step_sounds_during_record,
    rest_releases_note_on_playback,
    tie_sustains_no_reattack,
    grid_glyphs,
    head_marks_active_step,
    playback_audible,
]
