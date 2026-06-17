; ============================================================================
;  KBTEST  -  bare-metal keyboard / console register viewer
;  A diagnostic for REAL Atari hardware. No sound, no synth engine: just a
;  tight loop that reads the raw POKEY/console registers every frame and prints
;  their hex values to the GR.0 text screen, so you can see EXACTLY what the
;  hardware reports for each key.
;
;  WHAT IT SHOWS
;    KBCODE  ($D209)  raw keyboard scan code (the value the synth reads & masks)
;            SH= shift pressed?   CT= ctrl pressed?   DN= a key down right now?
;    SKSTAT  ($D20F)  serial/keyboard status (bit3=shift, bit2=key-down, both 0=pressed)
;    CONSOL  ($D01F)  START/SELECT/OPTION (active low: 6=START,5=SELECT,3=OPTION)
;    CH      ($02FC)  the OS keyboard register ($FF = no new key)
;    FRAME   (RTCLOK) a free-running counter: if it stops ticking, the loop hung
;
;  HOW TO USE  (option B from the plan):
;    I name a key, you press it, you read me the KBCODE hex value. KBCODE keeps
;    the LAST key's value after release, so you can release and still read it;
;    DN= tells you whether a key is held at that instant.
;
;  Target: PAL Atari XL/XE. Assemble with MADS.  ->  kbtest.xex
; ============================================================================

SAVMSC  = $58           ; OS screen-RAM pointer (lo/hi) for the current GR.0 screen
RTCLOK  = $14           ; low byte of the VBI frame counter
ATRACT  = $4D           ; attract-mode timer (clear each frame to stay bright)
CRSINH  = $02F0         ; cursor inhibit (1 = hide the text cursor)
CH      = $02FC         ; OS last-key register ($FF = none)

KBCODE  = $D209
SKSTAT  = $D20F
CONSOL  = $D01F

scr     = $CB           ; zp: screen base pointer
srcptr  = $CD           ; zp: string source pointer

        org $3000

start
        ; --- hide the cursor so it doesn't sit in a value field ---
        lda #1
        sta CRSINH

; ----------------------------------------------------------------------------
;  main loop: refresh the screen base, repaint labels + live values, forever.
;  Everything is redrawn every frame so the display self-corrects no matter
;  when SAVMSC settles (the OS can finish GR.0 setup *after* we start, which
;  moves the screen) or what loader launched us.
; ----------------------------------------------------------------------------
loop
        lda #1
        sta CRSINH              ; keep the cursor hidden
        lda #0
        sta ATRACT              ; keep the screen at full brightness

        ; re-read the live GR.0 screen base into scr (all writes use Y < 256)
        lda SAVMSC
        sta scr
        lda SAVMSC+1
        sta scr+1

        ; --- repaint the static labels ---
        ldy #0
        mwa #s_title srcptr
        jsr print
        ldy #40
        mwa #s_kb srcptr
        jsr print
        ldy #52                 ; three separate labels so none covers a value
        mwa #s_sh srcptr        ; column (a combined label would blank them each
        jsr print               ; frame and fight the value writes)
        ldy #57
        mwa #s_ct srcptr
        jsr print
        ldy #62
        mwa #s_dn srcptr
        jsr print
        ldy #80
        mwa #s_sk srcptr
        jsr print
        ldy #120
        mwa #s_con srcptr
        jsr print
        ldy #160
        mwa #s_ch srcptr
        jsr print
        ldy #200
        mwa #s_frame srcptr
        jsr print
        ldy #240
        mwa #s_hint srcptr
        jsr print

        ; --- live values ---
        lda KBCODE              ; KBCODE hex at row1 col8
        ldy #48
        jsr puthex

        lda SKSTAT              ; SH= : shift pressed (SKSTAT bit3 = 0 -> pressed)
        and #$08
        eor #$08
        ldy #55
        jsr putyn

        lda KBCODE              ; CT= : ctrl pressed (KBCODE bit6 set on hardware)
        and #$40
        ldy #60
        jsr putyn

        lda SKSTAT              ; DN= : a key is down now (SKSTAT bit2 = 0 -> down)
        and #$04
        eor #$04
        ldy #65
        jsr putyn

        lda SKSTAT              ; SKSTAT hex at row2 col8
        ldy #88
        jsr puthex

        lda CONSOL              ; CONSOL hex at row3 col8
        ldy #128
        jsr puthex

        lda CH                  ; CH (OS key reg) hex at row4 col8
        ldy #168
        jsr puthex

        lda RTCLOK              ; FRAME counter at row5 col8 (must keep ticking)
        ldy #208
        jsr puthex

        jmp loop

; ----------------------------------------------------------------------------
;  print: srcptr -> string ($FF terminator), Y = screen offset (< 256)
;  MADS .byte "..." already emits GR.0 internal screen codes, so the bytes go
;  straight to screen RAM with no conversion. ($FF can't collide with a glyph:
;  space is $00, all our chars are $10..$3F.)
; ----------------------------------------------------------------------------
print
        ldx #0
pr_l
        lda (srcptr,x)
        cmp #$FF
        beq pr_done
        sta (scr),y
        iny
        inc srcptr
        bne pr_l
        inc srcptr+1
        jmp pr_l
pr_done
        rts

; ----------------------------------------------------------------------------
;  puthex: A = byte -> two hex screen codes at offset Y
; ----------------------------------------------------------------------------
puthex
        pha
        lsr @
        lsr @
        lsr @
        lsr @
        jsr nib
        sta (scr),y
        iny
        pla
        and #$0F
        jsr nib
        sta (scr),y
        rts
nib                             ; A = nibble 0..15 -> GR.0 screen code for 0-9/A-F
        cmp #10
        bcc nib_num
        adc #$16                ; carry set: nibble + $16 + 1 = nibble + $17 ('A'=$21)
        rts
nib_num
        ora #$10                ; '0' screen code = $10
        rts

; ----------------------------------------------------------------------------
;  putyn: A = 0 -> 'N', non-zero -> 'Y', at offset Y
; ----------------------------------------------------------------------------
putyn
        tax
        beq yn_n
        lda #$39                ; 'Y' screen code
        bne yn_put
yn_n
        lda #$2E                ; 'N' screen code
yn_put
        sta (scr),y
        rts

; ----- label strings (ATASCII, $FF-terminated) ------------------------------
s_title .byte "ATARI KEYBOARD TEST",$FF
s_kb    .byte "KBCODE:",$FF
s_sh    .byte "SH=",$FF        ; value at col15 ; CT/DN at col20/25 (no overlap)
s_ct    .byte "CT=",$FF
s_dn    .byte "DN=",$FF
s_sk    .byte "SKSTAT:",$FF
s_con   .byte "CONSOL:",$FF
s_ch    .byte "CH:",$FF
s_frame .byte "FRAME:",$FF
s_hint  .byte "READ ME KBCODE",$FF     ; row6: must fit cols 0..15 (offset < 256)

        run start
