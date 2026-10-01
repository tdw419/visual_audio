# RECEIPT — R5.2 Stranger Documentation (docs/START_HERE.md)

Run g: product lane, builder af3e62239ce2, branch glyph-transpiler-autoloop,
base 44fac1c0 (R5.1 ledger commit). Date 2026-09-21 evening.

## Deliverable

- `docs/START_HERE.md` — what it is (GPU-native pixel-programmed machine,
  WGSL RV32IMA core, Hilbert-mapped RAM, E-K1 box isolation), what it's for
  (isolated co-resident agent workloads; P1.3 receipt pointer instead of
  re-quoted numbers), and the anchor workload two ways: the R5.1 one-file
  installer (skip-boot / --json / corrupt-verify) and
  `tools/glyph_run.py examples/sum_1_to_5.glyph` (source run + artifact-only
  run).
- `tests/test_r52_stranger_doc.py` — the gate: extracts every fenced bash
  block from the doc, executes it from the repo root, and asserts every
  promised line in the paired ```text block appears in the REAL output
  (verbatim, whitespace-squeezed for multi-line JSON, whitespace-stripped
  fallback, `exit: N` = returncode contract, `~regex` for per-run variable
  values like the manifest timing).

## RED legs at landing (gate self-check runs BEFORE green)

1. missing-anchor: all bash blocks replaced with `true` → promised lines
   absent → FAIL fires.
2. corrupted-command: installer command replaced with a nonexistent tool →
   promised `fleet_ready_verified` absent, exit 2 → FAIL fires.
3. fabricated-output: doc's promised fleet result `"714": 6` replaced with
   `"714": 999999` → promise not found in real output → FAIL fires. This is
   the fabrication detector: the gate cannot be satisfied by editing the
   doc's claims without the machine agreeing.

## GREEN (final run, /tmp/r52_gate3.log)

```
RED ok [missing-anchor]: promised pattern not in real output of 'true\n': ...
RED ok [corrupted-command]: promised line not in real output of
  'python3 tools/no_such_tool.py --json\n': '"status": "fleet_ready_verified"' (exit=2)
RED ok [fabricated-output]: promised line not in real output of
  'python3 glyphos_installer.py --json\n': '"results": {"714": 999999, ...}' (exit=0)
GREEN ok: every bash block ran (exit 0) and every promised line appeared in the real output
PASS: docs/START_HERE.md is executable truth
exit=0
```

pytest: 35 passed in 14.50s
(test_r52_stranger_doc + test_r51_installer + test_r43_storage +
test_box_abi_conformance + test_glyph_run + test_gh26_fleet).

## Landing-time defects kept

- First gate draft asserted every command exit 0 — the corrupt-verify
  tamper leg legitimately exits 1, so the doc's own `exit: 1` promise was
  counted as a failure. Fixed: `exit: N` promises are checked against the
  real returncode (the contract, not an assumption).
- First doc draft promised `payload verified: 21 members, manifest OK` —
  the real line carries a per-run millisecond count; tightened to a `~`
  regex promise rather than freezing a variable value as fact.
- Pretty-printed JSON promises failed verbatim matching (brace spacing);
  added the whitespace-stripped fallback. All three defects RED before the
  final green (/tmp/r52_gate1.log, r52_gate2.log).

## Scope

Zero production lines changed: docs/START_HERE.md (new) +
tests/test_r52_stranger_doc.py (new, force-added past .gitignore test_*.py).
No source, shader, baker, runner, or installer bytes touched.

## Honesty — what this PASS does NOT prove

- The gate re-executes the doc's commands at gate time; it does not pin
  their output forever — a future machine change breaks the gate RED,
  which is the intended behavior (drift becomes visible).
- Every performance question is delegated to
  RECEIPT_R13_preference.md + floors_authoritative.json; the doc quotes no
  rates on purpose.
- "This machine only" honesty carries over from R5.1: no second-machine
  claim, GlyphRunner substrate boot not a kernel-image boot.
- R5.3 (30-day real-use gate) is NOT startable by this rung; it needs
  Jericho's own report by definition.
