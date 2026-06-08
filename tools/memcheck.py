#!/usr/bin/env python3
"""Memory-map sanity check for the POKEY synth.

Runs at BUILD time (no emulator needed) and fails the build if new code/data
would corrupt something at runtime. It catches the exact class of bugs we hit
more than once:

  * loaded code/data growing into a region the program OVERWRITES at runtime
    (the line-address table `linetab`, or the framebuffer that clear_fb zeroes)
    -- this silently clobbered the parameter tables once and froze the synth;
  * the ANTIC display list crossing a 1 KB boundary (its DMA counter is 10-bit,
    so it wraps and the screen corrupts);
  * loaded segments overlapping each other;
  * a packed RAM variable/array overrunning its neighbour in page 6 / zero page.

It parses `synth.xex` (the loaded byte ranges) and `synth.lst` (label/EQU
addresses + NPARAM), so it tracks the build automatically. Exit code != 0 on
any problem, with a printed memory map.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XEX = os.path.join(ROOT, "synth.xex")
LST = os.path.join(ROOT, "synth.lst")


# ---- parse the Atari executable: list of (start, end) inclusive segments ----
def parse_xex(path):
    data = open(path, "rb").read()
    segs = []
    i, n = 0, len(data)
    while i + 4 <= n:
        word = data[i] | (data[i + 1] << 8)
        if word == 0xFFFF:          # header / segment separator (may repeat)
            i += 2
            continue
        start = word
        end = data[i + 2] | (data[i + 3] << 8)
        i += 4
        if end < start:
            raise SystemExit(f"memcheck: corrupt XEX segment {start:04X}>{end:04X}")
        segs.append((start, end))
        i += (end - start + 1)      # skip the segment's data bytes
    return segs


# ---- resolve symbols from the MADS listing -------------------------------
def _read_lst():
    return open(LST, encoding="latin-1").read().splitlines()


def resolve_equ(name, lines):
    """An EQU shows as e.g. `  167 = 000C  PER_PAGE = 12` (line `= VALUE`)."""
    pat = re.compile(r"^\s*\d+\s*=\s*([0-9A-Fa-f]{1,4})\s+" + re.escape(name) + r"\s*=")
    for ln in lines:
        m = pat.match(ln)
        if m:
            return int(m.group(1), 16)
    return None


def resolve_label(name, lines):
    """A label definition shows as `  672 239C  update_sound` (addr then name)."""
    pat = re.compile(r"^\s*\d+\s+([0-9A-Fa-f]{4})\s+" + re.escape(name) + r"\s*$")
    for ln in lines:
        m = pat.match(ln)
        if m:
            return int(m.group(1), 16)
    return None


def all_equs(lines):
    """Every `name = $value` EQU -> {name: addr}."""
    pat = re.compile(r"^\s*\d+\s*=\s*([0-9A-Fa-f]{1,4})\s+([A-Za-z_][A-Za-z0-9_]*)\s*=")
    out = {}
    for ln in lines:
        m = pat.match(ln)
        if m:
            out[m.group(2)] = int(m.group(1), 16)
    return out


def overlaps(a0, a1, b0, b1):
    return a0 <= b1 and b0 <= a1


def main():
    if not (os.path.exists(XEX) and os.path.exists(LST)):
        raise SystemExit("memcheck: build synth.xex / synth.lst first")
    lines = _read_lst()
    equ = all_equs(lines)

    NPARAM = resolve_equ("NPARAM", lines) or 13
    FB1 = equ.get("FB1") or resolve_equ("FB1", lines)
    FB2 = equ.get("FB2") or resolve_equ("FB2", lines)
    lt_lo = equ.get("linetab_lo")
    lt_hi = equ.get("linetab_hi")
    dlist = resolve_label("dlist", lines)

    segs = parse_xex(XEX)

    # --- runtime-write regions: the program clobbers these AFTER load. ---
    # clear_fb zeroes a full 8 KB from FB1, so the whole $4000-$5FFF is written.
    runtime = []
    if FB1 is not None:
        runtime.append(("framebuffer (clear_fb zeroes 8K)", FB1, FB1 + 0x2000 - 1))
    if lt_lo is not None:
        runtime.append(("linetab_lo (192)", lt_lo, lt_lo + 191))
    if lt_hi is not None:
        runtime.append(("linetab_hi (192)", lt_hi, lt_hi + 191))

    errors = []

    # 1. no loaded segment may sit inside a runtime-write region
    for s0, s1 in segs:
        for name, r0, r1 in runtime:
            if overlaps(s0, s1, r0, r1):
                lo, hi = max(s0, r0), min(s1, r1)
                errors.append(
                    f"loaded data ${s0:04X}-${s1:04X} overlaps {name} "
                    f"(${r0:04X}-${r1:04X}) at ${lo:04X}-${hi:04X} -- "
                    f"it will be clobbered at runtime")

    # 2. runtime regions must not overlap each other
    for i in range(len(runtime)):
        for j in range(i + 1, len(runtime)):
            n1, a0, a1 = runtime[i]
            n2, b0, b1 = runtime[j]
            if overlaps(a0, a1, b0, b1):
                errors.append(f"runtime region {n1} overlaps {n2}")

    # 3. loaded segments must not overlap each other
    so = sorted(segs)
    for i in range(len(so) - 1):
        if so[i][1] >= so[i + 1][0]:
            errors.append(
                f"loaded segments ${so[i][0]:04X}-${so[i][1]:04X} and "
                f"${so[i+1][0]:04X}-${so[i+1][1]:04X} overlap")

    # 4. display list must stay within one 1 KB ANTIC block
    if dlist is not None:
        dl_seg = next((s for s in segs if s[0] <= dlist <= s[1]), None)
        if dl_seg:
            d0 = dlist
            d1 = dl_seg[1]          # dlist runs to the end of its segment
            if (d0 >> 10) != (d1 >> 10):
                errors.append(
                    f"display list ${d0:04X}-${d1:04X} crosses a 1KB boundary "
                    f"(${(d0>>10)<<10:04X} vs ${(d1>>10)<<10:04X}) -- ANTIC's "
                    f"10-bit DL counter will wrap")

    # 5. packed RAM variables/arrays must not overrun their neighbour.
    #    Sizes of the multi-byte ones (single-byte vars default to 1). Keep in
    #    sync when adding arrays; prev_disp tracks NPARAM automatically.
    SIZES = {
        "scrptr": 2, "srcptr": 2, "adjptr": 2,         # ZP 16-bit pointers
        "voice_note": 4, "voice_level": 4, "voice_phase": 4, "voice_count": 4,
        "prev_disp": NPARAM, "dvoff": 4, "seq_notes": 16, "prev_vmeter": 4,
    }
    SKIP = {"FB1", "FB2", "linetab_lo", "linetab_hi", "ROMFONT", "RTCLOK"}
    vars_ = []
    for name, addr in equ.items():
        if name in SKIP:
            continue
        if 0x0080 <= addr <= 0x07FF:        # our ZP + page-6 working RAM
            sz = SIZES.get(name, 1)
            vars_.append((addr, addr + sz - 1, name, sz))
    vars_.sort()
    for i in range(len(vars_) - 1):
        a0, a1, an, asz = vars_[i]
        b0, b1, bn, bsz = vars_[i + 1]
        if a1 >= b0:
            errors.append(
                f"variable {an} (${a0:04X}, {asz}B) overruns {bn} (${b0:04X})")

    # ---- report ----------------------------------------------------------
    print("memory map:")
    rows = [("loaded $%04X-$%04X (%d B)" % (s0, s1, s1 - s0 + 1), s0) for s0, s1 in so]
    rows += [("%s $%04X-$%04X" % (n, a, b), a) for n, a, b in runtime]
    for label, _ in sorted(rows, key=lambda r: r[1]):
        print("  " + label)
    if dlist is not None:
        print("  dlist @ $%04X (1KB block $%04X)" % (dlist, (dlist >> 10) << 10))

    if errors:
        print("\nMEMCHECK FAILED:")
        for e in errors:
            print("  ✗ " + e)
        sys.exit(1)
    print("\nmemcheck OK (%d segments, no overlaps, dlist within 1KB)" % len(segs))


if __name__ == "__main__":
    main()
