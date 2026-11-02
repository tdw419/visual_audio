# RECEIPT_BM902_STAGE2_HANDOFF.md — TASK_BM902

**Date:** 2026-09-19 (builder cron af3e62239ce2, orchestrator-implemented)
**Brief:** `.builder_queue/brief_bm902_stage2_handoff.md` (check_brief PASS)
**Row:** `tools/bare_metal_poc/ROADMAP.md` Rung 9 → TASK_BM902
**Gate:** `bash tools/bare_metal_poc/rung9/run_bm902_diff.sh` → **GATE PASS,
exit 0**, all six legs in one clean invocation.

## What was built

stage2's PM handoff state, CONSTRUCTED and differ-tested against the frozen
BM901 oracle — no boot attempt, per the brief ("mismatches surface as diffs,
never as hangs").

- `bm902_stage2_construct.py` — builds the 4KB zeropage from MEASURED bytes:
  kernel-baked header band [0x1f1,0x268) copied byte-for-byte from
  `vmlinuz64.extracted`; e820 table + count copied from the oracle (same
  `-M pc -m 512` QEMU/SeaBIOS map both sides — the map is part of the oracle
  contract); loader fields set per `BM902_FIELD_PLAN.md`
  (type_of_loader=0xff, loadflags=0x81, vid_mode=0xffff, no initrd,
  heap_end_ptr=0xefff, cmd_line_ptr=0x1f800, code32_start=0x100000);
  STAGE2-CHOICE band 0x000-0x1e7 zeroed. cmdline = byte-exact oracle string
  (RECORDED CHOICE). regs = oracle register state pinned from the probe34
  real-chain captures (rsp identical too — see L3 note).
- `bm902_differ.py` — the gate's teeth: parses the whitelist from the field
  plan's fenced block (bands inclusive, union-merged, plus the 0x000-0x1e7
  STAGE2-CHOICE band), fails on ANY differing zeropage byte outside the
  union naming the offset; L2 cmdline byte-equal; L3 register compare.
- `run_bm902_diff.sh` — phases: construct ×2 → x2 determinism → L1/L2/L3 →
  L4 RED (flipped 0x214 code32_start, outside whitelist) → L5 RED (mutant
  field plan with the `0x210 type_of_loader` whitelist line removed) →
  receipt with pins.

## GREEN tail (pasted literally)

```
PHASE A PASS: x2 construction runs byte-identical
L1 PASS: zeropage diffs 138 bytes, all inside whitelist union (517 offsets)
L2 PASS: cmdline byte-identical (82 chars, NUL-terminated)
L3 PASS: registers match oracle (rsp loader-specific, ours 0x1f784)
DIFFER PASS: L1+L2+L3 green
GATE PASS: BM902 stage2 handoff (L1-L3 green, L4/L5 RED demonstrated, x2 identical)
```

Pins: constructed zp `f6605707…` (both legs); oracle pins unchanged
(`c3120d8e…` zp, `30cd829f…` cmdline) — sha256sum asserted in-gate.

## RED legs (shown able to fail)

- **L4:** one XOR-0xFF byte at zp[0x214] (code32_start LSB, kernel-baked,
  MUST-MATCH, outside whitelist) → differ exit≠0:
  `L1 FAIL: 1 zeropage diff(s) outside whitelist: 0x214`
- **L5:** field-plan mutant with `0x210 type_of_loader` deleted from the
  fenced whitelist (constructed zp has 0xff there vs oracle 0x33) → differ
  exit≠0: `L1 FAIL: 1 zeropage diff(s) outside whitelist: 0x210`
  — proves the whitelist is enforced, not decorative.

## Measured evidence behind the construction (this run, not doc-quoted)

- `bm902_zp_probe3.py`: oracle zeropage band [0x1f1,0x268) is byte-identical
  to `vmlinuz64.extracted` at the same offsets EXCEPT loader-owned bytes
  (0x1ef/0x1f0, 0x1fc-0x1fd root_dev, 0x210-0x211, 0x218-0x21f ramdisk,
  0x224-0x225 heap_end_ptr, 0x228-0x22b cmd_line_ptr) — 0 unexcused diffs.
  This is what licenses the "copy the file's bytes" construction.
- e820: 7 entries at 0x2d0 (region ends 0x35c); zeropage bytes above 0x35c
  all zero. Low region 0x000-0x1e7: 126 nonzero bytes (isolinux real-mode
  leftovers) — our construction zeroes it, and the 138-byte L1 diff total
  (126 low + 12 whitelisted high bytes) closes exactly.
- `bm902_zp_probe.py`: full field-value dump used to set loader fields from
  measurement (root_flags=0x1, ram_size=0xffff0000, vid_mode=0xffff,
  root_dev=0x0200, type_of_loader=0x33, loadflags=0x81, heap_end_ptr=0xf5f4).

## What this PASS does NOT prove (honest boundary)

- **No QEMU ran.** The construction is host-side Python; the gate proves the
  ARTIFACT is oracle-grade, not that a 16-bit stage2 binary produces it.
  The 16-bit stage2 that executes this construction is BM903+ work (the
  brief scopes BM902 to "stage2 constructs the handoff" verified
  differentially; a real assembler stage2 executing the construction under
  the probe34 GDB harness is the natural next rung step and is named as
  such in the roadmap row).
- L3 compares the register state we DECLARE (pinned oracle values), not
  register state produced by executed code — same boundary.
- The 0x000-0x1e7 STAGE2-CHOICE zeroing remains the field plan's flagged
  judgment call (escalation path documented there; reversible by dropping
  the band).
- x2 determinism is two invocations of a deterministic program — it pins
  the pipeline, not a hardware timing space.
