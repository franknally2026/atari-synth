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
BANK = 0x0700       # preset bank: slot * 18 saved bytes
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
    rep.section("input: plain letter-shortcut keys jump to a param (#4)")
    # First-letter scheme: plain shortcuts are the first (non-piano) letter of the
    # name. (key, expected param):
    jumps = [("V", 1), ("C", 3), ("L", 4), ("K", 6), ("D", 7), ("S", 8),
             ("A", 10), ("N", 12), ("H", 13), ("G", 14)]
    for key, exp in jumps:
        s.poke(CUR, 15)                      # start on PRESET (not a plain-shortcut target)
        got = _tap(s, CUR, lambda k=key: s.key(k))
        rep.check(f"'{key}' jumps to param {exp}", got == exp, f"cur_param={got}")
    # cross-page: 'A' from the sequencer screen jumps to ARPEGGIO (param 10, page 0)
    s.poke(CUR, 16); s.frame(4)
    got = _tap(s, CUR, lambda: s.key("A"))
    rep.check("'A' from the sequencer screen jumps to ARPEGGIO (cross-page)",
              got == 10 and s.peek(PAGE) == 0, f"cur_param={got} page={s.peek(PAGE)}")


def shift_letter_shortcuts(s, rep):
    rep.section("input: Shift+letter shortcuts (first-letter via Shift) (#4 shift plane)")
    # Shift sets KBCODE bit7, a distinct key. First-letter shortcuts that need Shift
    # (piano-key first letters W/O/R/P/T, or a letter taken plain). (letter, param):
    #   ^W WAVEFORM(0)  ^O OCTAVE(2)  ^L LFO DEPTH(5)  ^R RELEASE(9)  ^A ARP MODE(11)
    #   ^P PRESET(15)  ^T TEMPO(16)  ^D DRUM(17)  ^H RHYTHM(18)
    jumps = [("W", 0), ("O", 2), ("L", 5), ("R", 9), ("A", 11),
             ("P", 15), ("T", 16), ("D", 17), ("H", 18)]
    for key, exp in jumps:
        s.poke(CUR, 1)                       # start on VOLUME (a PLAIN-shortcut param)
        got = _tap(s, CUR, lambda k=key: s.a.key(k, shift=True))
        rep.check(f"Shift+'{key}' jumps to param {exp}", got == exp, f"cur_param={got}")
    # plain and shift of the same letter are different keys: plain A -> ARPEGGIO(10),
    # Shift+A -> ARP MODE(11)
    s.poke(CUR, 11)
    got = _tap(s, CUR, lambda: s.key("A"))
    rep.check("plain 'A' jumps to ARPEGGIO (10), not ARP MODE", got == 10, f"cur_param={got}")
    # a Shift shortcut must NOT also play a piano note. read_keyboard used to mask off
    # the Shift bit, collapsing Shift+W ($AE) onto W's note key ($2E) and blipping a
    # note on every shortcut. Hold Shift+W and confirm note_idx never leaves $FF.
    s.poke(CUR, 1); s.drain()
    fired = False
    s.a.key("W", shift=True)
    for _ in range(90):
        s.frame(1)
        if s.get("note_idx") != 0xFF:
            fired = True
        if s.peek(CUR) == 0:                 # shortcut landed (selection jumped)
            break
    s.frame(30)
    rep.check("Shift+W jumps selection without blipping a note",
              (not fired) and s.peek(CUR) == 0, f"note_fired={fired} cur={s.peek(CUR)}")


def inert_strike_16bit(s, rep):
    rep.section("ui: inert FX struck through in 16-bit clock mode (#3)")
    # GLIDE (param 14, FX screen / page 1) is dead in 16-bit -> its label gets a
    # strike line at the cell's middle row (scan 36+3=39). Check byte col 2 (x=16).
    s.set("clock15", 2); s.poke(CUR, 14); s.frame(20)          # 16-bit, view GLIDE
    struck = s.peek(s.fb_addr(16, 39))
    rep.check("GLIDE struck through in 16-bit", struck == 0xFF, f"strikebyte={struck:#x}")
    s.set("clock15", 0); s.poke(CUR, 0); s.frame(8)            # back to NORMAL
    s.poke(CUR, 14); s.frame(20)
    clean = s.peek(s.fb_addr(16, 39))
    rep.check("GLIDE not struck in NORMAL mode", clean != 0xFF, f"byte={clean:#x}")
    s.poke(CUR, 0); s.frame(4)


def preset_names_flash(s, rep):
    rep.section("ui: PRESET shows slot names + SAVED flash (#6)")
    VAL = (33, 36)                      # PRESET value cell (page 1, right col, row1)
    s.poke(PRESET_SLOT, 0); s.poke(CUR, 15); s.frame(20)
    rep.check("slot 0 shows INIT", s.cell(*VAL) == s.glyph(0x29), "no I")   # 'I'
    s.poke(PRESET_SLOT, 2); s.frame(20)
    rep.check("slot 2 shows LEAD", s.cell(*VAL) == s.glyph(0x2C), "no L")   # 'L'
    # SAVED flash (saved_flash=$06D4 set on save; force cell redraw via prev_disp+15=$067F)
    s.poke(0x06D4, 40); s.poke(0x067F, 0xFF); s.frame(4)
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
    s.poke(CUR, 15); s.frame(2); s.set("volume", 3); s.frame(2)
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
