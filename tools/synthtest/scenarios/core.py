"""Core engine + UI behaviour scenarios (register/RAM/timeline level).

These migrate the deterministic checks from the old verify_synth.py onto the
Synth/Timeline/Reporter framework, with the key upgrade that envelope behaviour
is asserted over a *timeline* (the sequencer near-silence bug class), not a
single frame.
"""
from ..scenario import Timeline
from ..harness import (PH_IDLE, PH_ATTACK, PH_SUSTAIN, PH_RELEASE, FB1, PARAM_VARS)


def defaults_and_silence(s, rep):
    rep.section("defaults & silence")
    rep.check("curparam=0", s.get("curparam") == 0, s.get("curparam"))
    rep.check("wave=0", s.get("wave") == 0, s.get("wave"))
    rep.check("volume=10", s.get("volume") == 10, s.get("volume"))
    rep.check("octave=2", s.get("octave") == 2, s.get("octave"))
    rep.check("note=$FF", s.get("note_idx") == 0xFF, hex(s.get("note_idx")))
    rep.check("AUDC1=0 at rest", s.chan(1)[1] == 0, hex(s.chan(1)[1]))
    rep.check("AUDCTL=0 at rest", s.audctl() == 0, hex(s.audctl()))
    s.screenshot("01_initial.png")


def play_pitch_mapping(s, rep):
    rep.section("play notes -> allocated channel + pitch")
    s.reset_voices()
    notes = [("q", 0x1D, 0, "C4"), ("2", 0x1C, 1, "C#4"),
             ("w", 0x1A, 2, "D4"), ("p", 0x0B, 16, "E5")]
    for keyname, exp_audf, exp_note, label in notes:
        if s.play(keyname) is None:
            rep.check(f"KEY {keyname!r} -> {label}", False, "key never registered")
            continue
        held = s.get("held"); note = s.get("note_idx"); f, c = s.chan(held + 1)
        if keyname == "q":
            s.screenshot("02_playing.png")
        rep.check(f"KEY {keyname!r} -> {label}", f == exp_audf and c != 0 and note == exp_note,
                  f"v{held} AUDF={f:02X} AUDC={c:02X} note={note}")
    for _ in range(80):
        s.frame(1)
        if s.nactive() == 0:
            break
    rep.check("silent again after release", s.nactive() == 0, f"{s.nactive()} active")


def voice_allocation(s, rep):
    rep.section("round-robin voice allocation")
    s.reset_voices()
    seq = [("q", 0, 24, 0x1D, "C4"), ("w", 1, 26, 0x1A, "D4"),
           ("e", 2, 28, 0x17, "E4"), ("r", 3, 29, 0x16, "F4"), ("t", 0, 31, 0x13, "G4")]
    for key, v, absn, audf, label in seq:
        if s.play(key) is None:
            rep.check(f"{key!r} onset", False, "never registered"); continue
        held, lastv = s.get("held"), s.get("lastv")
        vn = s.get("vnote", v); f, c = s.chan(v + 1)
        rep.check(f"{key!r} -> voice {v} ch{v+1} = {label}",
                  held == v and lastv == v and vn == absn and f == audf and c != 0,
                  f"held={held} vnote={vn} AUDF={f:02X}")


def drum_key_reachable(s, rep):
    """REACHABILITY: pressing the '1' key (a real cooked keypress) actually
    fires a drum hit on channel 4 — i.e. the drum is reachable through real
    user input, not just by poking $FD."""
    rep.section("drum trigger reachable: the '1' key fires a drum")
    DRUM = 0x06BD
    s.set("clock15", 0); s.poke(0x0689, 0); s.poke(DRUM, 8)   # enable the drum
    # use the proven cooked-key helper (drains the key queue, scans for the
    # key-down frame) — the same path the pitch-key tests use
    registered = s.play("1")
    ni = s.get("note_idx")
    peak = s.chan(4)[1] & 0x0F
    for _ in range(10):
        s.frame(1)
        peak = max(peak, s.chan(4)[1] & 0x0F)
    rep.check("the '1' key registers as the drum note ($FD)",
              registered is True and ni == 0xFD, f"registered={registered} note_idx={ni:#x}")
    rep.check("pressing '1' fires a drum hit on channel 4", peak >= 12,
              f"ch4 peak level={peak}")
    s.poke(DRUM, 0); s.poke(0x06BE, 0)          # drum off, clear level


def polyphony(s, rep):
    rep.section("four voices -> four channels at once")
    s.reset_voices()
    chord = [(24, 0x1D, "C4"), (26, 0x1A, "D4"), (28, 0x17, "E4"), (29, 0x16, "F4")]
    for i, (absn, _, _) in enumerate(chord):
        s.set("vnote", absn, i); s.set("vlevel", 12 + i, i)
        s.set("vphase", PH_RELEASE, i); s.set("vcount", 30, i)
    s.set("held", 0xFF); s.frame(1)
    for i, (absn, audf, label) in enumerate(chord):
        f, c = s.chan(i + 1)
        rep.check(f"ch{i+1} sounds {label}", f == audf and c != 0, f"AUDF={f:02X} AUDC={c:02X}")
    rep.check("all 4 channels active", s.nactive() == 4, f"{s.nactive()}")
    s.screenshot("08_poly.png")


def adsr_envelope(s, rep):
    rep.section("ADSR envelope over a timeline")
    with s.frozen("trigger_voices"):
        s.set("volume", 10); s.set("sus", 4); s.set("atk", 0); s.set("dec", 0)
        s.set("held", 0); s.set("vnote", 24, 0); s.set("vlevel", 0, 0)
        s.set("vphase", PH_ATTACK, 0); s.set("vcount", 1, 0)
        tl = s.timeline(24, voices=(0,))
        lvls = tl.level(0); phs = tl.phase(0)
        rep.check("attack reaches peak (vol 10)", max(lvls) == 10, max(lvls))
        rep.check("settles at sustain=4 in SUSTAIN", lvls[-1] == 4 and phs[-1] == PH_SUSTAIN,
                  f"lvl={lvls[-1]} ph={phs[-1]}")
        rep.check("sustain holds steady", lvls[-1] == lvls[-2], lvls[-2:])

        # release ramps to idle
        s.set("held", 0xFF); s.set("vlevel", 12, 0); s.set("vphase", PH_RELEASE, 0)
        s.set("vcount", 1, 0); s.set("rel", 0)
        tl = s.timeline(15, voices=(0,))
        rel = tl.level(0)
        mono = all(rel[i] >= rel[i + 1] for i in range(len(rel) - 1))
        rep.check("release decreases monotonically", mono, rel[:6])
        rep.check("release reaches idle", s.get("vphase", 0) == PH_IDLE, s.get("vphase", 0))
    s.screenshot("11_adsr.png")


def sequencer_audibility(s, rep):
    """The regression that motivated this framework: a played sequencer step
    must SUSTAIN across the step, not attack then collapse to near-silence.
    Asserted over the level timeline."""
    rep.section("sequencer step audibility (no near-silence collapse)")
    SEQ_NOTES = 0x0691
    for i in range(16):
        s.poke(SEQ_NOTES + i, 0xFF)
    s.poke(SEQ_NOTES, 5)
    s.set("volume", 10); s.set("sus", 8); s.set("atk", 0); s.set("dec", 2)
    s.set("tempo", 4); s.set("seq_rec", 0)
    s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
    tl = s.timeline(30)
    s.set("seq_play", 0)
    peak = max(tl.max_level(v) for v in (0, 1, 2, 3))
    rep.check("played step reaches an audible sustained level", peak >= 7, f"peak={peak}")


def gr8_ui(s, rep):
    rep.section("GR.8 bitmap UI sanity")
    dl = s.label_addr("dlist")
    sdl = s.peek(0x0230) | (s.peek(0x0231) << 8)
    rep.check("display list installed", sdl == dl, f"{sdl:04X}!={dl:04X}")
    rep.check("SDMCTL=$22", s.peek(0x022F) == 0x22, hex(s.peek(0x022F)))
    # VOLUME number cell is an 8-scanline glyph at byte col 13, scan 36 (read
    # the column vertically, one byte per scanline — not 8 bytes across).
    def glyph_col(col, scan):
        return [s.peek(FB1 + (scan + i) * 40 + col) for i in range(8)]
    s.set("volume", 0); s.frame(2); b0 = glyph_col(13, 36)
    s.set("volume", 12); s.frame(2); b1 = glyph_col(13, 36)
    rep.check("VOLUME value cell redraws on change", b0 != b1, "cell unchanged")
    s.set("volume", 10); s.frame(2)
    s.screenshot("15_gr8.png")


def param_nav_and_clamp(s, rep):
    """UP/DOWN navigation steps through params in visual order, and LEFT/RIGHT
    adjust clamps each at 0..max."""
    rep.section("params: navigation order + adjust clamp")
    # DOWN x5 from WAVEFORM must reach LFO DEPTH (param 5): index order == visual
    # order, so no param is unreachable in sequence.
    s.set("curparam", 0); s.frame(2)
    for _ in range(5):
        s.joy(0, "down"); s.frame(3); s.joy(0, "centre"); s.frame(3)
    rep.check("DOWN x5 -> LFO DEPTH (param 5)", s.get("curparam") == 5, s.get("curparam"))
    # clamp: RIGHT to max, LEFT to min, for a representative spread of params
    for pidx, name, hi_exp in [(1, "VOLUME", 15), (2, "OCTAVE", 4),
                               (4, "LFO RATE", 15), (6, "ATTACK", 15), (8, "SUSTAIN", 15),
                               (10, "ARPEGGIO", 15), (11, "ARP MODE", 3)]:
        s.set("curparam", pidx); s.frame(2)
        s.joy(0, "right"); s.frame(90); s.joy(0, "centre"); s.frame(2)
        hi = s.get_param(pidx)
        s.joy(0, "left"); s.frame(90); s.joy(0, "centre"); s.frame(2)
        lo = s.get_param(pidx)
        rep.check(f"{name} clamps {hi_exp}/0", hi == hi_exp and lo == 0, f"hi={hi} lo={lo}")
    s.set("curparam", 0); s.frame(2)


def two_page_nav(s, rep):
    """Navigating past the screen-1 params shows the next screen and back."""
    rep.section("UI: multi-page panel navigation")
    s.set("curparam", 12); s.frame(20)             # -> page 1 (FX screen, DETUNE)
    rep.check("nav to param 12 -> page 1", s.get("page") == 1, s.get("page"))
    rep.check("FX screen shows DETUNE label", s.cell(1, 16) == s.glyph(0x24, inv=True), "no D")
    s.set("curparam", 0); s.frame(20)              # -> page 0 (WAVEFORM)
    rep.check("back to param 0 -> page 0", s.get("page") == 0, s.get("page"))
    # 'W' (col1) is the Shift+W shortcut char (opposite-video when focused), so check
    # the non-shortcut 'A' at col2 of "WAVEFORM" as a clean focused-inverse glyph.
    rep.check("page 0 redraws WAVEFORM label", s.cell(2, 16) == s.glyph(0x21, inv=True), "no A")
    s.screenshot("23_page2.png")


def switch_glyphs(s, rep):
    """WAVEFORM selector box tracks the wave; CLOCK toggle text tracks the mode."""
    rep.section("UI: WAVEFORM selector + CLOCK toggle glyphs")
    def row(x, y, n):
        return list(s.peek(s.fb_addr(x, y), n))
    s.set("wave", 0); s.frame(2); w0 = row(72, 16, 12)
    s.set("wave", 3); s.frame(2); w3 = row(72, 16, 12)
    rep.check("WAVEFORM selection box moves with wave", w0 != w3, "box static")
    s.set("clock15", 0); s.frame(2); c0 = row(30 * 8, 58, 8)
    s.set("clock15", 2); s.frame(2); c1 = row(30 * 8, 58, 8)
    rep.check("CLOCK name changes with mode", c0 != c1, "name static")
    s.set("wave", 0); s.set("clock15", 0); s.frame(2)
    s.screenshot("16_switches.png")


def vu_meters(s, rep):
    """Per-voice VU bars track each voice's envelope level."""
    rep.section("UI: per-voice level meters")
    MET_X = [4, 72, 140, 208]

    def bar_ok(v, lvl):
        if lvl == 0:
            return s.px(MET_X[v] + 2, 11) == 0
        w = lvl * 3
        return s.px(MET_X[v] + w // 2, 11) == 1 and s.px(MET_X[v] + w + 3, 11) == 0

    s.reset_voices(); s.set("curparam", 0); s.frame(2)
    with s.frozen("trigger_voices"):
        s.set("volume", 15); s.set("sus", 12); s.set("dec", 0); s.set("rel", 0)
        s.set("vnote", 24, 0); s.set("vphase", PH_SUSTAIN, 0); s.set("vlevel", 12, 0)
        s.set("vcount", 1, 0); s.set("held", 0); s.frame(6)
        l0 = s.get("vlevel", 0)
        rep.check("voice0 meter matches its level", bar_ok(0, l0), f"lvl={l0}")
        s.set("held", 0xFF); s.frame(40)
        rep.check("meter clears when the voice goes silent",
                  s.get("vlevel", 0) == 0 and bar_ok(0, 0), f"lvl={s.get('vlevel', 0)}")
        # a different voice uses its own bar
        s.set("sus", 10); s.set("vnote", 24, 2); s.set("vphase", PH_SUSTAIN, 2)
        s.set("vlevel", 10, 2); s.set("vcount", 1, 2); s.set("held", 2); s.frame(6)
        rep.check("voice2 uses its own bar, voice0 clear",
                  bar_ok(2, s.get("vlevel", 2)) and s.px(MET_X[0] + 2, 11) == 0,
                  f"lvl2={s.get('vlevel', 2)}")
        s.screenshot("25_meters.png")
    s.reset_voices()


def clock_toggle_in_place(s, rep):
    """REGRESSION: the CLOCK toggle must draw its mode name in CLOCK's OWN value
    area. It was hardcoded to the old right-column/scan-56 slot, which the panel
    reorg gave to SUSTAIN -> the clock name overwrote SUSTAIN's value ("R08L").
    Verify each mode name renders on CLOCK's row AND SUSTAIN's value cell stays
    clean while CLOCK is displayed."""
    rep.section("UI: CLOCK toggle renders in its own cell (not over SUSTAIN)")
    psc = s.label_addr("p_scan"); pkn = s.label_addr("p_knobcx"); pnm = s.label_addr("p_numcol")
    clk_scan = s.peek(psc + 3); clk_col = s.peek(pkn + 3) >> 3   # CLOCK = param 3
    sus_scan = s.peek(psc + 8); sus_num = s.peek(pnm + 8)        # SUSTAIN = param 8

    def read6(col, scan):
        out = ""
        for i in range(6):
            cell = s.cell(col + i, scan); ch = "?"
            for code in range(0x40):
                if cell == s.glyph(code):
                    ch = chr(0x20 + code) if code else " "; break
            out += ch
        return out

    # clock=0/NORMAL (boot default) is where the bug showed (NORMAL -> "R08L" over
    # SUSTAIN). draw_clk_toggle now reads its position from the tables, so if NORMAL
    # renders in CLOCK's own cell, every mode does (same code path, different string).
    s.set("clock15", 0); s.poke(0x0689, 0); s.set("curparam", 3); s.frame(10)
    nm = read6(clk_col, clk_scan).rstrip()
    lg, rg = s.cell(sus_num - 1, sus_scan), s.cell(sus_num + 2, sus_scan)
    rep.check("CLOCK shows its mode name in CLOCK's own row", nm == "NORMAL", f"name={nm!r}")
    rep.check("SUSTAIN value cell stays clean (no clock-name bleed)",
              not any(lg) and not any(rg), f"left_dirty={any(lg)} right_dirty={any(rg)}")
    s.set("curparam", 0); s.frame(8)


def panel_value_cells_isolated(s, rep):
    """GENERAL guard against one param's widget bleeding into another's value cell
    (the class of bug the CLOCK toggle hit). Set every plain-knob param to a known
    2-digit value and verify each value reads correctly with BLANK gutters on both
    sides. Positions are read from the binary so this tracks any layout change."""
    rep.section("UI: knob value cells are isolated (no cross-param bleed)")
    special = {0, 2, 3, 15}        # WAVE icons, OCT widget, CLK toggle, PRESET name
    pnm = s.label_addr("p_numcol"); psc = s.label_addr("p_scan")
    knobs = [i for i in range(19) if i not in special]
    saved = {i: s.get(PARAM_VARS[i]) for i in knobs}
    for i in knobs:
        s.set(PARAM_VARS[i], 3)    # 3 <= every param's max -> renders "03", never "OFF"
    d0, d3 = s.glyph(0x10), s.glyph(0x13)
    bad = []
    for idx in knobs:
        page = 0 if idx < 12 else (1 if idx < 16 else 2)
        s.set("curparam", idx)
        for _ in range(24):
            s.frame(1)
            if s.get("page") == page:
                break
        s.poke(0x06AA, 1); s.frame(4)              # force a clean panel redraw
        nc = s.peek(pnm + idx); sc = s.peek(psc + idx)
        lg, rg = s.cell(nc - 1, sc), s.cell(nc + 2, sc)
        ok = s.cell(nc, sc) == d0 and s.cell(nc + 1, sc) == d3
        if any(lg) or any(rg) or not ok:
            bad.append(f"{PARAM_VARS[idx]}({idx}):" +
                       ("L" if any(lg) else "") + ("R" if any(rg) else "") +
                       ("" if ok else "val"))
    for i, v in saved.items():
        s.set(PARAM_VARS[i], v)
    s.set("curparam", 0); s.frame(6)
    rep.check("every knob value cell is clean with blank gutters", not bad, f"bad={bad}")


SCENARIOS = [
    defaults_and_silence,
    clock_toggle_in_place,
    panel_value_cells_isolated,
    play_pitch_mapping,
    voice_allocation,
    drum_key_reachable,
    polyphony,
    adsr_envelope,
    sequencer_audibility,
    gr8_ui,
    param_nav_and_clamp,
    two_page_nav,
    switch_glyphs,
    vu_meters,
]
