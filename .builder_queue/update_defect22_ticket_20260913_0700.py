#!/usr/bin/env python3
"""DEFECT-22 ticket update — builder cron af3e62239ce2, 2026-09-13 06:5x tick.

Adds this tick's MEASURED items and one correction. No claim of a rate, no
causality: every entry below is a counter or a command+output pair.
"""
import json

P = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(P))

d["crash_dump_forensics_2026_09_13_0655"] = (
    "Read the PRIMARY dump myself (output/arc_legA_194844c_run2.txt, 5716 B): "
    "the stack is COMPLETE (40 frames, outermost `<frozen runpy>`), so the named Python frame is "
    "the outermost thing that was executing — there is no hidden deeper Python frame. "
    "`git show 194844c:tools/glyph_isa_v2.py | sed -n '561p'` == `        self._check_alignment(x)` "
    "(the CALL line; `git diff --stat 194844c HEAD -- tools/glyph_isa_v2.py` is empty, so the line "
    "means the same at HEAD), yet the dump lists NO `_check_alignment` frame under it. So the earlier "
    "ticket wording ('glyph_isa_v2.py:561 _check_alignment') is imprecise: the fault landed at the "
    "call boundary (frame push / attribute lookup / allocator), not inside the checker's Python body. "
    "The crashed process had 35 native extensions resident (faulthandler footer): torch._C x12, numpy "
    "(6), PIL, psutil, zstandard.backend_c, _brotli, _cffi_backend, markupsafe/simplejson "
    "_speedups, charset_normalizer. CAPTURE PATH for a future seeded RED, measured this tick: "
    "`/usr/bin/gdb` EXISTS, `coredumpctl` does NOT, /proc/sys/kernel/core_pattern pipes to "
    "/usr/share/apport/apport and `ulimit -c` is 0 — so a core file is not the practical route; the "
    "route is a gdb replay of the seeded RED (`gdb -batch -ex run -ex bt -ex 'info threads' --args "
    "/usr/bin/python3 -m pytest <leg-A files> -p randomly --randomly-seed=<seed>`), which is what "
    "faulthandler cannot give (it never prints C frames)."
)

d["probe6_2026_09_13_0655"] = (
    "Probe #6 (LLM/native-context concentration) is INCONCLUSIVE BY ABORT, recorded as such: "
    "`.builder_queue/probe_defect22_llm_context_reps.sh`, R=12 reps of [gh12 -> owner -> 8 GPU files] "
    "in ONE process, seed 20260913, log output/defect22_llm_context_reps.txt. Killed after ~7.3 min at "
    "13% of the session (77 events: 67 passed / 10 failed, 0 Fatal Python errors) because the gh12 "
    "live-model leg's slow path (6 failed drafts) dominates wall-clock — R=12 was ~50 min at that rate. "
    "What the partial run DID show (measured, not a rate): all 10 executed gh12 instances carried a red "
    "— 1x test_full_loop_miss_to_verified_kernel_dispatch (test_gh12_autoatlas.py:105) and 9x "
    "test_registered_tile_persists_and_replays_offline (:141) — every one the identical arc-red-#1 "
    "signature `E_ATLAS_UNVERIFIED: no candidate verified in 6 attempts; last: no-halt: 5000 steps "
    "without HALT`; never a SIGSEGV. Hypothesis status: 'LLM/native context alone segfaults the arc' is "
    "UNTESTED (the run was cut short), and it is weakened by reading the crash stack: the owner test "
    "itself goes atlas.register -> generate.run_generated in every bake, so the torch/generate path runs "
    "in green runs too. Probe #5's negative (920 tests in one process, 0 crashes) stands."
)

d["gh12_leg_measurements_2026_09_13_0655"] = (
    "Measured this tick while probing (each entry is a command + its own output; 5 sessions total, run "
    "sequentially, NOT a rate and no causality claimed): "
    "(1) `pytest tests/test_gh12_autoatlas.py tests/test_gh22_device_driver_abi.py -q --randomly-seed=777` "
    "-> 9 passed in 15.46 s, 0 skips (so the ollama-gated leg RAN, it was not skipped); "
    "(2) `pytest tests/test_gh12_autoatlas.py tests/test_gh12_autoatlas.py -q --randomly-seed=20260913` "
    "-> 1 failed / 7 passed in 59.52 s, failure at test_gh12_autoatlas.py:105 (full_loop leg), same "
    "E_ATLAS_UNVERIFIED signature as the arc red #1; "
    "(3)+(4) `pytest tests/test_gh22_device_driver_abi.py tests/test_gh12_autoatlas.py -q -p no:randomly` "
    "and the REVERSE order -> 1 failed / 8 passed in 39.11 s and 39.21 s, both failing at "
    "test_gh12_autoatlas.py:141 (persists leg) with the same signature -> in that pair the red is "
    "neither order-dependent nor duplicate-instance-dependent; "
    "(5) probe #6 partial (see probe6 entry): 10/10 gh12 instances carried a red. "
    "So 4 of 5 sessions this tick had >=1 red, versus '1 red in 5 arc runs' in this ticket — the "
    "discrepancy is UNEXPLAINED and is now the most interesting open question here; candidates "
    "(none tested): host/model contention at the moment of the run (ollama measured serving "
    "`qwen2.5-coder:14b`, tools/glyph_gpt/escalate.py:32 requests exactly that tag, 8192 ctx), and this "
    "tick's own repeated invocations adding load. CORRECTED CLAIM: the parked ticket "
    "REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md says the resident model is `qwen3-coder:30b` "
    "(since 04:00); measured now via `curl -s localhost:11434/api/ps` the resident model is "
    "`qwen2.5-coder:14b` (10863650816 B, in VRAM). The 'which model's quirks would a pinned seed freeze "
    "us onto' premise of that ticket should be restated against the 14b."
)

d["ledger_2026_09_13_0655"] = (
    "ebfbbf0 + verification only: 0 arc runs this tick (deliberate: 10 runs / 0 disturbed post-194844c "
    "means an 11th green is noise). Verified the previous tick's landing MYSELF rather than trusting its "
    "claim: `bash tools/gate_arc_lega_naming.sh` -> rc=0 in 0.185 s, RED leg observed (pre-fix script at "
    "seed 999001 reused one path, log md5 7172985c... -> 8709f04b...) and GREEN holds (3 runs -> 3 "
    "artifacts; first record byte-identical 4b21e0b4... after 2 later runs; sidecar name carries the head). "
    "Row sweep re-run by parsing the roadmap table instead of grepping it: 68 table rows, 0 without a "
    "closure (the 10 checkmark-less rows are section headers: 'Host component', 'spatial_builder caller "
    "typesetting', 'atlas.link() label resolution', 'FSM grammar masking', 'GlyphCPUv2 oracle', "
    "'GlyphGPT coordination', 'launcher glue (load/run/receipt)', and 3 '#' separators). GLYPH_BACKLOG "
    "table re-read in full: BK-1..BK-14 + OBS-1, all already promoted and landed — no unpromoted row "
    "exists, so supply is still exhausted and the standing ask to Jericho is unchanged."
)

json.dump(d, open(P, "w"), indent=2)
print("updated", P, "keys:", len(d))
