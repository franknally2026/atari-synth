; ============================================================================
;  ATARI POKEY SYNTH  -  GR.8 bitmap UI
;  Keyboard-playable 4-voice POKEY synth with an ADSR envelope and a drawn
;  control panel (knobs + switches up top, a piano keyboard along the bottom).
;
;  Play:   white keys Q W E R T Y U I O P  (naturals C D E F G A B C D E)
;          black keys 2 3 5 6 7 9 0         (sharps  C# D# F# G# A# C# D#)
;  Panel:  joystick UP/DOWN selects a parameter, LEFT/RIGHT adjusts it.
;
;  Video:  GR.8 (ANTIC mode $0F), 320x192, 1bpp, custom display list.
;  Target: PAL Atari XL/XE.  Assemble with MADS.
; ============================================================================

; ----- OS / hardware equates ------------------------------------------------
RTCLOK  = $12           ; frame counter; +2 ($14) ticks every VBI
ATRACT  = $4D           ; attract-mode timer (clear to suppress colour cycling)
CRSINH  = $02F0         ; cursor inhibit
NOCLIK  = $02DB         ; key-click disable
STICK0  = $0278         ; OS joystick-0 shadow, active low
STRIG0  = $D010         ; joystick-0 trigger (fire), 0 = pressed
SDLSTL  = $0230         ; OS display-list pointer (shadow)
SDMCTL  = $022F         ; OS DMACTL shadow
COLOR1  = $02C5         ; COLPF1 shadow (hi-res foreground luminance)
COLOR2  = $02C6         ; COLPF2 shadow (background)
COLOR4  = $02C8         ; COLBK shadow (border)

CONSOL  = $D01F         ; console keys START/SELECT/OPTION (read, active low)
KBCODE  = $D209         ; raw keyboard scan code
SKSTAT  = $D20F         ; serial/keyboard status (read)
SKCTL   = $D20F         ; serial/keyboard control (write)
AUDF1   = $D200         ; channel-1 frequency divisor
AUDC1   = $D201         ; channel-1 control (distortion | volume)
AUDCTL  = $D208         ; POKEY global audio control

ROMFONT = $E000         ; OS ROM character set (8 bytes/glyph, screen-code index)
FB1     = $4000         ; framebuffer region 1 (scan lines 0..101)
FB2     = $5000         ; framebuffer region 2 (scan lines 102..191)
linetab_lo = $6000      ; 192 bytes: low byte of each scan line's address
linetab_hi = $60C0      ; 192 bytes: high byte
                        ; NOTE: kept ABOVE the framebuffers ($4000-$5E0F) and clear
                        ; of the program/descriptor tables ($2000-$3D59). The old
                        ; $3000 scratch collided with the param_*/p_* tables once the
                        ; code grew past $3000 (build_linetab clobbered the label
                        ; pointers -> draw_page_labels looped forever). Don't move it
                        ; back into program space.

KBTOP   = 124           ; piano keyboard top scan line

; ----- zero-page pointers (free OS scratch $CB-$D1) -------------------------
scrptr  = $CB           ; word: general dest pointer
srcptr  = $CD           ; word: source (font / table / string)
adjptr  = $CF           ; word: blit dest line / apply_adjust target

; ----- work variables (free RAM, page 6) ------------------------------------
cur_param   = $0600     ; selected panel parameter 0..7
wave_idx    = $0601     ; 0..3  -> SQUARE/PURE/BUZZ/NOISE
volume      = $0602     ; 0..15 (envelope peak)
octave      = $0603     ; 0..4  (centre 2 = +0)
clock15     = $0604     ; clock/range mode: 0 NORMAL, 1 15KHZ, 2 16-BIT
prev_pressed= $0605
rep_timer   = $0606
note_idx    = $0607     ; current note 0..16, or $FF = none
prev_note   = $0608     ; last highlighted note
pressed     = $0609
edge        = $060A
delta       = $060B
tmpA        = $060C
tmp2        = $060D
cnt         = $060E

; ADSR params (0..15)
atk_rate    = $062C
dec_rate    = $062D
sus_level   = $062E
rel_rate    = $062F
sus_clamp   = $0630

; voices (4)
voice_note  = $0610     ; 4: absolute chromatic index
voice_level = $0614     ; 4: envelope level 0..15
held_voice  = $0618
last_voice  = $0619
vfreq       = $061C
vctl        = $061D
prev_held   = $061E
voice_phase = $0620     ; 4: PH_*
voice_count = $0624     ; 4: frames to next step

; graphics scratch
xlo     = $0640
xhi     = $0641
py      = $0642
s0      = $0643
s1      = $0644
s_dy    = $0645
s_kc    = $0646
s_pc    = $0647
bc_code = $0648
bc_col  = $0649
bc_scan = $064A
bc_inv  = $064B
psi     = $064C
pcnt    = $064D
kcx     = $064E
kcy     = $064F
kfrm    = $0650
rw      = $0651
rh      = $0652
r_x     = $0653
r_xh    = $0654
r_y     = $0655
wxl     = $0656
wxh     = $0657
prev_param = $0658
prev_wave  = $0659
prev_vol   = $065A
prev_oct   = $065B
prev_atk   = $065C
prev_dec   = $065D
prev_sus   = $065E
prev_rel   = $065F
prev_clk   = $0660
pmode      = $0661      ; plot mode: 0 = set pixel, $FF = clear pixel
bc_mode    = $0662      ; blit mode: 0 = set (white on black), $FF = clear (black on white)

; LFO (vibrato) state
lfo_rate    = $0663     ; 0..15 panel param
lfo_depth   = $0664     ; 0..15 panel param
lfo_level_u = $0665     ; unsigned 0..2*lfo_max triangle counter
lfo_dir     = $0666     ; +1 / $FF
lfo_count   = $0667     ; frames to next LFO step
lfo_offset  = $0668     ; signed pitch offset added to AUDF
lfo_max     = $0669
lfo_max2    = $066A
; draw_param scratch (NOT touched by draw_knob/num2)
dp_val      = $066B
dp_numcol   = $066C
dp_scan     = $066D
; DETUNE (fat pitch)
detune      = $066E     ; 0..15 panel param
detune_amt  = $066F     ; detune >> 2 (per-voice AUDF step)
prev_disp   = $0670     ; NPARAM bytes ($0670-$067B): last displayed value
dvoff       = $06C1     ; 4 bytes: per-voice detune AUDF offset (moved up: prev_disp
                        ; grew with NPARAM and reached the old $0680 slot)
; arpeggiator
arp_rate    = $0684     ; 0 = off, 1..15 = step speed
arp_step    = $0685     ; pattern position 0..3
arp_timer   = $0686     ; frames to next arp step
; --- new feature work vars (allocated above the sequencer block at $06B5+ so
;     they stay clear of prev_disp, which grows with NPARAM) ---
arp_mode    = $06B5     ; arpeggiator pattern: 0 UP, 1 DOWN, 2 MINOR, 3 OCTAVE
porta_rate  = $06B6     ; portamento (glide): 0 off, 1..15 = AUDF step every N frames
porta_timer = $06B7     ; frames to next glide step
porta_cur   = $06B8     ; 4: current (gliding) AUDF per voice
porta_step  = $06BC     ; 1 on frames where the glide advances one step
drum_dec    = $06BD     ; DRUM param: 0 off, 1..15 = decay frames per level step
drum_level  = $06BE     ; current drum envelope level (0 = drum channel free)
drum_timer  = $06BF     ; frames to next drum decay step
hpf_cut     = $06C0     ; HP filter: 0 off, 1..15 cutoff (uses ch3 as the clock)
preset_slot = $06C5     ; PRESET param: selected patch slot 0..3
prev_preset = $06C6     ; last slot (detect selection change -> load)
preset_fp   = $06C7     ; previous fire-button state (edge detect for save)
drum_key    = $06C8     ; previous drum-key ('1') state (edge detect for live hit)
drum_beat   = $06C9     ; DRUMBEAT param: 0 off, 1..15 auto drum-machine rate
dbeat_timer = $06CA     ; frames to next tempo beat
dbeat_cnt   = $06CB     ; tempo beats remaining until the next auto drum hit
preset_bank = $0700     ; 4 slots x NSAVE bytes of saved params (page 7, free RAM)
sustain_ped = $0687     ; 1 while OPTION held -> notes don't release
vlimit      = $0688     ; active voice count: 4 (8-bit) or 2 (16-bit)
prev_clkm   = $0689     ; previous clock mode (detect change -> reset voices)
nlo         = $068A     ; 16-bit divider scratch (low/high)
nhi         = $068B
tempo       = $068C     ; sequencer tempo (0..15), page-2 param
page        = $068D     ; current panel page (cur_param / 12)
prev_page   = $068E
pg_base     = $068F     ; first param index of current page
pg_end      = $0690     ; one past last param index of current page
; step sequencer
seq_notes   = $0691     ; 16 steps: semitone 0..16, or $FF = rest
seq_play    = $06A1     ; 0 stopped / 1 playing
seq_rec     = $06A2     ; 0 / 1 record-armed
seq_pos     = $06A3     ; play head 0..15
seq_wpos    = $06A4     ; record write head 0..15
seq_timer   = $06A5     ; frames to next step
seq_prevn   = $06A6     ; previous note (record onset edge)
prev_spos   = $06A7     ; last drawn play head (display diff)
prev_splay  = $06A8
prev_srec   = $06A9
seq_dirty   = $06AA     ; 1 = step grid needs full redraw
con_now     = $06AB     ; console keys pressed bits (active high)
con_prev    = $06AC
; per-voice level meters (VU bars at the top, scan 9-13)
prev_vmeter = $06AD     ; 4: last drawn level per voice (incremental redraw)
dm_lo       = $06B1     ; meter draw scratch: lower envelope level
dm_hi       = $06B2     ; meter draw scratch: higher envelope level
seq_len     = $06B3     ; playback loop length = number of recorded steps (1..16)
rec_latch   = $06B4     ; real-time record: note played since last step ($FF=none)

NPARAM = 19             ; ...page2 16 HPF, 17 PRESET, 18 DRUMBEAT
NSAVE  = 17             ; params 0..16 are saved in a preset (PRESET itself is not)
PG2BASE = 16            ; first param index on page 2 (the third page)
PER_PAGE = 12
K_KNOB = 0              ; 0..15 value -> knob + 2-digit number
K_OCT  = 1              ; octave (0..4) -> knob + signed number
K_WAVE = 2              ; waveform icon selector
K_CLK  = 3              ; NORM|15K toggle

PH_IDLE    = 0
PH_ATTACK  = 1
PH_DECAY   = 2
PH_SUSTAIN = 3
PH_RELEASE = 4

REPDELAY = 15
REPFAST  = 4
DECAYRATE = 4
NUMKEYS  = 17

; ----------------------------------------------------------------------------
        org $2000

main
        lda #1
        sta CRSINH
        lda #$FF
        sta NOCLIK
        lda #$03
        sta SKCTL

        jsr gr8_init            ; set up GR.8 + clear

        ; parameter defaults
        lda #0
        sta cur_param
        sta wave_idx
        sta clock15
        sta prev_pressed
        lda #10
        sta volume
        lda #2
        sta octave
        lda #$FF
        sta note_idx
        sta prev_note
        sta held_voice
        sta prev_held
        lda #REPDELAY
        sta rep_timer
        lda #3
        sta last_voice
        ldx #3
init_voice
        lda #0
        sta voice_level,x
        sta voice_phase,x
        lda #1
        sta voice_count,x
        dex
        bpl init_voice
        lda #0
        sta atk_rate
        lda #2
        sta dec_rate
        lda #8
        sta sus_level
        lda #3
        sta rel_rate

        lda #8                  ; LFO defaults: mid rate, off (depth 0)
        sta lfo_rate
        lda #0
        sta lfo_depth
        sta lfo_level_u
        sta lfo_offset
        lda #1
        sta lfo_dir
        sta lfo_count
        lda #0
        sta detune
        sta arp_rate
        sta arp_step
        sta arp_mode
        sta porta_rate          ; portamento off; glide state cleared
        sta porta_cur
        sta porta_cur+1
        sta porta_cur+2
        sta porta_cur+3
        sta porta_step
        sta drum_dec            ; drum off, idle
        sta drum_level
        sta hpf_cut             ; high-pass filter off
        sta preset_slot         ; preset slot 0, no load/fire pending
        sta prev_preset
        sta preset_fp
        sta drum_key
        sta drum_beat           ; auto drum-beat off
        sta sustain_ped
        sta prev_clkm
        sta page
        sta seq_play
        sta seq_rec
        sta seq_pos
        sta seq_wpos
        sta con_prev
        lda #8
        sta tempo
        lda #1
        sta porta_timer
        sta drum_timer
        sta dbeat_timer
        sta dbeat_cnt
        lda #$FF
        sta prev_page           ; force first-frame page render
        sta seq_prevn
        sta prev_spos
        ldx #15                 ; clear sequencer pattern
        lda #$FF
seq_init
        sta seq_notes,x
        dex
        bpl seq_init
        lda #1
        sta arp_timer
        sta seq_timer
        lda #16                  ; default loop length (empty pattern = silence)
        sta seq_len
        lda #$FF
        sta rec_latch
        ldx #3                   ; VU meters start empty (match cleared screen)
        lda #0
vm_init
        sta prev_vmeter,x
        dex
        bpl vm_init

        lda #$FF                 ; force first-frame redraw of every widget
        sta prev_param
        ldx #NPARAM-1
init_prev
        sta prev_disp,x
        dex
        bpl init_prev

        ldx #4*NSAVE-1           ; copy factory presets into the editable bank
preset_copy
        lda preset_factory,x
        sta preset_bank,x
        dex
        bpl preset_copy

        jsr draw_static_gfx     ; panel labels + piano keyboard (once)

loop
        jsr wait_vbl            ; sync, then draw starting at the frame top
        lda #0
        sta ATRACT
        ; voice count: 16-bit mode (clock 2) uses 2 voices, else 4
        ldx #4
        lda clock15
        cmp #2
        bne lp_vl
        ldx #2
lp_vl
        stx vlimit
        ; reset all voices when the clock/range mode changes (avoid stuck notes)
        lda clock15
        cmp prev_clkm
        beq lp_same
        sta prev_clkm
        ldx #3
lp_clr
        lda #0
        sta voice_level,x
        sta voice_phase,x
        dex
        bpl lp_clr
        lda #$FF
        sta held_voice
        ldx vlimit              ; next note -> voice 0 (and keep last_voice valid
        dex                     ; for the new vlimit after a mode change)
        stx last_voice
lp_same
        jsr read_keyboard
        jsr read_console
        jsr trigger_voices
        jsr drum_key_tick       ; '1' key -> live drum hit (edge)
        jsr update_input
        jsr preset_tick         ; PRESET knob -> load; fire on PRESET -> save
        jsr lfo_tick
        jsr arp_tick
        jsr seq_tick
        jsr drum_beat_tick      ; DRUMBEAT -> auto drum-machine pulse (tempo-synced)
        jsr update_sound
        jsr drum_tick           ; drum overrides channel 4 while a hit rings
        jsr update_display
        jmp loop

; ============================================================================
;  ENGINE  (unchanged from the text-mode version)
; ============================================================================
read_keyboard
        lda SKSTAT
        and #$04
        bne rk_none
        lda KBCODE
        and #$3F
        ldx #NUMKEYS-1
rk_search
        cmp key_scan,x
        beq rk_found
        dex
        bpl rk_search
        cmp #$1F                ; not a pitched key: '1' = the DRUM trigger key
        beq rk_drum
rk_none
        lda #$FF
        sta note_idx
        rts
rk_drum
        lda #$FD                ; $FD = "drum note": flows through live-hit,
        sta note_idx            ; sequencer record (drum lane) and playback
        rts
rk_found
        stx note_idx
        rts

; Console keys (CONSOL $D01F, active low): OPTION (bit2) = sustain pedal (level),
; START (bit0) = play/stop, SELECT (bit1) = record arm (edge-triggered).
; Independent of the scanned key matrix, so they work while a note key is down.
read_console
        lda CONSOL
        eor #$07                ; now 1 = pressed
        and #$07
        sta con_now
        and #$04                ; OPTION -> sustain pedal (level)
        beq rc_noopt
        lda #1
        bne rc_setopt
rc_noopt
        lda #0
rc_setopt
        sta sustain_ped
        lda con_prev            ; edges = now & ~prev
        eor #$FF
        and con_now
        sta tmpA
        and #$01                ; START edge -> toggle play
        beq rc_nostart
        jsr seq_toggle_play
rc_nostart
        lda tmpA
        and #$02                ; SELECT edge -> toggle record
        beq rc_nosel
        jsr seq_toggle_rec
rc_nosel
        lda con_now
        sta con_prev
        rts

seq_toggle_play
        lda seq_play
        eor #1
        sta seq_play
        beq stp_done            ; just stopped
        lda #0                  ; just started: from step 0, fire soon
        sta seq_pos
        lda #1
        sta seq_timer
stp_done
        rts

; SELECT = real-time record: arming clears the pattern and STARTS the clock so
; you just play in time (the live note is captured on the step under the head).
; Disarming punches out but keeps the loop playing. To step-enter instead, stop
; the clock (START) while still armed -> rec + stopped writes one step per key.
seq_toggle_rec
        lda seq_rec
        eor #1
        sta seq_rec
        beq str_done            ; just disarmed -> punch out, keep playing
        ldx #15                 ; arm: clear the pattern
        lda #$FF
str_clr
        sta seq_notes,x
        dex
        bpl str_clr
        lda #0
        sta seq_wpos
        sta seq_len             ; (step entry grows this; real-time loops 16)
        sta seq_pos             ; record from step 0
        lda #$FF
        sta rec_latch
        lda #1
        sta seq_dirty
        sta seq_play            ; run the clock -> real-time record
        lda #16                 ; one full step of lead-in so step 0 is playable
        sec
        sbc tempo
        asl
        clc
        adc #2
        sta seq_timer
str_done
        rts

; ----------------------------------------------------------------------------
;  Step sequencer: record note onsets into a 16-step pattern; when playing,
;  step at the TEMPO rate and trigger each step's note via trigger_note.
; ----------------------------------------------------------------------------
seq_tick
        lda seq_rec             ; --- record: detect a new note onset ---
        beq sq_norec
        lda note_idx
        cmp #$FF
        beq sq_recdone
        cmp seq_prevn
        beq sq_recdone          ; same held note -> not a new onset
        ldy seq_play
        bne sq_latch            ; PLAYING+REC = real-time: latch; clock writes it
        ldx seq_wpos            ; STOPPED+REC = step entry: write here, advance
        sta seq_notes,x
        inx
        cpx seq_len             ; grow loop length to the furthest step filled
        bcc sq_nolen
        stx seq_len
sq_nolen
        cpx #16
        bne sq_wok
        ldx #0
sq_wok
        stx seq_wpos
        lda #1
        sta seq_dirty
        lda note_idx
        jmp sq_recdone
sq_latch
        sta rec_latch           ; real-time: remember the onset for the clock
        lda note_idx
sq_recdone
        sta seq_prevn
        jmp sq_play
sq_norec
        lda #$FF
        sta seq_prevn
        sta rec_latch           ; not armed -> drop any pending latch
sq_play
        lda seq_play            ; --- play / real-time clock ---
        bne sq_playing
        rts
sq_playing
        dec seq_timer
        beq sq_step
        rts
sq_step
        lda #16                 ; reload: interval = (16-tempo)*2 + 2 frames
        sec
        sbc tempo
        asl
        clc
        adc #2
        sta seq_timer
        ldx seq_pos             ; play this step's EXISTING note (timing reference)
        lda seq_notes,x
        cmp #$FE                ; TIE -> a held note continues: do NOT re-strike,
        beq sq_nostep           ; let the sustaining voice ring on (no blips)
        cmp #$FD                ; DRUM hit step
        bne sq_nodrum
        jsr drum_hit
        jmp sq_nostep
sq_nodrum
        cmp #$FF
        bne sq_playnote
        lda seq_rec             ; rest: during playback, release the held note so
        bne sq_nostep           ; the rest is silent (don't cut live monitoring)
        lda #$FF
        sta held_voice
        jmp sq_nostep
sq_playnote
        sta tmpA
        ldy octave
        lda octave_base,y
        clc
        adc tmpA
        jsr trigger_note
sq_nostep
        lda seq_rec             ; real-time: capture the live note into this step
        beq sq_adv
        lda rec_latch           ; a NEW onset latched since the last tick?
        cmp #$FF
        bne sq_cap              ; yes -> write the struck note (re-attack)
        lda note_idx            ; else still holding the same note?
        cmp #$FF
        beq sq_adv              ; nothing held -> leave step (rest)
        lda #$FE                ; held continuation -> TIE (sustains on playback)
sq_cap
        ldx seq_pos
        sta seq_notes,x
        lda #1
        sta seq_dirty
        lda #$FF
        sta rec_latch           ; consume the latch
sq_adv
        inc seq_pos             ; wrap at the recorded length (or 16 if empty)
        ldx seq_len
        bne sq_lim
        ldx #16
sq_lim
        cpx seq_pos
        bne sq_done
        lda #0
        sta seq_pos
sq_done
        rts

update_input
        lda STICK0
        and #$0F
        eor #$0F
        sta pressed
        lda prev_pressed
        eor #$FF
        and pressed
        sta edge
        lda edge
        and #$01
        beq ui_noup
        dec cur_param
        bpl ui_noup
        lda #NPARAM-1
        sta cur_param
ui_noup
        lda edge
        and #$02
        beq ui_nodn
        inc cur_param
        lda cur_param
        cmp #NPARAM
        bne ui_nodn
        lda #0
        sta cur_param
ui_nodn
        lda pressed
        and #$0C
        bne ui_lr_held
        lda #REPDELAY
        sta rep_timer
        jmp ui_done
ui_lr_held
        lda edge
        and #$0C
        bne ui_lr_fresh
        dec rep_timer
        beq ui_lr_repeat
        jmp ui_done
ui_lr_fresh
        lda #REPDELAY
        sta rep_timer
        jmp ui_lr_apply
ui_lr_repeat
        lda #REPFAST
        sta rep_timer
ui_lr_apply
        lda pressed
        and #$04
        beq ui_try_right
        lda #$FF
        sta delta
        jmp ui_adjust
ui_try_right
        lda pressed
        and #$08
        beq ui_done
        lda #$01
        sta delta
ui_adjust
        jsr apply_adjust
ui_done
        lda pressed
        sta prev_pressed
        rts

apply_adjust
        ldx cur_param
        lda param_lo,x
        sta adjptr
        lda param_hi,x
        sta adjptr+1
        ldy #0
        lda (adjptr),y
        clc
        adc delta
        bmi aa_lo
        cmp param_maxp1,x
        bcc aa_store
        lda param_max,x
        jmp aa_store
aa_lo
        lda #0
aa_store
        ldy #0
        sta (adjptr),y
        rts

trigger_voices
        lda arp_rate
        bne tv_done             ; ARP on -> arp_tick triggers notes instead
        lda note_idx
        cmp #$FD                ; $FD(drum)/$FE/$FF are not pitched notes -> no
        bcc tv_keydown          ; voice trigger (the drum is handled separately)
        ; no live key down: normally release everything. But during pure
        ; sequencer PLAYBACK (playing, not recording) leave held_voice alone so
        ; the step's note can sustain its envelope for the whole step instead of
        ; being force-released after one frame (which made it near-silent).
        lda seq_play
        beq tv_relall
        lda seq_rec
        beq tv_done             ; playback -> sequencer manages the gate
tv_relall
        lda #$FF
        sta held_voice
        sta prev_held
        rts
tv_keydown
        cmp prev_held
        beq tv_done
        sta prev_held
        ldy octave              ; abs note = octave base + semitone
        lda octave_base,y
        clc
        adc note_idx
        jsr trigger_note
tv_done
        rts

; trigger_note: A = absolute chromatic index -> grab next voice, start attack
trigger_note
        cmp #65                 ; clamp to chromatic table (0..64)
        bcc tn_ok
        lda #64
tn_ok
        sta tmpA
        lda porta_rate          ; portamento on -> MONOPHONIC glide on voice 0
        beq tn_alloc            ; (the new note slides from the previous pitch)
        ldx #0
        lda voice_phase,x
        bne tn_setnote          ; voice 0 already sounding -> glide from it
        ldy tmpA                ; voice 0 idle -> snap glide origin to target
        lda chromatic,y         ; (so the first note doesn't swoop in)
        sta porta_cur
        jmp tn_setnote
tn_alloc
        ldx last_voice
        inx
        cpx vlimit              ; wrap when x >= vlimit (not just ==): switching
        bcc tn_nowrap           ; to 16-bit drops vlimit 4->2, so a stale
        ldx #0                  ; last_voice of 2/3 must still wrap (else OOB)
tn_nowrap
        stx last_voice
tn_setnote
        lda tmpA
        sta voice_note,x
        lda #0
        sta voice_level,x
        lda #PH_ATTACK
        sta voice_phase,x
        lda atk_rate
        clc
        adc #1
        sta voice_count,x
        stx held_voice
        rts

; ----------------------------------------------------------------------------
;  Arpeggiator: while a key is held and ARP > 0, retrigger a chord pattern
;  (root, +4, +7, +12) from the held note, one step every (16-rate) frames.
; ----------------------------------------------------------------------------
arp_tick
        lda arp_rate
        bne at_on
        rts                     ; ARP off
at_on
        lda note_idx
        cmp #$FF
        bne at_held
        lda #0                  ; no key -> idle; let the last note release
        sta arp_step
        lda #1
        sta arp_timer
        lda #$FF
        sta held_voice
        rts
at_held
        dec arp_timer
        beq at_step
        rts
at_step
        lda #16                 ; reload step interval = 16 - rate (min 1)
        sec
        sbc arp_rate
        bne at_rok
        lda #1
at_rok
        sta arp_timer
        ldy octave              ; base = octave base + held semitone
        lda octave_base,y
        clc
        adc note_idx
        sta tmpA
        lda arp_mode            ; interval = arp_modes[mode*4 + step]
        asl
        asl
        clc
        adc arp_step
        tay
        lda arp_modes,y
        clc
        adc tmpA                ; note = base + interval
        jsr trigger_note
        lda arp_step            ; advance pattern position 0..3
        clc
        adc #1
        and #3
        sta arp_step
        rts
; arpeggiator patterns, 4 steps each, indexed mode*4 + step
arp_modes
        .byte 0,4,7,12          ; 0 UP    (major arp up)
        .byte 12,7,4,0          ; 1 DOWN  (major arp down)
        .byte 0,3,7,12          ; 2 MINOR (minor arp up)
        .byte 0,12,0,12         ; 3 OCT   (octave jump)

; ----------------------------------------------------------------------------
;  Drum voice: a noise-percussion hit on channel 4 (its own subsystem, not the
;  ADSR voice engine). Triggered by a $FD sequencer step. DRUM param = decay
;  length (0 = off). 8-bit clock modes only (in 16-bit, channel 4 is a joined
;  high channel). drum_tick runs after update_sound and overrides channel 4
;  while a hit rings; when it ends, voice 3's normal output resumes.
; ----------------------------------------------------------------------------
DRUM_AUDF = $1E                 ; noise tone of the drum (fixed)
drum_hit
        lda drum_dec            ; DRUM = 0 -> off
        beq dh_off
        lda clock15             ; no drum in 16-bit mode (channel 4 is paired)
        cmp #2
        beq dh_off
        lda #15
        sta drum_level
        lda drum_dec            ; full level held for one decay interval first
        sta drum_timer
dh_off
        rts
drum_tick
        lda drum_level
        bne dt_active
        rts                     ; idle -> leave channel 4 to voice 3
dt_active
        lda drum_dec            ; DRUM turned off -> silence any ringing drum
        beq dt_kill
        lda clock15             ; 16-bit reclaimed channel 4 -> drop the drum
        cmp #2
        bne dt_decay
dt_kill
        lda #0
        sta drum_level
        rts
dt_decay
        dec drum_timer
        bne dt_emit
        lda drum_dec            ; reload decay interval (DRUM param)
        sta drum_timer
        dec drum_level
dt_emit
        lda #DRUM_AUDF
        sta AUDF1+6             ; channel 4 frequency
        lda drum_level          ; AUDC = distortion 0 (white-ish noise) | level
        sta AUDC1+6
        rts

; live drum hit from the '1' key: fire on a fresh press (read_keyboard sets
; note_idx=$FD while '1' is held). Recording captures the $FD via the normal
; sequencer path, so this just gives the immediate audible hit.
drum_key_tick
        lda note_idx
        cmp #$FD
        bne dk_up
        lda drum_key
        bne dk_done             ; still held -> no re-fire
        jsr drum_hit
        lda #1
        sta drum_key
        rts
dk_up
        lda #0
        sta drum_key
dk_done
        rts

; auto drum-machine: when DRUMBEAT>0, fire the drum every (16-DRUMBEAT) tempo
; beats (tempo beat = the sequencer step interval). Free-running (no need to
; start the sequencer); needs DRUM>0 for the hit to sound.
drum_beat_tick
        lda drum_beat
        beq dbt_done            ; off
        dec dbeat_timer
        bne dbt_done
        lda #16                 ; reload one tempo beat = (16-tempo)*2 + 2 frames
        sec
        sbc tempo
        asl
        clc
        adc #2
        sta dbeat_timer
        dec dbeat_cnt
        bne dbt_done
        lda #16                 ; reload spacing = 16 - DRUMBEAT (min 1) and fire
        sec
        sbc drum_beat
        bne dbt_sok
        lda #1
dbt_sok
        sta dbeat_cnt
        jsr drum_hit
dbt_done
        rts

; ----------------------------------------------------------------------------
;  Presets: 4 slots of the 17 sound params (everything except PRESET itself).
;  Selecting a slot with the PRESET knob LOADS it live; pressing FIRE while the
;  PRESET param is selected SAVES the current sound into the slot. The bank is
;  seeded from preset_factory at boot. param_lo/param_hi give each param's
;  address, so save/load just walk those tables.
; ----------------------------------------------------------------------------
preset_tick
        lda STRIG0              ; fire-now: STRIG0 active low (0 = pressed)
        eor #$01
        and #$01
        sta tmpA                ; tmpA = 1 if pressed (survives jsr preset_save,
                                ; which only touches tmp2 — NOT tmpA)
        ldx cur_param
        cpx #17                 ; PRESET param selected?
        bne pt_load
        lda tmpA
        beq pt_load
        lda preset_fp           ; require a fresh press (edge), not a hold
        bne pt_load
        jsr preset_save
        lda preset_slot         ; keep prev in sync so we don't reload after save
        sta prev_preset
pt_load
        lda tmpA                ; remember fire state for next-frame edge detect
        sta preset_fp
        lda preset_slot         ; selection changed -> load that slot
        cmp prev_preset
        beq pt_done
        sta prev_preset
        jsr preset_load
pt_done
        rts

; bank offset of the current slot (slot * NSAVE) -> tmp2
preset_offset
        lda preset_slot
        asl                     ; *16
        asl
        asl
        asl
        clc
        adc preset_slot         ; + slot = *17
        sta tmp2
        rts
preset_save
        jsr preset_offset
        ldx #0
ps_loop
        lda param_lo,x
        sta srcptr
        lda param_hi,x
        sta srcptr+1
        ldy #0
        lda (srcptr),y          ; current param value
        ldy tmp2
        sta preset_bank,y       ; -> bank slot
        inc tmp2
        inx
        cpx #NSAVE
        bne ps_loop
        rts
preset_load
        jsr preset_offset
        ldx #0
pl_loop
        lda param_lo,x
        sta srcptr
        lda param_hi,x
        sta srcptr+1
        ldy tmp2
        lda preset_bank,y       ; saved value
        ldy #0
        sta (srcptr),y          ; -> param
        inc tmp2
        inx
        cpx #NSAVE
        bne pl_loop
        rts
; factory patches: NSAVE bytes each, in param order
;   wave vol oct atk dec det sus rel clk lfor lfod arp tempo arpm porta drum hpf
preset_factory
        .byte 1,10,2,0,2,0, 8,3,0,8,0,0, 8,0,0,0,0          ; 0 INIT
        .byte 1,12,2,6,4,6, 14,8,0,4,5,0, 8,0,0,0,0         ; 1 PAD
        .byte 0,13,3,0,2,0, 10,3,0,9,8,0, 8,0,6,0,4         ; 2 LEAD (porta+HP)
        .byte 0,12,2,0,0,8, 8,2,0,8,0,9, 10,0,0,0,0         ; 3 ARP

update_sound
        lda sus_level
        cmp volume
        bcc us_susok
        lda volume
us_susok
        sta sus_clamp
        ; per-voice detune offsets: dvoff = voice * (detune>>2)
        lda detune
        lsr
        lsr
        sta detune_amt
        lda #0
        sta dvoff
        lda detune_amt
        sta dvoff+1
        asl
        sta dvoff+2
        clc
        adc detune_amt
        sta dvoff+3
        ; portamento step gate: advance the glide one AUDF step every
        ; porta_rate frames (off -> emit snaps to target)
        lda #0
        sta porta_step
        lda porta_rate
        beq us_porta_rdy
        dec porta_timer
        bne us_porta_rdy
        sta porta_timer         ; A still = porta_rate -> reload
        lda #1
        sta porta_step
us_porta_rdy
        ldx #0
us_voice
        lda voice_phase,x
        bne us_active_voice
        jmp us_output           ; idle voice -> level 0 -> silenced in us_output
us_active_voice
        txa
        cmp held_voice
        beq us_tick
        lda sustain_ped         ; OPTION held -> hold this voice, don't release
        bne us_tick
        lda voice_phase,x
        cmp #PH_RELEASE
        beq us_tick
        lda #PH_RELEASE
        sta voice_phase,x
us_tick
        dec voice_count,x
        beq us_step
        jmp us_output
us_step
        ldy voice_phase,x
        lda us_jmp_lo-1,y
        sta adjptr
        lda us_jmp_hi-1,y
        sta adjptr+1
        jmp (adjptr)
us_release
        lda rel_rate
        clc
        adc #1
        sta voice_count,x
        lda voice_level,x
        beq us_rel_idle
        dec voice_level,x
        lda voice_level,x
        bne us_rel_done
us_rel_idle
        lda #PH_IDLE
        sta voice_phase,x
us_rel_done
        jmp us_output
us_attack
        lda atk_rate
        clc
        adc #1
        sta voice_count,x
        inc voice_level,x
        lda voice_level,x
        cmp volume
        bcc us_atk_done
        lda volume
        sta voice_level,x
        lda #PH_DECAY
        sta voice_phase,x
us_atk_done
        jmp us_output
us_decay
        lda dec_rate
        clc
        adc #1
        sta voice_count,x
        lda voice_level,x
        cmp sus_clamp
        bcc us_dec_sus
        beq us_dec_sus
        dec voice_level,x
        lda voice_level,x
        cmp sus_clamp
        bne us_dec_done
us_dec_sus
        lda sus_clamp
        sta voice_level,x
        lda #PH_SUSTAIN
        sta voice_phase,x
us_dec_done
        jmp us_output
us_sustain
        lda #1
        sta voice_count,x
        lda sus_clamp
        sta voice_level,x
us_output
        lda clock15
        cmp #2
        beq us_out16            ; 16-bit (joined-pair) path
        ; ---- 8-bit output (4 voices, one channel each) ----
        lda voice_level,x
        bne us_emit8
        txa                     ; idle -> silence this channel
        asl
        tay
        lda #0
        sta AUDC1,y
        jmp us_next
us_emit8
        ldy voice_note,x
        lda chromatic,y         ; target AUDF for this note
        sta tmpA
        lda porta_rate          ; --- portamento glide ---
        beq us_pt_snap          ; off -> snap to target
        lda porta_step
        beq us_pt_use           ; not a glide-step frame -> hold current
        lda porta_cur,x         ; step porta_cur one AUDF toward target
        cmp tmpA
        beq us_pt_use
        bcs us_pt_dn
        inc porta_cur,x
        jmp us_pt_use
us_pt_dn
        dec porta_cur,x
        jmp us_pt_use
us_pt_snap
        lda tmpA
        sta porta_cur,x
us_pt_use
        lda porta_cur,x
        clc
        adc lfo_offset
        clc
        adc dvoff,x
        sta vfreq
        ldy wave_idx
        lda wave_base,y
        ora voice_level,x
        sta vctl
        txa
        asl
        tay
        lda vfreq
        sta AUDF1,y
        lda vctl
        sta AUDC1,y
        jmp us_next
        ; ---- 16-bit output: voice x -> channel pair (2x lo, 2x+1 hi) ----
        ; AUDF lo->lo channel, hi->hi channel; volume on the HIGH channel.
us_out16
        txa
        asl
        asl
        tay                     ; Y = x*4 = low-channel offset
        lda voice_level,x
        bne us_emit16
        lda #0                  ; idle -> silence both channels of the pair
        sta AUDC1,y
        sta AUDC1+2,y
        jmp us_next
us_emit16
        ldy voice_note,x        ; N = chrom16[note]
        lda chrom16_lo,y
        sta nlo
        lda chrom16_hi,y
        sta nhi
        lda lfo_offset          ; + vibrato (signed 16-bit)
        bmi u16_lneg
        clc
        adc nlo
        sta nlo
        lda nhi
        adc #0
        sta nhi
        jmp u16_det
u16_lneg
        clc
        adc nlo
        sta nlo
        lda nhi
        adc #$FF
        sta nhi
u16_det
        clc                     ; + detune (positive)
        lda nlo
        adc dvoff,x
        sta nlo
        lda nhi
        adc #0
        sta nhi
        ldy wave_idx            ; AUDC for the audible (high) channel
        lda wave_base,y
        ora voice_level,x
        sta vctl
        txa
        asl
        asl
        tay                     ; Y = x*4
        lda nlo
        sta AUDF1,y             ; low byte -> low channel
        lda #0
        sta AUDC1,y             ; low channel silent
        lda nhi
        sta AUDF1+2,y           ; high byte -> high channel
        lda vctl
        sta AUDC1+2,y           ; output on high channel
us_next
        inx
        cpx vlimit
        beq us_loopdone
        jmp us_voice
us_loopdone
        ldx clock15
        lda audctl_tab,x
        ; high-pass filter (8-bit modes): channel 1 is high-passed, clocked by
        ; channel 3. Sacrifice voice 2's channel 3 as the (silent) cutoff clock.
        ; Higher HPF -> smaller AUDF3 -> higher cutoff -> more low-end removed.
        ldy hpf_cut
        beq us_nohp
        cpx #2                  ; not available in 16-bit (channel 3 is paired)
        beq us_nohp
        ora #$04                ; AUDCTL bit2: high-pass ch1 via ch3
        sta AUDCTL
        lda #16                 ; AUDF3 = (16 - HPF) * 4  (cutoff clock)
        sec
        sbc hpf_cut
        asl
        asl
        sta AUDF1+4             ; channel 3 frequency = cutoff
        lda #$A0                ; pure tone, volume 0 -> runs as clock, silent
        sta AUDC1+4             ; channel 3 control
        rts
us_nohp
        sta AUDCTL
        rts
audctl_tab
        .byte $00,$01,$78       ; NORMAL / 15kHz / 16-bit (join+1.79MHz both pairs)

us_jmp_lo
        .byte <us_attack, <us_decay, <us_sustain, <us_release
us_jmp_hi
        .byte >us_attack, >us_decay, >us_sustain, >us_release

wait_vbl
        lda RTCLOK+2
wv_l
        cmp RTCLOK+2
        beq wv_l
        rts

; ----------------------------------------------------------------------------
;  LFO (vibrato): a triangle that ramps a signed pitch offset between
;  -lfo_max and +lfo_max; rate sets step interval, depth sets amplitude.
;  No multiply: lfo_level_u counts 0..2*max, offset = level - max.
; ----------------------------------------------------------------------------
lfo_tick
        lda lfo_depth           ; depth 0 -> LFO fully off, instantly flat
        bne lt_on               ; (don't let the triangle counter decay slowly,
        sta lfo_offset          ;  which would leave a residual pitch offset)
        sta lfo_level_u
        rts
lt_on
        lsr                     ; amplitude = depth/2 (0..7)
        sta lfo_max
        dec lfo_count
        beq lt_step
        rts
lt_step
        lda #16                 ; reload: rate 0 -> slow (16), 15 -> fast (1)
        sec
        sbc lfo_rate
        sta lfo_count
        lda lfo_max
        asl
        sta lfo_max2            ; 2*max
        lda lfo_dir
        bmi lt_down
        inc lfo_level_u         ; ramp up
        lda lfo_level_u
        cmp lfo_max2
        bcc lt_offset
        lda lfo_max2            ; hit top -> clamp, reverse
        sta lfo_level_u
        lda #$FF
        sta lfo_dir
        jmp lt_offset
lt_down
        lda lfo_level_u
        beq lt_rev_up           ; at 0 -> reverse
        dec lfo_level_u
        jmp lt_offset
lt_rev_up
        lda #1
        sta lfo_dir
lt_offset
        lda lfo_level_u         ; offset = level - max  (signed)
        sec
        sbc lfo_max
        sta lfo_offset
        rts

; ============================================================================
;  GR.8 SETUP
; ============================================================================
gr8_init
        jsr build_linetab
        jsr clear_fb
        lda #$00                ; black background + border
        sta COLOR2
        sta COLOR4
        lda #$0E                ; bright foreground (luminance in hi-res)
        sta COLOR1
        lda #<dlist
        sta SDLSTL
        lda #>dlist
        sta SDLSTL+1
        lda #$22                ; normal width + screen DMA (OS VBI -> DMACTL)
        sta SDMCTL
        rts

; build the 192-entry scan-line address table (hides the FB1/FB2 split)
build_linetab
        lda #<FB1
        sta scrptr
        lda #>FB1
        sta scrptr+1
        ldx #0
blt1
        lda scrptr
        sta linetab_lo,x
        lda scrptr+1
        sta linetab_hi,x
        clc
        lda scrptr
        adc #40
        sta scrptr
        bcc blt1n
        inc scrptr+1
blt1n
        inx
        cpx #102
        bne blt1
        lda #<FB2
        sta scrptr
        lda #>FB2
        sta scrptr+1
blt2
        lda scrptr
        sta linetab_lo,x
        lda scrptr+1
        sta linetab_hi,x
        clc
        lda scrptr
        adc #40
        sta scrptr
        bcc blt2n
        inc scrptr+1
blt2n
        inx
        cpx #192
        bne blt2
        rts

; zero the framebuffer ($4000-$5FFF, 8K, covers both regions)
clear_fb
        lda #<FB1
        sta scrptr
        lda #>FB1
        sta scrptr+1
        lda #0
        ldx #32
        tay
cf_l
        sta (scrptr),y
        iny
        bne cf_l
        inc scrptr+1
        dex
        bne cf_l
        rts

; ============================================================================
;  GRAPHICS PRIMITIVES
; ============================================================================
; set one pixel: x = xhi:xlo (0..319), y = py (0..191)
plot
        lda xlo
        lsr
        lsr
        lsr
        sta tmpA                ; xlo>>3
        lda xhi
        beq pl_nohi
        lda tmpA
        clc
        adc #32                 ; + 256/8
        sta tmpA
pl_nohi
        ldy py
        lda linetab_lo,y
        clc
        adc tmpA
        sta scrptr
        lda linetab_hi,y
        adc #0
        sta scrptr+1
        lda xlo
        and #7
        tax
        lda bitmask_tab,x
        ldy pmode
        bne pl_clear
        ldy #0
        ora (scrptr),y
        sta (scrptr),y
        rts
pl_clear
        eor #$FF
        ldy #0
        and (scrptr),y
        sta (scrptr),y
        rts

; horizontal run of A pixels from (xlo:xhi,py), advancing x
hline
        sta s0
hl_l
        jsr plot
        inc xlo
        bne hl_nc
        inc xhi
hl_nc
        dec s0
        bne hl_l
        rts

; vertical run of A pixels from (xlo:xhi,py) downward
vline
        sta s0
vl_l
        jsr plot
        inc py
        dec s0
        bne vl_l
        rts

; rectangle outline: left=xlo:xhi, top=py, width=rw, height=rh
rect
        lda xlo
        sta r_x
        lda xhi
        sta r_xh
        lda py
        sta r_y
        lda rw                  ; top edge
        jsr hline
        lda r_x                 ; bottom edge
        sta xlo
        lda r_xh
        sta xhi
        lda r_y
        clc
        adc rh
        sec
        sbc #1
        sta py
        lda rw
        jsr hline
        lda r_x                 ; left edge
        sta xlo
        lda r_xh
        sta xhi
        lda r_y
        sta py
        lda rh
        jsr vline
        clc                     ; right edge x = left + rw - 1
        lda r_x
        adc rw
        sta xlo
        lda r_xh
        adc #0
        sta xhi
        sec
        lda xlo
        sbc #1
        sta xlo
        lda xhi
        sbc #0
        sta xhi
        lda r_y
        sta py
        lda rh
        jsr vline
        rts

; filled rectangle: left=xlo:xhi, top=py, width=rw, height=rh
fillrect
        lda xlo
        sta r_x
        lda xhi
        sta r_xh
        ldx rh
fr_l
        lda r_x
        sta xlo
        lda r_xh
        sta xhi
        txa
        pha
        lda rw
        jsr hline
        pla
        tax
        inc py
        dex
        bne fr_l
        rts

; ============================================================================
;  TEXT (blit 8x8 ROM-font glyphs; screen-code index)
; ============================================================================
; blit glyph bc_code at byte column bc_col, scan line bc_scan (EOR bc_inv)
; uses scrptr for the font pointer so the caller's srcptr (string) survives
blit_char
        lda bc_code
        sta s0
        lda #0
        sta s1
        asl s0
        rol s1
        asl s0
        rol s1
        asl s0
        rol s1                  ; s1:s0 = code*8
        lda s0
        sta scrptr
        lda s1
        clc
        adc #>ROMFONT
        sta scrptr+1
        ldx #0
bc_l
        txa
        clc
        adc bc_scan
        tay
        lda linetab_lo,y
        clc
        adc bc_col
        sta adjptr
        lda linetab_hi,y
        adc #0
        sta adjptr+1
        txa
        tay
        lda (scrptr),y
        eor bc_inv
        ldy bc_mode
        beq bc_set
        eor #$FF                ; clear mode: dest AND (NOT glyph)
        ldy #0
        and (adjptr),y
        sta (adjptr),y
        jmp bc_step
bc_set
        ldy #0
        sta (adjptr),y
bc_step
        inx
        cpx #8
        bne bc_l
        rts

; print $FF-terminated screen-code string srcptr at bc_col,bc_scan
print_strz
        lda #0
        sta psi
ps_l
        ldy psi
        lda (srcptr),y
        cmp #$FF
        beq ps_done
        sta bc_code
        jsr blit_char
        inc bc_col
        inc psi
        jmp ps_l
ps_done
        rts

; print pcnt screen-code bytes from srcptr at bc_col,bc_scan
print_n
        lda #0
        sta psi
pn_l
        ldy psi
        lda (srcptr),y
        sta bc_code
        jsr blit_char
        inc bc_col
        inc psi
        lda psi
        cmp pcnt
        bne pn_l
        rts

; draw A (0..99) as two digits at bc_col,bc_scan (advances bc_col by 2)
num2
        ldx #0
n2_l
        cmp #10
        bcc n2_done
        sec
        sbc #10
        inx
        jmp n2_l
n2_done
        pha
        txa
        clc
        adc #$10
        sta bc_code
        jsr blit_char
        inc bc_col
        pla
        clc
        adc #$10
        sta bc_code
        jsr blit_char
        inc bc_col
        rts

; ============================================================================
;  KNOB  (ring + pointer; centre kcx,kcy, position kfrm 0..15)
; ============================================================================
draw_knob
        jsr clr_knob_box
        lda #0
        sta pmode
        sta xhi
        ldx #0
dkc
        stx s_dy
        lda hw_tab,x
        sta s0                  ; half-width for this row
        lda kcy                 ; upper row cy-dy
        sec
        sbc s_dy
        sta py
        lda kcx
        sec
        sbc s0
        sta xlo
        jsr plot
        lda kcx
        clc
        adc s0
        sta xlo
        jsr plot
        lda kcy                 ; lower row cy+dy
        clc
        adc s_dy
        sta py
        lda kcx
        sec
        sbc s0
        sta xlo
        jsr plot
        lda kcx
        clc
        adc s0
        sta xlo
        jsr plot
        ldx s_dy
        inx
        cpx #7
        bne dkc
        ldx kfrm                ; pointer: rim, mid, centre
        lda kcx
        clc
        adc kn_ex,x
        sta xlo
        lda kcy
        clc
        adc kn_ey,x
        sta py
        jsr plot
        ldx kfrm
        lda kcx
        clc
        adc kn_mx,x
        sta xlo
        lda kcy
        clc
        adc kn_my,x
        sta py
        jsr plot
        lda kcx
        sta xlo
        lda kcy
        sta py
        jsr plot
        rts

; clear a 3-byte x 14-row box around the knob centre (erase before redraw)
clr_knob_box
        lda kcx
        lsr
        lsr
        lsr
        sec
        sbc #1
        sta s0                  ; start byte column
        lda kcy
        sec
        sbc #7
        sta s1                  ; top scan line
        ldx #14
ckb_row
        ldy s1
        lda linetab_lo,y
        clc
        adc s0
        sta scrptr
        lda linetab_hi,y
        adc #0
        sta scrptr+1
        lda #0
        ldy #0
        sta (scrptr),y
        ldy #1
        sta (scrptr),y
        ldy #2
        sta (scrptr),y
        inc s1
        dex
        bne ckb_row
        rts

; ============================================================================
;  STATIC LAYOUT  (drawn once)
; ============================================================================
draw_static_gfx
        lda #0
        sta bc_inv
        sta bc_mode
        ; title
        lda #<txt_title
        sta srcptr
        lda #>txt_title
        sta srcptr+1
        lda #11
        sta bc_col
        lda #0
        sta bc_scan
        jsr print_strz
        ; (parameter labels are drawn per-page by update_display on page change)
        ; NOTE label (top-right, on the title line)
        lda #<txt_note
        sta srcptr
        lda #>txt_note
        sta srcptr+1
        lda #30
        sta bc_col
        lda #0
        sta bc_scan
        jsr print_strz
        jsr draw_keyboard
        rts

draw_keyboard
        ; white keys: 10 FILLED rectangles, 28x56, pitch 30, from x=10
        lda #0
        sta pmode
        lda #10
        sta wxl
        lda #0
        sta wxh
        ldx #0
dkw
        stx s_kc
        lda wxl
        sta xlo
        lda wxh
        sta xhi
        lda #KBTOP
        sta py
        lda #28
        sta rw
        lda #56
        sta rh
        jsr fillrect
        clc
        lda wxl
        adc #30
        sta wxl
        lda wxh
        adc #0
        sta wxh
        ldx s_kc
        inx
        cpx #10
        bne dkw
        ; black keys: CLEAR 7 rectangles, 16x34 (black notches at the top)
        lda #$FF
        sta pmode
        ldx #0
dkb
        stx s_kc
        lda blackx_lo,x
        sta xlo
        lda blackx_hi,x
        sta xhi
        lda #KBTOP
        sta py
        lda #16
        sta rw
        lda #34
        sta rh
        jsr fillrect
        ldx s_kc
        inx
        cpx #7
        bne dkb
        lda #0
        sta pmode
        sta bc_inv
        ; white-key letters ON the keys (black on white)
        lda #$FF
        sta bc_mode
        ldx #0
dwl
        stx s_kc
        lda white_lblcol,x
        sta bc_col
        lda #160
        sta bc_scan
        lda white_lblch,x
        sta bc_code
        jsr blit_char
        ldx s_kc
        inx
        cpx #10
        bne dwl
        ; black-key numbers ON the black keys (white on black)
        lda #0
        sta bc_mode
        ldx #0
dbl
        stx s_kc
        lda black_lblcol,x
        sta bc_col
        lda #128
        sta bc_scan
        lda black_lblch,x
        sta bc_code
        jsr blit_char
        ldx s_kc
        inx
        cpx #7
        bne dbl
        rts

; ============================================================================
;  PER-FRAME DISPLAY
; ============================================================================
; redraw only the widgets whose value changed this frame (no per-frame
; clear/redraw -> no flicker, low cost).
update_display
        lda #0
        sta bc_inv
        sta bc_mode
        ; page ranges: 0 = 0..11 (osc/env/fx), 1 = 12..15 + sequencer grid,
        ; 2 = 16..NPARAM-1 (filter etc.)
        lda cur_param
        cmp #PER_PAGE
        bcc ud_pg0
        cmp #PG2BASE
        bcc ud_pg1
        lda #PG2BASE            ; page 2
        sta pg_base
        lda #NPARAM
        sta pg_end
        lda #2
        sta page
        jmp ud_pgset
ud_pg1
        lda #PER_PAGE           ; page 1 (sequencer)
        sta pg_base
        lda #PG2BASE
        sta pg_end
        lda #1
        sta page
        jmp ud_pgset
ud_pg0
        lda #0
        sta pg_base
        sta page
        lda #PER_PAGE
        sta pg_end
ud_pgset
        ; page change -> clear panel, redraw labels, force value + marker redraw
        lda page
        cmp prev_page
        beq ud_pgsame
        sta prev_page
        jsr clear_panel
        jsr draw_page_labels
        ldx pg_base
        lda #$FF
ud_rst
        sta prev_disp,x
        inx
        cpx pg_end
        bne ud_rst
        lda #$FF
        sta prev_param
        sta prev_spos           ; force sequencer grid/transport redraw on page 2
        sta prev_splay
        sta prev_srec
        lda #1
        sta seq_dirty
        ldx #3                  ; clear_panel wiped the VU bars -> redraw from 0
        lda #0
ud_pgvm
        sta prev_vmeter,x
        dex
        bpl ud_pgvm
ud_pgsame
        ; selection markers (current page; only when the selection moved)
        lda cur_param
        cmp prev_param
        beq ud_nomk
        sta prev_param
        ldx pg_base
ud_mk
        stx s_kc
        lda p_lblcol,x
        sec
        sbc #1
        sta bc_col
        lda p_scan,x
        sta bc_scan
        lda #$00
        cpx cur_param
        bne ud_mk_sp
        lda #$1E                ; '>'
ud_mk_sp
        sta bc_code
        jsr blit_char
        ldx s_kc
        inx
        cpx pg_end
        bne ud_mk
ud_nomk
        ; per-parameter value redraw on change (current page only)
        ldx pg_base
ud_pl
        stx s_kc
        lda p_vaddr_lo,x
        sta srcptr
        lda p_vaddr_hi,x
        sta srcptr+1
        ldy #0
        lda (srcptr),y          ; current value
        cmp prev_disp,x
        beq ud_pn
        sta prev_disp,x
        jsr draw_param
ud_pn
        ldx s_kc
        inx
        cpx pg_end
        bne ud_pl
        ; page-2 sequencer grid (step cells + play head + transport)
        lda page
        cmp #1
        bne ud_noseq
        jsr seq_draw
ud_noseq
        jsr draw_meters         ; per-voice VU bars (both pages)
        ; NOTE name + active-key indicator (on note change)
        lda note_idx
        cmp prev_note
        beq ud_donote
        sta prev_note
        jsr draw_note
        jsr key_indicator
ud_donote
        rts

; ----------------------------------------------------------------------------
;  Sequencer page (page 2) display: 16 step cells (block = note, '.' = rest),
;  a play-head marker above the active step, and PLAY/STOP + REC status.
; ----------------------------------------------------------------------------
seq_draw
        lda #0
        sta bc_inv
        sta bc_mode
        lda seq_dirty           ; full step grid redraw when the pattern changed
        beq sd_nogrid
        lda #0
        sta seq_dirty
        ldx #0
sd_cell
        stx s_kc
        txa                     ; col = 4 + step*2
        asl
        clc
        adc #4
        sta bc_col
        lda #56
        sta bc_scan
        ldx s_kc
        lda seq_notes,x
        cmp #$FF
        bne sd_notrest
        lda #$0E                ; '.' = rest
        bne sd_putcell
sd_notrest
        cmp #$FE
        bne sd_filled
        lda #$0D                ; '-' = tie (held note continues)
        bne sd_putcell
sd_filled
        lda #$80                ; solid block = note
sd_putcell
        sta bc_code
        jsr blit_char
        ldx s_kc
        inx
        cpx #16
        bne sd_cell
sd_nogrid
        lda seq_play            ; transport text on change
        cmp prev_splay
        bne sd_txt
        lda seq_rec
        cmp prev_srec
        beq sd_phead
sd_txt
        lda seq_play
        sta prev_splay
        lda seq_rec
        sta prev_srec
        lda seq_play
        beq sd_stop
        lda #<txt_play
        sta srcptr
        lda #>txt_play
        sta srcptr+1
        jmp sd_pput
sd_stop
        lda #<txt_stop
        sta srcptr
        lda #>txt_stop
        sta srcptr+1
sd_pput
        lda #4
        sta bc_col
        lda #72
        sta bc_scan
        jsr print_strz
        lda seq_rec
        beq sd_norec
        lda #<txt_rec
        sta srcptr
        lda #>txt_rec
        sta srcptr+1
        jmp sd_rput
sd_norec
        lda #<txt_blk3
        sta srcptr
        lda #>txt_blk3
        sta srcptr+1
sd_rput
        lda #10
        sta bc_col
        lda #72
        sta bc_scan
        jsr print_strz
sd_phead
        ; the ↓ head marks the active step: the WRITE head during step entry
        ; (rec armed + stopped), else the PLAY/clock head (playback or real-time).
        lda seq_rec
        beq sd_ph_useplay
        lda seq_play
        bne sd_ph_useplay       ; real-time record -> clock head, not write head
        lda seq_wpos
        jmp sd_ph_have
sd_ph_useplay
        lda seq_pos
sd_ph_have
        sta tmpA                ; tmpA = step to mark (survives blit_char)
        cmp prev_spos
        beq sd_done
        lda prev_spos
        cmp #16
        bcs sd_ph_new           ; previous head invalid ($FF) -> nothing to erase
        asl
        clc
        adc #4
        sta bc_col
        lda #48
        sta bc_scan
        lda #$00
        sta bc_code
        jsr blit_char
sd_ph_new
        lda tmpA
        asl
        clc
        adc #4
        sta bc_col
        lda #48
        sta bc_scan
        lda #$5D                ; down-arrow marker (distinct from note blocks)
        sta bc_code
        jsr blit_char
        lda tmpA
        sta prev_spos
sd_done
        rts

; ----------------------------------------------------------------------------
;  Per-voice level meters: 4 horizontal VU bars at scan 9-13, bar width =
;  voice envelope level * 3 px. Drawn INCREMENTALLY -- each frame only the
;  delta between the old and new level is set/cleared, so meters animating
;  with the envelopes cost a few pixels per voice, not a full redraw.
; ----------------------------------------------------------------------------
draw_meters
        ldx #0
dm_loop
        stx s_kc
        lda voice_level,x
        cmp prev_vmeter,x
        beq dm_next
        ldy prev_vmeter,x       ; old level
        sty tmp2
        sta prev_vmeter,x       ; store new
        cmp tmp2                ; new - old
        bcs dm_rise
        lda #$FF                ; level fell -> CLEAR from new to old
        sta pmode
        lda tmp2
        sta dm_hi               ; hi = old
        lda prev_vmeter,x
        sta dm_lo               ; lo = new
        jmp dm_calc
dm_rise
        lda #0                  ; level rose -> SET from old to new
        sta pmode
        lda tmp2
        sta dm_lo               ; lo = old
        lda prev_vmeter,x
        sta dm_hi               ; hi = new
dm_calc
        ldx s_kc
        lda dm_lo               ; xlo = met_x[v] + lo*3
        asl
        clc
        adc dm_lo
        clc
        adc met_x,x
        sta xlo
        lda #0
        sta xhi
        lda dm_hi               ; rw = (hi - lo)*3
        sec
        sbc dm_lo
        sta tmpA
        asl
        clc
        adc tmpA
        sta rw
        lda #9
        sta py
        lda #5
        sta rh
        jsr fillrect
dm_next
        ldx s_kc
        inx
        cpx #4
        bne dm_loop
        lda #0
        sta pmode
        rts
met_x   .byte 4,72,140,208

; clear the panel area (scan 8..123); leaves title row and keyboard intact
clear_panel
        lda #8
        sta s1
cpan
        ldy s1
        lda linetab_lo,y
        sta scrptr
        lda linetab_hi,y
        sta scrptr+1
        ldy #39
        lda #0
cpan2
        sta (scrptr),y
        dey
        bpl cpan2
        inc s1
        lda s1
        cmp #124
        bne cpan
        rts

; draw the current page's parameter labels
draw_page_labels
        lda #0
        sta bc_inv
        sta bc_mode
        ldx pg_base
dpgl
        stx s_kc
        lda p_lblptr_lo,x
        sta srcptr
        lda p_lblptr_hi,x
        sta srcptr+1
        lda p_lblcol,x
        sta bc_col
        lda p_scan,x
        sta bc_scan
        jsr print_strz
        ldx s_kc
        inx
        cpx pg_end
        bne dpgl
        rts

; draw one parameter widget; X = param index
draw_param
        lda p_kind,x
        cmp #K_WAVE
        bne dp_n1
        jmp draw_wave_selector
dp_n1
        cmp #K_CLK
        bne dp_n2
        jmp draw_clk_toggle
dp_n2
        lda p_knobcx,x          ; KNOB / OCT: common knob setup
        sta kcx
        lda p_scan,x
        clc
        adc #5
        sta kcy
        lda p_numcol,x
        sta dp_numcol
        lda p_scan,x
        sta dp_scan
        lda p_vaddr_lo,x
        sta srcptr
        lda p_vaddr_hi,x
        sta srcptr+1
        ldy #0
        lda (srcptr),y
        sta dp_val
        lda p_kind,x
        cmp #K_OCT
        beq dp_oct
        lda dp_val              ; --- K_KNOB ---
        sta kfrm
        jsr draw_knob
        lda dp_numcol
        sta bc_col
        lda dp_scan
        sta bc_scan
        lda dp_val
        jsr num2
        rts
dp_oct
        ldy dp_val              ; --- K_OCT ---
        lda oct_knob16,y
        sta kfrm
        jsr draw_knob
        lda dp_numcol
        sta bc_col
        lda dp_scan
        sta bc_scan
        jsr draw_octave_num
        rts

; NOTE name (3 chars) at col 7, scan 112 -- blank when silent
draw_note
        lda #35
        sta bc_col
        lda #0
        sta bc_scan
        lda note_idx
        cmp #$FF
        bne dn_play
        lda #$00                ; blank 3 cells
        sta bc_code
        jsr blit_char
        inc bc_col
        jsr blit_char
        inc bc_col
        jsr blit_char
        rts
dn_play
        ldx octave
        lda octave_base,x
        clc
        adc note_idx
        ldx #0
dn_div
        cmp #12
        bcc dn_div_done
        sec
        sbc #12
        inx
        jmp dn_div
dn_div_done
        ; A = semitone 0..11, X = octave step.  NB: blit_char clobbers X/s0/s1,
        ; so hold our values in tmpA/tmp2 (which blit_char does not touch).
        asl                     ; semitone*2 -> note_names index
        sta tmpA
        txa
        clc
        adc #2                  ; chromatic table is labelled from octave 2 (C2..)
        ; The chromatic dividers are tuned for the 15 kHz / 16-bit clocks. In
        ; NORMAL mode the 64 kHz clock makes every note sound TWO octaves higher
        ; (8-bit AUDF can't reach the low octaves), so the displayed octave must
        ; match what's actually heard: add 2 in NORMAL mode only.
        ldy clock15
        bne dn_oct_done         ; 15KHZ(1) / 16-BIT(2): label already correct
        clc
        adc #2                  ; NORMAL(0): +2 octaves to match the real pitch
dn_oct_done
        clc
        adc #$10                ; octave digit screen code
        sta tmp2
        ldx tmpA                ; name char 1
        lda note_names,x
        sta bc_code
        jsr blit_char
        inc bc_col
        ldx tmpA                ; name char 2
        lda note_names+1,x
        sta bc_code
        jsr blit_char
        inc bc_col
        lda tmp2                ; octave digit
        sta bc_code
        jsr blit_char
        rts

; octave value as sign + digit at bc_col,bc_scan.  NB: blit_char clobbers
; A/X/Y/s0/s1, so the sign char goes in tmpA and the digit in tmp2 first,
; then both are blitted (no live value kept across a blit_char call).
draw_octave_num
        lda octave
        sec
        sbc #2                  ; A = n (-2..+2)
        bmi don_neg
        beq don_zero
        lda #$0B                ; n > 0: '+'
        sta tmpA
        lda octave              ; digit = n = octave-2
        sec
        sbc #2
        clc
        adc #$10
        sta tmp2
        jmp don_emit
don_zero
        lda #$00                ; n = 0: blank sign, '0'
        sta tmpA
        lda #$10
        sta tmp2
        jmp don_emit
don_neg
        lda #$0D                ; n < 0: '-'
        sta tmpA
        lda #2                  ; digit = -n = 2 - octave
        sec
        sbc octave
        clc
        adc #$10
        sta tmp2
don_emit
        lda tmpA
        sta bc_code
        jsr blit_char
        inc bc_col
        lda tmp2
        sta bc_code
        jsr blit_char
        rts

; active-key indicator: clear a strip below the keys, draw a bar at the key
key_indicator
        ; clear strip y=186..190 (5 rows, full 40 bytes)
        lda #186
        sta s1
        ldx #5
ki_clr
        ldy s1
        lda linetab_lo,y
        sta scrptr
        lda linetab_hi,y
        sta scrptr+1
        ldy #39
        lda #0
ki_clr2
        sta (scrptr),y
        dey
        bpl ki_clr2
        inc s1
        dex
        bne ki_clr
        ; draw bar at active key (if any)
        lda note_idx
        cmp #$FF
        beq ki_done
        tax
        lda key_xind_lo,x
        sec
        sbc #4                  ; centre-4
        sta xlo
        lda key_xind_hi,x
        sbc #0
        sta xhi
        lda #186
        sta py
        lda #8
        sta rw
        lda #4
        sta rh
        lda #0
        sta pmode
        jsr fillrect
ki_done
        rts

; OR a bitmap into the framebuffer: srcptr=data, s0=wbytes, s1=hrows,
; bc_col=dest byte column, bc_scan=top scan line
blit_bitmap
        lda #0
        sta psi
        ldx #0
bbm_row
        txa
        clc
        adc bc_scan
        tay
        lda linetab_lo,y
        clc
        adc bc_col
        sta adjptr
        lda linetab_hi,y
        adc #0
        sta adjptr+1
        ldy #0
bbm_col
        sty s_dy
        ldy psi
        lda (srcptr),y
        ldy s_dy
        ora (adjptr),y
        sta (adjptr),y
        inc psi
        ldy s_dy
        iny
        cpy s0
        bne bbm_col
        inx
        cpx s1
        bne bbm_row
        rts

; WAVEFORM selector: 4 waveform icons, the active one boxed
draw_wave_selector
        lda #16                 ; clear icon strip: byte cols 9..18, 14 rows
        sta s1
        ldx #14
dws_clr
        ldy s1
        lda linetab_lo,y
        clc
        adc #9
        sta scrptr
        lda linetab_hi,y
        adc #0
        sta scrptr+1
        ldy #9
        lda #0
dws_clr2
        sta (scrptr),y
        dey
        bpl dws_clr2
        inc s1
        dex
        bne dws_clr
        ldx #0                  ; draw 4 icons (16x8)
dws_ic
        stx s_pc
        lda icon_ptr_lo,x
        sta srcptr
        lda icon_ptr_hi,x
        sta srcptr+1
        lda icon_col,x
        sta bc_col
        lda #18
        sta bc_scan
        lda #2
        sta s0
        lda #8
        sta s1
        jsr blit_bitmap
        ldx s_pc
        inx
        cpx #4
        bne dws_ic
        ldx wave_idx            ; box around the active icon
        lda icon_col,x
        asl
        asl
        asl                     ; byte col -> pixel x
        sec
        sbc #2
        sta xlo
        lda #0
        sta xhi
        sta pmode
        lda #16
        sta py
        lda #19
        sta rw
        lda #12
        sta rh
        jsr rect
        rts

; CLOCK mode: show the active mode name (NORMAL / 15 KHZ / 16-BIT)
draw_clk_toggle
        lda #54                 ; clear strip: byte cols 29..38, 14 rows
        sta s1
        ldx #14
dct_clr
        ldy s1
        lda linetab_lo,y
        clc
        adc #29
        sta scrptr
        lda linetab_hi,y
        adc #0
        sta scrptr+1
        ldy #9
        lda #0
dct_clr2
        sta (scrptr),y
        dey
        bpl dct_clr2
        inc s1
        dex
        bne dct_clr
        lda #0
        sta bc_inv
        sta bc_mode
        lda clock15             ; name = clock_names[mode*6]
        jsr mul6
        clc
        adc #<clock_names
        sta srcptr
        lda #>clock_names
        adc #0
        sta srcptr+1
        lda #30
        sta bc_col
        lda #56
        sta bc_scan
        lda #6
        sta pcnt
        jsr print_n
        rts

; A * 6 -> A
mul6
        sta tmpA
        asl
        sta tmp2
        lda tmpA
        asl
        asl
        clc
        adc tmp2
        rts

; ============================================================================
;  TABLES
; ============================================================================
; chromatic AUDF divisors, PAL 8-bit, C2..E7 (index 0 = C2)
chromatic
        .byte $78,$71,$6B,$65,$5F,$5A,$55,$50,$4B,$47,$43,$3F
        .byte $3C,$38,$35,$32,$2F,$2C,$2A,$27,$25,$23,$21,$1F
        .byte $1D,$1C,$1A,$18,$17,$16,$14,$13,$12,$11,$10,$0F
        .byte $0E,$0D,$0C,$0C,$0B,$0A,$0A,$09,$09,$08,$07,$07
        .byte $07,$06,$06,$05,$05,$05,$04,$04,$04,$03,$03,$03
        .byte $03,$03,$02,$02,$02
octave_base
        .byte 0,12,24,36,48
wave_base
        .byte $A0,$E0,$C0,$80
wave_names
        .byte "SQUARE","PURE  ","BUZZ  ","NOISE "
clock_names
        .byte "NORMAL","15 KHZ","16-BIT"
note_names
        .byte "C C#D D#E F F#G G#A A#B "

; 16-bit chromatic dividers, PAL 1.79 MHz clock, C2..E7 (index 0 = C2)
chrom16_lo
        .byte $F4,$FB,$2D,$87,$07,$AB,$71,$57,$5B,$7C,$B8,$0D
        .byte $7A,$FD,$96,$43,$03,$D5,$B8,$AB,$AD,$BE,$DB,$06
        .byte $3C,$7E,$CB,$21,$81,$EA,$5C,$D5,$56,$DE,$6D,$02
        .byte $9E,$3F,$E5,$90,$40,$F5,$AD,$6A,$2B,$EF,$B6,$81
        .byte $4E,$1F,$F2,$C8,$A0,$7A,$56,$35,$15,$F7,$DB,$C0
        .byte $A7,$8F,$78,$63,$4F
chrom16_hi
        .byte $34,$31,$2F,$2C,$2A,$27,$25,$23,$21,$1F,$1D,$1C
        .byte $1A,$18,$17,$16,$15,$13,$12,$11,$10,$0F,$0E,$0E
        .byte $0D,$0C,$0B,$0B,$0A,$09,$09,$08,$08,$07,$07,$07
        .byte $06,$06,$05,$05,$05,$04,$04,$04,$04,$03,$03,$03
        .byte $03,$03,$02,$02,$02,$02,$02,$02,$02,$01,$01,$01
        .byte $01,$01,$01,$01,$01

key_scan
        .byte $2F,$1E,$2E,$1A,$2A,$28,$1D,$2D,$1B,$2B,$33,$0B,$0D,$30,$08,$32,$0A

; apply_adjust parameter table (cur_param 0..7)
; NB: param_lo/hi MUST have one entry per param (0..NPARAM-1). They previously
; omitted TEMPO (index 12) -> apply_adjust read past the table when adjusting
; TEMPO via the joystick (wrote stray RAM). Now includes TEMPO + ARPMODE.
param_lo
        .byte <wave_idx,<volume,<octave,<atk_rate,<dec_rate,<detune
        .byte <sus_level,<rel_rate,<clock15,<lfo_rate,<lfo_depth,<arp_rate
        .byte <tempo,<arp_mode,<porta_rate,<drum_dec,<hpf_cut,<preset_slot,<drum_beat
param_hi
        .byte >wave_idx,>volume,>octave,>atk_rate,>dec_rate,>detune
        .byte >sus_level,>rel_rate,>clock15,>lfo_rate,>lfo_depth,>arp_rate
        .byte >tempo,>arp_mode,>porta_rate,>drum_dec,>hpf_cut,>preset_slot,>drum_beat
param_max
        .byte 3,15,4,15,15,15, 15,15,2,15,15,15, 15,3,15,15, 15,3,15
param_maxp1
        .byte 4,16,5,16,16,16, 16,16,3,16,16,16, 16,4,16,16, 16,4,16

; ----- parameter descriptor tables (NPARAM entries) -------------------------
;        0 WAVE  1 VOL  2 OCT  3 ATK  4 DEC | 5 SUS  6 REL  7 CLK  8 LFOR 9 LFOD
;        left column (0-4)                  | right column (5-9)
; INDEX ORDER == VISUAL ORDER so UP/DOWN steps through the panel as drawn:
;   left column top->bottom (0-5), then right column top->bottom (6-10).
;        0 WAVE 1 VOL 2 OCT 3 ATK 4 DEC 5 DET | 6 SUS 7 REL 8 CLK 9 LFOR 10 LFOD
;  left column 0-5             | right column 6-11 (incl ARP=11)
; Page 0 = indices 0-11 (osc/env/fx).  Page 2 = indices 12+ (layout positions
; reuse the page-0 grid, so all tables index by absolute param).
;        page 2: 12 TEMPO (r0 left) 13 ARPMODE (r0 right) 14 PORTA (r1 left) 15 DRUM (r1 right)
p_kind
        .byte K_WAVE,K_KNOB,K_OCT,K_KNOB,K_KNOB,K_KNOB
        .byte K_KNOB,K_KNOB,K_CLK,K_KNOB,K_KNOB,K_KNOB
        .byte K_KNOB,K_KNOB,K_KNOB,K_KNOB                 ; 12 TEMPO,13 ARPMODE,14 PORTA,15 DRUM
        .byte K_KNOB,K_KNOB,K_KNOB                        ; 16 HPF, 17 PRESET, 18 DRUMBEAT
p_scan
        .byte 16,36,56,76,96,110, 16,36,56,76,96,110
        .byte 16,16,36,36, 16,16,36
p_lblcol
        .byte 1,1,1,1,1,1, 21,21,21,21,21,21
        .byte 1,21,1,21, 1,21,1
p_knobcx
        .byte 86,86,86,86,86,86, 246,246,246,246,246,246
        .byte 86,246,86,246, 86,246,86
p_numcol
        .byte 13,13,13,13,13,13, 33,33,33,33,33,33
        .byte 13,33,13,33, 13,33,13
p_vaddr_lo
        .byte <wave_idx,<volume,<octave,<atk_rate,<dec_rate,<detune
        .byte <sus_level,<rel_rate,<clock15,<lfo_rate,<lfo_depth,<arp_rate
        .byte <tempo,<arp_mode,<porta_rate,<drum_dec,<hpf_cut,<preset_slot,<drum_beat
p_vaddr_hi
        .byte >wave_idx,>volume,>octave,>atk_rate,>dec_rate,>detune
        .byte >sus_level,>rel_rate,>clock15,>lfo_rate,>lfo_depth,>arp_rate
        .byte >tempo,>arp_mode,>porta_rate,>drum_dec,>hpf_cut,>preset_slot,>drum_beat
p_lblptr_lo
        .byte <txt_wave,<txt_vol,<txt_oct,<txt_atk,<txt_dec,<txt_det
        .byte <txt_sus,<txt_rel,<txt_clk,<txt_lfor,<txt_lfod,<txt_arp
        .byte <txt_tempo,<txt_arpm,<txt_porta,<txt_drum,<txt_hpf,<txt_preset,<txt_dbeat
p_lblptr_hi
        .byte >txt_wave,>txt_vol,>txt_oct,>txt_atk,>txt_dec,>txt_det
        .byte >txt_sus,>txt_rel,>txt_clk,>txt_lfor,>txt_lfod,>txt_arp
        .byte >txt_tempo,>txt_arpm,>txt_porta,>txt_drum,>txt_hpf,>txt_preset,>txt_dbeat

; knob geometry
bitmask_tab
        .byte $80,$40,$20,$10,$08,$04,$02,$01
hw_tab                          ; half-width per |dy| 0..6
        .byte 6,6,6,5,4,3,0
; pointer rim offsets (16 directions, clockwise from up), signed
kn_ex
        .byte 0,2,4,5,5,5,4,2,0,$FE,$FC,$FB,$FB,$FB,$FC,$FE
kn_ey
        .byte $FB,$FB,$FC,$FE,0,2,4,5,5,5,4,2,0,$FE,$FC,$FB
kn_mx
        .byte 0,1,2,3,3,3,2,1,0,$FF,$FE,$FD,$FD,$FD,$FE,$FF
kn_my
        .byte $FD,$FD,$FE,$FF,0,1,2,3,3,3,2,1,0,$FF,$FE,$FD
oct_knob16                      ; octave 0..4 -> knob position
        .byte 0,4,8,12,15

; keyboard layout
blackx_lo
        .byte 32,62,122,152,182,242,16
blackx_hi
        .byte 0,0,0,0,0,0,1
white_lblcol
        .byte 2,6,10,13,17,21,25,28,32,36
white_lblch                     ; Q W E R T Y U I O P (screen codes)
        .byte $31,$37,$25,$32,$34,$39,$35,$29,$2F,$30
black_lblcol                    ; byte col centering each number on its 16px black key
        .byte 4,8,16,19,23,31,34
black_lblch                     ; 2 3 5 6 7 9 0 (screen codes)
        .byte $12,$13,$15,$16,$17,$19,$10
; active-key indicator centre x per semitone 0..16
key_xind_lo
        .byte 24,40,54,70,84,114,130,144,160,174,190,204,234,250,8,24,38
key_xind_hi
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1

; waveform icons (16x8, 2 bytes/row) for the WAVEFORM selector
icon_sq                         ; square / pulse
        .byte $F8,$3F,$08,$20,$08,$20,$08,$20,$08,$20,$08,$20,$08,$20,$0F,$E0
icon_tri                        ; triangle (PURE)
        .byte $01,$80,$02,$40,$04,$20,$08,$10,$10,$08,$20,$04,$40,$02,$80,$01
icon_saw                        ; sawtooth (BUZZ)
        .byte $01,$01,$03,$03,$05,$05,$09,$09,$11,$11,$21,$21,$41,$41,$81,$81
icon_noise                      ; scattered dots (NOISE)
        .byte $20,$40,$00,$04,$04,$00,$80,$10,$01,$01,$10,$00,$00,$82,$42,$08
icon_col
        .byte 10,12,14,16       ; dest byte column of each icon
icon_ptr_lo
        .byte <icon_sq,<icon_tri,<icon_saw,<icon_noise
icon_ptr_hi
        .byte >icon_sq,>icon_tri,>icon_saw,>icon_noise

; ----- display list: GR.8 (ANTIC mode $0F), 192 lines, two LMS regions ------
; Fixed 1KB-aligned home, clear of linetab ($3000) and the framebuffer ($4000+),
; and within one 1KB block (ANTIC's DL counter is 10-bit).
        org $3C00
dlist
        .byte $70,$70,$70       ; 24 blank lines
        .byte $4F               ; LMS + mode F
        .word FB1
        :101 .byte $0F          ; 101 more lines (102 total from FB1)
        .byte $4F
        .word FB2
        :89 .byte $0F           ; 89 more lines (90 total from FB2)
        .byte $41               ; JVB
        .word dlist

; ----- text labels (screen codes, $FF-terminated) ---------------------------
txt_title  .byte "ATARI POKEY SYNTH",$FF
txt_wave   .byte "WAVEFORM",$FF
txt_vol    .byte "VOLUME",$FF
txt_oct    .byte "OCTAVE",$FF
txt_atk    .byte "ATTACK",$FF
txt_dec    .byte "DECAY",$FF
txt_sus    .byte "SUSTAIN",$FF
txt_rel    .byte "RELEASE",$FF
txt_clk    .byte "CLOCK",$FF
txt_note   .byte "NOTE",$FF
txt_norm   .byte "NORM",$FF
txt_15k    .byte "15K",$FF
txt_lfor   .byte "LFO RATE",$FF
txt_lfod   .byte "LFO DEPTH",$FF
txt_det    .byte "DETUNE",$FF
txt_arp    .byte "ARP",$FF
txt_tempo  .byte "TEMPO",$FF
txt_arpm   .byte "ARP MODE",$FF
txt_porta  .byte "PORTA",$FF
txt_drum   .byte "DRUM",$FF
txt_hpf    .byte "HP FILTER",$FF
txt_preset .byte "PRESET",$FF
txt_dbeat  .byte "DRUMBEAT",$FF
txt_play   .byte "PLAY",$FF
txt_stop   .byte "STOP",$FF
txt_rec    .byte "REC",$FF
txt_blk3   .byte "   ",$FF

        run main
