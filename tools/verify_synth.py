#!/usr/bin/env python3
"""
AltirraBridge verification harness for atari-synth.

Launches AltirraSDL headless, boots synth.xex, and checks behaviour against
expectations by reading POKEY's write-register state and the program's own
work variables in RAM. Saves screenshots for visual confirmation.

This is the reusable verification path for the project: add a check per feature
and call it from main(). Run:  python3 tools/verify_synth.py

NOTE: $D200/$D201 (AUDF1/AUDC1) are WRITE-ONLY; reading them returns POT0/POT1
(paddles). Always read audio register state via a.pokey(), never a.peek($D2xx).
"""
import os, re, sys, time, subprocess

REPO = os.path.expanduser("~/AltirraSDL")
SDK  = os.path.join(REPO, "src/AltirraSDL/AltirraBridge/sdk/python")
EMU  = os.path.join(REPO, "build/linux-release/src/AltirraSDL/AltirraSDL")
HERE = os.path.dirname(os.path.abspath(__file__))
XEX  = os.path.abspath(os.path.join(HERE, "..", "synth.xex"))
SHOTS = os.path.abspath(os.path.join(HERE, "..", "shots"))
LOG  = os.path.join(SHOTS, "emu.log")

LST  = os.path.abspath(os.path.join(HERE, "..", "synth.lst"))
sys.path.insert(0, SDK)
from altirra_bridge import AltirraBridge

def label_addr(name):
    """Resolve a MADS label to its address by parsing synth.lst (robust to
    code shifting between builds)."""
    pat = re.compile(r'^\s*\d+\s+([0-9A-Fa-f]{4})\s+' + re.escape(name) + r'\s*$')
    with open(LST) as f:
        for line in f:
            m = pat.match(line)
            if m:
                return int(m.group(1), 16)
    raise KeyError(f"label {name!r} not found in {LST}")

# work-variable addresses (must match synth.asm)
V_CURPARAM, V_WAVE, V_VOLUME, V_OCTAVE, V_CLOCK15, V_NOTEIDX = (
    0x0600, 0x0601, 0x0602, 0x0603, 0x0604, 0x0607)
V_VNOTE, V_VLEVEL, V_HELD, V_LASTV, V_PREVHELD = (
    0x0610, 0x0614, 0x0618, 0x0619, 0x061E)
V_VPHASE, V_VCOUNT = 0x0620, 0x0624
V_LFOR, V_LFOD = 0x0663, 0x0664
V_DETUNE = 0x066E
V_ARP, V_ARP_STEP, V_ARP_TIMER = 0x0684, 0x0685, 0x0686
V_ATK, V_DEC, V_SUS, V_REL = 0x062C, 0x062D, 0x062E, 0x062F
TRIGGER_ADDR = label_addr("trigger_voices")   # entry; patch $60=RTS to freeze
PH_IDLE, PH_ATTACK, PH_DECAY, PH_SUSTAIN, PH_RELEASE = 0, 1, 2, 3, 4

results = []
def check(name, ok, detail=""):
    results.append((name, ok))
    print(("  PASS " if ok else "  FAIL ") + name + (f"  [{detail}]" if detail else ""))

def launch():
    os.makedirs(SHOTS, exist_ok=True)
    log = open(LOG, "w")
    proc = subprocess.Popen([EMU, "--bridge", "--headless"],
                            stdout=log, stderr=subprocess.STDOUT)
    token = None
    for _ in range(200):
        try:
            m = re.search(r'token-file:\s*(\S+)', open(LOG).read())
            if m: token = m.group(1); break
        except FileNotFoundError:
            pass
        time.sleep(0.05)
    if not token:
        proc.kill(); raise RuntimeError("bridge token-file not seen; see " + LOG)
    for _ in range(40):
        if os.path.exists(token): break
        time.sleep(0.05)
    return proc, token

def main():
    proc, token = launch()
    a = AltirraBridge.from_token_file(token)
    h = lambda s: int(str(s).lstrip('$'), 16)        # parse "$1d"/"1d"
    pk = lambda reg: h(a.pokey()[reg])               # POKEY write-reg state
    pv = lambda addr: a.peek(addr)[0]                # work variable
    def chan(n):                                     # AUDFn, AUDCn (n=1..4)
        p = a.pokey(); return h(p[f"AUDF{n}"]), h(p[f"AUDC{n}"])
    def nactive():
        p = a.pokey(); return sum(1 for n in (1,2,3,4) if h(p[f"AUDC{n}"]))
    def reset_voices():
        # deterministic start: volume 10, snappy envelope, next onset -> v0, idle
        a.poke(V_VOLUME,10); a.poke(V_CLOCK15,0)
        a.poke(V_ATK,0); a.poke(V_DEC,2); a.poke(V_SUS,8); a.poke(V_REL,3)
        a.poke(V_LASTV,3); a.poke(V_HELD,0xFF); a.poke(V_PREVHELD,0xFF)
        for i in range(4):
            a.poke(V_VLEVEL+i,0); a.poke(V_VPHASE+i,0)
        a.frame(2)
    FB1, FB2 = 0x4000, 0x5000
    def fb_addr(x, y):                               # framebuffer addr of pixel
        base = FB1 + y*40 if y < 102 else FB2 + (y-102)*40
        return base + (x >> 3)
    def cell(col, scan):                             # 8 vertical bytes of a glyph
        return [a.peek(fb_addr(col*8, scan+i))[0] for i in range(8)]
    def glyph(code):                                 # ROM font glyph (screen code)
        return list(a.peek(0xE000 + code*8, 8))
    try:
        print("ping:", a.ping())
        a.boot(XEX); a.frame(300)                    # settle cold reset + init

        # ---- 1. initial panel state (defaults) + silence ----
        print("\n[1] initial state")
        st = {n: pv(addr) for n, addr in
              [("curparam",V_CURPARAM),("wave",V_WAVE),("volume",V_VOLUME),
               ("octave",V_OCTAVE),("clock15",V_CLOCK15),("note",V_NOTEIDX)]}
        print("    vars:", st)
        check("defaults curparam=0", st["curparam"]==0, st["curparam"])
        check("defaults wave=0",     st["wave"]==0,     st["wave"])
        check("defaults volume=10",  st["volume"]==10,  st["volume"])
        check("defaults octave=2",   st["octave"]==2,   st["octave"])
        check("defaults note=$FF",   st["note"]==0xFF,  hex(st["note"]))
        check("silent at rest AUDC1=0", pk("AUDC1")==0, hex(pk("AUDC1")))
        check("AUDCTL=0 at rest",        pk("AUDCTL")==0, hex(pk("AUDCTL")))
        a.screenshot(os.path.join(SHOTS, "01_initial.png"))

        # ---- 2. play notes -> correct pitch on the allocated channel ----
        # The bridge's KEY is a *cooked* keypress: key-down lasts ~1 frame and
        # has a repeat cooldown, so drain the queue between presses and scan a
        # few frames for the key-down frame. Notes are voice-allocated
        # round-robin, so each lands on its own channel (see section 8).
        print("\n[2] play notes (each -> its allocated channel, correct pitch)")
        def drain():                                 # wait until key queue is empty
            quiet = 0
            for _ in range(80):
                a.frame(1)
                quiet = quiet + 1 if pv(V_NOTEIDX) == 0xFF else 0
                if quiet >= 10:
                    return
        def play(keyname):
            drain()                                  # ensure no stale queued key
            a.key(keyname)
            for _ in range(60):                      # scan for the key-down frame
                a.frame(1)
                if pv(V_NOTEIDX) != 0xFF:
                    return True
            return None
        reset_voices()
        notes = [("q", 0x1D, 0, "C4"), ("2", 0x1C, 1, "C#4"),
                 ("w", 0x1A, 2, "D4"), ("p", 0x0B, 16, "E5")]
        for keyname, exp_audf, exp_note, label in notes:
            if play(keyname) is None:
                check(f"KEY {keyname!r} -> {label}", False, "key never registered")
                continue
            held = pv(V_HELD); note = pv(V_NOTEIDX); f, c = chan(held+1)
            if keyname == "q":
                a.screenshot(os.path.join(SHOTS, "02_playing.png"))
            ok = (f==exp_audf and c!=0 and note==exp_note)
            check(f"KEY {keyname!r} -> {label}",
                  ok, f"v{held} ch{held+1} AUDF={f:02X} AUDC={c:02X} note={note}")
        for _ in range(80):                          # let voices decay
            a.frame(1)
            if nactive()==0: break
        check("silent again after release", nactive()==0, f"{nactive()} active")
        # NOTE name renders "C 4" -- checked here (real key) BEFORE the joystick
        # sections, because a long burst of bridge JOY commands breaks subsequent
        # KEY injection (bridge quirk; see AltirraBridge/TODO.md).
        reset_voices()
        if play("q"):
            # NORMAL clock (default) sounds two octaves above the 15kHz/16-bit
            # tuning, so the valid label for this note is 'C 6' (see draw_note).
            ok = (cell(35,0)==glyph(0x23) and        # 'C'
                  cell(36,0)==glyph(0x00) and        # ' '
                  cell(37,0)==glyph(0x16))           # '6'
            check("note name renders 'C 6'", ok)
        else:
            check("note name renders 'C 6'", False, "key never registered")


        # ---- 8. round-robin allocation + per-channel pitch (incl. wrap) ----
        print("\n[8] voice allocation: each new note -> next channel")
        reset_voices()
        # (key, voice, abs idx, AUDF) at octave centre (base 24); t wraps to v0
        seq = [("q",0,24,0x1D,"C4"), ("w",1,26,0x1A,"D4"),
               ("e",2,28,0x17,"E4"), ("r",3,29,0x16,"F4"), ("t",0,31,0x13,"G4")]
        for key,v,absn,audf,label in seq:
            if play(key) is None:
                check(f"{key!r} onset", False, "never registered"); continue
            held, lastv = pv(V_HELD), pv(V_LASTV)
            vn = pv(V_VNOTE+v); f,c = chan(v+1)
            ok = (held==v and lastv==v and vn==absn and f==audf and c!=0)
            check(f"{key!r} -> voice {v} ch{v+1} = {label}",
                  ok, f"held={held} last={lastv} vnote={vn} AUDF{v+1}={f:02X} AUDC{v+1}={c:02X}")


        # ---- 10. release envelope decays to silence ----
        print("\n[10] release: level decays after the key lifts")
        reset_voices()
        play("q"); lvl0 = pv(V_VLEVEL+0)              # voice0 level at onset
        a.frame(20); lvl1 = pv(V_VLEVEL+0)            # later: should be lower
        check("voice0 sounds on attack", lvl0>0, lvl0)
        check("voice0 level decays on release", lvl1<lvl0, f"{lvl0}->{lvl1}")
        a.frame(80)
        check("decays to full silence", nactive()==0, f"{nactive()} active")

        # ---- ADSR ENVELOPE ----

        # ---- 12. a real note onset begins in ATTACK from silence ----
        print("\n[12] onset enters ATTACK phase from level 0")
        reset_voices()
        a.poke(V_ATK, 5)                              # slow attack: no full step on frame 0
        play("q")
        ph, lv, cnt = pv(V_VPHASE+0), pv(V_VLEVEL+0), pv(V_VCOUNT+0)
        check("onset phase = ATTACK", ph==PH_ATTACK, ph)
        check("onset starts near silence", lv<=1, lv)

        # ---- 3. joystick DOWN selects next parameter ----
        print("\n[3] joystick DOWN -> VOLUME (curparam 0->1)")
        a.joy(0,"down"); a.frame(3); a.joy(0,"centre"); a.frame(2)
        check("DOWN selects VOLUME(1)", pv(V_CURPARAM)==1, pv(V_CURPARAM))
        a.screenshot(os.path.join(SHOTS, "03_sel_volume.png"))

        # ---- 4. RIGHT held: auto-repeat raises volume, clamps at 15 ----
        print("\n[4] RIGHT held -> volume 10 -> 15 (clamp)")
        a.joy(0,"right"); a.frame(45); a.joy(0,"centre"); a.frame(2)
        check("RIGHT raises volume to 15", pv(V_VOLUME)==15, pv(V_VOLUME))
        a.screenshot(os.path.join(SHOTS, "04_volume_max.png"))

        # ---- 5. LEFT held: auto-repeat lowers volume, clamps at 0 ----
        print("\n[5] LEFT held -> volume -> 0 (clamp)")
        a.joy(0,"left"); a.frame(90); a.joy(0,"centre"); a.frame(2)
        check("LEFT lowers volume to 0", pv(V_VOLUME)==0, pv(V_VOLUME))

        # ---- 6. WAVEFORM switch wraps via taps ----
        print("\n[6] WAVEFORM cycle (2 taps -> BUZZ)")
        a.joy(0,"up"); a.frame(3); a.joy(0,"centre"); a.frame(2)
        check("UP selects WAVEFORM(0)", pv(V_CURPARAM)==0, pv(V_CURPARAM))
        for _ in range(2):
            a.joy(0,"right"); a.frame(3); a.joy(0,"centre"); a.frame(3)
        check("WAVEFORM +2 -> BUZZ(2)", pv(V_WAVE)==2, pv(V_WAVE))
        a.screenshot(os.path.join(SHOTS, "06_waveform.png"))

        # ---- 7. CLOCK switch drives AUDCTL bit 0 ----
        print("\n[7] CLOCK 3-mode: NORMAL / 15KHZ / 16-BIT -> AUDCTL")
        # select CLOCK (param 8) by poke -- avoid a long JOY burst that would
        # break later KEY injection (bridge quirk; see AltirraBridge/TODO.md).
        a.poke(V_CURPARAM, 8); a.frame(2)
        check("selection at CLOCK(8)", pv(V_CURPARAM)==8, pv(V_CURPARAM))
        a.poke(V_CLOCK15,0); a.frame(2)
        check("NORMAL -> AUDCTL $00", pk("AUDCTL")==0x00, hex(pk("AUDCTL")))
        a.joy(0,"right"); a.frame(3); a.joy(0,"centre"); a.frame(2)
        check("15KHZ (1) -> AUDCTL $01",
              pv(V_CLOCK15)==1 and pk("AUDCTL")==0x01, f"m={pv(V_CLOCK15)}")
        a.joy(0,"right"); a.frame(3); a.joy(0,"centre"); a.frame(2)
        check("16-BIT (2) -> AUDCTL $78",
              pv(V_CLOCK15)==2 and pk("AUDCTL")==0x78, f"m={pv(V_CLOCK15)}")
        a.joy(0,"right"); a.frame(3); a.joy(0,"centre"); a.frame(2)
        check("CLOCK clamps at 2", pv(V_CLOCK15)==2, pv(V_CLOCK15))
        a.poke(V_CLOCK15,0); a.frame(2)

        # ---- POLYPHONY ----
        # ---- 9. all four channels sounding at once (engine mixes voices) ----
        # Live keys can't overlap under scripted cooked-key latency (a note
        # fully decays before the next key emerges), so set the four voices
        # directly and confirm update_sound emits all four channels in one
        # frame. Section 8 proves real keys allocate to distinct channels;
        # this proves they are mixed simultaneously.
        print("\n[9] four voices -> four channels simultaneously")
        reset_voices()
        chord = [(24,0x1D,"C4"),(26,0x1A,"D4"),(28,0x17,"E4"),(29,0x16,"F4")]
        for i,(absn,_,_) in enumerate(chord):
            a.poke(V_VNOTE+i, absn); a.poke(V_VLEVEL+i, 12+i)  # distinct levels
            a.poke(V_VPHASE+i, PH_RELEASE); a.poke(V_VCOUNT+i, 30)  # active, no step
        a.poke(V_HELD, 0xFF)                          # all ringing/releasing
        a.frame(1)
        p = a.pokey()
        for i,(absn,audf,label) in enumerate(chord):
            f = h(p[f"AUDF{i+1}"]); c = h(p[f"AUDC{i+1}"])
            check(f"ch{i+1} sounds {label}", f==audf and c!=0,
                  f"AUDF{i+1}={f:02X} AUDC{i+1}={c:02X}")
        check("all 4 channels active at once", nactive()==4, f"{nactive()} active")
        a.screenshot(os.path.join(SHOTS, "08_poly.png"))

        # ---- 11. ADSR params adjust + clamp via joystick (table-driven) ----
        print("\n[11] ADSR params: joystick adjust + clamp 0..15")
        for pidx, addr, name in [(3,V_ATK,"ATTACK"),(4,V_DEC,"DECAY"),
                                 (6,V_SUS,"SUSTAIN"),(7,V_REL,"RELEASE")]:
            a.poke(V_CURPARAM, pidx); a.frame(2)
            a.joy(0,"right"); a.frame(90); a.joy(0,"centre"); a.frame(2)
            hi = pv(addr)
            a.joy(0,"left"); a.frame(90); a.joy(0,"centre"); a.frame(2)
            lo = pv(addr)
            check(f"{name} clamps 15 / 0", hi==15 and lo==0, f"hi={hi} lo={lo}")
        a.screenshot(os.path.join(SHOTS, "11_adsr.png"))

        # ---- 13. full attack->decay->sustain (trigger frozen so a voice holds) ----
        # The bridge can't hold a key, so freeze trigger_voices (RTS) to keep a
        # voice "held", then watch update_sound run the envelope deterministically.
        print("\n[13] attack ramps to peak, decays to sustain, holds")
        a.poke(TRIGGER_ADDR, 0x60)                    # patch: RTS (freeze voice mgr)
        try:
            a.poke(V_VOLUME,10); a.poke(V_SUS,4)
            a.poke(V_ATK,0); a.poke(V_DEC,0)
            a.poke(V_HELD,0)                          # voice0 is the held voice
            a.poke(V_VNOTE+0,24); a.poke(V_VLEVEL+0,0)
            a.poke(V_VPHASE+0,PH_ATTACK); a.poke(V_VCOUNT+0,1)
            seq = []
            for _ in range(24):
                a.frame(1); seq.append((pv(V_VLEVEL+0), pv(V_VPHASE+0)))
            peak = max(l for l,_ in seq)
            endl, endph = seq[-1]
            check("attack reaches peak (volume=10)", peak==10, peak)
            check("settles at sustain=4 in SUSTAIN phase",
                  endl==4 and endph==PH_SUSTAIN, f"lvl={endl} ph={endph}")
            check("sustain holds steady", seq[-1]==seq[-2], seq[-1])

            # ---- 14. release ramps to 0 / idle, and rate responds ----
            print("\n[14] release ramps to silence; rate is configurable")
            a.poke(V_HELD,0xFF)                       # not held -> release
            a.poke(V_VLEVEL+0,12); a.poke(V_VPHASE+0,PH_RELEASE)
            a.poke(V_VCOUNT+0,1); a.poke(V_REL,0)     # fast: 1 level/frame
            rel = []
            for _ in range(15):
                a.frame(1); rel.append(pv(V_VLEVEL+0))
            mono = all(rel[i] >= rel[i+1] for i in range(len(rel)-1))
            check("release decreases monotonically", mono, rel[:6])
            check("release reaches idle", pv(V_VPHASE+0)==PH_IDLE, pv(V_VPHASE+0))

            a.poke(V_VLEVEL+0,8); a.poke(V_VPHASE+0,PH_RELEASE)
            a.poke(V_VCOUNT+0,1); a.poke(V_REL,3)     # slow: 1 level / 4 frames
            a.frame(4); lvlA = pv(V_VLEVEL+0)         # after 4 frames: 1 step
            a.frame(4); lvlB = pv(V_VLEVEL+0)         # after 8 frames: 2 steps
            check("slower release rate steps slower", lvlA==7 and lvlB==6,
                  f"{lvlA},{lvlB}")
        finally:
            a.poke(TRIGGER_ADDR, 0xAD)                # restore LDA note_idx

        # ---- GR.8 BITMAP UI ----

        print("\n[15] GR.8 bitmap UI: display list, line table, drawn pixels")
        dl = label_addr("dlist")
        sdl = pv(0x0230) | (pv(0x0231) << 8)
        check("display list installed (SDLSTL->dlist)", sdl==dl, f"{sdl:04X}!={dl:04X}")
        # ANTIC's DL counter is 10-bit: the list must not cross a 1KB boundary
        check("display list within one 1KB block", (dl >> 10) == ((dl+201) >> 10),
              f"{dl:04X}-{dl+201:04X}")
        check("SDMCTL = $22 (normal width + screen DMA)", pv(0x022F)==0x22, hex(pv(0x022F)))
        check("colours set (fg=$0E bg=$00)",
              pv(0x02C5)==0x0E and pv(0x02C6)==0x00, f"{pv(0x02C5):02X}/{pv(0x02C6):02X}")
        # line table hides the FB1/FB2 split
        lt_lo, lt_hi = 0x6000, 0x60C0   # linetab moved above the framebuffers (was $3000)
        l0 = pv(lt_lo) | (pv(lt_hi) << 8)
        l102 = pv(lt_lo+102) | (pv(lt_hi+102) << 8)
        check("linetab[0] = FB1", l0==FB1, f"{l0:04X}")
        check("linetab[102] = FB2 (4K split)", l102==FB2, f"{l102:04X}")
        # a white-key top edge pixel was drawn (key 0 top edge at y=120)
        check("piano keyboard drawn", a.peek(fb_addr(16,124))[0] != 0,
              hex(a.peek(fb_addr(16,124))[0]))
        # title text drawn (glyph body rows, not the blank top row)
        def cell_col(x, ytop):                        # 8 vertical bytes of a glyph
            return [a.peek(fb_addr(x, ytop+i))[0] for i in range(8)]
        check("title text drawn", any(cell_col(88, 0)))
        # dynamic: changing VOLUME redraws its number cell (col 13, scan 48)
        a.poke(V_VOLUME,0);  a.frame(2); b0 = cell_col(13*8, 36)
        a.poke(V_VOLUME,12); a.frame(2); b1 = cell_col(13*8, 36)
        check("VOLUME value redraws on change", b0 != b1, "cell unchanged")
        # dynamic: the VOLUME knob pointer moves (sample the knob's full height)
        def knob_col(cx):
            return [tuple(a.peek(fb_addr(cx, y)-1, 3)) for y in range(35, 48)]
        a.poke(V_VOLUME,0);  a.frame(2); k0 = knob_col(86)
        a.poke(V_VOLUME,15); a.frame(2); k1 = knob_col(86)
        check("VOLUME knob pointer redraws on change", k0 != k1, "knob unchanged")
        a.poke(V_VOLUME,10); a.frame(2)
        a.screenshot(os.path.join(SHOTS, "15_gr8.png"))

        # ---- 16. switch glyphs: WAVEFORM selector + CLOCK toggle ----
        print("\n[16] switch glyphs: WAVEFORM icons + CLOCK toggle")
        def row(x, y, n):                             # n framebuffer bytes
            return list(a.peek(fb_addr(x, y), n))
        a.poke(V_WAVE,0); a.frame(2); w0 = row(72, 16, 12)   # box top edge
        a.poke(V_WAVE,3); a.frame(2); w3 = row(72, 16, 12)
        check("WAVEFORM selection box moves with wave", w0 != w3, "box static")
        a.poke(V_CLOCK15,0); a.frame(2); c0 = row(30*8, 58, 8)
        a.poke(V_CLOCK15,2); a.frame(2); c1 = row(30*8, 58, 8)
        a.poke(V_CLOCK15,0); a.frame(2)
        check("CLOCK name changes with mode", c0 != c1, "name static")
        a.poke(V_WAVE,0); a.poke(V_CLOCK15,0); a.frame(2)
        a.screenshot(os.path.join(SHOTS, "16_switches.png"))

        # ---- 17. LFO / vibrato ----
        print("\n[17] LFO: params clamp, and vibrato modulates pitch")
        for pidx, addr, name in [(9,V_LFOR,"LFO RATE"),(10,V_LFOD,"LFO DEPTH")]:
            a.poke(V_CURPARAM, pidx); a.frame(2)
            a.joy(0,"right"); a.frame(90); a.joy(0,"centre"); a.frame(2)
            hi = pv(addr)
            a.joy(0,"left"); a.frame(90); a.joy(0,"centre"); a.frame(2)
            lo = pv(addr)
            check(f"{name} clamps 15 / 0", hi==15 and lo==0, f"hi={hi} lo={lo}")
        # vibrato: freeze the voice manager, hold a C4 voice, watch AUDF1 wobble
        a.poke(TRIGGER_ADDR, 0x60)
        try:
            a.poke(V_VOLUME,10); a.poke(V_SUS,10)
            a.poke(V_LFOD,15); a.poke(V_LFOR,15)          # deep, fast vibrato
            a.poke(V_HELD,0)                              # voice0 is held (sustains)
            a.poke(V_VNOTE+0,24); a.poke(V_VLEVEL+0,10)
            a.poke(V_VPHASE+0,PH_SUSTAIN); a.poke(V_VCOUNT+0,8)
            seen = []
            for _ in range(24):
                a.frame(1); seen.append(chan(1)[0])       # AUDF1 each frame
            lo, hi = min(seen), max(seen)
            check("vibrato modulates pitch (AUDF1 wobbles)", hi > lo, f"{lo:02X}..{hi:02X}")
            check("vibrato stays near C4 ($1D +/-7)", 0x16 <= lo and hi <= 0x24,
                  f"{lo:02X}..{hi:02X}")
            a.poke(V_LFOD,0)                              # depth 0 -> settles flat
            for _ in range(20): a.frame(1)
            f1 = chan(1)[0]
            check("depth 0 -> no modulation (AUDF1 = $1D)", f1 == 0x1D, f"{f1:02X}")
        finally:
            a.poke(TRIGGER_ADDR, 0xAD)
        a.poke(V_LFOD,0); a.poke(V_LFOR,8); a.frame(2)
        a.screenshot(os.path.join(SHOTS, "17_lfo.png"))

        # ---- 18. DETUNE / fat pitch ----
        print("\n[18] DETUNE: reachable by nav, clamp, per-voice pitch spread")
        # DETUNE is param 5 (left col, below DECAY): DOWN x5 from WAVEFORM must
        # land on it -- guards index-order == visual-order.
        a.poke(V_CURPARAM, 0); a.frame(2)
        for _ in range(5):
            a.joy(0,"down"); a.frame(3); a.joy(0,"centre"); a.frame(3)
        check("DETUNE reachable: DOWN x5 -> param 5", pv(V_CURPARAM)==5, pv(V_CURPARAM))
        a.joy(0,"right"); a.frame(90); a.joy(0,"centre"); a.frame(2)
        hi = pv(V_DETUNE)
        a.joy(0,"left"); a.frame(90); a.joy(0,"centre"); a.frame(2)
        lo = pv(V_DETUNE)
        check("DETUNE clamps 15 / 0", hi==15 and lo==0, f"hi={hi} lo={lo}")
        # spread: 4 voices on the SAME note get AUDF +0/+3/+6/+9 at detune 15
        a.poke(TRIGGER_ADDR, 0x60)
        try:
            a.poke(V_LFOD,0); a.poke(V_DETUNE,15)     # detune>>2 = 3 -> step 3
            a.poke(V_HELD,0xFF)
            for i in range(4):
                a.poke(V_VNOTE+i,24); a.poke(V_VLEVEL+i,10)
                a.poke(V_VPHASE+i,PH_RELEASE); a.poke(V_VCOUNT+i,40)
            a.frame(1)
            f = [chan(n)[0] for n in (1,2,3,4)]
            check("detune spreads voices ($1D,$20,$23,$26)",
                  f==[0x1D,0x20,0x23,0x26], " ".join(f"{x:02X}" for x in f))
            a.poke(V_DETUNE,0); a.frame(8)  # settle (meter redraw can lag a few frames)
            f0 = [chan(n)[0] for n in (1,2,3,4)]
            check("detune 0 -> all voices same pitch ($1D)",
                  f0==[0x1D]*4, " ".join(f"{x:02X}" for x in f0))
        finally:
            a.poke(TRIGGER_ADDR, 0xAD)
        a.poke(V_DETUNE,0); a.frame(2)
        a.screenshot(os.path.join(SHOTS, "18_detune.png"))

        # ---- 19. text rendering: octave sign/digit glyphs ----
        # (blit_char clobbers X/s0/s1 — guard that the OCTAVE readout that carries
        #  a value across blit_char calls renders the right glyphs. The note-name
        #  glyph check is in section 2, before the joystick-heavy sections.)
        print("\n[19] text rendering: octave sign/digit")
        # OCTAVE (param 2): sign at col 13, digit at col 14, scan 56
        for octv, sign, digit, lbl in [(2,0x00,0x10," 0"),(4,0x0B,0x12,"+2"),
                                       (0,0x0D,0x12,"-2")]:
            a.poke(V_OCTAVE, octv); a.frame(2)
            ok = cell(13,56)==glyph(sign) and cell(14,56)==glyph(digit)
            check(f"octave reads {lbl!r}", ok)
        a.poke(V_OCTAVE,2); a.frame(2)

        # ---- 20. ARP / arpeggiator ----
        print("\n[20] ARP: clamp + chord cycling across voices")
        a.poke(V_CURPARAM, 11); a.frame(2)            # ARP is param 11
        a.joy(0,"right"); a.frame(90); a.joy(0,"centre"); a.frame(2); ahi = pv(V_ARP)
        a.joy(0,"left"); a.frame(90); a.joy(0,"centre"); a.frame(2); alo = pv(V_ARP)
        check("ARP clamps 15 / 0", ahi==15 and alo==0, f"hi={ahi} lo={alo}")
        # Behaviour: hold C4 with ARP on -> cycles root/+4/+7/+12 (C4 E4 G4 C5)
        # across the voices. Freeze read_keyboard so the held note stays set.
        RK = label_addr("read_keyboard")
        a.poke(RK, 0x60)
        try:
            a.poke(V_LFOD,0); a.poke(V_DETUNE,0); a.poke(V_OCTAVE,2)
            a.poke(V_NOTEIDX,0)                       # hold C4
            a.poke(V_LASTV,3); a.poke(V_ARP_STEP,0); a.poke(V_ARP_TIMER,1)
            a.poke(V_ARP,15)                          # fast
            for _ in range(6): a.frame(1)             # 6 arp steps
            vn = [pv(V_VNOTE+i) for i in range(4)]
            check("ARP cycles chord -> notes 24,28,31,36",
                  sorted(vn)==[24,28,31,36], vn)
        finally:
            a.poke(RK, 0xAD); a.poke(V_ARP,0); a.poke(V_NOTEIDX,0xFF)
        a.frame(2)
        a.screenshot(os.path.join(SHOTS, "20_arp.png"))

        # ---- 21. sustain pedal (OPTION console key) ----
        print("\n[21] OPTION = sustain pedal (holds notes, independent of keys)")
        a.poke(TRIGGER_ADDR, 0x60)                    # freeze voice manager
        try:
            a.poke(V_VOLUME,10); a.poke(V_SUS,10); a.poke(V_REL,0)
            a.poke(V_VNOTE+0,24); a.poke(V_VLEVEL+0,10)
            a.poke(V_VPHASE+0,PH_SUSTAIN); a.poke(V_VCOUNT+0,1)
            a.poke(V_HELD,0xFF)                       # voice0 NOT held -> would release
            a.consol(option=True)                     # press OPTION
            for _ in range(20): a.frame(1)
            held_lvl = pv(V_VLEVEL+0)
            a.consol()                                # release OPTION
            for _ in range(20): a.frame(1)
            rel_lvl = pv(V_VLEVEL+0)
            check("OPTION held -> note sustains", held_lvl>=8, held_lvl)
            check("OPTION up -> note releases", rel_lvl==0, rel_lvl)
        finally:
            a.poke(TRIGGER_ADDR, 0xAD); a.consol()
        a.frame(2)

        # ---- 22. 16-bit pitch mode (joined channel pairs) ----
        print("\n[22] 16-bit pitch: joined-pair register layout")
        a.poke(TRIGGER_ADDR, 0x60)
        try:
            a.poke(V_CLOCK15,2); a.poke(0x0689,2)     # clock_mode=2, prev=2 (no reset)
            a.poke(V_LFOD,0); a.poke(V_DETUNE,0)
            a.poke(V_VOLUME,10); a.poke(V_WAVE,0)
            a.poke(V_VNOTE+0,24); a.poke(V_VLEVEL+0,10)
            a.poke(V_VPHASE+0,PH_SUSTAIN); a.poke(V_VCOUNT+0,8); a.poke(V_HELD,0)
            a.poke(V_VLEVEL+1,0); a.poke(V_VPHASE+1,0) # voice1 idle
            a.frame(2)
            p = a.pokey()
            f1,f2 = h(p["AUDF1"]), h(p["AUDF2"])
            c1,c2 = h(p["AUDC1"]), h(p["AUDC2"])
            check("16-bit C4 divider (AUDF1=$3C AUDF2=$0D)",
                  f1==0x3C and f2==0x0D, f"{f1:02X} {f2:02X}")
            check("16-bit output on HIGH channel (AUDC1=0, AUDC2=$AA)",
                  c1==0x00 and c2==0xAA, f"{c1:02X} {c2:02X}")
            check("16-bit AUDCTL = $78 (join+1.79MHz)", pk("AUDCTL")==0x78,
                  hex(pk("AUDCTL")))
            a.screenshot(os.path.join(SHOTS, "22_16bit.png"))
        finally:
            a.poke(TRIGGER_ADDR, 0xAD); a.poke(V_CLOCK15,0)
        a.frame(2)

        # ---- 23. two-page panel: navigating past page 0 shows page 2 ----
        print("\n[23] 2-page panel: page switch + redraw")
        V_PAGE = 0x068D
        a.poke(V_CURPARAM, 12); a.frame(20)           # -> page 2 (TEMPO)
        pg2 = pv(V_PAGE); tlbl = cell(1,16)==glyph(0x34)   # 'T' of TEMPO at col1
        check("nav to param 12 -> page 2", pg2==1, pg2)
        check("page 2 shows TEMPO label", tlbl, "no T")
        a.screenshot(os.path.join(SHOTS, "23_page2.png"))
        a.poke(V_CURPARAM, 0); a.frame(20)            # -> page 0 (WAVEFORM)
        pg0 = pv(V_PAGE); wlbl = cell(1,16)==glyph(0x37)   # 'W' of WAVEFORM
        check("back to param 0 -> page 0", pg0==0, pg0)
        check("page 0 redraws WAVEFORM label", wlbl, "no W")

        # ---- 24. step sequencer (transport / playback / record) ----
        print("\n[24] step sequencer")
        V_TEMPO = 0x068C
        SEQ_NOTES, SEQ_PLAY, SEQ_REC = 0x0691, 0x06A1, 0x06A2
        SEQ_POS, SEQ_WPOS, SEQ_TIMER, SEQ_PREVN = 0x06A3, 0x06A4, 0x06A5, 0x06A6
        SEQ_LEN = 0x06B3
        a.poke(V_CURPARAM,0); a.frame(2)              # back to page 0
        # transport: START (console) toggles play
        a.poke(SEQ_PLAY,0)
        a.consol(start=True); a.frame(3); a.consol(); a.frame(3)
        check("START -> play on", pv(SEQ_PLAY)==1, pv(SEQ_PLAY))
        a.consol(start=True); a.frame(3); a.consol(); a.frame(3)
        check("START -> play off", pv(SEQ_PLAY)==0, pv(SEQ_PLAY))
        # playback: a step's note is triggered (step0=note5 -> 24+5=29, F4)
        for i in range(16): a.poke(SEQ_NOTES+i, 0xFF)
        a.poke(SEQ_NOTES+0, 5)
        a.poke(V_OCTAVE,2); a.poke(V_LASTV,3)
        a.poke(SEQ_POS,0); a.poke(SEQ_TIMER,1); a.poke(V_TEMPO,15)
        a.poke(SEQ_PLAY,1); a.frame(2)
        vn = [pv(V_VNOTE+i) for i in range(4)]
        check("playing step triggers its note (29)", 29 in vn, vn)
        a.poke(SEQ_PLAY,0)
        # audibility: a played step's note must SUSTAIN its envelope across the
        # step (not get force-released after one frame -> near-silent volume 1).
        for i in range(16): a.poke(SEQ_NOTES+i, 0xFF)
        a.poke(SEQ_NOTES+0, 5); a.poke(V_VOLUME,10); a.poke(V_SUS,8)
        a.poke(V_ATK,0); a.poke(V_DEC,2); a.poke(V_TEMPO,4)   # slow step -> reaches sustain
        a.poke(SEQ_REC,0); a.poke(SEQ_POS,0); a.poke(SEQ_TIMER,1); a.poke(SEQ_PLAY,1)
        peak = 0
        for _ in range(30):
            a.frame(1)
            peak = max(peak, max(pv(V_VLEVEL+i) for i in range(4)))
        a.poke(SEQ_PLAY,0)
        check("a played note reaches an audible (sustained) level", peak >= 7, f"peak level={peak}")
        # record: with read_keyboard frozen, a held note is written to the step
        RK = label_addr("read_keyboard")
        a.poke(RK, 0x60)
        try:
            for i in range(16): a.poke(SEQ_NOTES+i, 0xFF)
            a.poke(SEQ_REC,1); a.poke(SEQ_WPOS,0); a.poke(SEQ_PREVN,0xFF)
            a.poke(V_NOTEIDX,7); a.frame(2)
            check("record writes note 7 to step 0", pv(SEQ_NOTES+0)==7, pv(SEQ_NOTES+0))
            check("record advances write head", pv(SEQ_WPOS)==1, pv(SEQ_WPOS))
        finally:
            a.poke(RK,0xAD); a.poke(SEQ_REC,0); a.poke(V_NOTEIDX,0xFF)
        # the down-arrow head tracks the WRITE head while recording (page 2):
        # its glyph stem sits at byte col wpos*2+4 on scan 52.
        a.poke(V_CURPARAM,12); a.frame(4)             # page 2
        a.poke(RK,0x60)
        try:
            for i in range(16): a.poke(SEQ_NOTES+i, 0xFF)
            a.poke(SEQ_REC,1); a.poke(SEQ_WPOS,0); a.poke(SEQ_PREVN,0xFF); a.frame(3)
            a.poke(V_NOTEIDX,2); a.frame(3); a.poke(V_NOTEIDX,0xFF); a.frame(2)
            wp = pv(SEQ_WPOS)
            arr = [i for i in range(40) if pv(FB1 + 52*40 + i)]
            check("record: arrow follows the write head", arr==[wp*2+4],
                  f"wpos={wp} arrowcols={arr}")
        finally:
            a.poke(RK,0xAD); a.poke(SEQ_REC,0); a.poke(V_NOTEIDX,0xFF)
        # step-entry mode (rec armed + clock STOPPED) -> one step per keypress,
        # and playback then loops over the RECORDED length (no trailing-rest gap).
        for i in range(16): a.poke(SEQ_NOTES+i, 0xFF)
        a.poke(SEQ_REC,1); a.poke(SEQ_PLAY,0); a.poke(SEQ_WPOS,0)
        a.poke(SEQ_LEN,0); a.poke(SEQ_PREVN,0xFF)
        a.poke(RK,0x60)
        try:
            for n in (0,2,4):
                a.poke(V_NOTEIDX,n); a.frame(3); a.poke(V_NOTEIDX,0xFF); a.frame(3)
            check("step entry sets loop length to the step count", pv(SEQ_LEN)==3, pv(SEQ_LEN))
        finally:
            a.poke(RK,0xAD); a.poke(SEQ_REC,0)
        a.poke(SEQ_TIMER,1); a.poke(SEQ_POS,0); a.poke(V_TEMPO,12); a.poke(SEQ_PLAY,1)
        seen_pos = set()
        for _ in range(40): a.frame(1); seen_pos.add(pv(SEQ_POS))
        a.poke(SEQ_PLAY,0)
        check("playback wraps within the recorded length", seen_pos=={0,1,2}, sorted(seen_pos))
        # screenshot the sequencer page with a pattern, playing
        pat = [0,255,255,255, 4,255,255,255, 7,255,255,255, 12,255,255,255]
        for i,n in enumerate(pat): a.poke(SEQ_NOTES+i, n)
        a.poke(SEQ_TIMER,1); a.poke(SEQ_POS,0)
        a.poke(V_CURPARAM,12); a.frame(20)            # page 2 (sequencer view)
        a.poke(SEQ_PLAY,1); a.frame(8)
        a.screenshot(os.path.join(SHOTS, "24_seq.png"))
        a.poke(SEQ_PLAY,0); a.poke(V_CURPARAM,0); a.frame(2)

        # ---- 25. per-voice level meters (VU bars at scan 9-13) ----
        print("\n[25] level meters: VU bars track each voice's envelope level")
        def px(x, y):
            base = FB1 + y*40 if y < 102 else FB2 + (y-102)*40
            return (pv(base + x//8) >> (7 - (x % 8))) & 1
        MET_X = [4, 72, 140, 208]          # bar left edges; width = level*3 px
        def bar_ok(v, lvl):                # meter v reflects envelope level lvl
            if lvl == 0:
                return px(MET_X[v]+2, 11) == 0
            w = lvl*3
            return px(MET_X[v]+w//2, 11) == 1 and px(MET_X[v]+w+3, 11) == 0
        reset_voices(); a.poke(V_CURPARAM,0); a.frame(2)
        # Hold voices via the voice manager freeze (update_sound runs the real
        # envelope, so the meter shows exactly what the engine outputs).
        a.poke(TRIGGER_ADDR, 0x60)
        try:
            a.poke(V_VOLUME,15); a.poke(V_SUS,12); a.poke(V_DEC,0); a.poke(V_REL,0)
            a.poke(V_VNOTE+0,24); a.poke(V_VPHASE+0,3); a.poke(V_VLEVEL+0,12)
            a.poke(V_VCOUNT+0,1); a.poke(V_HELD,0); a.frame(6)
            l0 = pv(V_VLEVEL+0)
            check("voice0 meter matches its level", bar_ok(0, l0), f"lvl={l0}")
            a.poke(V_SUS,4); a.frame(16)                  # sustain target falls
            l0 = pv(V_VLEVEL+0)
            check("meter shrinks as the level falls", bar_ok(0, l0), f"lvl={l0}")
            a.poke(V_HELD,0xFF); a.frame(40)              # release -> silence
            check("meter clears when the voice goes silent",
                  pv(V_VLEVEL+0)==0 and bar_ok(0, 0), f"lvl={pv(V_VLEVEL+0)}")
            a.poke(V_SUS,10)                              # voice2 on its own bar
            a.poke(V_VNOTE+2,24); a.poke(V_VPHASE+2,3); a.poke(V_VLEVEL+2,10)
            a.poke(V_VCOUNT+2,1); a.poke(V_HELD,2); a.frame(6)
            l2 = pv(V_VLEVEL+2)
            check("voice2 uses its own bar (x=140), voice0 stays clear",
                  bar_ok(2, l2) and px(MET_X[0]+2, 11)==0, f"lvl={l2}")
            a.screenshot(os.path.join(SHOTS, "25_meters.png"))
        finally:
            a.poke(TRIGGER_ADDR, 0xAD)
        reset_voices()

        # ---- 26. real-time (tempo-synced) recording ----
        # SELECT alone runs the clock and records live: the note you play is
        # captured onto the step under the head, so held notes fill consecutive
        # steps and gaps stay rests (timing preserved). A one-step lead-in lets
        # the first note land on step 0. Non-destructive -> overdub across loops.
        print("\n[26] real-time recording (SELECT runs the clock + records)")
        a.poke(V_CURPARAM,12); a.frame(6)                 # page 2
        a.poke(V_TEMPO,8); a.poke(V_OCTAVE,2)
        if pv(SEQ_PLAY): a.consol(start=True); a.frame(3); a.consol(); a.frame(3)
        if pv(SEQ_REC):  a.consol(select=True); a.frame(3); a.consol(); a.frame(3)
        a.consol(select=True); a.frame(3); a.consol(); a.frame(3)   # SELECT only
        check("SELECT alone enters real-time record (clock running)",
              pv(SEQ_REC)==1 and pv(SEQ_PLAY)==1, f"rec={pv(SEQ_REC)} play={pv(SEQ_PLAY)}")
        a.poke(RK, 0x60)
        try:
            a.poke(V_NOTEIDX,5)                           # play at once: lead-in
            for _ in range(40):                           # -> should land on step 0
                a.frame(1)
                if pv(SEQ_POS) != 0: break
            a.poke(V_NOTEIDX,0xFF)
            s0 = pv(SEQ_NOTES+0)
            check("lead-in lets the first note land on step 0", s0==5, f"step0={s0}")
            a.poke(V_NOTEIDX,4);    a.frame(54)           # hold note 4 ~3 steps
            a.poke(V_NOTEIDX,0xFF); a.frame(54)           # release ~3 steps
            a.poke(V_NOTEIDX,7);    a.frame(36)           # hold note 7 ~2 steps
            a.poke(V_NOTEIDX,0xFF); a.frame(6)
        finally:
            a.poke(RK, 0xAD)
        a.consol(start=True);  a.frame(3); a.consol(); a.frame(3)   # stop
        a.consol(select=True); a.frame(3); a.consol(); a.frame(3)   # disarm
        steps = [pv(SEQ_NOTES+i) for i in range(16)]
        ties = steps.count(0xFE)                     # held continuation markers
        rests = steps.count(0xFF)
        # a HELD note is captured as ONE struck note + tie markers (not the same
        # note re-written each step -> on playback that would re-attack = blips).
        check("a held note records as one struck note + ties",
              steps.count(4) == 1 and ties >= 2, f"4x{steps.count(4)} ties={ties} steps={steps}")
        check("a second held note is captured later", steps.count(7) == 1, f"7x{steps.count(7)}")
        check("gaps between notes stay rests", rests >= 4, f"rests={rests}")
        # playback fidelity: the recorded semitones fire at octave_base+note
        rec_semis = sorted(set(s for s in steps if s not in (0xFF, 0xFE)))
        a.poke(SEQ_POS,0); a.poke(SEQ_TIMER,1); a.poke(SEQ_PLAY,1)
        fired = set()
        for _ in range(16*22):
            before = [pv(V_VNOTE+i) for i in range(4)]
            a.frame(1)
            after = [pv(V_VNOTE+i) for i in range(4)]
            for i in range(4):
                if after[i] != before[i]:
                    fired.add(after[i])
        a.poke(SEQ_PLAY,0)
        exp = set(24 + s for s in rec_semis)        # octave 2 -> base 24
        check("recorded notes play back at the right pitch",
              exp.issubset(fired), f"exp={sorted(exp)} fired={sorted(fired)}")
        # a TIED (held) note plays back as ONE sustained note, not re-struck
        # blips: struck once then it rings on through the ties (no dip to 0).
        for i in range(16): a.poke(SEQ_NOTES+i, 0xFF)
        a.poke(SEQ_NOTES+0,4); a.poke(SEQ_NOTES+1,0xFE); a.poke(SEQ_NOTES+2,0xFE)
        a.poke(SEQ_LEN,16); a.poke(V_VOLUME,10); a.poke(V_SUS,8)
        a.poke(V_ATK,0); a.poke(V_DEC,2); a.poke(V_TEMPO,4)
        a.poke(SEQ_REC,0); a.poke(SEQ_POS,0); a.poke(SEQ_TIMER,1); a.poke(SEQ_PLAY,1)
        lv = []
        for _ in range(70):
            a.frame(1); lv.append(max(pv(V_VLEVEL+i) for i in range(4)))
        a.poke(SEQ_PLAY,0)
        reattacks = sum(1 for i in range(1, len(lv)) if lv[i-1] == 0 and lv[i] > 0)
        held_min = min(lv[14:60])                   # the tied sustain region
        check("a tied note sustains (no re-strike blips)",
              reattacks <= 1 and held_min >= 6, f"peak={max(lv)} heldmin={held_min} reattacks={reattacks}")
        # NB: a brief COOKED-key tap during real-time record IS captured (latch),
        # but that can't be tested here -- by this point the bridge's JOY-breaks-
        # KEY quirk has disabled KEY injection. It's covered separately (the
        # latch path is exercised by the poked-note checks above, and the
        # read_keyboard->note_idx path by sections 2/8). See AltirraBridge/TODO.md.

    finally:
        try: a.frame(1)
        except Exception: pass
        proc.kill()                       # SIGKILL: headless AltirraSDL ignores SIGTERM
        try: proc.wait(timeout=5)
        except Exception: pass

    npass = sum(1 for _,ok in results if ok)
    print(f"\n==== {npass}/{len(results)} checks passed ====")
    sys.exit(0 if npass==len(results) else 1)

if __name__ == "__main__":
    main()
