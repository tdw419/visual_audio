# RECEIPT — DEFECT-22: per-file isolation is clean; the dot-position reading was an unsound instrument (2026-09-13, cron `af3e62239ce2`)

**Ticket:** `.builder_queue/DEFECT-22_arc_legA_instability.json` (OPEN — narrowed, not closed)
**HEAD:** `c2750bd` (branch `glyph-transpiler-autoloop`), `tracked_dirty=0`
**Interpreter:** `/usr/bin/python3` (py3.12 — the one with `mcp`), pytest 8.3.5
**Trigger:** monitor level-trigger `state=REPAIR_PENDING queue=1` (the open ticket is the only
`.json` in `.builder_queue/`) at the tick after SUITE-ISO-1 landed.

## 1. The instrument the ticket asked for: per-file isolation over the 52-file arc

```bash
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp')
/usr/bin/python3 tools/suite_iso_harness.py $FILES --timeout 300 --workers 8 --json > output/defect22_iso_sweep1.json
```

**Result: 52/52 files PASS, rc=0, 325 tests collected** — exactly the leg-A collected count
(324 passed + 1 skipped). No file-local FAIL, CRASH, TIMEOUT or ERROR. So the run-2 SIGSEGV is
**not** a file-local defect: every one of the 52 files is green in its own subprocess, and the
crash needs the shared-process context.

Measured per-file cost (why the default 15 s budget is wrong for this set — 4 files exceed it on a
loaded host):

| file | s | file | s |
|---|---|---|---|
| `tests/test_gh20_fs_v2.py` | 68.90 | `tests/test_bk11_coreutils.py` | 27.23 |
| `tests/test_bk13_net.py` | 47.99 | `tests/test_gh26_emit_admit.py` | 22.55 |
| `tests/test_gh12_autoatlas.py` | 36.98 | `tests/test_gh18_syscall_abi.py` | 17.48 |

(`tests/test_gh12_escalation.py` 13.10, `tests/test_gh23_libc_runtime.py` 6.22.) A tests-root sweep
at the harness default will therefore report `TIMEOUT` for gh20/bk13/gh12/bk11; use `--timeout 300`
when a real verdict is wanted.

## 2. Three further full-arc runs (verbose, so a crash names its own test)

`.builder_queue/defect22_legA_verbose_rerun.sh` → `output/defect22_legA_verbose_rerun_summary.txt`:

| run | rc | crash | wall | loadavg before→after | result |
|---|---|---|---|---|---|
| 1 | 0 | 0 | 142 s | 3.19→1.41 | 324 passed, 1 skipped (140.63 s) |
| 2 | 0 | 0 | 140 s | 1.41→1.08 | 324 passed, 1 skipped (138.68 s) |
| 3 | 0 | 0 | 141 s | 1.08→1.22 | 324 passed, 1 skipped (140.64 s) |

**Ledger, labelled as observations and not as a rate** (Jericho's single-trial rule): at `194844c`,
5 runs → 2 disturbed (1 gh12 sampling red, 1 SIGSEGV); at/after `c2750bd`, **4 runs → 0 disturbed**
(the SUITE-ISO-1 post-landing arc run plus these three). Total n=9, 2 disturbed. Nothing here
establishes a failure rate; the crash did not recur under 3 more attempts at the same shape.

Correction to a plausible-looking signal: run 1's 159.70 s (vs ~140 s green) is **explained by its
own failed gh12 leg** — six LLM drafts plus 5000-step no-halt checks — not by host load. Do not cite
that duration as a contention signature.

## 3. `-q` dot position is an unsound instrument (proven out-of-tree)

The ticket carried a "SIGSEGV at ~44 % + 23 dots" position. Counted exactly, run 2's captured
progress stream holds **197 completions (60.6 %)** → item #198 `tests/test_gh6_syscalls.py`, while
run 2's own faulthandler traceback names item **#264** `tests/test_gh22_device_driver_abi.py::
test_gh22_driver_abi_image_bakes` — a 127-item disagreement. Probe
`.builder_queue/probe_defect22_dot_lag.py` (out of tree, `/tmp/defect22_probe`, 200 trivial tests,
deliberate `SIGSEGV` inside test #150, same interpreter/redirect shape):

```
149 tests actually completed before the crash; only 135 dots reached the file
=> the dot stream LAGS (block-buffered stdout is lost when the process dies by signal)
```

So the captured dots are a **lagging lower bound**, not a position. The traceback is the
authoritative namer, and it is consistent with a real position past 197. Consequence for the record:
the crash owner has been known since run 2 — `test_gh22_device_driver_abi.py::
test_gh22_driver_abi_image_bakes`, at `_bake` → `build_default_atlas` → `register` → `run_generated`
→ `glyph_isa_v2.run` → `step` — while the dot reading pointed at a file ~127 items earlier. Any
future crash report must quote the faulthandler traceback, never a dot count.

## 4. What this does NOT show

- **Not a fix and not a mechanism.** The crash site is undiagnosed. The innermost frame is
  `tools/glyph_isa_v2.py:561 self._check_alignment(x)` — two lines, `x % INSTR_WIDTH` on a Python
  int — which cannot fault by itself; the frames are pure Python with no C-extension frame named,
  and host memory was never the constraint (62 GB RAM, 47 GB free). The mechanism needs a
  reproduction, not a guess.
- **Not a rate.** 2 disturbed in 9 runs, none in the last 4.
- **Isolation is a different claim.** 52/52 in separate subprocesses says nothing about
  cross-file contamination, which is exactly the context the crash needs — the isolated sweep
  cannot see it by construction.
- **The gh12 red is a separate, still-open design question**
  (`.builder_queue/REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md`): its verdict depends on what
  the local model drafts. It passed in the isolation sweep (4/4, 36.98 s) and is the one anomaly
  with a known non-deterministic source.
- **No new supply.** Roadmap has 0 open rows; `systems/GLYPH_BACKLOG.md`'s BK-1..BK-14 + OBS-1 table
  is exhausted. Nothing was promoted — inventing scope is not the loop's call.

## Next rung (not run this tick, gated on recurrence)

The crash needs shared-process context; at ~2/9 occurrence a one-process bisect over the 52-file set
is ~6 runs (≈15 min) per halving with no guarantee of a hit. Cheaper and honest: keep
`defect22_legA_verbose_rerun.sh` as the standing reproducer, and if the SIGSEGV recurs, bisect from
the faulthandler-named frame outward (run the owner file last after a growing prefix), rather than
re-running the whole arc and reading dots.

## 5. The ordered allocator instruments, RUN (2026-09-13 06:0x tick, head `9e4bfa5`)

The ticket's "cheapest next instrument" was discharged this tick, plus its C-level complement. Both
are full arc leg A (52 files, the same file list as every ledger run above), both at head `9e4bfa5`
(docs-only commits on top of `c2750bd`), both rc=0 with **no** `Fatal Python error` in the log:

| instrument | what it would catch | result | wall |
|---|---|---|---|
| `PYTHONMALLOC=debug` under `/usr/bin/python3 -X dev` | dangling/freed **Python-object** buffer → names the class instead of dying by signal | rc=0, crash=0, **324 passed / 1 skipped** | 153.84 s |
| `MALLOC_PERTURB_=42` (glibc fills freed memory) | use-after-free in a **C-allocated** buffer → reads visibly wrong instead of plausibly right | rc=0, crash=0, **324 passed / 1 skipped** | 139.06 s |

The second instrument is not redundant: `PYTHONMALLOC=debug` only guards *Python's own* allocator,
while the run-2 traceback names a **C-level call under `glyph_isa_v2.step`** with pure-Python frames
above it — exactly the shape a Python-allocator instrument cannot see.

Artifacts: `output/defect22_legA_pymalloc_debug_run1.txt`,
`output/defect22_legA_mallocperturb_run1.txt`; scripts
`.builder_queue/defect22_pymalloc_debug_run.sh`, `.builder_queue/defect22_mallocperturb_run.sh`.

**What this changes in the ledger:** post-`194844c` is now **6 runs / 0 disturbed** (`c2750bd` ×4,
`9e4bfa5` ×2); the whole series is **n=11, 2 disturbed**, both at `194844c`. The arc's green claim is
now also green under two corruption-detecting allocators — a stronger negative than a plain re-run,
because those instruments would have converted a silent native crash into a *named* abort.

**What this does NOT change:** the mechanism is still undiagnosed and DEFECT-22 stays OPEN. A green
run under a detector is a negative result **for that run only** — at ~2/11 occurrence a single clean
run misses the class roughly 78 % of the time. These two runs are ledger entries, not a closure, and
no future receipt may cite them as "the crash is fixed." The gh12 LLM-sampling red remains the
separate, still-open design question
(`.builder_queue/REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md`); it passed in both of these runs.

