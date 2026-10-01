import json, collections
p = '.builder_queue/DEFECT-22_arc_legA_instability.json'
d = json.load(open(p), object_pairs_hook=collections.OrderedDict)

d['ledger_2026_09_13_0625'] = (
    "6868694: 2 runs / 0 disturbed. (a) REPLAY of seed 1210907384 (the seed first pinned at 81f0a42) "
    "at a NEW head -> rc=0 / 324 passed / 1 skipped / 136.97 s / 0 crashes "
    "(output/arc_lega_seed1210907384.{txt,json}): the SAME order gives the SAME verdict, so a green is "
    "repeatable for a pinned order (the instrument's premise demonstrated on the green side). "
    "(b) FRESH order seed=118343565 -> rc=0 / 324 passed / 1 skipped / 139.29 s / 0 crashes "
    "(output/arc_lega_seed118343565.{txt,json}). Post-194844c: 9 runs / 0 disturbed. Whole series n=14 / "
    "2 disturbed, both at 194844c. Single skip verified deterministic and named: "
    "tests/test_gh9_window_span.py::test_tick_handler_code_avoids_written_words[0]."
)
d['instrument_wart_measured'] = (
    "tools/arc_lega.sh keys the log+sidecar filename on the SEED ALONE, so a replay OVERWRITES the earlier "
    "record of that seed (measured: output/arc_lega_seed1210907384.* moved head 81f0a42 -> 6868694, "
    "138.04 s -> 136.97 s). No run history is kept per seed. Reconcilable at the git layer (each head's "
    "numbers are in the commits), not in the artifacts."
)
d['supply_2026_09_13_0625'] = (
    "Live supply = THIS ticket only. Roadmap 0 open rows (every GH/BK/ENG/DEFECT/WF/OBS/OS-SKEL/SUBSTOR/"
    "TEST-COL/SUITE-ISO row carries a closure); GLYPH_BACKLOG table exhausted (BK-1..BK-14 + OBS-1 all "
    "promoted and landed); gh12 leg nondeterminism ticket is a Jericho design call (4 options costed); "
    "OS-SKEL step 9 parked (interface decision); OSS GL-6/GL-7 artifact-done but publication-reserved, "
    "GL-8 needs an outside human. The monitor counts *.json in .builder_queue, so queue=1 == this ticket == "
    "state REPAIR_PENDING: the loop is level-triggered on a defect whose reproduction rate at 6868694 is "
    "0/9, i.e. per-tick yield is ~0 until either a pinned-order RED occurs or Jericho renews supply."
)
d['next_step'] = (
    "REPLAYABLE: `SEED=<n> bash tools/arc_lega.sh` (pins pytest-randomly, logs seed + JSON sidecar). "
    "If a SIGSEGV recurs: (1) take the seed from the sidecar, re-run it once (sanity replay, proven to "
    "reproduce a verdict at 6868694), (2) run with VERBOSE=1 so the crash names its own test, (3) only "
    "then bisect from the faulthandler frame outward, owner file last. Does NOT need a rate: a pinned-order "
    "RED is the target. Do not re-run the isolation sweep (52/52) or the allocator instruments (clean x2). "
    "Per-tick yield is ~0 at 0/9 — one bounded instrument run per tick is the ceiling; the real unblock is "
    "supply or a reproduction, not another probe."
)
json.dump(d, open(p, 'w'), indent=2)
open(p, 'a').write('\n')
print('updated', p, 'keys:', len(d))
