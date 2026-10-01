#!/usr/bin/env python3
"""Tick close-out for 2026-09-13 14:0x CDT (cron af3e62239ce2): ticket keys + journal + near-escalation."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TICKET = ROOT / ".builder_queue" / "DEFECT-22_arc_legA_instability.json"

KEYS = {
    "lega_peak_shape_2026_09_13_1400": (
        "NAMED AND MEASURED (probe .builder_queue/probe_lega_peak_timeline.py, seed 2026091314, HEAD e1c7620, "
        "FOREGROUND on purpose so the reading is not taken against the cap under study -- artifact "
        "output/probe_lega_peak_timeline_2026091314_e1c7620.json). The 52-file run's pytest process peaks at "
        "VmHWM 2684.3 MB and the peak is ONE jump: +1925.2 MB at t=7.00 s inside tests/test_gh18_syscall_abi.py "
        "(the test completing at 11.07 s is test_gh18_syscall_table_window_reserved, so the transient sits in that "
        "test's window). RSS falls back to 758-1065 MB afterwards and the HWM stays FLAT for the remaining ~115 s "
        "over the other 50 files. Therefore leg A's ~1.28 GB in-run-vs-largest-isolated-file gap is NOT accumulation "
        "and NOT many-files: it is one test's transient in one file. Isolated cross-check: that file alone measured "
        "2652.9 MB (within 1% of the whole-run peak). Not identified and named as the next probe: WHICH allocation "
        "inside that test reserves ~1.9 GB -- this probe names file and test-id window only."
    ),
    "capture_footprint_2026_09_13_1400": (
        "THE 91%-OF-CAP NUMBER IS DECOMPOSED (probe .builder_queue/probe_capture_tree_peak.py run in the BACKGROUND "
        "so the 4 GiB worker scope applies; each sidecar confirms mem_limit_bytes=4,294,967,296; artifacts "
        "output/probe_capture_tree_peak_seed2026091315|316|317.jsonl). gdb's OWN footprint while the capture "
        "instrument drives leg A = VmRSS ~= VmHWM = 1056 MB, CONSTANT from t~5 s to exit (seed 2026091317) -- about "
        "26% of the 4 GiB cap, attributable to the debugger, not to the tests. Capture-path scope memory.peak = "
        "3702.9 / 3717.1 / 3723.1 MB (seeds 315/316/317) = 90.4-90.9% of cap, all rc=0 / crashes=0 / state=DONE. "
        "The earlier plain-path scope reading was 2.97 GB, so the capture path's ~0.74-0.96 GB excess is the size of "
        "gdb's measured footprint. CONSEQUENCE, as arithmetic not policy: a PLAIN leg-A run sits at 63-69% of the "
        "cap; the near-cap reading belongs to the CAPTURE instrument. Upper bound only, stated as such: the sum of "
        "per-process maxima (inferior VmHWM 2983 MB + gdb 1056 MB = 4039 MB) EXCEEDS the scope peak (3723 MB), so "
        "per-process RSS double-counts shared pages; gdb's 1056 MB is the direct measurement and the remainder was "
        "not split further. No policy applied: no cap, no exclusion, no worker default, no engine/test file touched."
    ),
    "instrument_bugs_2026_09_13_1400": (
        "Two bugs in THIS tick's new probes, reported because they produced wrong numbers first: (1) "
        "/proc/<pid>/task/<pid>/children yielded an EMPTY set for the capture pid on every sample, so the tree probe "
        "reported a 0 MB tree while the scope read 3.70 GB -- replaced with a /proc/<pid>/stat ppid walk, "
        "smoke-tested (2 children found on a forked bash); (2) read_kv split /proc/<pid>/status lines on ': ' while "
        "the real separator is ':\\t', silently dropping every value (same 0 MB symptom) -- replaced with a regex, "
        "smoke-tested (VmRSS 13732 kB on /proc/self/status). Seeds 2026091315 and 2026091316 ran under the broken "
        "parser: their scope/memory.peak columns are valid, their TREE columns are invalid and are not quoted "
        "anywhere. The numbers in the keys above come from seed 2026091317 (parser fixed) and from the plain-path "
        "probe, which parsed with a regex from the start."
    ),
    "ledger_2026_09_13_1400": (
        "e1c7620 + this tick: 3 CAPTURE-series arc runs (SEED=2026091315/316/317) and 1 PLAIN-series run "
        "(SEED=2026091314, foreground). All four rc=0 / 325 passed / 1 skipped / 1 deselected / crashes=0; "
        "segv_caught never triggered. Capture series 7 -> 10 runs / 0 disturbed; plain post-194844c 14 -> 15 runs / "
        "0 disturbed; whole arc series n=21 -> 25 / 2 disturbed, both at 194844c -- still two one-offs, NOT a rate. "
        "The plain run was foreground, so its sidecar records the uncapped gateway scope (scope_max_bytes null), "
        "which reproduces the recorded foreground/background asymmetry rather than a worker-scope reading."
    ),
    "supply_2026_09_13_1400": (
        "Live supply = THIS ticket only, re-measured this tick: python3 tools/supply_census.py -> TOTAL=59 OPEN=0; "
        "GLYPH_BACKLOG.md BK-1..BK-14 + OBS-1 all promoted and landed. This tick's changed files are two new probes "
        "in the queue, a receipt in systems/, and prose updates -- no engine/ABI/transpiler/test file, so the arc's "
        "green carries by dependency closure and is not re-quoted as new verification. Jericho's pending pick is "
        "unchanged: renew lane supply / accept DEFECT-22 as a documented stability bound and release the level "
        "trigger (move this .json to .builder_queue/resolved/) / re-point or slow the cron. Two design questions "
        "now carry their measurement half instead of waiting on it: the worker-cgroup cap and the harness "
        "memory-containment question."
    ),
    "next_step_2026_09_13_1400": (
        "UNCHANGED and still ARMED for the defect itself: the next RED needs `SEED=<seed> bash "
        "tools/arc_lega_capture.sh` and a sidecar reading capture.segv_caught=true with a non-null si_addr/pc_symbol. "
        "The three capture runs this tick sampled three more fresh pytest-randomly orders with no crash, which does "
        "not change the 0/15 post-194844c bound. Cheapest next units, in order: (a) the ~1.9 GB allocation SITE "
        "inside tests/test_gh18_syscall_abi.py (smaps/tracemalloc at the jump) -- the last unnamed quantity in leg "
        "A's footprint; (b) nothing else mechanical exists below this ticket."
    ),
}

ticket = json.loads(TICKET.read_text())
ticket.update(KEYS)
TICKET.write_text(json.dumps(ticket, indent=1) + "\n")
print(f"ticket: {TICKET} now {TICKET.stat().st_size} B, keys={len(ticket)}, added={len(KEYS)}")

JOURNAL = """

## TICK 2026-09-13 14:0x CDT (`e1c7620`) — leg A's peak NAMED, and the 91 % decomposed: ~1.06 GB of it is gdb

Wake cause: monitor diff `head ecef274 -> e1c7620` (this lane's own near-escalation doc commit). Supply re-measured
before anything else: `python3 tools/supply_census.py` -> **TOTAL=59 OPEN=0**; backlog BK-1..BK-14 + OBS-1 all
promoted and landed. So there was no eligible row, and the tick took the one measurement the previous receipts
**named and did not run** (the unexplained leg-A gap), not a new policy.

**Unit 1 — plain path, sampled 1 Hz inside a real leg-A run** (`.builder_queue/probe_lega_peak_timeline.py`, seed
2026091314, FOREGROUND so the reading is not taken against the cap under study; artifact
`output/probe_lega_peak_timeline_2026091314_e1c7620.json`). rc=0, 126.05 s, 52 files, 126 samples, line timing
usable (351 lines, span 124.5 s). The whole 52-file run's pytest `VmHWM` is **2684.3 MB** and it is set by exactly
**one jump: +1925.2 MB at t=7.00 s inside `tests/test_gh18_syscall_abi.py`** (the test completing at 11.07 s is
`test_gh18_syscall_table_window_reserved`). RSS falls back to 758-1065 MB and the HWM stays **flat for the remaining
~115 s over 50 files**. Cross-check: that file isolated measured 2652.9 MB. **So the ~1.28 GB gap is one test's
transient in one file — file-local, not accumulation** — which is the measurement half of both memory tickets.

**Unit 2 — capture path, whole-tree + scope footprint** (`.builder_queue/probe_capture_tree_peak.py`, BACKGROUND so
the 4 GiB worker scope applies; three runs, seeds 2026091315/316/317, all `rc=0 ticks=crashes=0 state=DONE`). Scope
`memory.peak` = **3702.9 / 3717.1 / 3723.1 MB = 90.4-90.9 % of cap**; inside it, **gdb's own `VmRSS` ≈ `VmHWM` =
1056 MB, constant** (~26 % of the cap, and the size of the capture path's excess over the plain path's 2.97 GB).
Honest bound, stated: the sum of per-process maxima (2983 + 1056 = 4039 MB) **exceeds** the scope peak (3723 MB), so
per-process RSS double-counts shared pages — gdb's figure is direct, the rest is not split. Receipt
`systems/RECEIPT_DEFECT22_LEGA_CAPTURE_FOOTPRINT.md`; both REPAIR_PENDING tickets gained this section as a measured
input, and **no policy was applied** (no cap, no exclusion, no default, no engine/test file touched).

Ledger: capture 7 -> 10 runs, plain post-`194844c` 14 -> 15, whole series n=25 with the same 2 disturbances at
`194844c` — still two one-offs, NOT a rate. Instrument honesty: two bugs in this tick's own probes (empty
`/proc/<pid>/task/<pid>/children`; `": "` vs `":\\t"` parsing) produced a 0 MB tree while the scope read 3.70 GB; both
are fixed, smoke-tested, and the two runs made under the broken parser have their tree columns marked invalid. Still
unnamed below this ticket: **which allocation inside that gh18 test reserves ~1.9 GB** (next probe, smaps at the jump).
"""

NEAR_ESC = """
## 2026-09-13 14:0x CDT — Almost asked: should this lane keep spending ticks on measurement while it holds?
**Decided instead:** took the specific measurement the previous two receipts had NAMED and left unrun (the leg-A vs
capture-path footprint gap) and landed it as a receipt, rather than either holding-and-reporting again or picking one
of the tickets' containment options myself.
**Reason:** the tickets' options are resource policy over Jericho's own worker instrument, so they stay his call — but
the measurement they were waiting on is mechanical, bounded, and the loop's own instrument, which is the same shape of
work the lane has landed without a ruling all day (naming 06:35, sidecar 09:15, apport path 09:25, the L6 note 13:32).
Doing nothing was not free either: `state=REPAIR_PENDING` is a level trigger on a defect at 0/15 post-`194844c`, so the
alternative was another re-measurement tick.
**Outcome:** `systems/RECEIPT_DEFECT22_LEGA_CAPTURE_FOOTPRINT.md`; leg A's peak named
(`tests/test_gh18_syscall_abi.py`, one +1925 MB transient); the 91 % figure decomposed with **gdb = 1056 MB** measured
directly; three clean capture-series runs added (10 / 0 disturbed). Honest residual: the allocation site inside that
test is still unnamed, and the policy questions are exactly where they were — filed, measured, and still Jericho's.
"""

for path, text in ((ROOT / "systems" / "GLYPH_SELF_HOSTING_ROADMAP.md", JOURNAL),
                   (ROOT / "NEAR_ESCALATIONS.md", NEAR_ESC)):
    with path.open("a") as fh:
        fh.write(text)
    print(f"appended {len(text)} chars to {path} ({path.stat().st_size} B)")
