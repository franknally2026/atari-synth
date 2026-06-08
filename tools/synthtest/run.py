#!/usr/bin/env python3
"""Entry point for the atari-synth test framework.

  python3 -m tools.synthtest.run            # run everything
  python3 -m tools.synthtest.run core       # only matching scenario groups
  python3 -m tools.synthtest.run --no-audio # skip PCM-capture scenarios

Boots synth.xex once under headless AltirraSDL, runs every registered scenario
against it, prints a grouped PASS/FAIL summary, and exits non-zero on any
failure (CI-friendly). PCM-acoustic scenarios are skipped with a notice if the
emulator build lacks the AUDIO_RECORD command.
"""
import sys
import time
import traceback

# allow both `python3 -m tools.synthtest.run` and direct execution
if __package__ in (None, ""):
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    from tools.synthtest.harness import Synth
    from tools.synthtest.scenario import Reporter
    from tools.synthtest.scenarios import REGISTRY
else:
    from .harness import Synth
    from .scenario import Reporter
    from .scenarios import REGISTRY


def main(argv):
    want_audio = "--no-audio" not in argv
    filters = [a for a in argv if not a.startswith("-")]

    def selected(fn):
        return not filters or any(f in fn.__module__ or f in fn.__name__ for f in filters)

    rep = Reporter()
    skipped = []
    t0 = time.time()

    with Synth() as s:
        audio_ok = want_audio and s.audio_available()
        if want_audio and not audio_ok:
            print("!! AUDIO_RECORD unavailable in this AltirraSDL build — "
                  "PCM-acoustic scenarios will be skipped.")
            print("   (rebuild AltirraSDL with the bridge audio command to enable them.)")

        for fn, needs_audio in REGISTRY:
            if not selected(fn):
                continue
            if needs_audio and not audio_ok:
                skipped.append(fn.__name__)
                continue
            try:
                fn(s, rep)
            except Exception as e:
                rep.section(fn.__name__)
                rep.check(f"{fn.__name__} raised {type(e).__name__}", False, str(e))
                traceback.print_exc()

    dt = time.time() - t0
    print("\n" + "=" * 60)
    if skipped:
        print(f"SKIPPED (no audio): {', '.join(skipped)}")
    fails = rep.failures()
    if fails:
        print(f"\n{len(fails)} FAILURE(S):")
        for g, n, d in fails:
            print(f"  [{g}] {n}" + (f"  ({d})" if d else ""))
    print(f"\n==== {rep.npass}/{len(rep.results)} checks passed "
          f"in {dt:.1f}s ====")
    return 0 if rep.nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
