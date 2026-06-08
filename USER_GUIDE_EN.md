# Atari POKEY Synth — User Guide

*Language: **English** · [Polski](USER_GUIDE_PL.md)*

Welcome! This is a hands-on manual for *playing* the synth. It walks you through
everything from your first note to recording a full pattern with drums and saving
your own sounds. No assembly or theory required — just follow along at the
keyboard.

---

## Contents

- [1. Starting up](#1-starting-up)
- [2. What you see on screen](#2-what-you-see-on-screen)
- [3. Playing your first notes](#3-playing-your-first-notes)
- [4. Changing a sound with the joystick](#4-changing-a-sound-with-the-joystick)
- [5. Tutorials](#5-tutorials)
  - [5.1 Shape a sound (the envelope)](#51-shape-a-sound-the-envelope)
  - [5.2 Add vibrato (the LFO)](#52-add-vibrato-the-lfo)
  - [5.3 Make it fat (detune)](#53-make-it-fat-detune)
  - [5.4 Get in tune (16-bit mode)](#54-get-in-tune-16-bit-mode)
  - [5.5 A gliding lead (portamento)](#55-a-gliding-lead-portamento)
  - [5.6 Arpeggios](#56-arpeggios)
  - [5.7 Brighten up (high-pass filter)](#57-brighten-up-high-pass-filter)
  - [5.8 Add drums](#58-add-drums)
  - [5.9 Record a pattern (the sequencer)](#59-record-a-pattern-the-sequencer)
  - [5.10 Add a drum lane to your pattern](#510-add-a-drum-lane-to-your-pattern)
  - [5.11 Save and recall your sounds (presets)](#511-save-and-recall-your-sounds-presets)
- [6. Controls cheat sheet](#6-controls-cheat-sheet)
- [7. Troubleshooting / FAQ](#7-troubleshooting--faq)
- [8. Tips](#8-tips)

---

## 1. Starting up

Load `synth.xex` on a **PAL** Atari 8-bit (or `./build.sh run` to launch the
emulator). You'll need a **joystick in port 1** for the control panel.

When it boots you'll see the control panel across the top of the screen and a
piano keyboard drawn along the bottom. That's it — you're ready to play.

---

## 2. What you see on screen

- **The panel (top):** rows of **knobs** and switches — these are your sound
  controls. One control at a time has a **`>` marker** next to it; that's the one
  the joystick will change.
- **The note name (top-right):** shows the note you're currently playing, e.g.
  `C 4`.
- **VU meters:** little bars that light up to show each of the four voices
  playing.
- **The piano keyboard (bottom):** the key you press lights up.

The panel has **three pages**. You don't pick a page directly — as you scroll
the selection up and down past the end of a page, it flips to the next page
automatically.

- **Page 1** — the main sound controls (waveform, volume, octave, envelope,
  detune, clock, LFO, arpeggiator).
- **Page 2** — the sequencer (tempo, arp mode, portamento, drum) plus the step
  grid.
- **Page 3** — the filter and presets.

---

## 3. Playing your first notes

Use the letter and number keys like a one-octave piano:

```
black keys:      2   3       5   6   7       9   0
white keys:    Q   W   E   R   T   Y   U   I   O   P
plays:         C   D   E   F   G   A   B   C   D   E
```

- The **white row** `Q W E R T Y U I O P` plays the natural notes.
- The **number row** `2 3 5 6 7 9 0` plays the sharps (the black keys).
- `1` is the **drum** key (more on that later). `4` and `8` do nothing — just
  like a real piano, there's no black key there.

Press a few keys. You should hear notes, see the key light up, and see the note
name appear top-right.

**Playing chords:** the Atari can only sense one key at a time, so to hold a
chord, either tap the notes in quick succession (they ring together for a moment)
or hold the **OPTION** console key as a sustain pedal — then every note you tap
keeps ringing until you let OPTION go.

---

## 4. Changing a sound with the joystick

Everything on the panel is changed the same way:

1. **Push the joystick Up or Down** to move the `>` marker to the control you
   want. (Keep pushing the same way to scroll through all the controls; it wraps
   around, and the page flips automatically as you go.)
2. **Push Left or Right** to turn that control down or up. Hold it and it
   auto-repeats.

That's the whole interface. Play a note while you tweak a knob to hear the change
live. Try it now: move the marker to **VOLUME** and push Left/Right — the note
gets quieter and louder.

> Throughout this guide, "**select X**" means *push Up/Down until the `>` marker
> is next to X*, and "**turn X up/down**" means *push Right/Left*.

---

## 5. Tutorials

Each tutorial is self-contained. Play a note (or hold one) while you make the
changes so you can hear them.

### 5.1 Shape a sound (the envelope)

The **envelope** controls how a note rises and falls: **ATTACK** (how fast it
fades in), **DECAY** (how fast it drops to the sustain level), **SUSTAIN** (the
level it holds while you hold the key), **RELEASE** (how fast it fades out after
you let go).

**Make an organ (instant on, holds, quick off):**
1. Select **ATTACK**, turn it to **0**.
2. Select **SUSTAIN**, turn it **up high** (12–15).
3. Select **RELEASE**, turn it to **2–3**.
4. Hold a key — it's loud immediately, stays steady, and stops quickly when you
   let go.

**Make a soft pad (slow swell):**
1. **ATTACK** up to **6–8** — now notes fade in slowly.
2. **RELEASE** up to **8+** — they fade out slowly too.
3. Hold OPTION and tap a few notes — a slow, swelling chord.

**Make a pluck (decays even while held):**
1. **ATTACK 0**, **DECAY 4**, **SUSTAIN 0**.
2. Hold a key — it plucks and dies away on its own.

### 5.2 Add vibrato (the LFO)

The **LFO** wobbles the pitch up and down for vibrato.

1. Select **LFO DEPTH**, turn it up to about **6**. Play a note — hear the pitch
   wobble.
2. Select **LFO RATE** and adjust how *fast* it wobbles.
3. Turn **LFO DEPTH** back to **0** to switch vibrato off.

Small depth + medium rate = a gentle shimmer. Big depth + slow rate = a deep,
slow bend.

### 5.3 Make it fat (detune)

**DETUNE** spreads the four voices slightly apart so they beat against each other
for a thick, chorused sound.

1. Select **DETUNE**, turn it up to **8–12**.
2. Tap several notes in quick succession (so more than one voice is ringing) —
   hear the shimmer/beating. Lower notes give a nice slow chorus.
3. Turn DETUNE to **0** for perfectly clean tuning.

### 5.4 Get in tune (16-bit mode)

By default (NORMAL clock) the synth plays in a high register and high notes are a
little out of tune. For accurate, in-tune pitch across the whole keyboard:

1. Select **CLOCK**.
2. Turn it to **16-BIT**.

Now the keyboard is tuned to concert pitch and stays in tune up high. (Trade-off:
16-bit mode plays **two notes at once** instead of four.) Turn CLOCK back to
**NORMAL** for the brighter, 4-voice default.

### 5.5 A gliding lead (portamento)

**Portamento** makes each new note *slide* from the previous one.

1. Select **PORTA** (it's on page 2 — scroll Down past the page-1 controls).
2. Turn it up to **6–10**.
3. Play a note, then another — the pitch glides between them. (With portamento
   on, the synth plays one note at a time, like a classic mono lead.)
4. Turn PORTA to **0** for normal, instant notes.

### 5.6 Arpeggios

Hold one key and let the synth play a repeating chord pattern.

1. Select **ARP** (page 1), turn it up to about **8**.
2. **Hold** a key — you'll hear a 4-note arpeggio built from that note. Higher
   ARP = faster.
3. Select **ARP MODE** (page 2) and try the patterns: **UP**, **DOWN**, **MINOR**,
   **OCT** (octave bounce).
4. Turn ARP to **0** to play normally again.

### 5.7 Brighten up (high-pass filter)

The **HP FILTER** removes low frequencies to thin out and brighten the sound.

1. Select **HP FILTER** (page 3 — scroll Down past portamento/drum).
2. Turn it up — the sound gets progressively thinner and brighter.
3. Turn it to **0** to switch the filter off.

(The filter affects the main voice; it works in NORMAL and 15 kHz modes.)

### 5.8 Add drums

There's a drum voice. First **enable it**, then trigger it.

1. Select **DRUM** (page 2), turn it up to about **8**. This switches the drum on
   and sets how long each hit rings. (On its own, nothing happens yet — you need
   to *trigger* it.)
2. **Tap the `1` key** — you get a drum hit each time. With DRUM turned up the
   hits ring longer; turned low they're tight and short.

**Want an automatic beat?**
3. Select **DRUMBEAT** (page 3) and turn it up. Now the drum pulses on its own,
   in time with the **TEMPO** control. Higher DRUMBEAT = more frequent hits.
   Turn DRUMBEAT to **0** to stop the auto-beat.

> If you turn DRUM (or DRUMBEAT) up and hear nothing: remember **DRUM must be
> above 0** to enable the drum at all, and you still need a trigger — tap `1`, or
> turn DRUMBEAT up, or sequence it (next section).

### 5.9 Record a pattern (the sequencer)

The sequencer records a 16-step loop. The console keys drive it:

- **START** = play / stop
- **SELECT** = record

Scroll to **page 2** (select TEMPO/ARP MODE/PORTA/DRUM) to see the step grid.

**Easiest way — play it in (real-time record):**
1. Press **SELECT** once. This clears the pattern and starts recording in time.
2. **Play notes** on the keyboard — they're captured onto the beat as you play.
3. Press **SELECT** again to stop recording. The loop keeps playing.
4. Press **START** to stop playback (and again to start it). Adjust **TEMPO** to
   taste.

Playing more notes while recording **overdubs** (adds to) the pattern, so you can
build it up in layers.

**Precise way — one step at a time (step entry):**
1. Press **SELECT** to arm recording, then press **START** to *stop the clock*.
2. Now each key you press fills **one step** and moves to the next. Build the
   melody note by note.
3. Press **START** to play your pattern back.

### 5.10 Add a drum lane to your pattern

Once you've recorded a melody, lay drums into the same pattern:

1. With the sequencer recording (real-time, from 5.9), make sure **DRUM** is
   turned up (page 2).
2. **Tap the `1` key on the beats you want a drum.** Those become drum hits in
   the pattern.
3. Stop recording (**SELECT**). Play it back (**START**) — melody and drums play
   together from the one loop.

### 5.11 Save and recall your sounds (presets)

There are **4 preset slots**, pre-loaded with starter sounds (INIT, PAD, LEAD,
ARP).

**Load a preset:**
1. Select **PRESET** (page 3).
2. Turn it Left/Right to pick a slot (0–3) — the sound changes the moment you
   land on a slot. Try them all.

**Save your own sound into a slot:**
1. Dial in a sound you like (any of the controls above).
2. Select **PRESET** and pick the slot you want to overwrite.
3. **Press the joystick fire button** — your current sound is saved into that
   slot.

Now you can switch away and come back to it any time by selecting that slot.

---

## 6. Controls cheat sheet

**Keyboard**
- `Q W E R T Y U I O P` — white notes (C D E F G A B C D E)
- `2 3 5 6 7 9 0` — black notes (sharps)
- `1` — drum hit (needs DRUM > 0)

**Joystick (port 1)**
- Up / Down — move the `>` marker (select a control; pages flip automatically)
- Left / Right — turn the selected control down / up
- Fire — save the current sound to the selected preset slot (when PRESET is
  selected)

**Console keys**
- START — sequencer play / stop
- SELECT — sequencer record (real-time; press START while armed for step entry)
- OPTION — sustain pedal (hold to keep notes ringing)

**The three panel pages** (reached by scrolling Up/Down)
- Page 1: WAVEFORM, VOLUME, OCTAVE, ATTACK, DECAY, DETUNE, SUSTAIN, RELEASE,
  CLOCK, LFO RATE, LFO DEPTH, ARP
- Page 2: TEMPO, ARP MODE, PORTA, DRUM (+ the step grid)
- Page 3: HP FILTER, PRESET, DRUMBEAT

---

## 7. Troubleshooting / FAQ

**I turned a knob (DRUM / DRUMBEAT) but hear nothing.**
The drum needs **DRUM above 0** to be enabled *and* a trigger: tap key `1`, turn
**DRUMBEAT** up for an auto-beat, or sequence it. DRUM alone just sets how the hit
sounds.

**I can't play a chord by holding several keys.**
The Atari keyboard only senses one key at a time. Tap notes in quick succession,
or hold **OPTION** (sustain pedal) and tap them — they'll ring together.

**The notes sound too high / a bit out of tune.**
That's the default NORMAL clock (it plays in a high register and high notes are
coarsely tuned). Set **CLOCK** to **16-BIT** for accurate, in-tune pitch.

**My melody plays but a held note keeps re-triggering / clicking in the loop.**
Hold the note longer while recording — held notes are stored as one strike plus
"ties" so they sustain smoothly. Very short rests between notes can sound choppy;
that's normal.

**I can't find a control.**
Keep pushing Up or Down — the selection scrolls through *all* controls across all
three pages and wraps around. Watch the `>` marker.

**Changing the OCTAVE didn't change a note that's already playing.**
Octave only affects the *next* note you play; notes already ringing keep their
pitch.

**The sequencer won't record drums.**
Make sure **DRUM > 0** first, then tap `1` while recording.

---

## 8. Tips

- **Play while you tweak.** Hold a note (or use OPTION) and adjust a knob to hear
  what it does in real time.
- **Start from a preset.** Load a slot you like (5.11), then tweak from there.
- **For a clean lead:** 16-BIT clock + a little LFO DEPTH; add HP FILTER to
  brighten, or PORTA for slides.
- **For a pad:** slow ATTACK and RELEASE, high SUSTAIN, a touch of DETUNE, held
  with OPTION.
- **Build a groove:** record a short melody (5.9), overdub a drum lane (5.10),
  set the TEMPO, and let it loop while you play over the top.
- **Lost the sound you had?** If you saved it to a preset (5.11), just reselect
  that slot.

Have fun!
