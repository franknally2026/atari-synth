"""Bridge-feature scenarios — exercise the AltirraBridge primitives the
framework now depends on.

  * AUDIO_STATE.freq_hz / period_cycles  (ilmenit/AltirraSDL#71)
  * Cooked KEY injection surviving JOY bursts  (ilmenit/AltirraSDL#72)

These are framework-level checks: the synth itself isn't really under
test here — we're asserting the bridge contract the rest of the
scenarios assume. Run early so a stale AltirraSDL surfaces with a clear
failure, not a confusing downstream one.
"""
from .. import notes
from ..harness import PH_SUSTAIN
from ..scenario import assert_engine_faithful_via_state


def _hold(s, idx, mode):
    """Hold voice 0 in SUSTAIN at chromatic index `idx` in clock `mode`."""
    s.set("clock15", mode); s.poke(0x0689, mode)
    s.set("wave", 1); s.set("volume", 12); s.set("sus", 14)
    s.set("lfod", 0); s.set("detune", 0); s.poke(0x06B6, 0)
    s.poke(0x0665, 0); s.poke(0x0668, 0)
    for i in range(4):
        s.set("vlevel", 0, i); s.set("vphase", 0, i)
    s.set("vnote", idx, 0); s.set("vlevel", 12, 0)
    s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
    s.frame(4)


def audio_state_schema(s, rep):
    """The AUDIO_STATE response has the fields the framework relies on.

    Fails loudly if the AltirraSDL build is pre-#71 — better than waiting
    for a downstream scenario to misbehave."""
    rep.section("bridge: AUDIO_STATE schema (#71)")
    st = s.audio_state()
    # top-level decode flags
    for k in ("audctl", "nine_bit_poly", "join_1_2", "join_3_4",
              "highpass_1_3", "highpass_2_4", "base_15khz", "channels"):
        rep.check(f"top-level has '{k}'", k in st, list(st.keys()))
    chans = st.get("channels", [])
    rep.check("channels has 4 entries", len(chans) == 4, len(chans))
    for i, ch in enumerate(chans, 1):
        for k in ("audf", "audc", "volume", "distortion", "clock",
                  "period_cycles", "freq_hz"):
            rep.check(f"ch{i} has '{k}'", k in ch, list(ch.keys()))


def audio_state_idle_silent(s, rep):
    """Every channel reports freq_hz=None when no voice is sounding
    (volume 0). Per #71 spec: freq_hz is None on muted/volume-only
    channels."""
    rep.section("bridge: AUDIO_STATE idle (#71)")
    s.reset_voices(); s.set("held", 0xFF); s.frame(4)
    st = s.audio_state()
    for i, ch in enumerate(st["channels"], 1):
        rep.check(f"ch{i} idle: volume == 0", ch["volume"] == 0, ch["volume"])
        rep.check(f"ch{i} idle: freq_hz is None", ch["freq_hz"] is None, ch["freq_hz"])


def audio_state_clock_labels(s, rep):
    """Per-channel ``clock`` label tracks AUDCTL: NORMAL -> 64kHz on all
    channels, 15 kHz mode -> 15kHz on the base-clocked channels."""
    rep.section("bridge: AUDIO_STATE per-channel clock label (#71)")
    with s.frozen("trigger_voices"):
        # NORMAL
        _hold(s, 24, notes.MODE_NORMAL)
        st = s.audio_state()
        # channel 1 is the audible one; its clock should be 64kHz
        c1 = st["channels"][0]["clock"]
        rep.check("NORMAL: ch1 clock is '64kHz'", c1 == "64kHz", c1)
        # 15 kHz
        _hold(s, 24, notes.MODE_15K)
        st = s.audio_state()
        c1 = st["channels"][0]["clock"]
        rep.check("15K: ch1 clock is '15kHz'", c1 == "15kHz", c1)
    s.set("clock15", 0); s.poke(0x0689, 0); s.frame(2)


def audio_state_faithful(s, rep):
    """Across the chromatic table, reported freq_hz matches the divider->Hz
    prediction to <1 cent in all three clock modes. This is a fast, audio-
    free engine-fidelity check that previously required PCM capture + FFT.
    The 16-BIT cases also pin the joined-pair fast-clock formula
    (period = n + 7) — the naive n + 1 form fails them by up to 30 cents."""
    rep.section("bridge: engine faithfulness via AUDIO_STATE (#71)")
    with s.frozen("trigger_voices"):
        # sample a few across each mode (sweeping all 65 takes a couple
        # of seconds; the assertion is exact, so a sparse sweep suffices)
        for mode_name, mode in [("NORMAL", notes.MODE_NORMAL),
                                ("15K",    notes.MODE_15K),
                                ("16BIT",  notes.MODE_16BIT)]:
            for idx in (0, 12, 24, 36, 48, 60, 64):
                _hold(s, idx, mode)
                assert_engine_faithful_via_state(
                    rep, s, f"{mode_name} idx{idx:>2}",
                    voice=0, idx=idx, mode=mode, tol_cents=1.0)
    s.set("clock15", 0); s.poke(0x0689, 0); s.frame(2)
    s.reset_voices()


def audio_state_freq_matches_division(s, rep):
    """Sanity: ``period_cycles`` is in **master PAL clock cycles** (Altirra
    implements POKEY as one chain in master ticks), so
    ``freq_hz * 2 * period_cycles ≈ master_pal_clock`` (~1.773 MHz) on
    every audible channel regardless of which base clock (64 kHz / 15 kHz
    / 1.79 MHz) the channel is tapped from. This is the
    independent-of-divider invariant — if it holds, the two fields aren't
    just both derived from ``audf``."""
    rep.section("bridge: freq_hz/period_cycles self-consistent (#71)")
    with s.frozen("trigger_voices"):
        for mode_name, mode in [("NORMAL", notes.MODE_NORMAL),
                                ("15K",    notes.MODE_15K),
                                ("16BIT",  notes.MODE_16BIT)]:
            _hold(s, 24, mode)
            st = s.audio_state()
            # audible channel: ch2 in 16-bit join, else ch1
            ch = st["channels"][1] if mode == notes.MODE_16BIT else st["channels"][0]
            recovered = ch["freq_hz"] * 2 * ch["period_cycles"]
            err = abs(recovered - notes.CLK_179) / notes.CLK_179
            rep.check(f"{mode_name}: freq_hz*2*period_cycles ≈ master PAL clock",
                      err < 0.001,
                      f"recovered={recovered:.0f} vs {notes.CLK_179:.0f} ({err*100:.2f}%, clock={ch['clock']})")
    s.set("clock15", 0); s.poke(0x0689, 0); s.frame(2)
    s.reset_voices()


def joy_burst_then_key_regression(s, rep):
    """ilmenit/AltirraSDL#72 regression: a long burst of cooked JOY
    commands must not break subsequent cooked KEY injection. Pre-fix,
    12+ consecutive JOY commands silently killed all later KEY input
    for the rest of the session. With #72 the framework no longer needs
    its 'KEY tests first, then JOY' ordering.

    This scenario picks the canonical repro from the issue text and a
    longer stress burst; both must allow KEY to register afterwards."""
    rep.section("bridge: JOY-burst-then-KEY (#72 regression)")
    for burst_n in (12, 50):
        s.reset_voices()
        s.set("clock15", 0); s.poke(0x0689, 0); s.frame(4); s.drain()
        # alternating direction/centre is the exact repro pattern from #72
        for i in range(burst_n):
            s.joy(0, "down" if i % 2 == 0 else "centre"); s.frame(2)
        s.joy(0, "centre"); s.frame(8); s.drain()
        # cooked KEY 'q' must still reach POKEY (note_idx = 0 = C4 absolute)
        got = s.play("q")
        ni = s.get("note_idx")
        ok = (got is True and ni == 0)
        rep.check(f"after {burst_n} JOYs: KEY 'q' registers (note_idx=0)",
                  ok, f"registered={got} note_idx={ni:#x}")
    s.reset_voices()


SCENARIOS = [
    audio_state_schema,
    audio_state_idle_silent,
    audio_state_clock_labels,
    audio_state_freq_matches_division,
    audio_state_faithful,
    joy_burst_then_key_regression,
]
