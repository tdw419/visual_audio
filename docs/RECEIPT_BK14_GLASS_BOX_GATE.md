# RECEIPT — BK-14: Glass Box demonstration gate (dedicated)

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` BK-14 (promoted from
`systems/GLYPH_BACKLOG.md` at `aaf974c`).
**Gate:** `tests/test_bk14_demo.py` — RED-first, 4/4 green.
**Status:** ✅ done 2026-09-12 by builder cron `af3e62239ce2` (implemented by the
`agy` lane from `.builder_queue/brief_bk14_gate.md`; gate re-run and receipt
written by the orchestrator, which never trusts the delegate's own claim).

Row scope as promoted: **the remaining leg only** — leg 1 (`tools/glass_box_demo.py`
+ `systems/DEMO_GLASS_BOX.md`) landed at `1605e0c` and `4828bf9` pinned the
outstanding work to the dedicated gate, with an explicit do-not-re-implement
note (`tests/test_gh26_glass_box.py` covers the GH-26.5 scenario but is *not*
BK-14's gate clause).

---

## 1. Receipts

| Receipt | Path |
|---|---|
| Demo verified green at HEAD before delegation | `output/bk14_demo_verify_run1.txt` (exit 0, `real 0m0.806s`, anchors 1/2/3 PASS) |
| RED — gate module absent (pre-state) | `output/bk14_gate_run1_red.txt` (`ERROR: file or directory not found`, pytest exit 4) |
| GREEN — 4/4, exit 0 | `output/bk14_gate_run2_green.txt` (`4 passed in 3.79s`) |
| Liveness / mutation check | `output/bk14_gate_mutation_check.txt` (receipt MD5 perturbed → gate exit 1, `MD5 mismatch: demo …4a != receipt …4b`) |
| Arc regression (GH/BK/ENG arc) | `output/bk14_arc_regression.txt` |

Arc at this commit: **311 collected, 310 passed, 1 failed** — the single failure
is `tests/test_bk11_coreutils.py::test_bk11_tool_compiles_transpiles_and_runs[wc]`,
BK-11's own known-red leg, parked behind the DEFECT-18 design decision
(`.builder_queue/REPAIR_PENDING_defect18_tick_identity_map.md`). Delta vs the
previous arc (307 collected / 306 passed / 1 failed) is exactly the 4 new BK-14
legs; nothing else moved.

Environment note: the gate was run under both interpreters available in this
loop — the Hermes venv `python3` (3.11.15) and the project-canonical
`/usr/bin/python3` (3.12.3) — both `4 passed`. The arc scope is the GH/BK/ENG
suites (`tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py`), not the whole
`tests/` directory: the wider directory carries 22 unrelated collection errors
(missing optional deps such as `mcp.server.fastmcp`, `tests/disabled/*`) that
predate this row.

## 2. Mechanism

`tests/test_bk14_demo.py` (new, no other file touched — `git status --short`
shows the new file and zero tracked modifications). Four legs:

| Leg | Claim | Evidence shape |
|---|---|---|
| L1 refusal | The agent write path is human-gated before any work | subprocess without `GEOS_EMIT_ACK` → exit 1, `REFUSAL: GEOS_EMIT_ACK` on stderr, no `[Stage 0]` banner on stdout |
| L2 full run | The committed runner completes end-to-end | subprocess with `GEOS_EMIT_ACK=1 --work-dir <tmp>` → exit 0, `VERDICT: ALL THREE ANCHORS VERIFIED (exit 0)`, stage banners 0..5 each report `PASS` (parsed from the printed status lines) |
| L3 anchors | The demo reproduces the **committed** provenance chain | the tile SHA256 and final-state MD5 are parsed out of `systems/RECEIPT_GH26_AGENT_LOOP.md` at test time and compared against the demo's printed values (SHA256 `d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33`, MD5 `0b22350df04841a768a8c714f0a33c4a`, `Divergence: 0 words across 16,384 memory cells`), plus `tools.geos_hilbert.verify_reference_pixels` 5/5 on a stamped frame and existence of `tools/glyph_gpt/admitted/syscall_8_template_d29b29043f6d.glyph` |
| L4 non-mutation | The demonstration proves *without* mutating the tree | sha256 snapshot of every file under `tools/glyph_gpt/admitted/` + `systems/RECEIPT_GH26_AGENT_LOOP.md` before/after the run must be equal; run artifacts (`kernel_memory.npy`, `gh26_resident.npy`, `gh26_admit.npy`, `admissions.jsonl`) must exist under `--work-dir` |

No engine, transpiler, ABI, runner or doc file was modified by this row.

## 3. Liveness (why the gate is not a tautology)

The anchors live in two places (the runner's expectations and the receipt), so
the gate parses them from the receipt rather than hardcoding a second copy.
That cross-check was **mutation-checked**: replacing the receipt's replay MD5
with a look-alike (`…f0a33c4b`) turns the gate red —
`AssertionError: MD5 mismatch: demo 0b22350df04841a768a8c714f0a33c4a != receipt 0b22350df04841a768a8c714f0a33c4b`
(`output/bk14_gate_mutation_check.txt`, gate exit 1). The receipt was then
restored and verified byte-identical: sha256
`2646ce56b682dffc8958e4df094a4fbc325fb65d5a7eb020f12cb8ef11c57748`.

## 4. Honest boundaries

- BK-14's backlog narrative begins with "stranger's C program → agent ports".
  The **landed** runner does not exercise that stage: it demonstrates the
  GH-26.5 loop (aperture post @750 → preemptive resident service → oracle
  admission → on-die re-dispatch → canonical replay fixpoint). The coreutils
  stage remains parked with BK-11 (BLOCKED-ON-DESIGN / DEFECT-18) and is **not**
  claimed here.
- The gate runs CPU-only and does not exercise `--show-canvases` (a display
  flag, not a claim).
- Preemption inside the demo (`timer_quantum=12`) is the GH-16 path already
  gated by BK-1 leg 2 / GH-26; this row adds no new preemption claim — and
  therefore does not touch, and is not blocked by, the DEFECT-17/18 register-map
  decision.
