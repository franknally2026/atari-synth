"""synthtest — acoustic + timeline test framework for atari-synth.

Layers:
  notes     pitch maths + AUDF/divider->Hz prediction (parses synth.asm tables)
  dsp       PCM analysis (pitch, timbre, ADSR envelope, vibrato, beat, silence)
  harness   Synth: launch/boot headless AltirraSDL, pokes/peeks, play, freeze,
            register/level Timeline capture, and PCM AUDIO_RECORD capture
  scenario  Timeline, Reporter, assert_* helpers, effect-combination matrix
  scenarios/  the actual tests (core engine, acoustic, combinations)

Run:  python3 -m tools.synthtest.run        (from the repo root)
"""
from . import notes, dsp, scenario, harness  # noqa: F401
