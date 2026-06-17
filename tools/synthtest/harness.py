"""Synth — the reusable AltirraBridge test harness for atari-synth.

Wraps the lifecycle (launch headless AltirraSDL, boot synth.xex, tear down),
the low-level pokes/peeks, and the synth-specific helpers that every test
needs: voice reset, cooked-key play, the "freeze a routine with RTS" trick,
register/level timeline capture, and — new — PCM audio recording via the
AUDIO_RECORD bridge command for true acoustic analysis.

Scenarios talk to a Synth instance; they never touch the raw bridge client.
Work-variable addresses live in VARS (named, single source of truth) and label
addresses resolve from synth.lst so tests survive code shifts.
"""
import os
import re
import sys
import time
import subprocess
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_SYNTH = os.path.abspath(os.path.join(HERE, "..", ".."))
ALTIRRA = os.path.expanduser("~/AltirraSDL")
SDK = os.path.join(ALTIRRA, "src/AltirraSDL/AltirraBridge/sdk/python")
EMU = os.path.join(ALTIRRA, "build/linux-release/src/AltirraSDL/AltirraSDL")
ASM = os.path.join(REPO_SYNTH, "synth.asm")
# Tests boot a DEDICATED test binary, never the shipping synth.xex. The shipping
# build keeps the keyboard IRQ OFF (fixes real-hw bugs #2/#3), but AltirraSDL's
# cooked-key bridge only delivers injected keys while the keyboard IRQ is enabled
# (ATPokeyEmulator::CanPushKey tests mIRQST & mIRQEN & $40). So we assemble a
# parallel binary with -d:EMU_KBD_IRQ=1 here and boot that. Code layout is byte-
# identical to the shipping build except one immediate operand, but we emit a
# matching listing too so label addresses are always in sync with the booted code.
XEX = os.path.join(REPO_SYNTH, "synth_emu.xex")
LST = os.path.join(REPO_SYNTH, "synth_emu.lst")
SHOTS = os.path.join(REPO_SYNTH, "shots")
AUDIO_DIR = os.path.join(SHOTS, "audio")

sys.path.insert(0, SDK)
from altirra_bridge import AltirraBridge  # noqa: E402

from . import dsp  # noqa: E402

# ---------------------------------------------------------------------------
# Named work variables (must match synth.asm). Single source of truth.
# ---------------------------------------------------------------------------
VARS = {
    "curparam": 0x0600, "wave": 0x0601, "volume": 0x0602, "octave": 0x0603,
    "clock15": 0x0604, "note_idx": 0x0607,
    "vnote": 0x0610, "vlevel": 0x0614, "held": 0x0618, "lastv": 0x0619,
    "prevheld": 0x061E, "vphase": 0x0620, "vcount": 0x0624,
    "atk": 0x062C, "dec": 0x062D, "sus": 0x062E, "rel": 0x062F,
    "lfor": 0x0663, "lfod": 0x0664, "detune": 0x066E,
    "arp": 0x0684, "arp_step": 0x0685, "arp_timer": 0x0686, "arp_mode": 0x06B5,
    "porta_rate": 0x06B6, "drum_dec": 0x06BD, "hpf_cut": 0x06C0,
    "preset": 0x06C5, "drum_beat": 0x06C9, "sustain_ped": 0x0687,
    "clock_mode": 0x0689, "prev_clkm": 0x0689,
    "tempo": 0x068C, "page": 0x068D,
    "seq_notes": 0x0691, "seq_play": 0x06A1, "seq_rec": 0x06A2,
    "seq_pos": 0x06A3, "seq_wpos": 0x06A4, "seq_timer": 0x06A5,
    "seq_prevn": 0x06A6, "seq_len": 0x06B3,
}

# Panel parameter index -> work-variable name (index order == visual order).
# NEW LAYOUT (2026-06-15): screen 1 VOICE 0-11, screen 2 FX/PATCH 12-15,
# screen 3 SEQUENCER/RHYTHM 16-18 (+ step grid). See synth.asm param tables.
PARAM_VARS = ["wave", "volume", "octave", "clock15", "lfor", "lfod",
              "atk", "dec", "sus", "rel", "arp", "arp_mode",
              "detune", "hpf_cut", "porta_rate", "preset",
              "tempo", "drum_dec", "drum_beat"]

# Envelope phases (jump-table order in update_sound)
PH_IDLE, PH_ATTACK, PH_DECAY, PH_SUSTAIN, PH_RELEASE = 0, 1, 2, 3, 4

# Framebuffer geometry (GR.8 split bitmap)
FB1, FB2 = 0x4000, 0x5000


class HarnessError(RuntimeError):
    pass


_test_xex_built = False


def _build_test_xex(force=False):
    """Assemble the test-only binary (XEX + matching listing) with the keyboard
    IRQ enabled, so AltirraSDL's cooked-key bridge can type. Built once per run."""
    global _test_xex_built
    if _test_xex_built and not force:
        return
    r = subprocess.run(
        ["mads", ASM, "-d:EMU_KBD_IRQ=1", f"-o:{XEX}", f"-l:{LST}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if r.returncode != 0:
        raise HarnessError(
            "failed to assemble the EMU_KBD_IRQ=1 test binary:\n"
            + r.stdout.decode(errors="replace"))
    _test_xex_built = True


class Synth:
    """A booted synth.xex under headless AltirraSDL, with helpers."""

    def __init__(self, audio=True):
        self.proc = None
        self.token = None
        self.a = None
        self.audio_supported = None   # learned on first record attempt
        self._recording = False
        os.makedirs(SHOTS, exist_ok=True)
        os.makedirs(AUDIO_DIR, exist_ok=True)

    # -- lifecycle ----------------------------------------------------------
    def __enter__(self):
        self.launch()
        self.boot()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def launch(self):
        log = open(os.path.join(SHOTS, "emu.log"), "w")
        self.proc = subprocess.Popen([EMU, "--bridge", "--headless"],
                                     stdout=log, stderr=subprocess.STDOUT)
        logpath = os.path.join(SHOTS, "emu.log")
        token = None
        for _ in range(200):
            try:
                m = re.search(r'token-file:\s*(\S+)', open(logpath).read())
                if m:
                    token = m.group(1)
                    break
            except FileNotFoundError:
                pass
            time.sleep(0.05)
        if not token:
            self.proc.kill()
            raise HarnessError("bridge token-file not seen; see shots/emu.log")
        for _ in range(40):
            if os.path.exists(token):
                break
            time.sleep(0.05)
        self.token = token
        self.a = AltirraBridge.from_token_file(token)

    def boot(self, settle=300):
        _build_test_xex()
        self.a.boot(XEX)
        self.a.frame(settle)
        self._probe_capabilities()

    def _probe_capabilities(self):
        """Fail fast if the AltirraSDL build predates the bridge fixes we now
        depend on (ilmenit/AltirraSDL#71 freq_hz, #72 JOY-then-KEY).

        Run once at boot so a stale binary surfaces here, not as confusing
        scenario failures later."""
        try:
            st = self.a.audio_state()
        except AttributeError as e:
            raise HarnessError(
                "Bridge SDK lacks audio_state() — update the AltirraBridge SDK "
                "to a build that includes #71"
            ) from e
        if "channels" not in st or not st["channels"] or "freq_hz" not in st["channels"][0]:
            raise HarnessError(
                "AltirraSDL build lacks AUDIO_STATE.freq_hz — rebuild from "
                "ilmenit/AltirraSDL commit 31bf4d9a (PR #74) or later"
            )

    def close(self):
        if self._recording:
            with contextlib.suppress(Exception):
                self.a._cmd_ok("AUDIO_RECORD stop")
        with contextlib.suppress(Exception):
            self.a.frame(1)
        if self.proc:
            self.proc.kill()      # headless AltirraSDL ignores SIGTERM
            with contextlib.suppress(Exception):
                self.proc.wait(timeout=5)

    # -- primitives ---------------------------------------------------------
    def frame(self, n=1):
        self.a.frame(n)

    def peek(self, addr, n=1):
        if n == 1:
            return self.a.peek(addr)[0]
        return list(self.a.peek(addr, n))

    def poke(self, addr, val):
        self.a.poke(addr, val)

    def screenshot(self, name):
        self.a.screenshot(os.path.join(SHOTS, name))

    def key(self, name):
        self.a.key(name)

    def joy(self, port, direction, fire=False):
        self.a.joy(port, direction, fire=fire)

    def consol(self, **kw):
        self.a.consol(**kw)

    # named work variables -------------------------------------------------
    def get(self, name, index=0):
        """Read a named work variable (optionally indexed for per-voice vars)."""
        return self.peek(VARS[name] + index)

    def set(self, name, value, index=0):
        self.poke(VARS[name] + index, value)

    def get_param(self, pidx):
        """Read a panel parameter's value by its index (0..12)."""
        return self.get(PARAM_VARS[pidx])

    # label resolution -----------------------------------------------------
    @staticmethod
    def label_addr(name, _cache={}):
        if name in _cache:
            return _cache[name]
        pat = re.compile(r'^\s*\d+\s+([0-9A-Fa-f]{4})\s+' + re.escape(name) + r'\s*$')
        with open(LST) as f:
            for line in f:
                m = pat.match(line)
                if m:
                    _cache[name] = int(m.group(1), 16)
                    return _cache[name]
        raise KeyError(f"label {name!r} not found in {LST}")

    # POKEY register state -------------------------------------------------
    @staticmethod
    def _h(s):
        return int(str(s).lstrip("$"), 16)

    def pokey(self):
        p = self.a.pokey()
        return {k: self._h(v) if isinstance(v, str) and "$" in str(v) else v
                for k, v in p.items()}

    def chan(self, n):
        """(AUDFn, AUDCn) for channel n (1..4)."""
        p = self.a.pokey()
        return self._h(p[f"AUDF{n}"]), self._h(p[f"AUDC{n}"])

    def audctl(self):
        return self._h(self.a.pokey()["AUDCTL"])

    def nactive(self):
        p = self.a.pokey()
        return sum(1 for n in (1, 2, 3, 4) if self._h(p[f"AUDC{n}"]))

    def audio_state(self):
        """Decoded POKEY per-channel state with the audible output frequency
        the emulator is actually emitting (ilmenit/AltirraSDL#71). Returns:

          {
            "audctl": int,
            "nine_bit_poly", "join_1_2", "join_3_4",
            "highpass_1_3", "highpass_2_4", "base_15khz": bool,
            "channels": [
              {"audf", "audc", "volume", "distortion", "clock",
               "period_cycles", "freq_hz"}, ... x4
            ]
          }

        ``freq_hz`` is ``None`` on idle / muted channels and on the
        low-side of a joined 16-bit pair (the audible Hz is reported on
        the high channel of the pair: ch2 for 1+2, ch4 for 3+4)."""
        return self.a.audio_state()

    def channel_freq_hz(self, voice):
        """Reported audible Hz for the voice running on POKEY channel
        ``voice+1`` (1..4). Joins are handled: a 16-bit pair reports on
        the high channel, so a voice rendered into the pair returns the
        audible side."""
        st = self.audio_state()
        ch = st["channels"]
        n = voice + 1   # 1..4
        # joined 16-bit pair: audible Hz on high channel
        if st.get("join_1_2") and n == 1:
            return ch[1]["freq_hz"]
        if st.get("join_3_4") and n == 3:
            return ch[3]["freq_hz"]
        return ch[n - 1]["freq_hz"]

    # -- synth-specific helpers --------------------------------------------
    def reset_voices(self, volume=10):
        """Deterministic start: set a snappy envelope, idle all voices, next
        onset -> voice 0."""
        self.set("volume", volume); self.set("clock15", 0)
        self.set("atk", 0); self.set("dec", 2); self.set("sus", 8); self.set("rel", 3)
        self.set("lastv", 3); self.set("held", 0xFF); self.set("prevheld", 0xFF)
        for i in range(4):
            self.set("vlevel", 0, i); self.set("vphase", 0, i)
        # clear the LFO triangle so a deep-LFO scenario can't leak a residual
        # pitch offset into a later test (lfod alone decays it only slowly)
        self.poke(0x0665, 0); self.poke(0x0668, 0)   # lfo_level_u, lfo_offset
        self.frame(2)

    def drain(self, limit=80, need=10):
        """Step frames until the cooked-key queue is empty (note_idx stable $FF)."""
        quiet = 0
        for _ in range(limit):
            self.frame(1)
            quiet = quiet + 1 if self.get("note_idx") == 0xFF else 0
            if quiet >= need:
                return

    def play(self, keyname, scan=60):
        """Press a cooked key and scan for the key-down frame. Returns True if
        the note registered, else None. Always drain() first."""
        self.drain()
        self.key(keyname)
        for _ in range(scan):
            self.frame(1)
            if self.get("note_idx") != 0xFF:
                return True
        return None

    @contextlib.contextmanager
    def frozen(self, label):
        """Patch a routine's entry with $60 (RTS) to freeze it, restore the
        original LDA-abs opcode ($AD) on exit. The canonical way to hold a
        voice / held note while driving the state machine by hand, since the
        cooked bridge KEY can't sustain a key."""
        addr = self.label_addr(label)
        orig = self.peek(addr)
        self.poke(addr, 0x60)
        try:
            yield
        finally:
            self.poke(addr, orig)

    def hold_voice(self, voice=0, note=24, level=10, phase=PH_SUSTAIN, count=8):
        """Set one voice to a steady sounding state (used inside frozen())."""
        self.set("vnote", note, voice)
        self.set("vlevel", level, voice)
        self.set("vphase", phase, voice)
        self.set("vcount", count, voice)
        self.set("held", voice)

    @contextlib.contextmanager
    def held_key(self, semitone):
        """Hold a note through the REAL trigger path: freeze read_keyboard so
        note_idx stays put, then set it. trigger_voices (running) allocates a
        voice using octave_base[octave]+semitone, so this exercises the octave
        knob / arp / engine exactly as a live key would — and the note sustains
        for capture. Yields, then releases on exit.

        Defensively clears transport/arp/gate state so a fresh note always
        triggers regardless of what a previous scenario left behind (the
        sequencer gate and arp both suppress trigger_voices)."""
        self.set("seq_play", 0); self.set("seq_rec", 0); self.set("arp", 0)
        self.set("prevheld", 0xFF); self.set("held", 0xFF)
        with self.frozen("read_keyboard"):
            self.set("note_idx", 0xFF); self.frame(2)
            self.set("note_idx", semitone); self.frame(10)  # trigger -> sustain
            try:
                yield
            finally:
                self.set("note_idx", 0xFF)
        self.frame(2)

    def step_seq(self, pattern, tempo=10, frames=None):
        """Load a 16-step pattern (semitones, 0xFF rest, 0xFE tie), start the
        clock from step 0, and return after `frames` (default: 2 loops)."""
        for i in range(16):
            self.set("seq_notes", pattern[i] if i < len(pattern) else 0xFF, i)
        self.set("seq_len", len([p for p in pattern]) if pattern else 0)
        self.set("tempo", tempo); self.set("seq_rec", 0)
        self.set("seq_pos", 0); self.set("seq_timer", 1); self.set("seq_play", 1)

    # -- audio recording ----------------------------------------------------
    def _audio_cmd(self, args):
        return self.a._cmd_ok("AUDIO_RECORD " + args)

    def audio_available(self):
        """Probe once whether the build supports AUDIO_RECORD."""
        if self.audio_supported is None:
            try:
                self._audio_cmd("status")
                self.audio_supported = True
            except Exception:
                self.audio_supported = False
        return self.audio_supported

    @contextlib.contextmanager
    def recording(self, name):
        """Record PCM to shots/audio/<name>.wav for the duration of the block.
        Frames stepped inside the block are captured. Yields the wav path."""
        path = os.path.join(AUDIO_DIR, name if name.endswith(".wav") else name + ".wav")
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)
        self._audio_cmd(f"start path={path}")
        self._recording = True
        try:
            yield path
        finally:
            self._audio_cmd("stop")
            self._recording = False

    def capture(self, name, frames, warmup=2):
        """Record `frames` worth of audio and return a dsp.Clip. warmup frames
        run before recording so the tap is attached and steady.

        The AUDIO_RECORD tap occasionally returns a truncated/empty WAV late in
        a long run; a WAV far shorter than the requested window is always a tap
        glitch (never legitimate silence, which still yields full-length ~0
        samples), so re-record automatically rather than hand a bogus clip to
        the caller."""
        want = int(frames * 44100 / 50 * 0.5)   # >=50% of expected samples
        clip = None
        for _ in range(3):
            if warmup:
                self.frame(warmup)
            with self.recording(name) as path:
                self.frame(frames)
            self.frame(1)                        # let the writer flush
            clip = dsp.load_wav(path)
            if clip.n >= want:
                break
        return clip

    # -- framebuffer inspection (GR.8 split bitmap) ------------------------
    @staticmethod
    def fb_addr(x, y):
        base = FB1 + y * 40 if y < 102 else FB2 + (y - 102) * 40
        return base + (x >> 3)

    def glyph(self, code, inv=False):
        """The ROM font's 8-byte glyph for a screen code. inv=True returns the
        inverse-video form (each byte EOR $FF) — used for the focused param's
        label, which is drawn in inverse video (the selection highlight)."""
        g = list(self.a.peek(0xE000 + code * 8, 8))
        return [b ^ 0xFF for b in g] if inv else g

    def cell(self, col, scan):
        """The 8 vertical bytes of a glyph cell at char column `col`, scanline `scan`."""
        return [self.peek(self.fb_addr(col * 8, scan + i)) for i in range(8)]

    def px(self, x, y):
        """A single framebuffer pixel (0/1)."""
        base = FB1 + y * 40 if y < 102 else FB2 + (y - 102) * 40
        return (self.peek(base + x // 8) >> (7 - (x % 8))) & 1

    # -- register / level timeline -----------------------------------------
    def timeline(self, frames, voices=(0, 1, 2, 3), extra=None):
        """Step `frames` frames, sampling POKEY + per-voice levels each frame.
        Returns a Timeline (see scenario.py). `extra` is an optional list of
        work-variable names to also sample per frame."""
        from .scenario import Timeline
        rows = []
        extra = extra or []
        for _ in range(frames):
            self.frame(1)
            p = self.a.pokey()
            row = {
                "audf": [self._h(p[f"AUDF{n}"]) for n in (1, 2, 3, 4)],
                "audc": [self._h(p[f"AUDC{n}"]) for n in (1, 2, 3, 4)],
                "audctl": self._h(p["AUDCTL"]),
                "level": [self.get("vlevel", v) for v in voices],
                "phase": [self.get("vphase", v) for v in voices],
            }
            for name in extra:
                row[name] = self.get(name)
            rows.append(row)
        return Timeline(rows, voices)
