# RECEIPT — DEFECT-17 option (d): loud refusal gate for RV x31 (t6)

**Landed:** `7a4208a` (2026-09-12, builder cron `af3e62239ce2`) · **Roadmap row:** DEFECT-17
**Ruling:** `.builder_queue/RULING_20260912_defect18_a_defect17_d.md` § Decision 2 (option (d)).
**Ticket:** `.builder_queue/REPAIR_PENDING_defect17_x31_hw_stack.md` → CLOSED.
**Design context:** `.builder_queue/EVIDENCE_defect17_gcc_x31_scan_20260912.md` (28 programs /
8,006 instructions / 5 optimisation levels / **0 x31 writes / 0 x31 reads**).

## Symptom → root cause → fix

| Step | Fact |
|---|---|
| Symptom | A program's `li t6, 90` transpiles to `LDI r31 0x5a`; the next `RET` pops garbage. Silent — no gate, no fault. |
| Root cause | The transpiler's register map is the identity map (`x0..x30` → `r0..r30`) and glyph **r31 is the hardware call stack pointer** (CALL/RET/PUSH/POP all use it). RV `x31`/t6 — a caller-saved scratch GCC may use freely — has no home, so an x31 write lands on the stack pointer. |
| Why it was a decision, not a patch | Both candidate fixes (spill x31 to a fixed data word at every rd/rs1/rs2==31 site; or reserve a glyph register and relocate the RV register that owned it) change the register-map contract every landed identity-map / WGSL-parity receipt depends on. |
| Ruling (d) | The scan says this toolchain never emits x31 in the gate corpora, so buying a map change would re-derive those receipts for a producer that does not exist yet. **Refuse loudly instead** — same discipline as `INTEGRITY_FAIL`: a detectable failure must not be silent. Rejected: (c) narrows the "stranger's C program runs provably unmodified" claim; (b′) is deferred with the scanner as tripwire. |
| Fix | Additive: `scan_rv_x31_references()` + `RVX31RefusalError` in `tools/rv64i_to_glyph.py`, called at the top of `transpile_rv32i_to_glyph()` (the single choke point both the raw-text path and `transpile_elf_to_glyph()` pass through); `main()` catches it, writes the message to stderr, exits 1. Zero engine lines, zero lowering/register-map change. |

Refusal message shape (measured, from the gate): `REFUSAL: RV x31 (t6) referenced at pc 0x0:
word 0x05a00f93 (addi), role dest. Glyph r31 is the hardware call stack pointer; lowering x31
onto r31 would silently corrupt it.`

## Verification (all runs by the orchestrator, not by the implementer)

| Leg | Command | Result | Log |
|---|---|---|---|
| RED, pre-change | `/usr/bin/python3 -m pytest tests/test_defect17_x31_refusal.py -q` with the tool change stashed (worktree at `1387572`) | **exit 2** — `ImportError: cannot import name 'RVX31Record'` (the refusal contract does not exist) | `output/defect17_gate_run1_red.txt` |
| RED, falsification | same gate with the scan present but the raise neutered (`if False and violations`) | **exit 1, 5 FAILED** — L1 dest / L1 nonzero-base / L1 all-roles / L3 CLI ELF / L3 CLI raw. The gate fails on *assertions*, not only on import → **not vacuous** | `output/defect17_falsification_assert_red.txt` |
| GREEN, gate | `tests/test_defect17_x31_refusal.py` + `tests/test_bk1_argv.py` | **exit 0, 16 tests** | `output/defect17_gate_run2_green.txt` |
| GREEN, arc | this gate + BK-1 / GH-21 / BK-11 / GH-23 / GH-9 loader / GH-9 window-span / BK-10 / BK-13 / GH-22 / BK-12 / GH-18 | **78 collected, 1 skipped, exit 0** | `output/defect17_arc_regression.txt` |
| GREEN, landed copy | gate + BK-1 + GH-21 on the main checkout; `md5sum` of `tools/rv64i_to_glyph.py` identical to the worktree (`8591b3d547f82ae516016c2d33bbb126`) | **exit 0, 0 FAILED** | `output/defect17_gate_main_green.txt` |
| GREEN, independent | repo **pre-commit hook** on the commit — Glyph & Transpiler differential suites, including `test_rv64i_to_glyph_xv6_nano.py` (12) | **37 passed** | hook output at commit `7a4208a` |

## What is NOT claimed

- The scan covers the transpiled text section only; an x31 reference that never reaches it is
  not seen.
- `decode_instruction()` returning `None` (data / unknown encoding) is skipped **by design** —
  the gate cannot refuse what it cannot decode.
- No claim is made about non-GCC producers (clang is not installed here), `-mcmodel` /
  `-msave-restore` code models, or hand-written asm beyond the two landed shims: those are
  exactly the tripwire cases. **Re-run `EVIDENCE_defect17_gcc_x31_scan_20260912.md`'s scan on a
  widened corpus; if it ever reports non-zero, option (b′) reopens and this ruling flips.**
- L4's corpus leg is a measured count over the repo's own BK-1 / BK-11 corpora, not a proof
  about arbitrary C.

## Next (queued, not started)

DEFECT-18 option (a) — the engine snapshots/restores the USER regfile on tick (engine work →
worktree isolation per AGENTS.md). Roadmap row DEFECT-18, same ruling.
