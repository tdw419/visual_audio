# BRIEF — TASK_BM902: stage2 constructs the handoff (Rung 9, step 2 — differential vs BM901 oracle)

**Row:** `tools/bare_metal_poc/ROADMAP.md` → Rung 9 → TASK_BM902
**Spec pointer (READ FIRST):** `tools/bare_metal_poc/ROADMAP.md` Rung 9 section
(lines ~265–300), including the standing hard rule from BM901: *mismatches
surface as DIFFS, never as hangs*. The oracle of record is
`tools/bare_metal_poc/rung9/ORACLE_BOOT_PARAMS.md` +
`rung9/oracle_zp_leg{0,1}.bin` (sha256 `c3120d8e…`) +
`rung9/oracle_cmdline_leg{0,1}.bin` (sha256 `30cd829f…`) +
`rung9/oracle_regs` fields (rip=0x100000, rsi=0x13ab0, cs=0x10, ds/ss/es=0x18,
cr0=0x11, eflags=0x46, rsp=0x1f784). Documentation/arch/x86/boot.rst (protocol
2.13+) is the semantics reference; the ORACLE, not the doc, is the pass bar.

## Goal

stage2 — our own code, not isolinux — constructs the protected-mode handoff:
zero-page populated field-by-field, cmdline resident and pointed to, GDT with
flat 0x10/0x18 segments, jump to the kernel's 32-bit entry with the captured
register state. Verification is a DIFFERENTIAL test against the BM901 dump,
not a boot attempt.

## Method

1. **Instrument, don't guess:** capture stage2's constructed handoff with the
   SAME GDB-stub technique proven in `rung9/probe34_capture.py` (hw-bp at the
   PM entry, registers sampled pre-first-instruction, memory dumped).
   Reuse the capture harness; do not fork a second one.
2. **Diff, never reconcile silently:** byte-compare constructed zeropage and
   cmdline against the oracle dumps. Field-level differences are expected ONLY
   where they are LOADER-SPECIFIC BY CONSTRUCTION (type_of_loader=0x33 is
   isolinux's chainload identity — ours must classify differently, e.g.
   0xff/undefined-per-protocol; loadflags bit0=0 if we ship no initrd). Every
   other byte must match. Each intentional difference goes in a named
   variability table with its cause — the BM901 discipline exactly.
3. **Classify before build:** before writing stage2 handoff code, write the
   field table `rung9/BM902_FIELD_PLAN.md` marking each zeropage field
   oracle-value / ours-expected / loader-specific? — committed BEFORE the
   capture legs run (one gate-able step = one run = one commit).
4. **Kernel:** TinyCore vmlinuz64 (`rung9/vmlinuz64.extracted`), same as the
   oracle. Kernel swap = oracle re-run first, cheap by design.
5. **No pixels.** BM903 introduces the pixel medium. This rung is
   conventional-load only (e.g. `-kernel`/direct load or a minimal stage1).

## Verification (row gate — falsifiable)

Gate command:

```bash
bash tools/bare_metal_poc/rung9/run_bm902_diff.sh
```

Gate artifact: `rung9/bm902_diff_receipt.txt` + `rung9/bm902_zp.bin`,
`rung9/bm902_cmdline.bin`, `rung9/bm902_regs.json`. PASS requires ALL of:

- [ ] **L1 identity:** constructed zeropage byte-compares EQUAL to the oracle
      dump except ONLY bytes whose offsets appear in the named
      loader-specific variability table (table is data: offsets enumerated,
      counts asserted — a diff outside table offsets fails the gate).
- [ ] **L2 cmdline:** cmdline bytes match the oracle string exactly (content
      we control may differ ONLY if the string is also compared for
      structural validity: NUL-terminated, cmd_line_ptr points at it,
      length matches header). State which was chosen in the receipt.
- [ ] **L3 registers:** GPRs/segment-regs/CR0/EFLAGS at the entry match the
      oracle values (rsp may differ; name it in the variability table if so).
- [ ] **L4 RED single-byte:** flipping one byte in the constructed zeropage
      (outside variability offsets) makes the differ exit NON-ZERO naming the
      offset — demonstrated in the gate output.
- [ ] **L5 RED class-flag:** demoting a loader-specific field to
      "must-match" (mutant table) makes the gate RED — proves L1's
      whitelist is enforced, not decorative.
- [ ] ×2 construction runs byte-identical to each other (determinism bar).

## Failure evidence (RED-first requirement)

The differ must be shown able to FAIL before it is trusted: L4 and L5 are the
RED legs and their output is pasted literally in the receipt. If any leg
cannot be made to fail, the gate is decoration and the step is NOT done.

## Files in scope

`tools/bare_metal_poc/rung9/` ONLY (new files: `BM902_FIELD_PLAN.md`,
`bm902_stage2*.py/asm/S`, `run_bm902_diff.sh`, `bm902_diff_receipt.txt`,
`bm902_*.{bin,json}`), plus the TASK_BM902 cell in
`tools/bare_metal_poc/ROADMAP.md` and this task's receipt.

## Must-not-touch

`rung1`..`rung7` trees (read-only), `rung9/oracle_*` dumps and
`ORACLE_BOOT_PARAMS.md` (the reference is frozen; if it looks wrong, file
REPAIR_PENDING, never edit), `tools/glyph_gpt/**`, `glyph_dispatch/**`,
WGSL shaders, `voicebook/`, `.rts/`, `rs_fixtures.json`.

## Boundary

QEMU-only software rung. No pixel machinery, no hardware, no BM903 work.
TASK_BM001 (landing bare_metal_poc) stays HOLD; this brief lands NOTHING but
its own artifacts + receipt + roadmap cell, per the house pattern.

## Definition of done

All six gate legs green in one run of `run_bm902_diff.sh` from a clean
invocation, RED legs demonstrated in the same run, ×2 determinism satisfied,
receipt + pins committed, ROADMAP cell TASK_BM902 marked ✅ with the pasted
GREEN tail, and `git status --short` confirms only in-scope files changed.

## Never weaken a live guard

If a verification leg (differ comparison, variability-table count assertion,
pin check) blocks the step, the step is wrong — do not weaken or delete the
leg to reach green. Interfaces are LOCKED: the capture harness
(`probe34_capture.py`) and the oracle artifact formats are fixed; if a locked
signature looks wrong, file `REPAIR_PENDING_BM902_<topic>.md` with options
cheapest-first and HOLD, per the skeleton contract.
