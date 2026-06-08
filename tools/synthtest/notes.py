"""Note / pitch maths for atari-synth acoustic testing.

Two jobs:

1. Predict the frequency POKEY *should* emit for a given divider, so the
   acoustic layer can assert the audio engine renders what the registers
   command (catches clock-mode / 16-bit / engine bugs).
2. Provide equal-tempered references + a cents helper, so we can assert
   musical relationships (octave doubling, semitone ratio, in-tune-ness)
   independently of any naming convention.

The chromatic AUDF tables are PARSED from synth.asm so they never drift from
the source of truth. POKEY pitch is a pure function of the divider + clock, so
predicting it here and comparing to measured audio is a true engine check.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASM = os.path.abspath(os.path.join(HERE, "..", "..", "synth.asm"))

# ---------------------------------------------------------------------------
# PAL POKEY clocks (Hz). PAL master = 1.773447 MHz.
#   64 kHz base   = master / 28  = 63337.4 Hz
#   15 kHz base   = master / 114 = 15556.6 Hz
#   1.79 MHz      = master              (used by 16-bit joined pairs)
# POKEY square-wave output completes one cycle every two counter reloads, so
#   f = clock / (2 * (DIVIDER + 1))
# (The high-frequency 1.79 MHz path has a small fixed offset on real silicon;
#  for the joined 16-bit divider the +1 form matches the synth's table to <1
#  cent, so we use it and treat residual error as measurement tolerance.)
# ---------------------------------------------------------------------------
PAL_MASTER = 1_773_447.0
CLK_64K = PAL_MASTER / 28.0     # 63337.4
CLK_15K = PAL_MASTER / 114.0    # 15556.6
CLK_179 = PAL_MASTER            # 1773447

# Clock-mode index (synth's clock15 var): 0 NORMAL, 1 15KHZ, 2 16BIT
MODE_NORMAL, MODE_15K, MODE_16BIT = 0, 1, 2


def pokey_freq_8bit(audf, clock=CLK_64K):
    """Output Hz for an 8-bit channel with divider AUDF on the given clock."""
    return clock / (2.0 * (audf + 1))


def pokey_freq_16bit(lo, hi, clock=CLK_179):
    """Output Hz for a joined 16-bit pair (divider = lo + 256*hi)."""
    n = (hi << 8) | lo
    return clock / (2.0 * (n + 1))


def audf_freq(audf, mode=MODE_NORMAL):
    """Predicted Hz for an 8-bit AUDF in NORMAL or 15KHZ mode."""
    return pokey_freq_8bit(audf, CLK_15K if mode == MODE_15K else CLK_64K)


# ---------------------------------------------------------------------------
# Equal temperament (A4 = 440). Scientific pitch: C4 = 261.626 Hz.
# ---------------------------------------------------------------------------
A4 = 440.0
_SEMI = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def et_freq(midi):
    """Equal-tempered frequency for a MIDI note number (A4=69=440Hz)."""
    return A4 * (2.0 ** ((midi - 69) / 12.0))


def cents(measured, reference):
    """Pitch error in cents (measured vs reference). +ve = sharp."""
    if measured <= 0 or reference <= 0:
        return float("inf")
    import math
    return 1200.0 * math.log2(measured / reference)


def nearest_et(freq):
    """Nearest equal-tempered note to a frequency. Returns (name, midi, cents_off)."""
    if freq <= 0:
        return ("?", 0, float("inf"))
    import math
    midi = round(69 + 12 * math.log2(freq / A4))
    ref = et_freq(midi)
    octave = midi // 12 - 1
    return (f"{_SEMI[midi % 12]}{octave}", midi, cents(freq, ref))


# ---------------------------------------------------------------------------
# Tables parsed from synth.asm (.byte rows under a label until the next label).
# ---------------------------------------------------------------------------
def _parse_byte_table(label, _cache={}):
    if label in _cache:
        return _cache[label]
    with open(ASM) as f:
        lines = f.readlines()
    vals, capturing = [], False
    label_re = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\b')
    for line in lines:
        stripped = line.rstrip("\n")
        # a bare label at column 0 starts/stops capture
        m = label_re.match(stripped)
        if m:
            name = m.group(1)
            if name == label:
                capturing = True
                # label line may also carry a .byte after it; fall through
            elif capturing:
                break  # next label -> table ended
        if not capturing:
            continue
        bm = re.search(r'\.byte\s+(.+)', stripped)
        if not bm:
            continue
        body = bm.group(1).split(';')[0]
        for tok in body.split(','):
            tok = tok.strip()
            if not tok or tok.startswith('"'):
                continue
            if tok.startswith('$'):
                vals.append(int(tok[1:], 16))
            elif re.fullmatch(r'\d+', tok):
                vals.append(int(tok))
    _cache[label] = vals
    return vals


def chromatic():
    """8-bit AUDF divisor per absolute chromatic index (0 = labelled C2)."""
    return _parse_byte_table("chromatic")


def chrom16():
    """List of (lo, hi) 16-bit dividers per absolute chromatic index."""
    lo = _parse_byte_table("chrom16_lo")
    hi = _parse_byte_table("chrom16_hi")
    return list(zip(lo, hi))


def octave_base():
    """Absolute chromatic index for each octave-knob setting (0..4)."""
    return _parse_byte_table("octave_base")


# Absolute chromatic index -> the synth's own label (e.g. "C4" follows the
# table comment: index 0 is labelled C2, so index = (octave-2)*12 + semitone).
def synth_label(idx):
    octave = 2 + idx // 12
    return f"{_SEMI[idx % 12]}{octave}"


# The note name the synth DISPLAYS for an absolute chromatic index, mirroring
# draw_note in synth.asm: octave digit = index//12 + 2, plus 2 more in NORMAL
# mode (its 64 kHz clock sounds two octaves above the 15 kHz/16-bit tuning).
# A valid label == the note you actually hear, so this should equal the nearest
# equal-tempered note of the measured pitch.
def displayed_note(idx, mode=MODE_NORMAL):
    octv = idx // 12 + 2 + (2 if mode == MODE_NORMAL else 0)
    return f"{_SEMI[idx % 12]}{octv}"


# Predicted Hz for an absolute chromatic index in each mode, straight from the
# parsed tables — what the engine is *commanded* to produce.
def predicted_freq(idx, mode=MODE_NORMAL):
    if mode == MODE_16BIT:
        lo, hi = chrom16()[idx]
        return pokey_freq_16bit(lo, hi)
    audf = chromatic()[idx]
    return audf_freq(audf, mode)


if __name__ == "__main__":
    # Quick self-report: how the three modes map index 0/12/24 to pitch.
    for idx in (0, 12, 24, 36):
        n = synth_label(idx)
        fn = predicted_freq(idx, MODE_NORMAL)
        f15 = predicted_freq(idx, MODE_15K)
        f16 = predicted_freq(idx, MODE_16BIT)
        print(f"idx {idx:2d} ({n}): NORMAL {fn:8.2f}Hz [{nearest_et(fn)[0]}]  "
              f"15K {f15:8.2f}Hz [{nearest_et(f15)[0]}]  "
              f"16BIT {f16:8.2f}Hz [{nearest_et(f16)[0]}]")
