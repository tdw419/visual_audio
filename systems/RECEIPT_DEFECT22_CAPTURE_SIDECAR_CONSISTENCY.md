# RECEIPT — DEFECT-22 capture instrument: the sidecar no longer records a captured SIGSEGV as "no crash"

**Date:** 2026-09-13 ~09:15 CDT · **Seat:** builder orchestrator (cron `af3e62239ce2`) · **Head:** `d62e96a`
**Ticket:** `.builder_queue/DEFECT-22_arc_legA_instability.json` · **Type:** mechanical hardening of an existing instrument (no engine/transpiler/ABI/WGSL file touched)

## Trigger

The monitor woke this tick on a level trigger only — `head=d62e96a tracked_dirty=0 state=REPAIR_PENDING queue=1 ticket_age_h 0 → 1`. Nothing in the tree changed and no new supply exists, so instead of a 13th green arc run (noise at 0/12 disturbed) the tick went at the warts the ticket itself lists for the instrument built at `5da0a63`. The ticket named this one in prose; nobody had measured it.

## Finding — measured, not inferred

The sidecar's `crashes` field is the grep count of the *inferior's own* `Fatal Python error` lines. A captured SIGSEGV never produces those lines: gdb's `handle SIGSEGV stop` fires first and the process prints nothing. So for exactly the RED this instrument exists to record, the record said:

```bash
OUTDIR=/tmp/d22probe/out PY=<crasher stub> SEED=999003 bash tools/arc_lega_capture.sh
# rc=139, transcript shows DEFECT22_CAPTURE: segv_caught=true, si_addr=0x0,
#           pc_symbol='__strlen_avx2 + 29 ... /libc.so.6'
```

```json
{ "seed": 999003, "head": "d62e96a", "rc": 139, "crashes": 0,
  "capture": { "segv_caught": true, "signal": "SIGSEGV", "pc": "0x7ffff7d8badd",
               "si_addr": "0x0",
               "pc_symbol": "__strlen_avx2 + 29 in section .text of /lib/x86_64-linux-gnu/libc.so.6" } }
```

`segv_caught: true` next to `crashes: 0`. A reader (or a later gate leg) keying on `crashes` reads a captured crash as **no crash** — a false negative in the one artifact a future RED is supposed to make unambiguous. Pre-fix record preserved: `output/defect22_sidecar_contradiction_PREFIX_d62e96a.json` (+ `.txt`).

## Finding 2 — an instrument failure could read as a verdict (found by getting it wrong)

The parse step was launched with a bare `"$PY" - …`, while the gdb leg routes a non-ELF `PY` (gate stub) through `/bin/bash`. With a non-executable stub the parse step died `Permission denied`; the run still printed `arc leg A (live capture) :: … rc= segv= si_addr= pc=` and exited 2 **with a transcript and no sidecar**. Measured pre-fix: `rc=2`, no `.json`, empty rc in the summary line.

## Fix (both legs of the same property: the record must not lie)

`tools/arc_lega_capture.sh`
- `crashes` is now derived, not raw: a caught SIGSEGV counts as one crash (`if segv_caught: crashes = max(crashes, 1)`), the raw grep count is kept as **`faulthandler_crashes`** for audit, and the rule used is stated in **`crash_count_source`** (`live_capture` | `faulthandler` | `none`). Existing keys keep their meaning; the two new keys are additions.
- The parse step now runs through the same `"${GDB_EXEC[@]}"` guard as the inferior, so the two can no longer disagree about how `PY` is invoked.
- If the sidecar was not written the instrument prints `FATAL: capture sidecar was not written …` and exits **2** — it refuses to print a verdict, and the transcript is named in the message.

`tools/gate_arc_lega_capture.sh` — new **L1b leg**, non-vacuous by falsifier:
- predicate: `capture.segv_caught is true ⇒ crashes >= 1`; and `segv_caught is not true ⇒ crashes == 0`;
- GREEN leg: L1's own captured-SIGSEGV sidecar must satisfy it;
- RED leg: the **pre-fix instrument, pinned to revision `d62e96a`** (`git show`), is run against the same crasher and must FAIL the same predicate — with a premise check that the recovered script lacks `crash_count_source`, so the leg cannot silently go stale (the lesson from the naming gate, which broke when its pinned revision became HEAD).

## Verification (my own runs, this tick)

| What | Command | Result |
|---|---|---|
| gate, all legs incl. L1b | `bash tools/gate_arc_lega_capture.sh` | **rc=0** — L1 PASS, **L1b PASS** (green predicate rc=0; pre-fix predicate rc=3 = contradiction observed; premise 1), L2/L3/L4/L5 PASS |
| sidecar honesty, post-fix | `OUTDIR=/tmp/d22probe/out_post PY=<crasher stub> SEED=999003 bash tools/arc_lega_capture.sh` | rc=139 · `crashes: 1`, `faulthandler_crashes: 0`, `crash_count_source: "live_capture"`, `segv_caught: true` → no contradiction (`output/defect22_sidecar_POST_d62e96a_crasher.json`) |
| plumbing fix | same, with a **non-executable** stub | rc=139, sidecar written (`output/defect22_sidecar_noexec_interpreter_d62e96a.json`) — pre-fix this was rc=2 with no sidecar |
| acceptance on the real 52 files | `SEED=1208765432 bash tools/arc_lega_capture.sh` | **rc=0 · 325 passed / 1 skipped / 1 deselected / 123.06 s · segv=no** (`output/arc_lega_capture_seed1208765432_d62e96a.{txt,json,gdb.txt}`) |

Capture-instrument series after this tick: **n=2 runs / 0 disturbed** (kept separate from the plain-run ledger — a capture run is a different experiment). The instrument has still **not** caught the real defect.

## NOT verified / not done

- **The real defect is still uncaptured.** `5da0a63` established the mechanism against a crash we caused on purpose; this tick only makes the *record* of a real capture trustworthy. `si_addr`-on-the-real-defect remains unproven.
- **No plain arc leg A run this tick** (post-`194844c`: 12 runs / 0 disturbed — a 13th green is noise). The crash mechanism from the recovered 05:18 core is still UNDIAGNOSED.
- The gate's L5 hygiene check still verifies tracked-modified == 0 + presence of the four in-scope files, not a full untracked-file allowlist (unchanged, known).
- `tests/fixtures/faulthandler_segv_fixture.py` is a deliberate crasher: apport reports whose `ProcCmdline` is that fixture (e.g. `/var/crash/*.crash` at 08:01) are expected instrument artifacts, never evidence of a new arc crash.
