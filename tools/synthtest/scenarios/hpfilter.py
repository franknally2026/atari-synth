"""High-pass filter — comprehensive coverage of the HPF parameter (index
13, on the FX/Patch screen / page 1). POKEY's hardware high-pass: AUDCTL bit 2 high-passes
channel 1, clocked by channel 3. With HPF > 0 the synth sets bit 2 and turns
channel 3 into the (silent) cutoff clock (AUDF3 = (16-HPF)*4), so voice 0's tone
loses its low end. 8-bit clock modes only (channel 3 is paired in 16-bit).
"""
from .. import dsp, notes
from ..harness import PH_SUSTAIN

HPF = 0x06C0


def _voice0(s, idx, wave=0):
    """Hold voice 0 on a note (other voices idle) for steady capture."""
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.set("wave", wave); s.set("volume", 13); s.set("sus", 14)
    s.set("lfod", 0); s.set("detune", 0)
    for i in range(4):
        s.set("vlevel", 0, i); s.set("vphase", 0, i)
    s.set("vnote", idx, 0); s.set("vlevel", 13, 0)
    s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)


def hpf_param(s, rep):
    rep.section("hpfilter: parameter on the FX/PATCH screen (page 1)")
    rep.check("HPF defaults to 0 (off)", s.get_param(13) == 0, s.get_param(13))
    s.set("curparam", 13); s.frame(8)
    rep.check("nav to HPF -> FX screen (page 1)", s.get("page") == 1, s.get("page"))
    # HP FILTER is page-1 right column (col 21, scan 16). 'H' (col21) is the plain
    # shortcut (underlined), so check the non-shortcut 'P' at col 22 as clean inverse.
    rep.check("HP FILTER label renders on the FX screen",
              s.cell(22, 16) == s.glyph(0x30, inv=True), "no P")
    s.joy(0, "right"); s.frame(100); s.joy(0, "centre"); s.frame(2)
    hi = s.get_param(13)
    s.joy(0, "left"); s.frame(130); s.joy(0, "centre"); s.frame(2)
    lo = s.get_param(13)
    rep.check("HPF clamps 15 / 0", hi == 15 and lo == 0, f"hi={hi} lo={lo}")
    s.poke(HPF, 0); s.set("curparam", 0); s.frame(8)


def hpf_register(s, rep):
    """HPF > 0 sets AUDCTL bit 2 and programs channel 3 as the silent cutoff
    clock; HPF = 0 leaves AUDCTL clean."""
    rep.section("hpfilter: AUDCTL bit2 + channel-3 cutoff clock")
    with s.frozen("trigger_voices"):
        _voice0(s, 0)
        # AUDCTL settles a few frames after a page-change redraw, so allow a
        # short settle before reading the register state.
        s.poke(HPF, 0); s.frame(8)
        rep.check("HPF 0 -> AUDCTL bit2 clear", (s.audctl() & 0x04) == 0, hex(s.audctl()))
        s.poke(HPF, 8); s.frame(8)
        f3, c3 = s.chan(3)
        rep.check("HPF 8 -> AUDCTL bit2 set (HP ch1<-ch3)", (s.audctl() & 0x04) != 0,
                  hex(s.audctl()))
        rep.check("channel 3 = cutoff clock, silent (vol 0)", (c3 & 0x0F) == 0,
                  f"AUDC3={c3:#x}")
        rep.check("channel 3 AUDF = (16-HPF)*4 cutoff", f3 == (16 - 8) * 4,
                  f"AUDF3={f3} want {(16-8)*4}")
    s.poke(HPF, 0)


def hpf_attenuates_lows(s, rep):
    """ACOUSTIC flagship: the high-pass removes the low fundamental and pushes
    the spectral centre of mass upward."""
    rep.section("hpfilter: removes the low fundamental (PCM)")
    fund = notes.predicted_freq(0, notes.MODE_NORMAL)   # idx 0 ~262 Hz
    with s.frozen("trigger_voices"):
        _voice0(s, 0, wave=0)
        s.poke(HPF, 0); off = s.capture("hpf_off", 30)
        _voice0(s, 0, wave=0)
        s.poke(HPF, 8); on = s.capture("hpf_on", 30)
    s.poke(HPF, 0)
    coff = dsp.spectral_features(off)["centroid"]
    con = dsp.spectral_features(on)["centroid"]
    rep.check("fundamental present with HPF off", dsp.has_tone_at(off, fund, tol_frac=0.05),
              f"~{fund:.0f}Hz")
    rep.check("fundamental removed with HPF on", not dsp.has_tone_at(on, fund, tol_frac=0.05),
              f"~{fund:.0f}Hz")
    rep.check("HPF raises the spectral centroid (brighter)", con > coff * 1.5,
              f"off={coff:.0f}Hz -> on={con:.0f}Hz")


def hpf_cutoff_scales(s, rep):
    """Higher HPF = higher cutoff = more low end removed = higher centroid."""
    rep.section("hpfilter: higher HPF cuts more (centroid rises)")
    def centroid(hpf):
        with s.frozen("trigger_voices"):
            _voice0(s, 0, wave=0)
            s.poke(HPF, hpf)
            c = s.capture(f"hpf_c{hpf}", 30)
        s.poke(HPF, 0)
        return dsp.spectral_features(c)["centroid"]
    lo = centroid(4)
    hi = centroid(12)
    rep.check("HPF 12 brighter than HPF 4", hi > lo + 200,
              f"HPF4 centroid={lo:.0f}Hz, HPF12={hi:.0f}Hz")


def hpf_disabled_in_16bit(s, rep):
    """The HP filter is not engaged in 16-bit mode (channel 3 is a joined pair):
    AUDCTL keeps its 16-bit value, bit 2 not forced on."""
    rep.section("hpfilter: disabled in 16-bit mode")
    with s.frozen("trigger_voices"):
        s.set("wave", 1); s.set("volume", 13); s.set("sus", 14)
        s.set("clock15", 2); s.poke(0x0689, 2)
        s.set("vnote", 24, 0); s.set("vlevel", 13, 0)
        s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
        s.poke(HPF, 12); s.frame(2)
        rep.check("16-bit AUDCTL stays $78 (no HP bit forced)", s.audctl() == 0x78,
                  hex(s.audctl()))
    s.poke(HPF, 0); s.set("clock15", 0); s.poke(0x0689, 0)


SCENARIOS = [
    hpf_param,
    hpf_register,
    hpf_attenuates_lows,
    hpf_cutoff_scales,
    hpf_disabled_in_16bit,
]
