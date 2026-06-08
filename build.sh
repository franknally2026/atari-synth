#!/bin/sh
# Assemble the synth and (optionally) launch it in atari800 (PAL).
set -e
cd "$(dirname "$0")"

mads synth.asm -o:synth.xex -l:synth.lst
echo "built synth.xex"

# memory-map sanity check: abort the build if new code/data would clobber a
# runtime region (linetab / framebuffer), the dlist crosses a 1KB boundary, or
# a packed variable overruns its neighbour. (set -e aborts on a non-zero exit.)
python3 tools/memcheck.py

if [ "$1" = "run" ]; then
    atari800 -pal synth.xex
fi
