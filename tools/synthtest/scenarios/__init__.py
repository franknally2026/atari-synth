"""Scenario registry.

Each entry: (callable, needs_audio). needs_audio scenarios are skipped (and
reported as skipped, not failed) when the emulator build lacks the
AUDIO_RECORD bridge command, so the framework degrades gracefully.
"""
from . import (bridge, core, acoustic, combos, sequencer, arpmodes, portamento,
               drum, hpfilter, presets, stress, quantitative, timing, workflow,
               input)

# (scenario, needs_audio). Sequencer behavioural checks don't need audio; only
# its PCM playback check does.
# core.defaults_and_silence asserts on boot state and must run first; bridge
# scenarios mutate state (joystick navigation, voice pokes), so they sit
# after core. Stale-AltirraSDL detection happens in Synth.boot()'s
# capability probe before any scenario runs.
REGISTRY = (
    [(fn, False) for fn in core.SCENARIOS]
    + [(fn, False) for fn in bridge.SCENARIOS]
    + [(fn, True) for fn in acoustic.SCENARIOS]
    + [(acoustic.clock_switch_voice_wrap, True)]
    + [(sequencer.transport, False),
       (sequencer.realtime_arm_clears_and_runs, False),
       (sequencer.multi_step_playback, False),
       (sequencer.step_entry_record, False),
       (sequencer.loop_length_wraps, False),
       (sequencer.realtime_record, False),
       (sequencer.realtime_record_monitors_pattern, False),
       (sequencer.realtime_overdub_keeps_existing, False),
       (sequencer.realtime_record_drum_tap, False),
       (sequencer.realtime_held_drum_no_tie, False),
       (sequencer.drum_step_sounds_during_record, False),
       (sequencer.rest_releases_note_on_playback, False),
       (sequencer.tie_sustains_no_reattack, False),
       (sequencer.grid_glyphs, False),
       (sequencer.head_marks_active_step, False),
       (sequencer.playback_audible, True)]
    + [(arpmodes.arpmode_param, False),
       (arpmodes.arpmode_patterns, False),
       (arpmodes.arpmode_direction, False),
       (arpmodes.arpmode_acoustic, True),
       (arpmodes.tempo_adjust_fixed, False)]
    + [(portamento.porta_param, False),
       (portamento.porta_register_ramp, False),
       (portamento.porta_pitch_glide_acoustic, True),
       (portamento.porta_rate_scales, False),
       (portamento.porta_off_instant, False)]
    + [(drum.drum_param, False),
       (drum.drum_seq_trigger, False),
       (drum.drum_key_fires, False),
       (drum.drum_lane_record, False),
       (drum.drumbeat_param, False),
       (drum.auto_beat, False),
       (drum.drum_decay, False),
       (drum.drum_off, False),
       (drum.drum_acoustic, True),
       (drum.drum_reserves_voice3, False),
       (drum.drum_decay_scales, False),
       (drum.drum_coexists_with_melody, True)]
    + [(hpfilter.hpf_param, False),
       (hpfilter.hpf_register, False),
       (hpfilter.hpf_attenuates_lows, True),
       (hpfilter.hpf_cutoff_scales, True),
       (hpfilter.hpf_disabled_in_16bit, False)]
    + [(presets.preset_param, False),
       (presets.preset_load_recall, False),
       (presets.preset_factory_distinct, False),
       (presets.preset_save_fire, False),
       (presets.preset_changes_sound, True)]
    + [(stress.note_range_extremes, False),
       (stress.lfo_audf_overflow, False),
       (stress.rapid_clock_switch, True),
       (stress.porta_plus_arp, True),
       (stress.mega_combo, True),
       (stress.sequencer_edge_patterns, False),
       (stress.extreme_envelopes, False),
       (stress.rapid_retrigger, False),
       (stress.octave_shift_while_ringing, False),
       (stress.porta_in_16bit, True),
       (stress.drum_plus_hpfilter, False),
       (stress.seq_plus_arp, True),
       (stress.silence_after_chaos, True)]
    + [(quantitative.tuning_sweep_16bit, True),
       (quantitative.octave_sweep, True),
       (quantitative.volume_monotonic, True),
       (quantitative.adsr_frame_timing, False),
       (quantitative.sustain_clamp, False),
       (quantitative.lfo_depth_monotonic, False),
       (quantitative.detune_beat_hz, True),
       (quantitative.waveform_harmonics, True)]
    + [(timing.seq_rhythm_from_audio, True),
       (timing.seq_tempo_exact_frames, False),
       (timing.arp_rate_exact, False),
       (timing.drumbeat_period_exact, False)]
    + [(workflow.record_play_roundtrip, False),
       (workflow.melody_plus_drums, False),
       (workflow.preset_roundtrip_all_params, False),
       (workflow.golden_fingerprints, True),
       (workflow.capture_determinism, True),
       (workflow.full_user_session, True)]
    + [(combos.curated_presets, True),
       (combos.pairwise_matrix, True),
       (combos.arp_plus_effects, True),
       (combos.sixteenbit_plus_effects, True),
       (combos.effects_on_chord, True),
       (combos.combo_timeline_no_collapse, False)]
    # input scenarios run LAST: they poke cur_param/volume and overwrite preset
    # slot 0, so keeping them at the end avoids polluting earlier scenarios.
    + [(fn, False) for fn in input.SCENARIOS]
)
