"""Arpeggiator MODES — comprehensive coverage of the new ARPMODE parameter
(param 13, page 2): UP / DOWN / MINOR / OCTAVE patterns.

Also regression-tests the TEMPO joystick-adjust fix: param_lo/hi used to omit
TEMPO so apply_adjust ran off the end of the table; adding ARPMODE fixed that.
"""
from .. import dsp, notes

ARP_MODE = 0x06B5
MODES = {
    0: ("UP",    [24, 28, 31, 36]),   # major arp up
    1: ("DOWN",  [36, 31, 28, 24]),   # major arp down
    2: ("MINOR", [24, 27, 31, 36]),   # minor arp up (minor 3rd)
    3: ("OCT",   [24, 36, 24, 36]),   # octave jump
}


def _arp_order(s, mode, frames=40, rate=12):
    """Run the arp in `mode` (octave 2, note_idx 0) and return the ordered list
    of distinct notes it triggers (the pattern, in order)."""
    seq, last = [], None
    with s.frozen("read_keyboard"):
        s.poke(ARP_MODE, mode); s.set("note_idx", 0); s.set("lastv", 3)
        s.set("arp_step", 0); s.set("arp_timer", 1); s.set("arp", rate)
        for _ in range(frames):
            s.frame(1)
            hv = s.get("held")
            if hv != 0xFF:
                n = s.get("vnote", hv)
                if n != last:
                    seq.append(n); last = n
        s.set("arp", 0); s.set("note_idx", 0xFF)
    s.frame(3)
    return seq


def arpmode_param(s, rep):
    """ARPMODE is param 13 on page 2: default 0, clamps 0..3, label renders."""
    rep.section("arpmode: parameter (default / clamp / label)")
    rep.check("ARPMODE defaults to 0 (UP)", s.get_param(13) == 0, s.get_param(13))
    # select param 13 and clamp via the joystick
    s.set("curparam", 13); s.frame(6)
    rep.check("nav to ARPMODE -> page 2", s.get("page") == 1, s.get("page"))
    s.joy(0, "right"); s.frame(40); s.joy(0, "centre"); s.frame(2)
    hi = s.get_param(13)
    s.joy(0, "left"); s.frame(40); s.joy(0, "centre"); s.frame(2)
    lo = s.get_param(13)
    rep.check("ARPMODE clamps 3 / 0", hi == 3 and lo == 0, f"hi={hi} lo={lo}")
    # the 'ARP MODE' label is drawn on page 2 (right column, scan 16): 'A'
    rep.check("ARP MODE label renders on page 2", s.cell(21, 16) == s.glyph(0x21), "no A")
    s.set("curparam", 0); s.frame(6)


def arpmode_patterns(s, rep):
    """Each mode triggers its notes in the right ORDER (not just the right set —
    UP and DOWN share a note set but differ in direction)."""
    rep.section("arpmode: each mode's pattern (ordered)")
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.set("octave", 2); s.set("volume", 13); s.set("sus", 10)
    s.set("atk", 0); s.set("rel", 1)
    for mode, (name, expect) in MODES.items():
        seq = _arp_order(s, mode)
        rep.check(f"ARP {name}: pattern {expect}", seq[:4] == expect, f"got {seq[:4]}")
    s.poke(ARP_MODE, 0)


def arpmode_direction(s, rep):
    """UP and DOWN share the same notes but opposite direction — a pure
    ordering check (the reverse of each other)."""
    rep.section("arpmode: UP and DOWN are reverses")
    s.set("octave", 2); s.set("volume", 13); s.set("sus", 10); s.set("atk", 0); s.set("rel", 1)
    up = _arp_order(s, 0)[:4]
    down = _arp_order(s, 1)[:4]
    rep.check("DOWN is UP reversed", down == up[::-1], f"up={up} down={down}")
    rep.check("UP and DOWN share the same note set", set(up) == set(down), f"{set(up)}")
    s.poke(ARP_MODE, 0)


def arpmode_acoustic(s, rep):
    """ACOUSTIC: the modes actually SOUND different — MINOR's pitch set differs
    from UP's (the minor third), and OCT sounds just two pitches."""
    rep.section("arpmode: modes sound distinct (PCM)")
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.set("octave", 1); s.set("volume", 13); s.set("sus", 12)
    s.set("atk", 0); s.set("dec", 0); s.set("rel", 1); s.set("lfod", 0); s.set("detune", 0)

    def hear(mode):
        with s.frozen("read_keyboard"):
            s.poke(ARP_MODE, mode); s.set("note_idx", 0); s.set("lastv", 3)
            s.set("arp_step", 0); s.set("arp_timer", 1); s.set("arp", 6)
            clip = s.capture(f"arpmode_{mode}", 90)
            s.set("arp", 0); s.set("note_idx", 0xFF)
        s.frame(3)
        return clip

    up = hear(0); minor = hear(2); octv = hear(3)
    up_p, min_p = dsp.distinct_pitches(up), dsp.distinct_pitches(minor)
    rep.check("UP sounds several distinct pitches", len(up_p) >= 3, f"heard={sorted(up_p)}")
    rep.check("MINOR sounds different from UP (minor 3rd)", up_p != min_p,
              f"UP={sorted(up_p)} MINOR={sorted(min_p)}")
    # OCT alternates a note and its octave; name-based pitch detection collapses
    # octaves, so confirm via the spectrum that BOTH octave tones are present.
    f_lo = notes.predicted_freq(12, notes.MODE_NORMAL)   # octave 1 base -> idx 12
    f_hi = notes.predicted_freq(24, notes.MODE_NORMAL)   # + 12 semitones
    rep.check("OCT sounds both a note and its octave",
              dsp.has_tone_at(octv, f_lo, tol_frac=0.06) and dsp.has_tone_at(octv, f_hi, tol_frac=0.06),
              f"want {f_lo:.0f}+{f_hi:.0f}Hz; peaks={[round(f) for f, _ in dsp.spectral_peaks(octv, 6)]}")
    s.poke(ARP_MODE, 0)


def tempo_adjust_fixed(s, rep):
    """Regression: TEMPO (param 12) joystick adjust now works. param_lo/hi used
    to omit TEMPO, so apply_adjust read off the end of the table and adjusting
    TEMPO wrote stray RAM instead of changing it."""
    rep.section("regression: TEMPO joystick adjust (param_lo/hi off-by-one)")
    s.set("curparam", 12); s.frame(6); s.set("tempo", 8); s.frame(2)
    s.joy(0, "right"); s.frame(40); s.joy(0, "centre"); s.frame(2)
    hi = s.get("tempo")
    s.joy(0, "left"); s.frame(110); s.joy(0, "centre"); s.frame(2)
    lo = s.get("tempo")
    rep.check("TEMPO actually responds to the joystick", hi > 8 and lo < hi,
              f"8 -> RIGHT={hi} -> LEFT={lo}")
    rep.check("TEMPO clamps at 0", lo == 0, f"lo={lo}")
    s.set("curparam", 0); s.frame(6)


SCENARIOS = [
    arpmode_param,
    arpmode_patterns,
    arpmode_direction,
    arpmode_acoustic,
    tempo_adjust_fixed,
]
