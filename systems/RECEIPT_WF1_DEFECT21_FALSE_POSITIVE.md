# RECEIPT — DEFECT-21: WF-1 claim scanner flagged a limitation LABEL as a landed claim

**Run:** builder cron `af3e62239ce2`, 2026-09-13 ~04:00–04:10 CDT
**Tree:** branch `glyph-transpiler-autoloop`, HEAD `7bfafc0` (`tracked_dirty=0`, `state=CLEAN`), plus the
one test-file edit below.
**Trigger:** the monitor saw the tree go `DIRTY_ACTIVE` → `CLEAN` with head moving to `7bfafc0` (the
previous tick's ecall-duplicate revert). PHASE 1 found 0 eligible roadmap rows, so this tick spent its
budget on **PHASE 3 verification**, which is how the defect was found.

## 1. What was RED

Not the canonical arc — that is green (§ 4). The red is in a suite the canonical arc list **does not
include**: `tests/test_wf1_tick_claim_bound.py` (WF-1's claim-bound gate, landed `5d7665d`).

```
/usr/bin/python3 -m pytest tests/test_wf1_tick_claim_bound.py -q   ->  4 passed, 1 failed, rc=1
python3         -m pytest tests/test_wf1_tick_claim_bound.py -q   ->  4 passed, 1 failed, rc=1
FAILED tests/test_wf1_tick_claim_bound.py::test_wf1_l3_no_gpu_tick_parity_claim
       AssertionError: Found ungrounded GPU tick parity claims in repo
```

Evidence: `output/wf1_gate_run8_red_7bfafc0.txt` (py3.12), `output/wf1_gate_run8_red_venv.txt` (venv).

## 2. Root cause — named, not inferred

I ran the committed scanner over the declared claim surface out-of-tree
(`output/wf1_rediscan_probe.py` → `output/wf1_rediscan_7bfafc0.txt`): **1 flagged unit across 138 claim
files** — `systems/RECEIPT_SUBSTOR-1_SUBSTRATE_STORAGE_ORACLE.md`:

> **Not run this tick:** the full arc suite (only the gate plus its L5 leg were run), the GPU/WGSL parity
> legs, and any QEMU lockstep run.

That is the loop's own standing limitation label, not an assertion at all. It matched none of the 30
committed negation patterns (the three scanner tokens `this tick`, `GPU/WGSL` and `parity` are all present
in it), so `gpu_tick_parity_claims()` read a **statement of what was not done** as a landed claim. The gate's own vocabulary list already admits sibling limitation markers
(`not verified`, `unbuilt`, `unmeasurable`, `nothing to measure`); `not run` was simply missing.

## 3. Fix — two adjacency-matched negation patterns (the precedented widening)

`tests/test_wf1_tick_claim_bound.py`:

- `_NEGATION_PATTERNS` += `r"not\s+run\b"`, `r"not\s+been\s+run\b"` with a measured provenance comment.
  Adjacency-matched deliberately: an overclaim whose negation does not touch "run" still trips (§ 5, W4).
- `test_wf1_l3` gains **known negative 4** (the verbatim SUBSTOR clause) plus a discrimination control
  (the same sentence with its label replaced by a plain `This tick:` **must** trip).

No engine, baker, transpiler or shader file touched; one file changed (`git status --short` = ` M
tests/test_wf1_tick_claim_bound.py` only).

## 4. Verification (my own runs, before → after)

| run | before | after |
|---|---|---|
| `tests/test_wf1_tick_claim_bound.py` (`/usr/bin/python3`) | 4 passed / **1 failed**, rc=1 | **5 passed**, rc=0 (`output/wf1_gate_run9_green_py312.txt`) |
| same (repo `python3`, Hermes venv) | 4 passed / **1 failed**, rc=1 | **5 passed**, rc=0 (`output/wf1_gate_run9_green_venv.txt`) |
| real claim surface, 138 files | **1 flagged** (`output/wf1_rediscan_7bfafc0.txt`) | **0 flagged** (`output/wf1_rediscan_post_defect21.txt`) |
| adversarial corpus, 8 positives (`output/wf1_orch_probe.py`) | 7/8 caught | **7/8 caught — unchanged** (`output/wf1_orch_probe_post_defect21.txt`) |
| extended suite set, 12 files (osskel/substor/obs1/wf1/spatial) | **1 failed**, rc=1 (`output/arc2_new_suites.txt`) | **83 passed / 0 failed / 0 errors**, rc=0 (`output/arc2_new_suites_post_fix.xml`) |
| canonical arc, 52 files | green | **325 tests / 0 failures / 0 errors / 1 skipped / 142.6 s**, rc=0 (`output/arc_verify_7bfafc0.xml`) |

The adversarial corpus is the anti-vacuity check that matters here: widening a guard list is exactly how
WF-1's first scanner became blind (a 36-pattern list that contained builder vocabulary and missed 3/8
positives). **No detection power was lost** — all 7 catchable positives still trip; the 8th (P8) is the
gate's own declared boundary (it carries no tick token at all) and was missed before this change too.

**Self-check after landing this receipt and the roadmap footer** (both sit inside the declared claim
surface, 138 → 139 files): the scanner flagged **one** unit — a §2 sentence of this receipt that described
the defect — so that sentence was reworded to quote the three scanner tokens as inline code spans (data, not
assertion). Final state: **0 flagged / 139 files**, gate 5/5 on both interpreters. This is the same
phenomenon as WF-1's own landing (the guard fires on the documentation that describes it), handled the same
way — reword the prose, never widen the guard to silence it.

## 5. Guard-withdrawal probe — what the widening does and does not do

`output/defect21_guard_withdrawal_probe.py` → `output/defect21_guard_withdrawal_probe.txt`:

| # | case | result |
|---|---|---|
| W1 | `WGSL tick parity verified: CPU ≡ GPU for preemption.` | TRIP (baseline detection intact) |
| W2 | the SUBSTOR limitation clause | CLEAN (the fix) |
| W3 | same clause with the label replaced by `This tick:` | **TRIP** — the label, not the sentence, is what clears it |
| W4 | overclaim + **non-adjacent** `not … run` ("does not need to be run separately") | **TRIP** — adjacency holds |
| W5 | overclaim + `…; the WASM leg was not run.` in one unit | CLEAN |
| W6 | overclaim + `…; the legacy leg was not verified.` (pre-existing pattern) | CLEAN |
| W7 | `**Not run this tick:** the full arc suite.` (limitation, no claim) | CLEAN |

**Honest boundary (measured, not hidden):** W5 shows the new patterns join the *pre-existing* unit-level
negation boundary — the scanner clears a whole claim unit when any negation matches it, and that is
already true for all 30 older patterns (W6, unchanged by this receipt). So this fix does not introduce a
novel blindness class; it adds one more way to clear a unit that describes itself with a negation. A
sentence that asserts parity **and** separately says something was not run remains undetectable by this
scanner — same as today for "not verified". Tightening that would mean re-scoping the negation from
unit-level to token-proximity, which is a design change to a landed gate, not a vocabulary addition.

## 6. Finding worth carrying forward: the canonical arc list is narrower than the corpus

The canonical arc command recorded in `systems/RECEIPT_ARC_VERIFY_3e2bd8e.md` globs
`tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py`. It **omits**
`test_osskel_*`, `test_substor_*`, `test_obs1_*`, `test_wf1_*` and `test_spatial_rv32i_cpu.py` — the
suites for the newest landed rows. That is why this red gate could sit at a clean HEAD: the loop's own
"arc green at HEAD" claim is true *of the 52 files it names* and silent about the other 12.
Recommended arc command from this tick on (both legs, authoritative counts from junitxml):

```bash
# leg A — the 52-file canonical arc (unchanged, comparable with prior receipts)
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py \
        | grep -vE 'glass_box|gh24_s2_mcp')
/usr/bin/python3 -m pytest $FILES -q --junitxml=output/arc_verify_<head>.xml
# leg B — the newer row suites (83 tests, 8.3 s)
/usr/bin/python3 -m pytest tests/test_osskel_*.py tests/test_substor_*.py \
        tests/test_obs1_*.py tests/test_wf1_*.py tests/test_spatial_rv32i_cpu.py \
        -q --junitxml=output/arc_new_suites_<head>.xml
```

`/usr/bin/python3` (py3.12) is the interpreter that has `mcp`, so leg B's `test_obs1_*` /
`test_defect20_*` modules collect there and not under the Hermes cron venv (measured this tick:
`tests/` collection is 18 errors under `/usr/bin/python3` vs 21 under the venv — the 3 extra are
`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`, not regressions).

## 7. Files

- changed: `tests/test_wf1_tick_claim_bound.py` (guard list + known negative 4)
- new: this receipt; ticket `.builder_queue/resolved/DEFECT-21_wf1_limitation_label.json`
- evidence on disk (untracked, `output/`): `wf1_rediscan_probe.py`, `wf1_rediscan_7bfafc0.txt`,
  `wf1_rediscan_post_defect21.txt`, `wf1_gate_run8_red_7bfafc0.txt`, `wf1_gate_run8_red_venv.txt`,
  `wf1_gate_run9_green_py312.txt`, `wf1_gate_run9_green_venv.txt`, `wf1_orch_probe_pre_defect21.txt`,
  `wf1_orch_probe_post_defect21.txt`, `defect21_guard_withdrawal_probe.py`/`.txt`,
  `arc_verify_7bfafc0.xml`, `arc2_new_suites.txt`, `arc2_new_suites_post_fix.xml`

## NOT verified this tick

The full arc **under the Hermes cron venv** for the canonical list (leg A was run under py3.12 only,
matching the `3e2bd8e` receipt's interpreter), any WGSL/GPU execution (the fix is a pure Python text
scanner; no GPU leg applies and none is claimed), the OSS lane repo (`b5aa3f2`/`0aa14b1` still unpushed
and out of this lane), and TEST-COL-1's remaining legs (still parked on Jericho's `src`-conflict ruling).
