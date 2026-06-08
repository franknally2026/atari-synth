# synthtest — acoustic + timeline test framework for atari-synth

A regression and feature-acceptance harness that verifies the synth **by what it
sounds like**, not just by what its registers say at one instant. Built because
point-in-time register peeks missed the sequencer near-silence bug: AUDF/AUDC
"looked fine" while the note collapsed to silence one frame after attack.

## Two layers

1. **Acoustic (PCM + DSP).** Records the real mixed POKEY output to a WAV via the
   `AUDIO_RECORD` bridge command and analyses it: fundamental pitch (Hz),
   timbre/spectrum (waveform identity), amplitude/ADSR envelope, vibrato rate &
   depth, detune beating, and true silence. This is the only way to confirm
   things registers can't — e.g. the **real output frequency in 16-bit mode**,
   and that an effect actually *sounds* the way it should.

2. **Timeline (deterministic).** Captures POKEY registers + per-voice envelope
   levels **every frame** and asserts on the whole trajectory (e.g. "a held
   note's level never collapses after onset"). No emulator audio needed; fast
   and precise. This is the direct guard against the sequencer-bug class.

Plus an **effect-combination matrix**: curated musical presets (including the
`SUS=3 + LFO=7 + ARP=2` case) and an automated **pairwise** cover of every
effect-pair, each asserted to stay audible and non-collapsing.

## Run

```sh
python3 -m tools.synthtest.run             # everything
python3 -m tools.synthtest.run acoustic    # only the acoustic group
python3 -m tools.synthtest.run --no-audio  # skip PCM capture (timeline only)
```

Boots `synth.xex` once under headless AltirraSDL, runs every scenario, prints a
grouped PASS/FAIL summary, exits non-zero on any failure. WAVs land in
`shots/audio/`, screenshots in `shots/`.

## Layout

| File | Role |
|---|---|
| `notes.py` | pitch maths; AUDF/16-bit divider → Hz; parses the chromatic tables straight from `synth.asm` |
| `dsp.py` | PCM analysis (FFT autocorrelation pitch, spectral timbre, RMS/ADSR envelope, vibrato, beat) |
| `harness.py` | `Synth`: launch/boot/teardown, pokes/peeks, `play()`, `frozen()`, register/level `timeline()`, PCM `capture()` |
| `scenario.py` | `Timeline`, `Reporter`, `assert_*` acoustic/timeline helpers, combo-matrix generators |
| `scenarios/core.py` | engine + UI behaviour (timeline-based): defaults, play, polyphony, ADSR, GR.8 UI, param nav/clamp, 2-page nav, selector/toggle glyphs, VU meters |
| `scenarios/acoustic.py` | real-sound checks: pitch, label==pitch, octave/semitone tuning, all 3 clock modes, OCTAVE knob, VOLUME, ADSR timing, LFO rate, arpeggiator, chords, timbre, vibrato, detune |
| `scenarios/sequencer.py` | transport, multi-step playback, step-entry + real-time record, ties, loop length, PCM playback |
| `scenarios/arpmodes.py` | ARP modes (UP/DOWN/MINOR/OCT) patterns + acoustic; TEMPO-adjust regression |
| `scenarios/portamento.py` | portamento glide: AUDF ramp, audible pitch slide, rate scaling, off=instant |
| `scenarios/drum.py` | drum voice: live '1'-key hit + drum-lane recording + DRUMBEAT auto-beat + $FD seq trigger, channel-4 decay, noise timbre, decay scaling, coexists with melody |
| `scenarios/hpfilter.py` | high-pass filter: AUDCTL bit2 + ch3 cutoff clock, low-fundamental removal, cutoff scaling, 16-bit disable |
| `scenarios/presets.py` | patch presets: load on slot select, fire-to-save, factory bank, distinct patches, audibly different |
| `scenarios/stress.py` | unusual/widest scenarios: note-range extremes + clamp, LFO AUDF 8-bit wraparound, rapid clock-mode thrashing, conflicting effects (porta+arp, drum+HP, seq+arp, porta in 16-bit), mega-stack, degenerate sequencer patterns, extreme ADSR, octave-change-while-ringing, rapid retrigger, and the silence-after-chaos integrity guard |
| `scenarios/quantitative.py` | *exact* measurements & property sweeps: full-range 16-bit tuning (<25c), octave-doubling across the keyboard, loudness monotonic over all 16 levels, ADSR steps every (rate+1) frames, sustain=min(sus,vol) tracking, LFO depth scaling, detune beat frequency = AUDF-spread Hz, waveform harmonic identity (odd_even, SQUARE≡PURE) |
| `scenarios/timing.py` | rhythm from the rendered audio (inter-onset interval = tempo) + exact per-frame step counts (seq (16-tempo)*2+2, arp 16-rate, drum-beat period) |
| `scenarios/workflow.py` | multi-stage / end-to-end: record→play→verify, melody+drum in one pattern, full 17-param preset round-trip, factory golden (audible + brightness ordering), capture determinism, and a full user session (build→save→record→play→load→reload) with audio checkpoints |
| `scenarios/combos.py` | curated presets + pairwise matrix + stacked acoustic combos + held-note no-collapse |

## Adding a test

A scenario is just `def my_scenario(s, rep): ...` that drives the `Synth` and
records checks via `rep.check(name, ok, detail)` or the `assert_*` helpers.
Register it in `scenarios/__init__.py` as `(my_scenario, needs_audio)`.

To hold a steady note for acoustic analysis (the cooked bridge key can't sustain
a key), freeze the voice manager and drive a voice directly:

```python
with s.frozen("trigger_voices"):
    s.set("wave", 1); s.set("volume", 13); s.set("sus", 14)
    s.set("vnote", 24, 0); s.set("vlevel", 14, 0)
    s.set("vphase", PH_SUSTAIN, 0); s.set("held", 0)
    clip = s.capture("my_tone", frames=30)   # ~0.6 s of PCM
    assert_pitch_hz(rep, clip, "my_tone", expect_hz=261.6)
```

## The emulator side

`AUDIO_RECORD start path=<file> [raw] [stereo]` / `stop` / `status` is added in
`AltirraSDL/src/AltirraSDL/source/bridge/bridge_commands_audio.cpp`. It attaches
an `ATAudioWriter` as the audio output tap, which captures the mixed POKEY
output (pre-resample) and writes a 44.1 kHz mono 16-bit WAV — working in
`--headless` because the tap is independent of the output device. The command is
compiled only into the GUI `AltirraSDL` target (guarded by
`ALTIRRA_BRIDGE_AUDIO_REC`); the headless `AltirraBridgeServer` target, which
doesn't link `ATAudioWriter`, is unaffected.
