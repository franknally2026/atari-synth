"""Portamento (pitch glide) — comprehensive coverage of the GLIDE parameter
(param 14, on the FX/Patch screen / page 1; labelled PORTA pre-reorg). Glide is
monophonic: with GLIDE > 0 a new note slides from the previously-played pitch on
voice 0, one AUDF step every GLIDE frames.

This is the flagship acoustic test: we RECORD the transition and confirm the
pitch actually slides through intermediate frequencies, not jumps.
"""
import numpy as np
from .. import dsp, notes

GLIDE = 0x06B6
GLIDE_TIMER = 0x06B7


def _settle_then_play(s, note_a, note_b, glide, settle=30):
    """With GLIDE set, play note_a (settle), then trigger note_b. Leaves the
    glide in progress; caller captures/samples. Returns nothing.

    NB: reset porta_timer to a full step delay when triggering note_b so the
    first sampled frame deterministically shows the OLD pitch (the glide origin)
    before any step. Otherwise the start sample depends on porta_timer's phase
    carried over from earlier scenarios — a 1-frame fragility (start 29 vs 28)."""
    s.set("clock15", 0); s.poke(0x0689, 0); s.set("octave", 2)
    s.set("volume", 13); s.set("sus", 12); s.set("atk", 0); s.set("rel", 2)
    s.set("lfod", 0); s.set("detune", 0)
    # idle all voices first so the first note (A) snaps porta_cur to A's pitch
    # (a clean glide origin), regardless of what a prior glide left behind.
    for i in range(4):
        s.set("vlevel", 0, i); s.set("vphase", 0, i)
    s.set("held", 0xFF); s.set("prevheld", 0xFF)
    s.poke(GLIDE, glide)
    s.set("note_idx", note_a)
    for _ in range(settle):
        s.frame(1)
    s.set("note_idx", note_b)
    s.poke(GLIDE_TIMER, glide)   # full step delay -> first frame still shows note_a


def porta_param(s, rep):
    rep.section("glide: parameter (default / clamp / nav / label)")
    rep.check("GLIDE defaults to 0 (off)", s.get_param(14) == 0, s.get_param(14))
    s.set("curparam", 14); s.frame(6)
    rep.check("nav to GLIDE -> FX screen (page 1)", s.get("page") == 1, s.get("page"))
    s.joy(0, "right"); s.frame(100); s.joy(0, "centre"); s.frame(2)
    hi = s.get_param(14)
    s.joy(0, "left"); s.frame(130); s.joy(0, "centre"); s.frame(2)
    lo = s.get_param(14)
    rep.check("GLIDE clamps 15 / 0", hi == 15 and lo == 0, f"hi={hi} lo={lo}")
    # 'GLIDE' on the FX screen, row1 left (col 1, scan 36). 'G' (col1) is the plain
    # shortcut (underlined), so check the non-shortcut 'L' at col 2 as clean inverse.
    rep.check("GLIDE label renders on the FX screen",
              s.cell(2, 36) == s.glyph(0x2C, inv=True), "no L")
    s.set("curparam", 0); s.frame(6)


def porta_register_ramp(s, rep):
    """The emitted AUDF ramps monotonically from the old note to the new one
    (deterministic register view of the glide)."""
    rep.section("portamento: AUDF ramps monotonically to the target")
    with s.frozen("read_keyboard"):
        _settle_then_play(s, 0, 7, glide=8)       # idx24 (AUDF29) -> idx31 (AUDF19)
        seq = []
        for _ in range(110):
            s.frame(1); seq.append(s.chan(1)[0])
        s.set("note_idx", 0xFF)
    start, end = seq[0], seq[-1]
    mono = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))   # 29 -> 19 descends
    intermediate = len(set(seq)) >= 6                              # passes through steps
    rep.check("AUDF starts at the old note (29)", start == 29, f"start={start}")
    rep.check("AUDF reaches the new note (19)", end == 19, f"end={end}")
    rep.check("AUDF glides monotonically through intermediates",
              mono and intermediate, f"distinct={len(set(seq))} mono={mono}")


def porta_pitch_glide_acoustic(s, rep):
    """ACOUSTIC flagship: the PITCH actually slides through intermediate
    frequencies (a glide), not a single jump."""
    rep.section("portamento: pitch audibly glides (PCM)")
    with s.frozen("read_keyboard"):
        _settle_then_play(s, 0, 7, glide=8)
        clip = s.capture("porta_glide", 80, warmup=0)
        s.set("note_idx", 0xFF)
    # band-limit to the A..B region (~1000..1700Hz) so octave-error outliers
    # don't pollute the glide measurement
    t, f = dsp.pitch_track(clip, hop_ms=8.0, win_ms=30.0, fmin=850.0, fmax=2000.0)
    voiced = f[f > 0]
    heard = dsp.distinct_pitches(clip, hop_ms=8.0, win_ms=30.0, fmin=850.0, fmax=2000.0)
    # a glide over ~7 semitones passes through several distinct pitches;
    # an instant jump would show ~2.
    rep.check("pitch passes through several intermediate steps (glide)",
              len(heard) >= 4, f"heard={sorted(heard)}")
    if len(voiced) >= 6:
        early = float(np.median(voiced[:len(voiced) // 3]))
        late = float(np.median(voiced[-len(voiced) // 3:]))
        rep.check("pitch rises from A toward B over the glide",
                  late > early * 1.2, f"early={early:.0f}Hz -> late={late:.0f}Hz")


def porta_rate_scales(s, rep):
    """A higher GLIDE value glides more slowly (takes more frames to reach the
    target)."""
    rep.section("portamento: higher GLIDE = slower glide")
    def glide_frames(glide):
        with s.frozen("read_keyboard"):
            _settle_then_play(s, 0, 7, glide=glide)
            n = 0
            for _ in range(200):
                s.frame(1); n += 1
                if s.chan(1)[0] == 19:        # reached target AUDF
                    break
            s.set("note_idx", 0xFF)
        s.frame(2)
        return n
    fast = glide_frames(4)
    slow = glide_frames(12)
    rep.check("GLIDE 12 glides slower than GLIDE 4",
              slow > fast + 10, f"glide4={fast} frames, glide12={slow} frames")


def porta_off_instant(s, rep):
    """GLIDE 0 = off: the new note sounds at its target pitch immediately (no
    glide), and play is polyphonic (round-robin), not mono."""
    rep.section("portamento: GLIDE 0 = instant (no glide)")
    with s.frozen("read_keyboard"):
        _settle_then_play(s, 0, 7, glide=0)
        s.frame(2)
        held = s.get("held")
        audf = s.chan(held + 1)[0]
        s.set("note_idx", 0xFF)
    rep.check("GLIDE 0: new note is at target AUDF at once (no ramp)",
              audf == 19, f"AUDF={audf} on voice {held}")


SCENARIOS = [
    porta_param,
    porta_register_ramp,
    porta_pitch_glide_acoustic,
    porta_rate_scales,
    porta_off_instant,
]
