"""INPUT model — the laptop-play controls added in the UI/UX pass:

  #2  Up/Down navigation auto-repeat (was edge-only; L/R adjust already repeated)
  #5  arrow keys mirror the joystick, Tab cycles pages, Return saves a preset.

The Atari arrow keys are Ctrl + the -/=/+/* keys; Ctrl sets KBCODE bit6 ($40), so
they arrive UNMASKED as $4E/$4F/$46/$47 (Up/Down/Left/Right). read_navkeys decodes
them into kbd_dir, which update_input ORs into the joystick bits -> identical
nav/adjust/auto-repeat. Cooked keys land with variable latency, so key checks
inject then scan frames for the watched address to change (like Synth.play()).
"""

CUR = 0x0600        # cur_param
PAGE = 0x068D       # current panel page
NAV_PREV = 0x06CF   # read_navkeys edge-detect latch
PRESET_SLOT = 0x06C5
BANK = 0x0700       # preset bank: slot * 17 saved bytes
VOL = 1             # VOLUME param index (saved at slot offset +1)


def _tap(s, addr, keyfn, scan=90, gap=30):
    """Inject a cooked key, scan up to `scan` frames for `addr` to change, then a
    long gap so the key fully releases (nav_prev -> $FF) before the next tap.
    The cooked-key queue lands with variable (sometimes large) latency, so scan
    generously to catch each tap's effect inside its own window."""
    s.drain()                    # flush any pending cooked key first
    base = s.peek(addr)
    keyfn()
    for _ in range(scan):
        s.frame(1)
        if s.peek(addr) != base:
            break
    s.frame(gap)
    return s.peek(addr)


def updown_autorepeat(s, rep):
    rep.section("input: Up/Down navigation auto-repeats (#2)")
    s.poke(CUR, 0); s.frame(2)
    s.joy(0, "down"); s.frame(40); s.joy(0, "centre"); s.frame(2)
    adv = s.peek(CUR)
    rep.check("held DOWN advances several params (auto-repeat)", adv > 1,
              f"cur_param 0 -> {adv}")
    # regression: L/R adjust auto-repeat must still work. Set a known start so the
    # frame budget is deterministic (15-frame initial delay + 4 frames/step).
    s.poke(CUR, 1); s.set("volume", 8); s.frame(2)   # VOLUME = 8
    v0 = s.get_param(1)
    s.joy(0, "left"); s.frame(80); s.joy(0, "centre"); s.frame(2)
    v1 = s.get_param(1)
    rep.check("held LEFT keeps adjusting VOLUME to 0", v1 == 0, f"{v0} -> {v1}")


def tab_page_flip(s, rep):
    rep.section("input: Tab cycles pages 0->1->2->0 (#5)")
    s.poke(CUR, 0); s.frame(2)
    seq = [s.peek(PAGE)]
    for _ in range(3):
        _tap(s, PAGE, lambda: s.key("TAB"))
        seq.append(s.peek(PAGE))
    rep.check("Tab cycles the page", seq == [0, 1, 2, 0], f"seq={seq}")


def arrow_keys_navigate(s, rep):
    rep.section("input: arrow keys mirror the joystick (#5)")
    s.poke(CUR, 5); s.frame(2)
    up = _tap(s, CUR, lambda: s.a.key("MINUS", ctrl=True))    # Ctrl+MINUS = $4E = UP
    dn = _tap(s, CUR, lambda: s.a.key("EQUALS", ctrl=True))   # Ctrl+EQUALS = $4F = DOWN
    rep.check("Ctrl+'-' (UP) moves selection up", up == 4, f"5 -> {up}")
    rep.check("Ctrl+'=' (DOWN) moves selection down", dn == 5, f"{up} -> {dn}")


def letter_shortcuts(s, rep):
    rep.section("input: letter-shortcut keys jump to a param (#4)")
    # All 12 page-0 params + DRUMBEAT get a unique in-label letter (ARP->ARPEGGIO
    # frees 'G'). (key, expected param):
    jumps = [("M", 0), ("V", 1), ("A", 2), ("K", 3), ("D", 4), ("N", 5),
             ("S", 6), ("L", 7), ("C", 8), ("F", 9), ("H", 10), ("G", 11), ("B", 18)]
    for key, exp in jumps:
        s.poke(CUR, 17)                      # start on PRESET (not a shortcut target)
        got = _tap(s, CUR, lambda k=key: s.key(k))
        rep.check(f"'{key}' jumps to param {exp}", got == exp, f"cur_param={got}")
    # cross-page: 'G' from page 2 jumps to ARPEGGIO (param 11, page 0)
    s.poke(CUR, 16); s.frame(4)
    got = _tap(s, CUR, lambda: s.key("G"))
    rep.check("'G' from page 2 jumps to ARPEGGIO (cross-page)",
              got == 11 and s.peek(PAGE) == 0, f"cur_param={got} page={s.peek(PAGE)}")


def shift_letter_shortcuts(s, rep):
    rep.section("input: Shift+letter shortcuts (page 1/2 params) (#4 shift plane)")
    # Shift sets KBCODE bit7, a distinct key. (letter, expected param):
    jumps = [("M", 12), ("D", 13), ("A", 14), ("H", 16), ("S", 17)]
    for key, exp in jumps:
        s.poke(CUR, 0)                       # start on WAVEFORM (a PLAIN-shortcut param)
        got = _tap(s, CUR, lambda k=key: s.a.key(k, shift=True))
        rep.check(f"Shift+'{key}' jumps to param {exp}", got == exp, f"cur_param={got}")
    # plain and shift of the same letter are different keys: plain M -> WAVEFORM(0)
    s.poke(CUR, 12)
    got = _tap(s, CUR, lambda: s.key("M"))
    rep.check("plain 'M' still jumps to WAVEFORM (0), not TEMPO", got == 0, f"cur_param={got}")


def inert_strike_16bit(s, rep):
    rep.section("ui: inert FX struck through in 16-bit clock mode (#3)")
    # PORTA (param 14, page 1) is dead in 16-bit -> its label gets a strike line at
    # the cell's middle row (scan 36+3=39). Check byte col 2 (x=16) of that row.
    s.set("clock15", 2); s.poke(CUR, 14); s.frame(20)          # 16-bit, view PORTA
    struck = s.peek(s.fb_addr(16, 39))
    rep.check("PORTA struck through in 16-bit", struck == 0xFF, f"strikebyte={struck:#x}")
    s.set("clock15", 0); s.poke(CUR, 0); s.frame(8)            # back to NORMAL
    s.poke(CUR, 14); s.frame(20)
    clean = s.peek(s.fb_addr(16, 39))
    rep.check("PORTA not struck in NORMAL mode", clean != 0xFF, f"byte={clean:#x}")
    s.poke(CUR, 0); s.frame(4)


def preset_names_flash(s, rep):
    rep.section("ui: PRESET shows slot names + SAVED flash (#6)")
    VAL = (33, 16)                      # PRESET value cell (page 2, right col)
    s.poke(PRESET_SLOT, 0); s.poke(CUR, 17); s.frame(20)
    rep.check("slot 0 shows INIT", s.cell(*VAL) == s.glyph(0x29), "no I")   # 'I'
    s.poke(PRESET_SLOT, 2); s.frame(20)
    rep.check("slot 2 shows LEAD", s.cell(*VAL) == s.glyph(0x2C), "no L")   # 'L'
    # SAVED flash (saved_flash=$06D4 set on save; force the cell redraw via prev_disp+17)
    s.poke(0x06D4, 40); s.poke(0x0681, 0xFF); s.frame(4)
    rep.check("SAVED flash shows", s.cell(*VAL) == s.glyph(0x33), "no S")   # 'S'
    s.frame(60)
    rep.check("flash reverts to the name", s.cell(*VAL) == s.glyph(0x2C), "no L")
    s.poke(PRESET_SLOT, 0); s.poke(CUR, 0); s.frame(4)


def return_saves_preset(s, rep):
    rep.section("input: Return saves a preset, PRESET-only (#5)")
    s.poke(PRESET_SLOT, 0); s.frame(2)
    # not on PRESET -> Return must NOT save (bank sentinel stays 99)
    s.poke(CUR, VOL); s.frame(2); s.set("volume", 7); s.frame(2)
    s.poke(BANK + VOL, 99); s.frame(2)
    _tap(s, NAV_PREV, lambda: s.key("RETURN"))
    neg = s.peek(BANK + VOL)
    rep.check("Return off PRESET does NOT save", neg == 99, f"bank[vol]={neg}")
    # on PRESET -> Return saves the current params into slot 0
    s.poke(CUR, 17); s.frame(2); s.set("volume", 3); s.frame(2)
    s.poke(BANK + VOL, 99); s.frame(2)
    pos = _tap(s, BANK + VOL, lambda: s.key("RETURN"))
    rep.check("Return on PRESET saves the patch", pos == 3, f"bank[vol]={pos}")


SCENARIOS = [
    updown_autorepeat,
    tab_page_flip,
    arrow_keys_navigate,
    letter_shortcuts,
    shift_letter_shortcuts,
    inert_strike_16bit,
    preset_names_flash,
    return_saves_preset,
]
