# RECEIPT — SUITE-BASE-1: the full-width suite baseline is locked, and the 4 TIMEOUTs are resolved

Row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:353` (SUITE-BASE-1, ⏳ queued 2026-09-13)
Lane: builder cron `af3e62239ce2`, 2026-09-13. Head at start `ec32ec6`, at receipt `594f647`
(branch `glyph-transpiler-autoloop`).

## State

The baseline **reproduces**: the exact command, re-run, yields the same FAIL and TIMEOUT
verdicts with a denominator change that is fully attributable to landed fixes. Two of the four
`-t 150` TIMEOUTs were budget misconfiguration — under a `-t 400` secondary pass both complete
and both **fail**; two remain >400s unknowns.

| run | command | files | collected | verdicts | wall |
|---|---|---|---|---|---|
| baseline (row, 2026-09-13 16:01) | see row 353 | 254 | 1590 | PASS 233 · FAIL 17 · TIMEOUT 4 | 470.21 s |
| **lock re-run (pinned)** | `PATH=/usr/bin:$PATH bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4 --sink output/SUITE_BASE1_LOCK_SINK.jsonl` | **256** | **1608** | **PASS 235 · FAIL 17 · TIMEOUT 4** | 468.54 s |
| secondary budget pass | same wrapper, `-t 400`, the 4 TIMEOUT files | 4 | 43 | FAIL 2 · TIMEOUT 2 | 400.68 s |

Artifacts (all committed): `systems/SUITE_BASELINE_2026-09-13_PINNED_RERUN.txt`,
`output/SUITE_BASE1_RERUN_PINNED_20260913.txt`, `output/SUITE_BASE1_LOCK_SINK.jsonl` (256 records),
`output/SUITE_BASE1_TIMEOUT400_20260913.txt`, `output/SUITE_BASE1_TIMEOUT_SINK.jsonl`,
`.builder_queue/suite_base1_cmp.py` (per-file comparator), plus the interpreter-artifact run
`output/SUITE_BASE1_RERUN_20260913_1622.txt`.

## GATE 1 — the exact command reproduces, with attributed deltas only

`.builder_queue/suite_base1_cmp.py systems/SUITE_BASELINE_2026-09-13.txt output/SUITE_BASE1_RERUN_PINNED_20260913.txt`:

```
baseline files 254 rerun files 256
--- ONLY IN RERUN ---            (2 files, both PASS)
--- ONLY IN BASELINE ---         (none)
--- VERDICT CHANGES ---
changes: 0
--- COLLECTED DELTAS (same file, same verdict) ---
   tests/test_arc_determinism_audit.py: coll 3 -> 4 (+1)
   tests/test_gh20_fs_v2.py: coll 5 -> 10 (+5)
   tests/test_suite_iso_harness.py: coll 7 -> 10 (+3)
total collected delta over parsed files: 9
```

**Zero verdict changes. Denominator +18 collected / +2 files = 1590 → 1608, all attributable:**

| delta | +collected | landed fix |
|---|---|---|
| `tests/test_instrument1_mark_registration.py` (new, PASS 4/4) | +4 | INSTRUMENT-1 (`73f8559`) |
| `tests/test_sweep_preflight.py` (new, PASS 5/5) | +5 | SWEEP-CONTAIN-1 (`0cc6bed`) |
| `tests/test_suite_iso_harness.py` coll 7→10 (9 pass/1 fail under the *venv* interpreter only) | +3 | SWEEP-OOM-ACCT-1 (`944a629`) |
| `tests/test_gh20_fs_v2.py` coll 5→10 | +5 | DEFECT-25 (`76a5261`) |
| `tests/test_arc_determinism_audit.py` coll 3→4 | +1 | DEFECT-24 (`c6f877a`) |

PASS 233 → 235 is exactly those two new PASS files; FAIL 17 and TIMEOUT 4 are unchanged.
**This is not denominator drift: no file left the denominator, and every added test is traceable
to a commit that landed between the baseline and this run.**

## The row's command was UNDER-SPECIFIED — interpreter and PATH are part of the gate

The row writes the command as `suite_sweep.sh -b 12G -w 4 -- suite_iso_harness.py tests -t 150 -w 4`.
`tools/suite_iso_harness.py` is mode `rw-r--r--` with shebang `#!/usr/bin/env python3`, so that
literal form does not even run (no PATH entry). Re-running it the obvious way (`python3` = the
Hermes venv on PATH: py3.11.15 / pytest 9.1.1) gave:

```
Sweep finished in 435.38s. Files: 256, Total collected: 1611
Verdicts: ERROR: 3, FAIL: 23, PASS: 226, TIMEOUT: 4
```

— i.e. it looked like a 10-verdict regression against the baseline. It is not. Under
`/usr/bin/python3` (py3.12.3 / pytest 8.3.5), 8 of those 9 changed files reproduce their baseline
verdicts exactly:

| file | venv python3 | /usr/bin/python3 | baseline |
|---|---|---|---|
| test_color_explorer / test_dct_steganography / test_gh24_s2_mcp_server / test_nested_buffer | FAIL | PASS | PASS |
| test_defect20_write_identity / test_gh26_glass_box / test_obs1_mcp_transport_identity | ERROR (rc=2) | PASS | PASS |
| test_suite_iso_harness | FAIL (coll 10) | PASS 10/10 | PASS (coll 7) |

**Pin: `/usr/bin/python3` for the harness AND `PATH=/usr/bin:$PATH`.** The PATH half is not
cosmetic: `tests/test_cross_lingual_say.py` shells out to a bare `python3`, and the venv python3
has no `phonemizer`, so `tools/speak.py` silently drops the `Word 1 ARPAbet:` line the test
asserts on. Evidence, same test:

| invocation | result |
|---|---|
| default PATH (venv python3) | `1 failed in 4.22 s` (`SystemExit: 1`) |
| `PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_cross_lingual_say.py -q` | `1 passed in 1.62s` (baseline: 1.61 s) |

The row's gate text has been edited to carry the pinned form.

## GATE 2 — the 4 TIMEOUTs, resolved by a `-t 400` secondary pass (the row's allowed option)

`-t 150` hid two real FAILs behind the budget; it did not hide them as failures, it hid them as
"OUT-OF-BUDGET UNKNOWN". At `-t 400`:

| file | verdict at -t 400 | collected | result | reading |
|---|---|---|---|---|
| `tests/test_pixel_lm_train.py` | FAIL | 6 | 5 passed, **1 failed**, 218.21 s | budget misconfiguration; the failing leg is **contention-sensitive** (see caveat) |
| `tests/test_ollama_security_analysis.py` | FAIL | 37 | 36 passed, **1 failed**, 391.87 s | budget misconfiguration; one real FAIL was masked |
| `tests/test_xv6_boot_regression.py` | TIMEOUT | 0 | killed at 400.11 s | still out-of-budget unknown (>400 s); row notes `BOOT_TIMEOUT=300` |
| `tests/test_probe_stval.py` | TIMEOUT | 0 | killed at 400.67 s | still out-of-budget unknown (>400 s); no declared budget found |

**Caveat on `test_pixel_lm_train.py`, and it is a live disagreement:** a parallel orchestrator lane
measured the same file **PASS 6/6 in 80 s at `-w 1`** and recorded it in the roadmap's
SUITE-COLLECT-1 row (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:356`) with the note that its budget is
parallel-aware. My run failed 1 of 6 at `-w 4` in 218 s. Both are **n=1**, at different worker
counts, and neither was repeated — so "one masked real FAIL" is *not* established for this file.
What is established: at `-t 150 -w 4` it is an out-of-budget unknown, and it is the one file in the
set whose verdict is sensitive to the parallelism it is run under. The other three files agree
across both lanes (ollama FAIL 36/37; xv6 + probe_stval coll=0 at 400 s).

So the honest denominator is **18 known failing files (17 baseline + `test_ollama_security_analysis`)
plus 1 contention-sensitive candidate**, and 2 files remain unknowns above 400 s. `-t 150` was kept
as the global budget (the row forbids lifting it); the override is a separate one-shot pass, per the
row's own "allowlist or a `-t 400` secondary pass".

## Findings handed forward

1. **SUITE-FIX-1 gains the files `-t 150` was hiding**: `test_ollama_security_analysis.py` (36/37,
   one failing leg, ~392 s — slow *and* failing) and `test_pixel_lm_train.py` (contention-sensitive:
   FAIL 5/6 at `-w 4` here, PASS 6/6 in 80 s at `-w 1` per the parallel lane's SUITE-COLLECT-1 row).
   A fix for the latter must be measured at the cadence it will be run under, or it will flip.
2. **The harness cannot name a failing leg.** `tools/suite_iso_harness.py:345` keeps only
   `lines[-1]`, and the sink records the same. For a FAIL whose pytest tail is
   `1 failed, 36 passed in 391.25s`, the artifact does not record *which* test failed — the
   17 (now 19) baseline FAILs are named nowhere in the baseline artifact. Filed as
   `.builder_queue/TICKET_harness_failname_1.md` (short-summary capture). This is why the
   baseline had to be clustered by file, and it will slow SUITE-FIX-1 until it is fixed.
3. **Two records can share one physical line in the text artifact.** A worker's own stdout
   without a trailing newline runs into the next `[VERDICT]` line (seen in all three full runs,
   e.g. `... 7 passed in 1.20s[PASS   ] tests/test_glyph_linter.py ...`). The `--sink` JSONL is
   immune (256/256 records in the lock run). The comparator uses `findall`, not `match`.
4. **The lock run exercised the SWEEP-CONTAIN-1 widening path for real:** enclosing scope
   `memory.max = 4294967296` (the Hermes worker scope) → `widening to MemoryMax=12G
   MemoryHigh=12G (workers=4)`, and the sweep completed with no OOM kill
   (`rc=-9` verdicts are the harness's own `-t` budget, not the cgroup).

## What this PASS does NOT prove

- **Not** that the tree is green: 17 files still FAIL and 4 verdicts are TIMEOUTs. The lock is
  about *reproducibility*, not correctness.
- **Not** that the two remaining `>400 s` files terminate at all. `test_probe_stval.py` in
  particular may be a true hang; 400 s only bounds it.
- **Not** that the baseline artifact itself was produced with a pinned interpreter — the pinned
  form is *derived* here (it is the form that reproduces the baseline verdicts; the original
  header records no command line, no interpreter, no PATH). Baseline provenance remains one
  inference deep.
- **Not** a whole-machine isolation result: the sweep ran in the Hermes worker scope on a box with
  other sessions active (load ~5.7 at start). Parallel-session file churn *between* the baseline
  and this run is exactly what the +2 files / +18 collected deltas reflect; nothing was run twice
  at the same head to measure run-to-run variance.
- `test_cross_lingual_say.py`'s PATH dependence was measured on that one file, at one seed; it is
  the only file whose verdict moved between the two interpreters *in the full runs*, but the
  general claim ("no other test shells out to bare `python3`") was not proven — it was inferred
  from the single verdict difference.

## Commands (verbatim)

```
# lock re-run (GATE 1)
PATH=/usr/bin:$PATH bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- \
  /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4 \
  --sink output/SUITE_BASE1_LOCK_SINK.jsonl | tee output/SUITE_BASE1_RERUN_PINNED_20260913.txt

# secondary budget pass (GATE 2)
PATH=/usr/bin:$PATH bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- \
  /usr/bin/python3 tools/suite_iso_harness.py \
  tests/test_ollama_security_analysis.py tests/test_pixel_lm_train.py \
  tests/test_probe_stval.py tests/test_xv6_boot_regression.py -t 400 -w 4 \
  --sink output/SUITE_BASE1_TIMEOUT_SINK.jsonl | tee output/SUITE_BASE1_TIMEOUT400_20260913.txt

# comparison
python3 .builder_queue/suite_base1_cmp.py \
  systems/SUITE_BASELINE_2026-09-13.txt output/SUITE_BASE1_RERUN_PINNED_20260913.txt
```
