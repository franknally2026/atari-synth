# Atari POKEY Synth

A keyboard-playable POKEY synthesizer for the **PAL Atari 8-bit** (XL/XE), with a
hi-res on-screen control panel, a 4-voice envelope engine, a pile of effects
(LFO, detune, portamento, arpeggiator with modes, high-pass filter), three
oscillator/clock modes, a drum voice, a 16-step sequencer, and patch presets.
Written from scratch in 6502 assembly (MADS), inspired loosely by softsynths
like Surge XT — a tiny subset, running on real hardware.

Single source file: `synth.asm` → `synth.xex`.

> **Just want to play it?** See the hands-on, step-by-step manual (first notes,
> tutorials, recording a beat, saving sounds):
> **[English](USER_GUIDE_EN.md)** · **[Polski](USER_GUIDE_PL.md)**.
> This README is the technical reference (every parameter, the architecture).

---

## Contents

1. [Quick start](#quick-start)
2. [Controls at a glance](#controls-at-a-glance)
3. [Playing notes](#playing-notes)
4. [The control panel](#the-control-panel) — the 3 pages and all 19 parameters
5. [Features in depth](#features-in-depth) — what each does and how to use it
6. [Recipes](#recipes) — building specific sounds
7. [How it works](#how-it-works) — architecture, POKEY, timing, memory
8. [Known behaviors & limitations](#known-behaviors--limitations)
9. [Testing](#testing)
10. [Files & development](#files--development)

---

## Quick start

```sh
./build.sh          # assemble -> synth.xex (runs the build-time memory check)
./build.sh run      # assemble and launch in atari800 (PAL)
```

Requires `mads` and `atari800` on `PATH`. The `.xex` is a standard Atari binary
load file (loads at `$2000`, runs at `main`). Always run **PAL** (`atari800 -pal`)
— the pitch tables are tuned for the PAL clock.

When it boots you get the control panel up top and a drawn piano keyboard along
the bottom. Press a letter/number key to play; use the joystick to drive the
panel.

---

## Controls at a glance

| Input | Action |
|---|---|
| **Letter/number keys** | Play notes (see [Playing notes](#playing-notes)) |
| **Key `1`** | Trigger a **drum** hit (when `DRUM` > 0) |
| **Joystick Up / Down** *(or arrow keys)* | Select the previous / next panel parameter (the focused label goes inverse-video; wraps; changes page automatically; auto-repeats when held) |
| **Joystick Left / Right** *(or arrow keys)* | Decrease / increase the selected parameter (auto-repeats when held) |
| **Joystick Fire** *(or **Return**)* | While the `PRESET` parameter is selected: **save** the current sound into the selected slot |
| **Tab** | Jump to the next page (0 → 1 → 2 → 0) |
| **Letter shortcut** | Jump straight to a parameter by its underlined letter (Shift+letter for the inverse-marked ones) — see [Shortcuts](#parameter-shortcuts) |
| **START** (console) | Sequencer **play / stop** |
| **SELECT** (console) | Sequencer **record** arm (real-time record; see [Sequencer](#step-sequencer)) |
| **OPTION** (console) | **Sustain pedal** (hold to keep notes ringing) |

The joystick is read from the OS shadow (`STICK0`/`STRIG0`), so use the joystick
in **port 1**. The **arrow keys mirror the joystick** (Up/Down navigate,
Left/Right adjust) for laptop play with no joystick. The console keys are read
directly from `CONSOL`, independent of the keyboard matrix, so they work while a
note key is held.

#### Parameter shortcuts

Each parameter's label has one **underlined letter** — press it to jump the
selection straight to that parameter (across pages). Where the natural first
letter is a piano key (W, O, R, P, T) or already taken, the shortcut is
**Shift+letter** and the letter is drawn inverse instead of underlined. Examples:
`V`→VOLUME, `C`→CLOCK, `A`→ARPEGGIO, `D`→DECAY, `G`→GLIDE, `H`→HP FILTER;
`Shift+W`→WAVEFORM, `Shift+R`→RELEASE, `Shift+T`→TEMPO, `Shift+D`→DRUM.

---

## Playing notes

The bottom two rows of the keyboard are a one-octave piano:

```
black keys:      2   3       5   6   7       9   0
white keys:    Q   W   E   R   T   Y   U   I   O   P
naturals:      C   D   E   F   G   A   B   C   D   E
```

- **White row** `Q W E R T Y U I O P` = the naturals **C D E F G A B C D E**.
- **Number row** `2 3 5 6 7 9 0` = the sharps **C# D# F# G# A# C# D#**.
- **`1`** is the **drum** trigger (not a pitch). **`4`** and **`8`** are silent —
  there is no black key between E–F or B–C, so those positions are left out,
  exactly like a real piano.

The currently-held key is highlighted on the drawn keyboard and its note name
(e.g. `C 4`, `F#5`) is shown top-right. Use the `OCTAVE` parameter to move the
whole keyboard up or down by octaves.

### Polyphony (4 voices)

Each new key-press is assigned to the next POKEY channel **round-robin** and runs
its own ADSR envelope, so successive notes ring together across all four
channels. The most recent key is the "held" voice (it sustains); older notes
decay and free their channel.

> **Why no real chords?** The Atari keyboard is a scanned matrix — the hardware
> only ever reports **one** key at a time, so a physically-held chord can't be
> detected. The model is *voice-allocation-on-attack*: play notes in quick
> succession (or use the [sustain pedal](#sustain-pedal) / [arpeggiator](#arpeggiator)) and they ring together.

In **16-bit** clock mode the engine is **2-voice** (each voice uses a channel
pair); NORMAL and 15 kHz modes are 4-voice.

---

## The control panel

Parameters live on **three pages**, grouped by role. You don't switch pages
directly — navigating Up/Down past the end of a page moves to the next page
automatically (the page shown always follows the selected parameter), or press
**Tab** to jump straight to the next page. The selected parameter's label is
shown in **inverse video** (the focus highlight).

- **Page 0 — Voice** (params 0–11): oscillator, envelope, vibrato, arpeggiator.
- **Page 1 — FX / Patch** (params 12–15): detune, filter, glide, preset.
- **Page 2 — Sequencer / Rhythm** (params 16–18): tempo, drum, rhythm, plus the
  16-step grid and transport.

### Full parameter reference

| # | Name | Range | Page | What it does |
|--:|------|-------|:----:|---|
| 0 | `WAVEFORM` | SQUARE / PURE / BUZZ / NOISE | 0 | Oscillator timbre (POKEY distortion) |
| 1 | `VOLUME` | 0–15 | 0 | Envelope peak / master level |
| 2 | `OCTAVE` | −2 … +2 | 0 | Transpose the keyboard by octaves |
| 3 | `CLOCK` | NORMAL / 15 KHZ / 16-BIT | 0 | Oscillator clock / range mode |
| 4 | `LFO RATE` | 0–15 | 0 | Vibrato speed (higher = faster) |
| 5 | `LFO DEPTH` | 0–15 (0 = off) | 0 | Vibrato amount (pitch wobble) |
| 6 | `ATTACK` | 0–15 | 0 | Envelope attack time (0 = instant, 15 = slow) |
| 7 | `DECAY` | 0–15 | 0 | Decay time from peak down to sustain |
| 8 | `SUSTAIN` | 0–15 | 0 | Held-note level (clamped to VOLUME) |
| 9 | `RELEASE` | 0–15 | 0 | Release time after the key lifts |
| 10 | `ARPEGGIO` | 0–15 (0 = off) | 0 | Hold-to-arpeggiate speed |
| 11 | `ARP MODE` | UP / DOWN / MINOR / OCT (0–3) | 0 | Arpeggio pattern |
| 12 | `DETUNE` | 0–15 (0 = off) | 1 | Spread the voices' tuning (fat / chorus) |
| 13 | `HP FILTER` | 0–15 (0 = off) | 1 | High-pass filter cutoff |
| 14 | `GLIDE` | 0–15 (0 = off) | 1 | Portamento (pitch glide) time |
| 15 | `PRESET` | 0–3 | 1 | Patch slot (select = load; Fire/Return = save) |
| 16 | `TEMPO` | 0–15 | 2 | Sequencer / rhythm tempo (higher = faster) |
| 17 | `DRUM` | 0–15 (0 = off) | 2 | Drum decay / enable |
| 18 | `RHYTHM` | 0–15 (0 = off) | 2 | Auto drum-machine rate |

Both arpeggiator controls (`ARPEGGIO`, `ARP MODE`) live on the Voice page; all
the beat controls (`TEMPO`, `DRUM`, `RHYTHM`) live on the Sequencer page with the
step grid, since that's where you build rhythms.

`ATTACK`/`DECAY`/`RELEASE` are **frames-per-level-step minus one**: the envelope
moves one level (of 16) every `value + 1` frames, so 0 is fastest (1 frame/step)
and 15 is slowest (16 frames/step). At PAL 50 fps a full 0→15 attack is ~0.3 s
at `ATTACK=0` and ~5 s at `ATTACK=15`.

---

## Features in depth

### Waveforms (`WAVEFORM`)

Four POKEY oscillator timbres:

- **SQUARE** and **PURE** — both are *pure-tone* distortions (a divided square
  wave with odd harmonics). They sound nearly identical; PURE is provided as the
  "clean" default.
- **BUZZ** — a poly-counter distortion: a buzzier, harmonically richer tone.
- **NOISE** — a poly-counter pseudo-random tone. POKEY "noise" is a periodic poly
  pattern, *not* white noise — it's semi-tonal but clearly noisier than the pure
  waves. Good for percussion-ish and effect sounds.

### `VOLUME` and `OCTAVE`

- **VOLUME** sets the envelope's peak level (the channel's POKEY volume nibble).
  Louder = higher; 0 is silent.
- **OCTAVE** transposes the keyboard ±2 octaves (centre = no shift). It affects
  *new* notes — a note already ringing keeps its pitch when you change octave.

### ADSR envelope (`ATTACK` / `DECAY` / `SUSTAIN` / `RELEASE`)

Every voice runs a classic four-stage envelope:

- **ATTACK** — rise from 0 to VOLUME when the key is struck.
- **DECAY** — fall from the peak down to the SUSTAIN level.
- **SUSTAIN** — the level held while the key (or sustain pedal) is down.
  Internally clamped to `min(SUSTAIN, VOLUME)` — sustain can't exceed the peak.
- **RELEASE** — fall to silence after the key lifts.

Set short ATTACK/RELEASE for plucky/percussive sounds, long ones for pads.
SUSTAIN at 0 gives a pluck (decays to silence even while held); SUSTAIN near
VOLUME gives an organ-like hold.

### `DETUNE` — fat / chorus

Each voice gets a small pitch offset of `voice_index × (DETUNE / 4)`. When notes
ring across several voices they **beat** against each other for a thick,
chorused sound. At higher (lower-pitched) notes the offsets are small Hz
differences → slow audible beating; at very high notes they become large jumps.
0 = all voices perfectly in tune.

### LFO / vibrato (`LFO RATE`, `LFO DEPTH`)

A triangle LFO adds a small ± pitch offset to every sounding voice each frame:

- **LFO DEPTH** sets the amount (the pitch swing). 0 = off (instantly flat).
- **LFO RATE** sets the speed. The triangle period is
  `4 × (DEPTH/2) × (16 − RATE)` frames, so deep + slow vibrato can be very slow
  (well under 1 Hz) and shallow + fast is a quick shimmer.

In 8-bit modes the depth is in raw `AUDF` units, so the *musical* depth (in cents)
is larger at high notes than low notes (POKEY's pitch is `clock / (2 × (divider+1))`).
In **16-bit** mode the offset is scaled to the note's own (much larger) divider, so
LFO and DETUNE stay audible there too — a fixed percentage of pitch at any note.

### Glide / portamento (`GLIDE`)

With `GLIDE` > 0 the synth becomes **monophonic** and a new note **glides** from
the previously-played pitch to the new one instead of jumping. `GLIDE` sets the
glide time (higher = slower glide). 0 = off (normal polyphonic, instant pitch).
Great for lead lines and slides. (8-bit clock modes only; struck through and
ignored in 16-bit, where the channel pairs leave no spare voice.)

### Arpeggiator (`ARPEGGIO`, `ARP MODE`)

Hold a key with `ARPEGGIO` > 0 and the synth cycles a 4-note chord pattern built
from the held note, one step every `16 − ARPEGGIO` frames (so higher = faster).

`ARP MODE` selects the pattern (intervals from the held root):

| Mode | Pattern | Sounds like |
|---|---|---|
| **UP** | root, +4, +7, +12 | major arpeggio ascending |
| **DOWN** | +12, +7, +4, root | major arpeggio descending |
| **MINOR** | root, +3, +7, +12 | minor arpeggio ascending |
| **OCT** | root, +12, root, +12 | octave bounce |

Set `ARPEGGIO = 0` to play notes directly. (Like the rest, it's
hold-to-arpeggiate, since the keyboard reports one key.)

### Clock / range modes (`CLOCK`)

Three oscillator modes, each with its own tuning and channel layout:

- **NORMAL** — 64 kHz POKEY clock, 8-bit dividers, **4 voices**. The default.
  Note: the chromatic table is tuned for the 15 kHz/16-bit clocks, so in NORMAL
  every note actually sounds **two octaves above** its displayed name (the note
  readout compensates and shows the real octave). High notes are coarsely tuned
  (8-bit divider quantization).
- **15 KHZ** — 15 kHz clock, 8-bit, 4 voices. Two octaves lower than NORMAL;
  roughly in tune (a touch flat at the top).
- **16-BIT** — joins channel pairs (CH1+CH2, CH3+CH4) into 16-bit dividers
  clocked at 1.79 MHz. **Accurately tuned across the whole range** (within a
  couple of cents), but **2 voices** (each voice uses a channel pair). Use this
  when you want correct, wide-range pitch.

### High-pass filter (`HP FILTER`)

POKEY's hardware high-pass: with `HP FILTER` > 0, channel 1 (voice 0) is
high-passed, using channel 3 as the cutoff clock. Higher values raise the cutoff,
removing more low end and brightening the tone. 0 = off.

Trade-offs: it **filters voice 0 only**, and it **consumes channel 3** (voice 2
goes silent while the filter is engaged). It's disabled in 16-bit mode (channel 3
is part of a pair there).

### Drum voice (`DRUM`, `RHYTHM`)

A noise-percussion hit on channel 4, separate from the melodic voices. `DRUM`
enables it and sets the **decay length** (0 = off; higher = longer ring). Both
drum controls live on the **Sequencer page** with the step grid. Once
`DRUM` > 0, fire it **three ways**:

1. **Live** — press key **`1`**. Each press is an instant drum hit; the `DRUM`
   knob changes how long it rings.
2. **Auto drum-machine** — turn up **`RHYTHM`** (with `DRUM` > 0). The drum
   pulses automatically, synced to `TEMPO`, every `16 − RHYTHM` beats (higher =
   more frequent). 0 = off. This is the "turn a knob and immediately hear a beat"
   control.
3. **Sequenced** — record drums into the [sequencer](#step-sequencer) (see *drum
   lane* below): pressing `1` while recording lays down drum steps that play back
   in your pattern.

The drum is silenced in 16-bit mode (channel 4 is part of a pair there).

### Sustain pedal (OPTION)

Hold the **OPTION** console key and notes keep ringing instead of releasing — so
you can tap several notes in succession and hold them as a chord, then let OPTION
go to release them all. It's independent of the key matrix, so it works while a
note key is down (where a second *key* couldn't be detected).

### Step sequencer

A 16-step pattern sequencer on the **Sequencer page** (page 2 — navigate to
`TEMPO`/`DRUM`/`RHYTHM`, or press Tab, to see the step grid). Steps hold a note, a
rest, a tie, or a drum. Each step is drawn with its own glyph: **♪** note,
**`X`** drum, **`-`** tie, **`·`** rest, and a **↓** head marks the active step.

**Transport (console keys):**

- **START** — play / stop.
- **SELECT** — record arm.

**Recording — two modes:**

- **Real-time record** — press **SELECT** alone. This clears the pattern, starts
  the clock, and records the notes you play *in time* onto the steps under the
  play head (a one-step lead-in lets the first note land on step 0). Holding a
  note records it as one struck note followed by **ties** (so it sustains on
  playback instead of re-striking). Recording is non-destructive — play another
  pass to **overdub**. Press SELECT again to punch out (the loop keeps playing).
- **Step entry** — while armed, press **START** to *stop* the clock. Now each key
  you press writes **one step** and advances the write head, growing the loop
  length. (`REC` armed + clock stopped = step entry.)

**Playback** loops over the recorded length at `TEMPO`. The step interval is
`(16 − TEMPO) × 2 + 2` frames, so `TEMPO` 0 is slow (~22 16th-notes/min feel) and
15 is fast.

**Step types** (what a stored step does on playback):

- **note** — (re)strikes that pitch through the normal voice/envelope path.
- **rest** — releases the held note (silence).
- **tie** — lets the previous note keep ringing (no re-strike — no "blip").
- **drum** — fires a drum hit (the *drum lane*). Recorded by pressing key `1`
  during recording.

So you can record a melody and then overdub a drum lane into the same pattern.

### Presets (`PRESET`)

Four patch slots, seeded with factory patches (INIT / PAD / LEAD / ARP) at boot.

- **Load** — selecting a slot with the `PRESET` knob loads it live (all the sound
  parameters change to that patch).
- **Save** — while `PRESET` is the selected parameter, press the **joystick fire
  button** (or **Return**) to save the current sound into the selected slot.

Presets store **all 18 sound parameters** (everything except the `PRESET` selector
itself) — including `TEMPO`, `DRUM` and `RHYTHM`. A slot's name (INIT / PAD / LEAD
/ ARP) is shown in place of a value, and a brief `SAVED` flash confirms a save.

### On-screen readouts

- **Note name** (top-right) — the note currently playing, e.g. `C 4`, reflecting
  the actual sounding octave in the current clock mode.
- **VU meters** — per-voice level bars, so you can see each voice's envelope.
- **Knobs / switches** — values are drawn as 16-position knobs; WAVEFORM is a row
  of waveform icons with the active one boxed; CLOCK shows the mode name.

---

## Recipes

- **Organ** — WAVEFORM PURE, ATTACK 0, DECAY 2, SUSTAIN 15, RELEASE 2. Hold notes
  (or use OPTION) for sustained chords.
- **Pluck/lead** — WAVEFORM SQUARE, ATTACK 0, DECAY 4, SUSTAIN 6, RELEASE 3, a
  little LFO DEPTH for vibrato.
- **Fat / chorus** — DETUNE 8–12 and play notes in quick succession (or arpeggiate)
  so several voices ring and beat.
- **Glide lead** — GLIDE 6–10; play legato lines and hear the pitch slide.
- **Pad** — WAVEFORM PURE, slow ATTACK (6+) and RELEASE (8+), SUSTAIN high, a slow
  LFO (low RATE, mid DEPTH), some DETUNE; hold with OPTION.
- **Bright lead** — 16-BIT clock for clean pitch, HP FILTER 6–10 to thin the lows.
- **Drum beat** — DRUM 6–10, then RHYTHM 8–15 for an auto pulse, or tap key `1`,
  or record a drum lane in the sequencer alongside a melody.
- **Arp riff** — hold a key, ARPEGGIO 6–10, try the ARP MODE patterns (UP/DOWN/MINOR/OCT).

---

## How it works

### Frame loop (PAL, 50 Hz)

Once per video frame the main loop runs, in order: read keyboard → read console →
read nav-keys (arrows / Tab / Return / letter shortcuts) → trigger voices →
drum-key → input (panel) → preset tick → LFO tick → arp tick → sequencer tick →
drum-beat tick → **update sound** → drum tick → update display.
`update_sound` is where the envelopes advance and the POKEY registers get
written; the drum overrides channel 4 last. One frame = 20 ms, which is the unit
of all envelope and sequencer timing.

### Sound generation (POKEY)

Each voice maps to a POKEY channel (`AUDF`/`AUDC`). Per frame, `update_sound`:

- computes `sus_clamp = min(SUSTAIN, VOLUME)` and the per-voice detune offsets;
- runs each voice's ADSR state machine (one level step per `rate+1` frames);
- emits, for each sounding voice, `AUDF = pitch (+ portamento glide) + LFO offset
  + detune offset` and `AUDC = waveform distortion | level`;
- sets the global `AUDCTL` for the clock mode (and OR-s in the high-pass bit when
  the filter is on).

Pitch comes from PAL chromatic tables: an **8-bit** divider table (`chromatic`)
for NORMAL/15 kHz, and a **16-bit** divider table (`chrom16_lo`/`hi`) for 16-bit
mode. POKEY channel frequency ≈ `clock / (2 × (divider + 1))`; PAL clocks are
64 kHz = 63337 Hz, 15 kHz = 15557 Hz, 1.79 MHz = 1773447 Hz.

The drum is a separate subsystem on channel 4 (white-noise distortion + its own
fast decay), and the high-pass filter borrows channel 3 as a silent cutoff clock.

### Panel (table-driven)

Every parameter is one entry across a set of descriptor tables (`p_kind`,
`p_scan`, `p_lblcol`, `p_knobcx`, `p_numcol`, `p_vaddr`, `p_lblptr`) plus
`param_lo/hi/max/maxp1` for the joystick adjust+clamp. `update_display` walks the
current page's entries and draws by kind (knob / octave / waveform / clock).
Navigation (`cur_param`) is a single linear ring over all parameters; the index
order equals the visual layout order, and the page is derived from the index.
Adding a feature = a few table rows + its engine code.

### Display (GR.8 bitmap)

ANTIC mode `$0F` (320×192, 1bpp) via a custom display list with two LMS regions
(`$4000`/`$5000`) spanning the 4 KB boundary; a runtime line-address table hides
the split. Everything is drawn with bitmap primitives (ROM-font text, circle
knobs with a 16-position pointer, waveform icons, the piano keyboard). Redraw is
**diff-based** (only widgets whose value changed) so there's no flicker. The
display list sits at a fixed 1 KB-aligned address (`$3C00`) within one 1 KB block
(ANTIC's DL counter is 10-bit).

### Input

Keyboard is polled raw via `KBCODE` gated by `SKSTAT` bit 2 (no CIO), so it
responds in real time and tracks release. The joystick uses the OS shadow
(`STICK0`) with edge detection and auto-repeat; the fire button is `STRIG0`; the
console keys are read from `CONSOL` (edge-triggered for START/SELECT, level for
OPTION).

### Memory map (high level)

- Code + tables: `$2000`–~`$3970`
- Display list: `$3C00`
- Framebuffer: `$4000`–`$5FFF`
- Line-address table: `$6000`–`$617F`
- Work variables: page 6 (`$0600`+); preset bank: `$0700`

`build.sh` runs a build-time memory check (`tools/memcheck.py`) that fails the
build on segment overlaps or a display list crossing a 1 KB boundary.

---

## Known behaviors & limitations

- **NORMAL clock sounds two octaves above the note name's nominal pitch** (the
  chromatic table is tuned for the 15 kHz / 16-bit clocks). The on-screen note
  readout shows the real octave. Use **16-BIT** for accurate concert-pitch
  tuning.
- **High notes in 8-bit modes are coarsely tuned** — the 8-bit divider can't
  resolve a true semitone up high. 16-bit mode is in tune across the whole range.
- **POKEY "NOISE" is a periodic poly pattern, not white noise** (semi-tonal).
- **16-bit mode is 2-voice** (channel pairs); NORMAL/15 kHz are 4-voice.
- **A deep LFO on very high notes can glitch in 8-bit modes** — the 8-bit `AUDF`
  wraps when the offset pushes it past 0/255, briefly jumping the pitch. (16-bit
  scales the offset to the note, so it doesn't wrap there.)
- **HP filter uses channel 3** (voice 2 goes silent while it's on) and **only
  filters voice 0**; disabled in 16-bit.
- **`DRUM`, `RHYTHM`, `GLIDE` and `HP FILTER` are disabled in 16-bit mode** (the
  channel pairing leaves no spare channels) — they're struck through on screen.
  `LFO` and `DETUNE` still work in 16-bit (offset scaled to the note).
- **No true held chords** from the keyboard (scanned matrix reports one key) —
  use succession + sustain pedal, or the arpeggiator/sequencer.
- Tuned for **PAL**; on NTSC the pitch is ~1% sharp (regenerate the tables from
  the NTSC base if exact tuning matters).

---

## Testing

The synth is verified — code *and* audio — by an extensive headless test
framework that drives the emulator (AltirraSDL) via AltirraBridge, captures real
PCM and analyses it, and checks per-frame register/level timelines. It covers
every feature at register, timeline, and quantitative-acoustic levels (exact Hz /
ms / cents, full-range tuning sweeps, rhythm-from-audio, multi-stage user
workflows, and unusual/edge scenarios).

```sh
python3 -m tools.synthtest.run            # run everything
python3 -m tools.synthtest.run acoustic   # one group
python3 -m tools.synthtest.run --no-audio # skip PCM capture (timeline only)
```

See **`tools/synthtest/README.md`** for the full framework documentation.
(`tools/verify_synth.py` is the older single-file harness, superseded by
`tools/synthtest`.)

---

## Files & development

- `synth.asm` — the entire synth (single source file).
- `build.sh` — assemble (`./build.sh`) / assemble + run (`./build.sh run`).
- `tools/memcheck.py` — build-time memory-map check (wired into `build.sh`).
- `tools/synthtest/` — the test framework (see its README).
- `synth.xex` / `synth.lst` — build outputs (executable + MADS listing).

**Adding a parameter** (recipe): extend `NPARAM`; add an entry to every parallel
table (`param_lo/hi/max/maxp1` and the `p_*` descriptor tables — keep index order
== visual order); add a `txt_` label; allocate a work variable (new ones go after
the existing page-6 block, ~`$06DB+`, clear of the `prev_disp` array); default it
in `init`;
implement the engine tick; then add coverage in `tools/synthtest`. `build.sh`'s
memcheck guards the memory layout as the variable block grows.
