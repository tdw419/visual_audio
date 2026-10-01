# RECEIPT — DEFECT-22: the arc's file order is randomized, and was never recorded

**Date:** 2026-09-13 06:2x tick · **Builder cron:** `af3e62239ce2` · **Head:** `81f0a42`
**Ticket:** `.builder_queue/DEFECT-22_arc_legA_instability.json` (stays **OPEN**)
**Predecessors:** `systems/RECEIPT_ARC_LEGA_INTERMITTENT_194844c.md`,
`systems/RECEIPT_DEFECT22_ISOLATION_AND_DOT_LAG.md`

## 1. The measurement that was missing

`RECEIPT_ARC_LEGA_INTERMITTENT_194844c.md:95` listed as **not measured**: *"whether
pytest-randomly was actually active in runs 1–5."* It is active. Measured this tick:

```
/usr/bin/python3 -m pytest tests/test_gh6_syscalls.py --co -q --randomly-seed=111 > /tmp/rd1.txt
/usr/bin/python3 -m pytest tests/test_gh6_syscalls.py --co -q --randomly-seed=222 > /tmp/rd2.txt
=> order DIFFERS across seeds  -> randomly ACTIVE
   plugin: /home/jericho/.local/lib/python3.12/site-packages/pytest_randomly/__init__.py
   -v run logs: 'Plugins: {... randomly: 4.0.1}' + 'Using --randomly-seed=NNN'
   no `no:randomly` guard in pytest.ini / pyproject.toml / setup.cfg / conftest.py, no PYTEST_ADDOPTS
```

The arc interpreter is `/usr/bin/python3`, so **every leg-A run to date executed the 52
files in a different order**, and the `-q` runs logged no seed (pytest-randomly prints
the seed in the header, which `-q` suppresses).

## 2. What that invalidates

| Artifact | Status after this measurement |
|---|---|
| `-p no:randomly` on 194844c run 3 (`RECEIPT_ARC_LEGA_INTERMITTENT_194844c.md:27`) | **confound**, not a fix — it pinned an order once, nothing else |
| `.builder_queue/count_run2_progress.py:8` ("no pytest-randomly is installed, so order == collection order") | **premise FALSE** — docstring corrected this tick |
| "leg A green 6/6 since 194844c" | 6 *different* experiments, not 6 repetitions of one — the greens do not exclude an order-dependent red |
| Either disturbed run's order | **unrecoverable** (no seed logged) |

## 3. Instrument landed (durable fix for the *knowability* problem)

`tools/arc_lega.sh` — canonical leg-A runner: pins `--randomly-seed` (fresh random by
default, or `SEED=<n>` for replay), logs the seed, writes a JSON sidecar
(`seed`, `head`, `rc`, `crashes`, `seconds`, `summary`, `loadavg_before`), exits with
pytest's rc. **Validated end-to-end this tick** against a previously recorded order:

```
SEED=1210907384 bash tools/arc_lega.sh
 -> arc leg A :: seed=1210907384 head=81f0a42 rc=0 crashes=0 secs=139
    Using --randomly-seed=1210907384
    324 passed, 1 skipped in 138.04s
    output/arc_lega_seed1210907384.{txt,json}
```

This is instrumentation, not a fix: the order dependence (and therefore the
intermittency) remains; what changes is that any future RED is replayable.

## 4. Cheap discriminating probe run, and its honest power

`_check_alignment` (`tools/glyph_isa_v2.py:438`) is `if x % INSTR_WIDTH != 0: raise` —
one modulo that cannot segfault, so `:561` is a **victim frame** and the fault originates
elsewhere (async native/GPU callback, or heap corruption from a C extension). Leading
context candidate: 8 of the 52 leg-A files create wgpu/Vulkan devices (RTX 5090).

Probe (`.builder_queue/probe_defect22_gpu_context_reps.sh`): the crashed owner module plus
those 8 GPU files, **20 repetitions inside one process**, `-v`, faulthandler on:

```
R=20 head=81f0a42 rc=0 crashes=0 secs=83  load_before=0.47 0.60 1.24
920 passed in 82.64s   (output/defect22_gpu_context_reps.txt)
```

**Power bound, stated plainly:** 920 executions is ~26 % of the ~3575 executions that
produced 2 disturbances, so against a *uniform* per-execution rate this negative is weak
(≈0.5 expected events). It is informative only against a hypothesis that predicts a
*higher* rate in this concentrated context. **It does not close DEFECT-22 and is not
evidence of absence.**

## 5. Ledger (own runs, no delegate claims)

| Head | Runs | Disturbed |
|---|---|---|
| 194844c | 5 | 2 (gh12 sampling red; SIGSEGV) |
| c2750bd | 4 | 0 |
| 9e4bfa5 | 2 | 0 (PYTHONMALLOC=debug; MALLOC_PERTURB_=42) |
| **81f0a42** | **1 (seed pinned)** | **0** |
| **total** | **12** | **2, both at 194844c** |

## 6. Not done / not claimed

- Mechanism still **undiagnosed**; no cause attributed.
- No rate claim: 2 events in 12 runs, all at one head, remains "two one-offs", not a rate.
- The gh12 LLM-sampling red is a separate open design question
  (`.builder_queue/REPAIR_PENDING_gh12_ollama_gate_nondeterminism.md`) and is not touched here.
- No pytest.ini change: pinning a seed globally would hide order dependence rather than fix
  it, and pytest.ini is shared with parallel sessions — the runner pins per run instead.
