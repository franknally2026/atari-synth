# Testing — atari-synth

Everything in this project is verified automatically, without real hardware and
without a human listener. This document describes **what** is tested, **how**
each layer works, **what tooling is available**, and how to extend it.

---

## The big picture

There are three verification layers, run in this order:

| Layer | Tool | When | Needs emulator? | Checks |
|---|---|---|---|---|
| 1. Memory-map sanity | `tools/memcheck.py` | every build (wired into `build.sh`) | no | the binary can't corrupt itself at runtime |
| 2. Behavioural harness (legacy) | `tools/verify_synth.py` | on demand | yes (headless) | 103 register/RAM/UI checks across 26 sections |
| 3. Acoustic + timeline framework | `tools/synthtest/` | on demand / before commit | yes (headless) | ~110 scenarios: real PCM sound analysis + frame-by-frame trajectories |

Plus one utility:

* `tools/shot.py` — boots `synth.xex` headless and writes a single screenshot
  (`tools/shot.py [out.png]`, default `shots/gr8_test.png`). Handy for a quick
  visual look at the UI without running any tests.

All emulator-based layers drive **AltirraSDL** headless over **AltirraBridge**
(JSON-IPC): they launch `AltirraSDL --bridge --headless`, read the bridge token
file from the emulator log, boot `synth.xex`, then poke/peek RAM, inject input,
step frames, take screenshots and record audio. No window ever opens; everything
works in CI.

### Prerequisites

* `mads` on PATH (to build `synth.xex` + `synth.lst`).
* The AltirraSDL fork built at `~/AltirraSDL/build/linux-release/` with the
  bridge enabled. The Python SDK is used straight from the repo
  (`~/AltirraSDL/src/AltirraSDL/AltirraBridge/sdk/python`); nothing to install.
* Python 3 with `numpy` (the DSP layer; `scipy` not required).
* For the acoustic scenarios: an AltirraSDL build that includes the
  `AUDIO_RECORD` bridge command (see "The emulator side" below). Without it the
  framework still runs — PCM scenarios are *skipped and reported*, not failed.
* Always build first: `./build.sh` (the tests resolve label addresses from
  `synth.lst`, so it must match `synth.xex`).

### Quick reference — running everything

```sh
./build.sh                                 # assemble + memcheck (layer 1)
python3 tools/verify_synth.py              # layer 2: 103 legacy checks
python3 -m tools.synthtest.run             # layer 3: all scenarios
python3 -m tools.synthtest.run acoustic    # only groups matching "acoustic"
python3 -m tools.synthtest.run --no-audio  # skip PCM capture (timeline only)
tools/shot.py                              # one screenshot of the booted UI
```

All test entry points exit non-zero on any failure (CI-friendly). Outputs land
in `shots/` (screenshots, `emu.log`) and `shots/audio/` (captured WAVs) — both
gitignored.

---

## Layer 1 — `tools/memcheck.py` (build-time memory-map sanity)

Runs inside `build.sh` after assembly; **fails the build** on any problem. It
needs no emulator: it parses the load segments out of `synth.xex` and the
label/EQU addresses out of `synth.lst`, so it tracks the build automatically.

It exists because this class of bug bit the project more than once (growing
descriptor tables silently clobbered the parameter tables via the `linetab`
scratch area and froze the synth). It checks:

1. **No loaded segment sits inside a runtime-write region** — the regions the
   program overwrites after load: the 8 KB framebuffer (`clear_fb` zeroes
   `FB1..FB1+$1FFF`) and the two 192-byte `linetab_lo/hi` tables.
2. **Runtime-write regions don't overlap each other.**
3. **Loaded XEX segments don't overlap each other.**
4. **The ANTIC display list stays within one 1 KB block** (ANTIC's DL counter
   is 10-bit; crossing the boundary wraps it and corrupts the screen).
5. **Packed RAM variables don't overrun their neighbours** in zero page /
   page 6 — multi-byte arrays (`voice_*[4]`, `seq_notes[16]`,
   `prev_disp[NPARAM]`, ZP pointers…) are checked against the next symbol.
   When you add a new array, add its size to the `SIZES` dict in `memcheck.py`.

It always prints the resulting memory map (loaded ranges, runtime regions,
dlist block) so you can eyeball the layout even on success.

---

## Layer 2 — `tools/verify_synth.py` (legacy behavioural harness)

The original single-file harness: boots the synth once and runs **26 numbered
sections / 103 checks**, printing `PASS`/`FAIL` per check and exiting non-zero
on any failure. It reads POKEY's *write-register state* via the bridge's
`pokey()` snapshot and the program's own work variables in RAM, and inspects
the GR.8 framebuffer for UI checks. Screenshots of each stage land in `shots/`.

Coverage (section numbers as printed):

| # | What |
|---|---|
| 1 | boot defaults (curparam/wave/volume/octave/note) + true silence at rest |
| 2 | cooked-key notes → correct AUDF/AUDC on the allocated channel; note-name glyph renders |
| 3–5 | joystick param navigation; VOLUME adjust + clamp 0..15 |
| 6–7 | WAVEFORM cycling; CLOCK 3-mode → AUDCTL `$00`/`$01`/`$78` + clamp |
| 8 | round-robin voice allocation incl. wrap (5th note → voice 0) |
| 9 | 4 voices on 4 channels simultaneously (true polyphony at the register level) |
| 10, 12–14 | ADSR: onset enters ATTACK from 0; attack→peak→sustain hold; release monotonic to idle; release rate law |
| 11 | ADSR param adjust + clamp via joystick (table-driven) |
| 15 | GR.8 UI plumbing: SDLSTL→dlist, dlist within 1 KB, SDMCTL, colours, linetab 4K split, keyboard/title pixels, dynamic redraw of value cell + knob pointer |
| 16 | WAVEFORM selector box + CLOCK toggle glyphs track state |
| 17–18 | LFO clamp + AUDF vibrato wobble; DETUNE clamp + per-voice spread `+0/+3/+6/+9` |
| 19 | octave sign/digit text rendering (`+2`, `-2`, ` 0`) |
| 20 | arpeggiator clamp + chord cycling 24/28/31/36 |
| 21 | OPTION console key = sustain pedal |
| 22 | 16-bit mode register layout (joined pair `$3C/$0D`, output on the high channel, AUDCTL `$78`) |
| 23 | 2-page panel switch + label redraw |
| 24 | step sequencer: transport, playback, audibility, record, write head + arrow, step entry, loop length, wrap |
| 25 | per-voice VU meters track envelope levels pixel-exactly |
| 26 | real-time recording: lead-in, held note → one strike + ties, rests preserved, playback pitch fidelity, tie sustains without re-attack |

**Status:** kept green, but new feature tests go into `tools/synthtest/`
(layer 3), which migrated these checks onto a reusable framework and added the
two things this file can't do: whole-trajectory assertions and real audio
analysis. Note this harness predates the 3-page UI reorg (and the
GLIDE/RHYTHM/ARPEGGIO renames): it drives the engine by RAM address and console
input, so it stays valid, but its "2-page panel switch" check (section 23)
reflects the older 2-page layout — the authoritative page/param-order coverage
now lives in layer 3's `core.py` and the per-feature modules.

---

## Layer 3 — `tools/synthtest/` (acoustic + timeline framework)

The main test framework. Born from a bug the register peeks missed: a
sequencer step *looked* fine (AUDF/AUDC correct at the sampled instant) but the
envelope collapsed to near-silence one frame after attack. The framework
therefore verifies the synth **by what it sounds like and by its whole
trajectory**, not by single-instant register snapshots.

### Two verification modes

1. **Acoustic (PCM + DSP).** The `AUDIO_RECORD` bridge command taps POKEY's
   mixed output into a 44.1 kHz mono 16-bit WAV — works headless. The DSP layer
   then measures: fundamental pitch (Hz, sub-sample autocorrelation), framewise
   pitch tracks, spectra and timbre descriptors, RMS/ADSR envelopes, vibrato
   rate/depth, detune beat frequency, note onsets/rhythm, and true silence.
   This is the only way to verify things registers cannot express — e.g. the
   real output frequency in 16-bit mode, that the four waveforms are genuinely
   distinct timbres, or that the displayed note name equals the note you hear.

2. **Timeline (deterministic).** `Synth.timeline(frames)` samples POKEY
   registers + per-voice envelope levels/phases **every frame** and the
   scenarios assert on the whole trajectory: "a held note's level never
   collapses after onset", "the envelope steps exactly every (rate+1) frames",
   "AUDF glides monotonically through intermediates". Fast, exact, and needs no
   audio support in the emulator.

### Architecture

```
tools/synthtest/
├── run.py        entry point + filtering + summary  (python3 -m tools.synthtest.run)
├── harness.py    Synth: emulator lifecycle + all test primitives
├── scenario.py   Timeline, Reporter, assert_* helpers, combo-matrix generator
├── dsp.py        PCM analysis (numpy): pitch, spectrum, envelope, modulation…
├── notes.py      pitch maths; predicts the Hz POKEY *should* emit
└── scenarios/    one module per feature area; registered in __init__.py
```

**`harness.py` — the `Synth` class.** One booted emulator per test run
(context manager). The vocabulary every scenario uses:

| Helper | Purpose |
|---|---|
| `get/set(name, idx)` | named work variables — the `VARS` dict is the single source of truth for the page-6 addresses (must match `synth.asm`) |
| `get_param(i)` / `PARAM_VARS` | panel parameter by index, in visual order |
| `label_addr(name)` | resolve any MADS label from `synth.lst`, so tests survive code moving between builds |
| `pokey()/chan(n)/audctl()/nactive()` | POKEY **write-register state** via the bridge (never `peek($D2xx)` — see gotchas) |
| `audio_state()` / `channel_freq_hz(v)` | decoded POKEY snapshot with the **actual audible Hz** the emulator is emitting per channel (ilmenit/AltirraSDL#71). For joined 16-bit pairs the audible Hz is reported on the high channel of the pair (ch2 / ch4); `channel_freq_hz()` resolves the join |
| `play(key)` / `drain()` | cooked-key press with queue drain + key-down scan |
| `frozen(label)` | patch a routine's entry with `$60` (RTS) to freeze it, restore on exit — *the* way to hold a voice, since the cooked bridge KEY can't sustain a key |
| `held_key(semitone)` | hold a note through the **real trigger path** (freeze `read_keyboard`, set `note_idx`) so octave/arp/engine behave exactly as for a live key |
| `hold_voice(...)` / `reset_voices()` | set/clear voice state directly for deterministic starts |
| `step_seq(pattern, tempo)` | load a 16-step pattern and start the clock |
| `timeline(frames, extra=[...])` | frame-by-frame capture → `Timeline` |
| `capture(name, frames)` | record PCM → `dsp.Clip` (auto-retries truncated WAVs — a known tap glitch) |
| `recording(name)` / `audio_available()` | raw AUDIO_RECORD control / capability probe |
| `cell/glyph/px/fb_addr` | GR.8 framebuffer + ROM-font inspection for UI checks |
| `screenshot/key/joy/consol/frame/peek/poke` | thin bridge passthroughs |

**`scenario.py`.** A scenario is just `def my_scenario(s, rep)` — the "DSL" is
deliberately thin. It provides:

* `Timeline` — trajectory queries: `max_level`, `min_level_after_onset` (the
  direct guard against the attack-then-collapse bug class), `audf_span`,
  `sustained_level`, `active_count`, per-frame `var(...)`.
* `Reporter` — grouped PASS/FAIL collection, printed live, summarised at exit.
* Acoustic/timeline assertion helpers, each expressing one intent:
  `assert_audible_sustained`, `assert_silent`, `assert_pitch_hz` (cents
  tolerance), `assert_octave_up`, `assert_engine_faithful` (measured pitch ==
  divider→Hz prediction — a true engine check), `assert_modulated`
  (vibrato present/absent + rate band), `assert_timbre` (tonal/noise),
  `assert_no_collapse`, `spectral_fingerprint`/`assert_fingerprint_close`.
* The **effect-combination matrix**: `CURATED_PRESETS` (hand-picked musical
  patches, including the original user-reported `SUS=3 + LFO=7 + ARP=2` case)
  and `all_pairs(DEFAULT_AXES)` — a greedy **pairwise** cover over the effect
  axes (wave, octave, clock mode, sustain, LFO depth, detune), so every
  value-pair of any two axes appears in at least one tested combo with far
  fewer rows than the full product.

**`dsp.py`.** Pure numpy analysis of captured WAVs: `pitch` (FFT
autocorrelation with central-lobe rejection, subharmonic guard and parabolic
refinement), `pitch_track`/`median_pitch`/`distinct_pitches`, `spectrum` +
`spectral_features` (centroid, flatness, rolloff85, odd/even harmonic ratio),
`envelope` + `adsr` segmentation, `modulation` (LFO/vibrato rate+depth with a
real-presence test), `beat_freq` (detune beating), `onsets` /
`inter_onset_intervals` (rhythm with hysteresis against POKEY square-wave RMS
ripple), `fall_time`, `has_tone_at`/`spectral_peaks` (chord checks),
`rms`/`peak`/`is_silent`.

**`notes.py`.** Predicts the frequency POKEY *should* emit: PAL clock maths
(`f = clock / (2*(DIVIDER+1))` on the 64 kHz / 15 kHz / 1.79 MHz clocks),
equal-temperament references, the `cents` error helper, and — crucially — the
chromatic AUDF tables are **parsed out of `synth.asm` itself**, so the
predictions can never drift from the source of truth. `displayed_note(idx,
mode)` mirrors `draw_note`'s labelling so "label == what you hear" is testable.
Run `python3 -m tools.synthtest.notes` for a quick mode→pitch self-report.

**`run.py`.** Boots once, runs every registered scenario, prints a grouped
summary with a failure list, and exits non-zero on any failure. Positional
args filter by module/function-name substring; `--no-audio` (or a build
without `AUDIO_RECORD`) skips PCM scenarios and lists them as SKIPPED.
A scenario that raises is recorded as a failure, not a crash of the run.

### Scenario catalogue (what is actually tested)

Registered in `scenarios/__init__.py` as `(callable, needs_audio)` — ~110
scenarios, several hundred individual checks. Param/page coverage tracks the
current 3-page layout (Page 1 Voice, Page 2 FX/Patch, Page 3 Sequencer) and the
GLIDE/RHYTHM/ARPEGGIO names. By module:

**`bridge.py` — the AltirraBridge contract this framework depends on:**
`AUDIO_STATE` schema (top-level flags, 4 channels, all expected per-channel
fields); idle channels report `freq_hz=None`; per-channel `clock` label tracks
mode (NORMAL→`64kHz`, 15K→`15kHz`); `freq_hz / period_cycles` are
self-consistent with the PAL POKEY clocks; engine fidelity in 8-bit modes
asserted directly from reported Hz (no PCM, sub-1¢ tolerance); the
ilmenit/AltirraSDL#72 JOY-burst-then-KEY regression (12 and 50 consecutive
`JOY` commands — KEY must still register).

**`core.py` — engine + UI fundamentals (timeline level, no audio needed):**
boot defaults & silence; cooked-key → channel/pitch mapping; round-robin voice
allocation incl. wrap; the `'1'` drum key is reachable via a *real* keypress;
4-voice polyphony; ADSR over a timeline (attack→peak→sustain hold, monotonic
release to idle); the founding regression — a sequencer step must sustain, not
collapse; GR.8 UI sanity (dlist install, SDMCTL, dynamic redraw); param
navigation order + clamp for a representative spread; multi-page panel
navigation + label redraw; the CLOCK toggle and per-param value cells draw in
their own slots (no cross-param bleed — the "R08L" regression net);
WAVEFORM/CLOCK switch glyphs; VU meters.

**`acoustic.py` — "does it actually sound right" (PCM):** silence really is
silent; NORMAL-clock pitch is engine-faithful; displayed label == heard note
(NORMAL + 16-bit); 15 kHz mode in tune; the OCTAVE *knob* shifts pitch one
octave through the real trigger path; VOLUME scales RMS; ATTACK/RELEASE rates
audibly change envelope timing; LFO RATE scales vibrato speed; the arpeggiator
audibly cycles several pitches; a simultaneous C/E/G chord presents three
distinct tones in the mix; octave doubling; semitone == +100 cents (16-bit);
16-bit real output pitch (registers can't tell you this); the four waveforms
are distinct timbres (SQUARE/PURE pure-tone, BUZZ richer, NOISE noisier);
vibrato present at depth 15 / absent at 0; detune produces audible beating.
Plus the `clock_switch_voice_wrap` regression: a stale `last_voice` from a
4-voice NORMAL session must wrap when 16-bit drops the limit to 2 (used to
silence the note and corrupt voice RAM).

**`sequencer.py`:** START transport; a 16-step pattern visits all steps and
triggers each note; step-entry recording grows the loop length; playback wraps
within the *recorded* length; real-time record (SELECT): lead-in lands on step
0, a held note records as one strike + `$FE` ties; ties play back as one
sustained note with no re-attack blips (timeline); a recorded pattern is
audibly played back with multiple pitches (PCM).

**`arpmodes.py`:** ARPMODE param (default/clamp/label/page); each mode's
*ordered* pattern — UP `[24,28,31,36]`, DOWN reversed, MINOR (minor 3rd), OCT
(note+octave); UP/DOWN are exact reverses; modes are acoustically distinct
(MINOR ≠ UP; OCT shows both octave tones in the spectrum); the TEMPO
joystick-adjust regression (param_lo/hi off-by-one used to write stray RAM).

**`portamento.py`:** the GLIDE param (page 2, FX/Patch) — default/clamp/nav/label;
AUDF ramps monotonically old→new through intermediate steps; **acoustic
flagship** — the pitch audibly *glides* through ≥4 intermediate notes and rises
toward the target; higher GLIDE = slower glide (frames-to-target); GLIDE 0 =
instant, polyphonic.

**`drum.py`:** param default/clamp/nav/label (DRUM and RHYTHM live on page 3,
the Sequencer page); `$FD` sequencer step fires a channel-4 hit; the `'1'` key
fires a live hit (and does nothing with DRUM off); drum steps record into the
pattern and fire on playback (drum lane); RHYTHM param + free-running auto-beat
(more frequent at higher values, off at 0); the hit decays monotonically from
~15 to silence at the fixed noise
pitch; DRUM 0 silences a ringing hit; the hit is acoustically a decaying
broadband noise burst (with register fallback if the tap glitches); higher
DRUM rings longer; the drum coexists with melodic voices (chord tone still in
the spectrum while ch4 rings).

**`hpfilter.py`:** the HP FILTER param on page 2, the FX/Patch page
(default/clamp/label); HPF>0 sets AUDCTL bit 2 with channel 3 as the *silent*
cutoff clock at `(16-HPF)*4`;
**acoustic flagship** — the low fundamental disappears from the spectrum and
the centroid rises; higher HPF = brighter; cleanly disabled in 16-bit mode
(channel 3 is a joined pair there).

**`presets.py`:** PRESET param; selecting each slot live-loads its factory
patch (values verified against `synth.asm`'s factory bank); the 4 factory
patches are distinct 18-param signatures; FIRE saves the current sound into
the slot and survives a switch-away-and-back; presets are acoustically
different (INIT pure vs LEAD square+HP flatness gap).

**`stress.py` — boundaries, thrashing, conflicting effects, integrity:**
lowest/highest table notes + the chromatic clamp at idx 64; deep LFO on a high
note wraps 8-bit AUDF (documented glitch) *and* recovers cleanly; clock-mode
thrashing every frame with voices live, then a fresh note still sounds;
portamento+arp coexist; the mega-stack (BUZZ+detune+LFO+HP+pedal) stays
audible with no level collapse; degenerate patterns (all-drum fires, all-tie
strikes nothing, all-rest silent); extreme ADSR (sus=0 blip, atk=15 crawl);
machine-gun retriggering cycles all voices then everything falls silent;
changing OCTAVE never repitches already-ringing voices; portamento is a clean
no-op in 16-bit; drum + HP filter share channels 3/4 cleanly; sequencer + arp
simultaneously stays audible and shuts off to silence; and the integrity
guarantee — after a chaos burst (notes+arp+drum+seq+mode flips+effects),
switching everything off returns **true PCM silence**.

**`quantitative.py` — exact measurements and property sweeps:** full-range
16-bit tuning sweep, every sampled note <5 cents from its designed pitch;
octave-doubling across the whole keyboard (<20 cents); RMS strictly monotonic
over **all 16** volume levels with level 0 silent; the envelope steps exactly
every `(rate+1)` frames for ATTACK and RELEASE at several rates; sustain ==
`min(sus, volume)` and tracks *live* changes to either; LFO AUDF swing
monotonic in depth and `≈ 2*(depth>>1)` at depth 14; the measured detune beat
matches the Hz predicted from the actual AUDF spread; waveform harmonic
identity (SQUARE odd-dominant, SQUARE≡PURE, BUZZ/NOISE poly distortions).

**`timing.py` — the synth plays at the tempo we designed:** sequencer
inter-onset interval measured **from the rendered audio** matches
`(16-tempo)*2+2` frames per step at two tempos (and in the right ratio); the
exact frame count is pinned deterministically at tempo 0/8/15; arp steps every
`16-arp_rate` frames exactly; the RHYTHM auto-beat hits every `(16-RHYTHM)` tempo
beats exactly.

**`workflow.py` — end-to-end user flows with checkpoints:** record a melody →
play it back → exact pitches re-trigger; one pattern mixing melody + a drum
step plays both; full 18-param preset round-trip (save, perturb everything,
reload — all 18 saved params restore; the PRESET selector itself is not stored); every
factory preset renders an audible sustained sound (regression net); **capture
determinism** — the same patch captured twice gives the same pitch/RMS/centroid
within documented tolerances, so quantitative checks aren't chasing tap noise;
and a full user session (build patch A → save → record+play pattern B → load a
different factory patch C ≠ A → reload the slot D ≈ A acoustically — the
round-trip preserves the *sound*, not just the RAM bytes).

**`combos.py` — the combination matrix:** curated musical presets (pad, lead,
fat-arp, buzzy, and the original user case `sus3+lfo7+arp2`) each audible and
sustained; the automated **pairwise** matrix driven through the real trigger
path — every combo must stay audible and non-collapsing; specific stacks
(arp+vibrato+detune; 16-bit+LFO+detune in tune; effects on a real chord keep
≥2 of its 3 tones); and the timeline no-collapse guard over stacked effects,
which runs even without audio support.

### Test-technique cheatsheet (how scenarios drive the synth)

These are the load-bearing tricks; reuse them rather than reinventing:

* **Hold a note** — the bridge `KEY` is *cooked*: key-down lasts ~1 frame, so a
  key can never be held. Either `frozen("trigger_voices")` + set voice state
  directly (engine renders it; good for steady captures), or
  `held_key(semitone)` (freezes `read_keyboard`, sets `note_idx`; exercises
  the real trigger path incl. octave/arp/porta).
* **Deterministic starts** — `reset_voices()` before key-driven tests; idle all
  voices and zero the LFO counter+offset (`$0665`/`$0668`) before pitch
  measurements (a residual LFO offset decays only slowly and skews AUDF).
* **Clock-mode pokes** — set both `clock15` *and* `prev_clkm` (`$0689`): equal
  values suppress the engine's mode-change voice reset; unequal force it.
  Tests use each deliberately.
* **Capture hygiene** — `capture()` re-records up to 3× when the WAV comes back
  far shorter than requested (a known tap glitch late in long runs — real
  silence still yields a full-length near-zero file). Pitch from capture is
  rock-solid; RMS/centroid drift modestly between captures, so quantitative
  checks use ordering/tolerances that absorb it (see `capture_determinism`).
* **Low notes for modulation analysis** — detune/LFO measurements use idx 0
  (large AUDF) so one AUDF step is a small Hz change → clean slow beats and
  wobbles.

### Adding a test

1. Write `def my_scenario(s, rep):` in the matching `scenarios/*.py` (or a new
   module). Drive the `Synth`, record results via `rep.section(...)` +
   `rep.check(name, ok, detail)` or the `assert_*` helpers.
2. Register it in `scenarios/__init__.py` as `(my_scenario, needs_audio)` —
   set `needs_audio=True` only if it calls `capture()`.
3. **Leave the synth clean**: switch off every effect you enabled (arp, drum,
   HPF, porta, pedal, LFO incl. `$0665`/`$0668`), restore clock mode, stop the
   sequencer. Scenarios share one booted emulator; leaked state is the #1
   source of flaky downstream failures.
4. If the feature adds RAM variables: add them to `VARS` (and `PARAM_VARS` if
   it's a panel param) in `harness.py`, and to `memcheck.py`'s `SIZES` if it's
   an array.
5. Run just your group while iterating: `python3 -m tools.synthtest.run mymodule`.

### Known gotchas (verified the hard way)

* **POKEY `$D200-$D208` are write-only** — reading them returns the paddle
  POTs. Always use the bridge's `pokey()` snapshot of write-register state.
* **AltirraSDL build requirement** — the framework hard-requires a bridge
  build that includes `AUDIO_STATE.freq_hz` (ilmenit/AltirraSDL#71) and the
  JOY-then-KEY fix (#72), i.e. commit `31bf4d9a` (PR #74) or later. `Synth.boot()`
  capability-probes both and fails fast if the binary is stale. (Historically,
  pre-#72 a burst of 12+ consecutive `JOY` commands silently broke all
  subsequent `KEY` injection — see `bridge.joy_burst_then_key_regression`
  for the regression coverage; with the fix this no longer constrains test
  ordering.)
* **Headless AltirraSDL ignores SIGTERM** — the harness uses `kill()`.
* **AUDIO_RECORD truncation** — see capture hygiene above.
* **MADS listing as symbol table** — `label_addr()`/`memcheck` parse
  `synth.lst`; if a label is missing, check it's a column-0 label (EQUs and
  labels have different listing formats — `memcheck.py` handles both).

### The emulator side of AUDIO_RECORD

`AUDIO_RECORD start path=<file> [raw] [stereo]` / `stop` / `status` is a bridge
command added to the AltirraSDL fork
(`src/AltirraSDL/source/bridge/bridge_commands_audio.cpp`). It attaches an
`ATAudioWriter` as an audio tap, capturing the mixed POKEY output
(pre-resample) to a 44.1 kHz mono 16-bit WAV — and because the tap is
independent of any output device, it works under `--headless`. It is compiled
only into the GUI `AltirraSDL` target (guard: `ALTIRRA_BRIDGE_AUDIO_REC`); the
`AltirraBridgeServer` target doesn't link `ATAudioWriter` and is unaffected.
