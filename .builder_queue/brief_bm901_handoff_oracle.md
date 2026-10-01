# BRIEF — TASK_BM901: Boot-handoff oracle (Rung 9, step 1 — oracle FIRST)

**Row:** `tools/bare_metal_poc/ROADMAP.md` → Rung 9 → TASK_BM901
**Provenance:** Jericho 2026-09-18 — protected-mode-entry capture point chosen
deliberately ("boot_params fully populated, nothing pixel-fed has touched
memory — a mismatch there is unambiguous: construction, not stomping"), plus
the sequencing discipline that Rung 8 must arrive as a pure transport test.
**Standing rule (hard):** NO stage2 handoff code (BM902) starts before this
oracle exists. The failure mode being retired is the silent wrong-but-
plausible handoff; mismatches must surface as DIFFS, never as hangs.

## Goal

A field-by-field known-correct reference of the Linux protected-mode handoff,
captured from the REAL chain in QEMU (SeaBIOS → isolinux → bzImage):

1. Register state at the PM entry (all GPRs, EFLAGS, CR0/CR3/CR4, EFER,
   GDTR/IDTR) — ×2.
2. Full `boot_params` (the zero-page struct, `size_of_boot_params` bytes at
   the real-mode kernel base) — ×2.
3. Cmdline buffer at `hdr.cmd_line_ptr` — ×2.
4. E820 table as the real chain built it (part of boot_params / setup data).

Deliverable: `tools/bare_metal_poc/rung9/ORACLE_BOOT_PARAMS.md` — table of
offset / size / field name / measured value ×2 / variability+cause /
spec-expected (Documentation/arch/x86/boot.rst) / delta. Plus binary dumps
with sha256 pins (`boot_params_dump.bin`, `cmdline_dump.bin`,
`oracle_regs.json`) and `rung9/run_oracle.sh` reproducing it end-to-end.

## Method (measured, not transcribed from the spec)

1. **Kernel:** TinyCore's vmlinuz64 (already in `rung7/`, serial recipe
   proven at TC-1). Alpine-virt bzImage is the alternate if serial output
   fails. Tag every table with the kernel version — a kernel swap later
   means a cheap oracle re-run, not an assumption.
2. **Chain:** plain `-cdrom` real ISO. NO pixel machinery anywhere in the
   oracle — pixels enter at BM903. The oracle captures what the real chain
   does; that is the entire point of the reference.
3. **Capture (×2 independent legs, cross-checked):**
   - GDB stub (`-s`): break at the PM entry — the first far-jump target
     after setup completes, per the boot protocol's entry conditions
     (flat 32-bit CS, GDTR loaded, A20 on). `dump binary memory` for the
     tables, register read at the same stop.
   - QEMU-direct `-kernel` leg as a SECOND reference: diffing real-chain vs
     QEMU-direct isolates chainload-specific fields (type_of_loader et al.).
     Differences are flagged in the table, never silently reconciled.
   - Fallback if gdb multiarch misbehaves: QEMU monitor `info registers` +
     `xp` at the break — weaker, say so in the receipt.
4. **Determinism bar:** ×2 captures byte-identical EXCEPT fields listed in
   a variability table with causes (same discipline as normalizing the
   `login[NNN]` lines at TC-1: runtime scheduler output is not medium or
   chain nondeterminism, but it must be NAMED).
5. **Non-vacuity RED legs (the differ must be able to fail):**
   - Flip one byte in a captured dump → differ flags it.
   - Capture a DIFFERENT kernel image → table differs where it should
     (proves the schema is real, not a self-satisfied constant).
6. **E820 topology scope note (named divergence, decided 2026-09-18):**
   E820 is host-topology-dependent and this oracle's host is QEMU. Both
   legs run under the same QEMU, so E820 will NOT appear as a leg-diff —
   it is not a variability-table field. The captured E820 is QEMU's memory
   fiction, and that fiction IS the oracle's target by construction. When
   real hardware later (Rung 8+ hardware legs) reports a different E820
   than this captured target, that is an EXPECTED, NAMED divergence — not
   a defect and not a new mystery to chase; record such comparisons as
   "diverges by topology, oracle = QEMU reference" in the receipt.

## Verification (row gate)

- [ ] ×2 byte-identical captures modulo named-variability fields.
- [ ] Differ demonstrably REDs on a single flipped byte.
- [ ] Field table covers every byte of `size_of_boot_params` with per-field
      provenance (measured vs spec, deltas flagged).
- [ ] Receipt + sha256 pins + `run_oracle.sh` from clean; Rung 9 BM901 cell
      updated. Deliverables in `rung9/` (NEW subtree, rung1-7 read-only).

## Files in scope

`tools/bare_metal_poc/rung9/` (NEW subtree) only: `ORACLE_BOOT_PARAMS.md`,
`boot_params_dump.bin`, `cmdline_dump.bin`, `oracle_regs.json`,
`run_oracle.sh`, plus the Rung 9 BM901 cell in
`tools/bare_metal_poc/ROADMAP.md` and this task's receipt. rung1-7 are
read-only; no other file in the tree may change.

## Gate command

```bash
bash tools/bare_metal_poc/rung9/run_oracle.sh
```

Gate artifact: the rung9 oracle run plus its differ. Passing means:

- the differ exits 0 on the x2 byte-identical captures (modulo the
  named-variability table), and
- the differ exits non-zero on each RED leg: a single flipped byte and a
  different kernel image must both be flagged.

## Boundary

QEMU-only software rung. No pixels, no hardware, no stage2 code. BM001
(TASK landing bare_metal_poc) stays HOLD; this brief lands NOTHING but its
own receipt + roadmap cell, per the house pattern.
