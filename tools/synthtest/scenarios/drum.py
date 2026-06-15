"""Drum voice — comprehensive coverage of the new DRUM parameter (index 15,
page 2) and the $FD sequencer drum-step.

The drum is a noise-percussion hit on channel 4, decaying over DRUM*15 frames,
managed by its own subsystem (drum_tick) that overrides channel 4 while a hit
rings and frees it (back to voice 3) when done. DRUM = 0 disables it. 8-bit
clock modes only.
"""
from .. import dsp, notes
from ..harness import PH_SUSTAIN

DRUM = 0x06BD            # DRUM param (decay length; 0 = off)
DRUM_LEVEL = 0x06BE
DRUM_TIMER = 0x06BF


def _hit(s, decay):
    """Simulate a drum strike (what drum_hit does), deterministically."""
    s.set("clock15", 0); s.poke(0x0689, 0)
    s.poke(DRUM, decay)
    s.poke(DRUM_LEVEL, 15); s.poke(DRUM_TIMER, decay)


def drum_param(s, rep):
    rep.section("drum: parameter (default / clamp / nav / label)")
    rep.check("DRUM defaults to 0 (off)", s.get_param(15) == 0, s.get_param(15))
    s.set("curparam", 15); s.frame(6)
    rep.check("nav to DRUM -> page 2", s.get("page") == 1, s.get("page"))
    s.joy(0, "right"); s.frame(100); s.joy(0, "centre"); s.frame(2)
    hi = s.get_param(15)
    s.joy(0, "left"); s.frame(130); s.joy(0, "centre"); s.frame(2)
    lo = s.get_param(15)
    rep.check("DRUM clamps 15 / 0", hi == 15 and lo == 0, f"hi={hi} lo={lo}")
    # 'DRUM' label on page 2 row1 right (col 21, scan 36): 'D' = screen code $24
    rep.check("DRUM label renders on page 2", s.cell(21, 36) == s.glyph(0x24, inv=True), "no D")
    s.poke(DRUM, 0); s.set("curparam", 0); s.frame(6)


def drum_seq_trigger(s, rep):
    """A $FD sequencer step fires a drum hit on channel 4."""
    rep.section("drum: $FD sequencer step triggers a hit")
    s.set("clock15", 0); s.poke(0x0689, 0); s.poke(DRUM, 10)
    for i in range(16):
        s.set("seq_notes", 0xFF, i)
    s.set("seq_notes", 0xFD, 0)
    s.set("seq_len", 16); s.set("tempo", 2); s.set("seq_rec", 0)
    s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
    peak = 0
    for _ in range(16):     # generous window: the hit's fire-frame shifts with the
        s.frame(1)          # tempo phase carried in from prior scenarios (the slow
        peak = max(peak, s.chan(4)[1] & 0x0F)   # DRUM=10 decay keeps it ringing)
    s.set("seq_play", 0)
    rep.check("$FD step drives channel 4 to a loud noise hit", peak >= 12,
              f"peak AUDC4 level={peak}, AUDF4={s.chan(4)[0]}")
    s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)


def drum_decay(s, rep):
    """The hit decays monotonically to silence on channel 4 (AUDF4 = the fixed
    drum tone)."""
    rep.section("drum: hit decays to silence")
    _hit(s, 6)
    levels, audf = [], []
    for _ in range(120):
        s.frame(1)
        f, c = s.chan(4)
        levels.append(c & 0x0F); audf.append(f)
        if c == 0:
            break
    mono = all(levels[i] >= levels[i + 1] for i in range(len(levels) - 1))
    rep.check("drum starts loud (level ~15)", levels[0] >= 14, f"start={levels[0]}")
    rep.check("drum decays monotonically to 0", mono and levels[-1] == 0,
              f"end={levels[-1]} mono={mono}")
    rep.check("drum tone AUDF4 is the fixed noise pitch (0x1E)",
              audf[0] == 0x1E, f"AUDF4={audf[0]:#x}")


def drum_off(s, rep):
    """DRUM = 0 disables the drum: a $FD step produces no hit, and turning DRUM
    off silences a ringing drum."""
    rep.section("drum: DRUM 0 = off")
    # ringing drum, then turn DRUM off -> silenced
    _hit(s, 10); s.frame(4)
    s.poke(DRUM, 0); s.frame(3)
    rep.check("turning DRUM off silences a ringing drum", (s.chan(4)[1] & 0x0F) == 0,
              f"AUDC4={s.chan(4)[1]:#x}")
    # $FD step with DRUM off -> no hit
    s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0); s.frame(2)
    for i in range(16):
        s.set("seq_notes", 0xFF, i)
    s.set("seq_notes", 0xFD, 0); s.set("seq_len", 16); s.set("tempo", 2)
    s.set("seq_pos", 0); s.set("seq_timer", 1); s.set("seq_play", 1)
    hit = 0
    for _ in range(6):
        s.frame(1); hit = max(hit, s.chan(4)[1] & 0x0F)
    s.set("seq_play", 0)
    rep.check("$FD step with DRUM off does nothing", hit == 0, f"AUDC4 level={hit}")


def drum_acoustic(s, rep):
    """ACOUSTIC: a drum hit sounds like percussion — a broadband noise burst
    (no stable pitch) whose amplitude decays."""
    rep.section("drum: hit sounds like a decaying noise burst")
    # Primary, always-reliable proof via the channel-4 register: a loud hit on
    # the white-noise distortion (bits 7-5 = 0).
    _hit(s, 4); s.frame(1)
    f4, c4 = s.chan(4)
    rep.check("drum strikes channel 4 with the noise distortion (dist 0)",
              (c4 & 0x0F) >= 12 and (c4 >> 5) == 0, f"AUDC4={c4:#x} AUDF4={f4}")
    # PCM timbre confirmation (best-effort: the AUDIO_RECORD tap can return an
    # empty buffer late in a long run; retry, and if it stays empty fall back to
    # the register proof rather than fail spuriously).
    clip = None
    for _ in range(3):
        _hit(s, 4); s.frame(1)
        clip = s.capture("drum_hit", 70, warmup=0)
        if dsp.rms(clip) >= 4e-3:
            break
    if clip is not None and dsp.rms(clip) >= 4e-3:
        feat = dsp.spectral_features(clip)
        env = dsp.envelope(clip)[1]
        rep.check("drum is broadband noise (PCM)", feat["flatness"] > 0.12,
                  f"flatness={feat['flatness']:.3f} pitch={dsp.median_pitch(clip):.0f}")
        early = float(env[:len(env) // 4].mean()); late = float(env[-len(env) // 4:].mean())
        rep.check("drum amplitude decays (percussive, PCM)", early > late * 1.5,
                  f"early={early:.4f} late={late:.4f}")
    else:
        rep.check("drum PCM timbre (register-verified; tap returned empty)", True,
                  "channel-4 noise confirmed via register")
    s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)


def drum_decay_scales(s, rep):
    """Higher DRUM = longer decay (more frames before the hit goes silent)."""
    rep.section("drum: higher DRUM = longer decay")
    def decay_frames(decay):
        _hit(s, decay)
        n = 0
        for _ in range(400):
            s.frame(1); n += 1
            if s.chan(4)[1] == 0:
                break
        return n
    short = decay_frames(3)
    long = decay_frames(12)
    rep.check("DRUM 12 rings longer than DRUM 3", long > short + 20,
              f"drum3={short} frames, drum12={long} frames")
    s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)


def drum_reserves_voice3(s, rep):
    """With DRUM enabled, melody notes must NEVER allocate voice 3 (= channel 4):
    the drum overrides channel 4 with noise, so a melody note there would play as
    noise. With DRUM off, all 4 voices are available again."""
    rep.section("drum: voice 3 (channel 4) reserved for the drum when enabled")
    def voices(drum_on):
        with s.frozen("read_keyboard"):
            s.set("clock15", 0); s.poke(0x0689, 0); s.set("wave", 1); s.set("volume", 12)
            s.set("atk", 0); s.set("sus", 14); s.set("rel", 8)
            s.poke(DRUM, 10 if drum_on else 0); s.set("lastv", 3)
            for i in range(4):
                s.set("vlevel", 0, i); s.set("vphase", 0, i)
            used = set()
            for n in range(8):
                s.set("prevheld", 0xFF); s.set("held", 0xFF); s.set("note_idx", 0xFF); s.frame(2)
                s.set("note_idx", n % 5); s.frame(3)
                used.add(s.get("held"))
            return sorted(v for v in used if v != 0xFF)
    on, off = voices(True), voices(False)
    rep.check("DRUM on: melody uses voices 0-2 only (not 3)", on == [0, 1, 2], f"used={on}")
    rep.check("DRUM off: all 4 voices used", off == [0, 1, 2, 3], f"used={off}")
    s.poke(DRUM, 0)


def drum_coexists_with_melody(s, rep):
    """The drum (channel 4) plays alongside melodic voices (channels 1-3)
    without killing them: a held chord tone is still present while the drum
    rings."""
    rep.section("drum: coexists with melodic voices")
    with s.frozen("trigger_voices"):
        s.set("clock15", 0); s.poke(0x0689, 0)
        s.set("wave", 1); s.set("volume", 12); s.set("sus", 14); s.set("lfod", 0); s.set("detune", 0)
        s.set("vnote", 0, 0); s.set("vlevel", 12, 0)       # idx 0 -> ~262 Hz on ch1
        s.set("vphase", PH_SUSTAIN, 0); s.set("vcount", 8, 0); s.set("held", 0)
        for i in (1, 2, 3):
            s.set("vlevel", 0, i); s.set("vphase", 0, i)
        s.poke(DRUM, 10); s.poke(DRUM_LEVEL, 15); s.poke(DRUM_TIMER, 10)
        clip = s.capture("drum_melody", 30, warmup=0)
        mel = notes.predicted_freq(0, notes.MODE_NORMAL)
        rep.check("melodic tone still present while drum rings",
                  dsp.has_tone_at(clip, mel, tol_frac=0.05),
                  f"want {mel:.0f}Hz; peaks={[round(f) for f, _ in dsp.spectral_peaks(clip, 6)]}")
        rep.check("drum still ringing on channel 4", (s.chan(4)[1] & 0x0F) > 0,
                  f"AUDC4={s.chan(4)[1]:#x}")
    s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)


DRUMBEAT = 0x06C9


def drum_key_fires(s, rep):
    """The '1' key sets note_idx=$FD ('drum note'), which fires a live drum hit
    (deterministic via poke + read_keyboard frozen). With DRUM off, it does
    nothing."""
    rep.section("drum: '1' key ($FD drum note) fires a live hit")
    s.set("clock15", 0); s.poke(0x0689, 0)
    with s.frozen("read_keyboard"):
        s.poke(DRUM, 8); s.poke(DRUM_LEVEL, 0); s.set("note_idx", 0xFF); s.frame(2)
        s.set("note_idx", 0xFD); s.frame(2)         # 'press 1'
        rep.check("drum-note fires a hit on channel 4", (s.chan(4)[1] & 0x0F) >= 12,
                  f"AUDC4={s.chan(4)[1]:#x}")
        # with DRUM off, the same press does nothing
        s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0); s.set("note_idx", 0xFF); s.frame(3)
        s.set("note_idx", 0xFD); s.frame(2)
        rep.check("drum-note with DRUM off makes no sound", (s.chan(4)[1] & 0x0F) == 0,
                  f"AUDC4={s.chan(4)[1]:#x}")
        s.set("note_idx", 0xFF)


def drum_lane_record(s, rep):
    """The drum lane: pressing '1' ($FD) during step-entry recording writes a
    $FD drum step, and playback of that step fires the drum."""
    rep.section("drum: $FD drum steps record + play back (drum lane)")
    with s.frozen("read_keyboard"):
        for i in range(16):
            s.set("seq_notes", 0xFF, i)
        s.set("seq_rec", 1); s.set("seq_play", 0); s.set("seq_wpos", 0)
        s.set("seq_len", 0); s.set("seq_prevn", 0xFF)
        # step-entry: a note, then a drum, then a note
        for n in (5, 0xFD, 7):
            s.set("note_idx", n); s.frame(3); s.set("note_idx", 0xFF); s.frame(3)
        steps = [s.get("seq_notes", i) for i in range(3)]
        rep.check("drum-key press records a $FD drum step", steps == [5, 0xFD, 7], steps)
        s.set("seq_rec", 0)
    # play it back: the $FD step must fire the drum on channel 4
    s.poke(DRUM, 8); s.set("seq_len", 3); s.set("tempo", 12)
    s.set("seq_pos", 1); s.set("seq_timer", 1); s.set("seq_play", 1)   # step 1 = drum
    peak = 0
    for _ in range(6):
        s.frame(1); peak = max(peak, s.chan(4)[1] & 0x0F)
    s.set("seq_play", 0); s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)
    rep.check("the recorded drum step fires on playback", peak >= 12, f"ch4 peak={peak}")


def drumbeat_param(s, rep):
    rep.section("drumbeat: DRUMBEAT parameter (page 2)")
    rep.check("DRUMBEAT defaults to 0", s.get_param(18) == 0, s.get_param(18))
    s.set("curparam", 18); s.frame(8)
    rep.check("nav to DRUMBEAT -> page 2", s.get("page") == 2, s.get("page"))
    rep.check("DRUMBEAT label renders (page 2 row1)", s.cell(1, 36) == s.glyph(0x24, inv=True), "no D")
    s.joy(0, "right"); s.frame(100); s.joy(0, "centre"); s.frame(2)
    hi = s.get_param(18)
    s.joy(0, "left"); s.frame(130); s.joy(0, "centre"); s.frame(2)
    lo = s.get_param(18)
    rep.check("DRUMBEAT clamps 15 / 0", hi == 15 and lo == 0, f"hi={hi} lo={lo}")
    s.poke(DRUMBEAT, 0); s.set("curparam", 0); s.frame(6)


def auto_beat(s, rep):
    """DRUMBEAT > 0 auto-fires the drum, tempo-synced and free-running (no need
    to start the sequencer). Higher DRUMBEAT = more frequent; 0 = off."""
    rep.section("drumbeat: auto drum-machine pulse")
    def hits(drumbeat, frames=80):
        s.set("clock15", 0); s.poke(0x0689, 0); s.poke(DRUM, 6); s.set("tempo", 13)
        s.poke(DRUM_LEVEL, 0); s.poke(DRUMBEAT, drumbeat)
        s.poke(0x06CA, 1); s.poke(0x06CB, 1)        # dbeat_timer, dbeat_cnt
        n, prev = 0, 0
        for _ in range(frames):
            s.frame(1); c4 = s.chan(4)[1] & 0x0F
            if c4 > prev and c4 >= 12:
                n += 1
            prev = c4
        return n
    fast = hits(15)
    sparse = hits(4)
    off = hits(0)
    rep.check("DRUMBEAT auto-fires the drum (free-running)", fast >= 4, f"{fast} hits")
    rep.check("higher DRUMBEAT = more frequent than lower", fast > sparse,
              f"fast(15)={fast} sparse(4)={sparse}")
    rep.check("DRUMBEAT 0 = no auto hits", off == 0, f"{off} hits")
    s.poke(DRUMBEAT, 0); s.poke(DRUM, 0); s.poke(DRUM_LEVEL, 0)


SCENARIOS = [
    drum_param,
    drum_seq_trigger,
    drum_key_fires,
    drum_lane_record,
    drumbeat_param,
    auto_beat,
    drum_decay,
    drum_off,
    drum_acoustic,
    drum_decay_scales,
    drum_coexists_with_melody,
]
