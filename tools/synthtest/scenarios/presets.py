"""Presets — comprehensive coverage of the new PRESET parameter (index 17, page
2). 4 patch slots hold the 17 sound params; selecting a slot with the PRESET
knob LOADS it live, and pressing FIRE while PRESET is selected SAVES the current
sound into the slot. The bank is seeded with 4 factory patches at boot.

NB: after a page change the panel takes a few frames to settle, so the checks
allow short settle windows.
"""
from .. import dsp

PRESET = 0x06C5
BANK = 0x0700
NSAVE = 17
# factory patches (param order: wave vol oct atk dec det sus rel clk lfor lfod
# arp tempo arpm porta drum hpf) — must match preset_factory in synth.asm
FACTORY = {
    0: dict(wave=1, volume=10, octave=2, sus=8, arp=0, porta_rate=0, hpf_cut=0),
    1: dict(wave=1, volume=12, octave=2, atk=6, sus=14, lfod=5, detune=6),
    2: dict(wave=0, volume=13, octave=3, porta_rate=6, hpf_cut=4, lfod=8),
    3: dict(wave=0, volume=12, detune=8, arp=9, tempo=10),
}


def _load_slot(s, slot):
    """Select a slot (guaranteeing a change so the live-load fires) and settle."""
    s.poke(PRESET, (slot + 1) & 3); s.frame(5)
    s.poke(PRESET, slot); s.frame(8)


def preset_param(s, rep):
    rep.section("presets: PRESET parameter (page 2)")
    rep.check("PRESET defaults to 0", s.get_param(17) == 0, s.get_param(17))
    s.set("curparam", 17); s.frame(8)
    rep.check("nav to PRESET -> page 2", s.get("page") == 2, s.get("page"))
    rep.check("PRESET label renders on page 2 (right col)", s.cell(21, 16) == s.glyph(0x30, inv=True), "no P")
    s.set("curparam", 0); s.frame(8)


def preset_load_recall(s, rep):
    """Selecting each slot loads its factory patch into the live params."""
    rep.section("presets: selecting a slot loads its patch")
    for slot, patch in FACTORY.items():
        _load_slot(s, slot)
        bad = {k: (s.get(k), v) for k, v in patch.items() if s.get(k) != v}
        rep.check(f"slot {slot} loads its patch", not bad,
                  "ok" if not bad else f"mismatch {bad}")
    s.poke(PRESET, 0)


def preset_factory_distinct(s, rep):
    """The 4 factory patches are genuinely different sounds."""
    rep.section("presets: factory patches are distinct")
    sigs = []
    for slot in range(4):
        _load_slot(s, slot)
        sigs.append(tuple(s.get_param(i) for i in range(NSAVE)))  # full 17-param patch
    rep.check("4 factory patches are distinct", len(set(sigs)) == 4,
              f"{len(set(sigs))} unique of 4")
    s.poke(PRESET, 0)


def preset_save_fire(s, rep):
    """FIRE while PRESET is selected saves the current sound into the slot;
    selecting another slot and back restores the saved values."""
    rep.section("presets: FIRE saves the current sound to the slot")
    _load_slot(s, 0)                       # start from a known patch on slot 0
    s.set("curparam", 17); s.frame(8)      # select PRESET (settle the page)
    # tweak a couple of params to a distinctive signature
    s.set("detune", 11); s.set("sus", 5); s.frame(2)
    s.joy(0, "centre", fire=True); s.frame(8); s.joy(0, "centre"); s.frame(3)
    saved_det = s.peek(BANK + 5)           # detune is param index 5
    rep.check("FIRE wrote the slot (detune=11 in bank)", saved_det == 11, f"bank detune={saved_det}")
    # clobber, switch away and back -> the saved values return
    s.set("detune", 0); s.set("sus", 15)
    s.poke(PRESET, 1); s.frame(6); s.poke(PRESET, 0); s.frame(8)
    rep.check("reloading the slot restores the saved sound",
              s.get("detune") == 11 and s.get("sus") == 5,
              f"detune={s.get('detune')} sus={s.get('sus')}")
    s.set("curparam", 0); s.poke(PRESET, 0); s.frame(6)


def preset_changes_sound(s, rep):
    """ACOUSTIC: different presets actually sound different (e.g. the LEAD patch
    with its high-pass + square wave vs the INIT pure tone)."""
    rep.section("presets: different presets sound different (PCM)")
    def hear(slot):
        _load_slot(s, slot)
        with s.held_key(0):
            clip = s.capture(f"preset_{slot}", 28)
        return dsp.spectral_features(clip)["flatness"]
    f_init = hear(0)    # PURE wave, no filter  -> very tonal (low flatness)
    f_lead = hear(2)    # SQUARE + HP filter    -> harmonically rich (higher flatness)
    rep.check("INIT (pure) and LEAD (square+HP) sound clearly different",
              f_lead - f_init > 0.05 and f_lead > 0.1,
              f"INIT flatness={f_init:.3f} LEAD flatness={f_lead:.3f}")
    # leave a clean state for later scenarios: load INIT (porta/hpf/etc = 0) and
    # let it actually apply
    _load_slot(s, 0)


SCENARIOS = [
    preset_param,
    preset_load_recall,
    preset_factory_distinct,
    preset_save_fire,
    preset_changes_sound,
]
