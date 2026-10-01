# RECEIPT — WF-1 GPU tick semantics: the bound is now guarded, not narrated

**Date:** 2026-09-12 · **Seat:** builder orchestrator (cron `af3e62239ce2`) · **Row:** WF-1
(`systems/GLYPH_SELF_HOSTING_ROADMAP.md`) · **Ruling:** `.builder_queue/RULING_WF1_gpu_tick_semantics.md`
(option (ii) now / option (i) when a consumer exists)

## What was owed

The DEFECT-18 receipt (`systems/RECEIPT_DEFECT18_ENGINE_TICK_REGISTERS.md:85-89`) had to add a **prose
caveat** — the WGSL engine delivers no ticks, so "CPU ≡ GPU" is not a testable claim for preemption —
precisely because **nothing enforced that bound**. WF-1 ruled: build the guard, not the capability
(no consumer exists; the residency tier that presumes preemption is unbuilt).

## What landed

One new module, `tests/test_wf1_tick_claim_bound.py` (5 legs). No engine, transpiler, baker, WGSL,
roadmap or receipt file was modified by the implementer.

| leg | what it asserts | how it can fail |
|---|---|---|
| L1 | WGSL engine (`tools/wgsl_glyph_isa_v2.py`) carries **no** tick delivery (no `KTICK` token, no read of the tick MMIO word index, no timer countdown), **and** the CPU engine does (`glyph_isa_v2.KTICK_PC_ADDR == BOX_MMIO_BASE + 0x3C`, read as `self.memory[KTICK_PC_ADDR >> 2]`) | trips the moment WGSL gains a tick path — the failure message carries the deletion instruction |
| L1b | non-vacuity: the *same* detector function (`wgsl_tick_delivery_hits`) trips on a copy of the WGSL text with a tick read / `KTICK` constant / tick word index injected | proves L1 passes on real content, not on a typo or a stub |
| L2 | the CPU tick legs exist and pass — `tests/test_gh16_preemption.py` + `tests/test_defect18_tick_regfile.py` run by subprocess; exit 0, `>0 passed`, `0 failed` (count parsed, not hardcoded) | the CPU half of the claim is exercised every run, not assumed |
| L3 | the claim surface (roadmap + `systems/RECEIPT_*.md` + `docs/*.md`, 126 files measured) yields **zero** positive GPU tick-parity claims while WGSL lacks tick delivery | fails on the synthetic positive in-module, and on any real landed overclaim |
| L4 | the module docstring carries the ruling's DELETION INSTRUCTION | keeps the gate ephemeral by construction, not by memory |

## Evidence (all orchestrator-run)

| artifact | result |
|---|---|
| `output/wf1_gate_run1_red.txt` | **RED first**: `ERROR: file or directory not found: tests/test_wf1_tick_claim_bound.py` (module absent) |
| `output/wf1_gate_run2_green.txt` | `/usr/bin/python3 -m pytest tests/test_wf1_tick_claim_bound.py -q` → `.....` 5 passed, exit 0 (agy's tree) |
| `output/wf1_gate_run3_green.txt` | same command **after the orchestrator tightening below** → 5 passed, exit 0 (the tree that was committed) |
| `output/wf1_gate_run2_green_py311.txt` | venv `python3` (3.11.15) → 5 passed, exit 0 |
| `output/arc_verify_wf1_junit.txt` / `output/arc_verify_wf1.xml` | arc, 53 files, **328 passed / 2 skipped / 0 failed, exit 0**, 135.94 s |
| `output/wf1_orch_probe.txt`, `output/wf1_orch_probe_tightened.txt`, `output/wf1_orch_probe_final.txt` | independent falsification probes (below) |
| `output/wf1_gate_run5_green.txt` / `_py311`, `output/arc_verify_wf1b_junit.txt` | intermediate checkpoints during the hardening: 5 passed on both interpreters, arc 328/2 skipped/0 failed exit 0 in 136.07 s |
| `output/wf1_gate_run6_green.txt` / `output/wf1_gate_run6_green_py311.txt` | **the committed tree** (docs settled, so L3 re-scanned the final claim surface): 5 passed, exit 0 under py3.12 and py3.11 |
| `output/arc_verify_wf1c_junit.txt` / `output/arc_verify_wf1c.xml` | **the committed tree**: 53 files, **328 passed / 2 skipped / 0 failed, exit 0**, 136.55 s; `tests/test_gh26_glass_box.py` 8 passed separately (not in the arc list) |
| `output/wf1_orch_probe_selfcheck.txt`, `output/wf1_selfcheck_as_landed.py` | self-check: the **as-landed** scanner (`5d7665d`) flags **9** units in this tick's own roadmap footer + receipt; the current scanner flags **0** — both over the same 127 files |

### Orchestrator falsification probes (the gate is not taken on faith)

Run against the gate's own pure functions, not through pytest (`output/wf1_orch_probe_final.txt`):

- **real claim surface**: 0 flagged over **126** files; each of the three known negatives is clean
  individually — `systems/GLYPH_SELF_HOSTING_ROADMAP.md:544-545`,
  `systems/RECEIPT_ARC_VERIFY_3e2bd8e.md:88`, `systems/RECEIPT_DEFECT18_ENGINE_TICK_REGISTERS.md:85-86`.
- **adversarial positives**: **7/8 caught** — plain positive, `is verified`, `measured … matches`,
  `parity probe: GPU matches CPU`, `criteria`, `bound is met`, and a table-row shaped claim.
- **the 1 miss is the designed scope boundary**: `GPU preemption matches the CPU engine byte-for-byte`
  carries no tick token, and this gate is a *tick*-parity bound. Recorded, not papered over.
- **detector non-vacuity**: real WGSL text → `[]`; injected `box_mmio[15u]` tick read → 1 hit;
  injected `KTICK_PC_ADDR` → 1 hit; injected bare word index `8207u` → 1 hit.

### Hardening lineage (every step measured; the gate flagged the loop's own documentation)

Two different failure classes showed up, in order. Both numbers below are from
`output/wf1_orch_probe_*.txt` and `output/wf1_orch_probe_selfcheck.txt` (the latter runs the
**as-landed scanner from commit `5d7665d`** against the current tree, via
`output/wf1_selfcheck_as_landed.py`).

| stage | rule set | adversarial probe (8 positives) | real claim surface |
|---|---|---|---|
| as **proposed by agy** | 36 guard patterns, including builder vocabulary (`probe`, `bound`, `criteria`, `synthetic`, `residual`, `pre-registered`) | **5/8 caught** — `tick parity probe: GPU matches CPU` and `The bound is met: …` were suppressed by their own guard words, i.e. a real overclaim phrased with builder vocabulary would have passed | 0 flagged (126 files — the receipt did not exist yet) |
| as **landed** (`5d7665d`) | 16 negation-only patterns | **7/8 caught** | **9 flagged — all four roadmap-footer units and all five WF-1 receipt units.** The gate flagged the very documentation this tick wrote |
| **final** | sentence-in-paragraph units (a line is not a boundary, `;` is not a boundary), code spans stripped per paragraph after unwrapping, limitation vocabulary (`unbuilt`, `unmeasurable`, `nothing to measure`, `deleted in the same commit`), `page swap` as a scope marker | **7/8 caught** (the 1 miss carries no tick token at all — designed boundary) | **0 flagged / 127 files** |

The three fixes, each driven by a measured false positive rather than taste:

1. **Builder vocabulary out** (`probe`, `bound`, `criteria`, …): those words suppressed real claims.
2. **Unit granularity**: splitting on `; ` and on line breaks tore a claim from its own disclaimer —
   the word "deleted in the same commit" was cut at a markdown wrap, so the parenthetical's first
   clause read as a landed claim. A claim unit is now a sentence inside an unwrapped paragraph.
3. **Code spans stripped per paragraph**: a claim quoted as an example — e.g. this receipt's own
   adversarial probe strings — is data, not an assertion; and a span can straddle a wrap, so the
   strip happens after the join (stripping line-locally left the second quoted example alive,
   `output/wf1_orch_probe_final4.txt`).

The lesson worth carrying to future gate briefs: **a scanner that passes on the tree it was written
against can still be blind to the class it was written for, and can also be wrong about its own
documentation.** Probe both directions — synthetic positives to prove it trips, and the loop's own
prose to prove it does not.

## Not claimed / honest boundaries

- **WGSL tick delivery is NOT built.** The delivery row's acceptance criteria are pre-registered in the
  WF-1 roadmap row (KTICK delivers an acted-on tick; on/off byte-identical on the GPU engine; parity
  against the CPU reference; **this gate deleted in the same commit that makes it false**).
- **The claim scanner is a heuristic over prose, not a proof.** A claim phrased without any parity token
  (`parity`/`≡`/`byte-identical`/`matches`/`verified`) is invisible to it; a positive claim wrapping
  itself in a negation word is a residual risk. It is a *guard against silent overclaim*, which is what
  the ruling asked for, not a theorem. L1 (source-level) is the exact half of the gate; L3 (prose) is
  the defensive half.
- **L4 is meta**: it tests a docstring, deliberately. Rationale (agy's, accepted): the gate is designed
  to be deleted atomically with the delivery commit, so the instruction lives where a future builder
  meets the failure.
- **Arc skip delta is environmental, not a regression.** The `3e2bd8e` arc was 325/1-skipped; this arc is
  330/2-skipped. The +5 tests are this module. The +1 skip is
  `test_gh26_live_surface::test_gh26_geoobs_reads_live_publish_dir` — deterministic under the venv
  (`python3` 3.11.15 → `s`, `/usr/bin/python3` 3.12.3 → 4 passed), by its own `skipif` on
  `mcp.server.fastmcp` (`tests/test_gh26_live_surface.py:102-116`). Nothing in this change touches it.
- Not run this tick: the py3.12 whole-arc (the arc leg uses the venv interpreter, matching the previous
  arc receipt's command); GPU tick parity itself (there is nothing to measure — that is the point of
  the bound).
