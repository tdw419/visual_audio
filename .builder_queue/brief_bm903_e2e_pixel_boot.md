# BRIEF — TASK_BM903: end-to-end — pixel medium carries bzImage+cmdline, kernel boots through the standard handoff

**Row:** `tools/bare_metal_poc/ROADMAP.md` → Rung 9 → TASK_BM903
**Spec pointer (READ FIRST):**
- `tools/bare_metal_poc/ROADMAP.md` Rung 9 section, including the standing hard
  rule from BM901: *mismatches surface as DIFFS, never as hangs* (any boot leg
  carries a wall-clock timeout and a serial-anchor poll, never an indefinite wait).
- `rung9/ORACLE_BOOT_PARAMS.md` + frozen oracle dumps (`oracle_zp_leg{0,1}.bin`
  sha256 `c3120d8e…`, `oracle_cmdline_leg{0,1}.bin` sha256 `30cd829f…`,
  oracle regs rip=0x100000/rsi=0x13ab0/cs=0x10/cr0=0x11/eflags=0x46).
- `rung9/RECEIPT_BM902_STAGE2_HANDOFF.md` § "What this PASS does NOT prove" —
  this task is that boundary's closer: the BM902 oracle-grade construction
  becomes EXECUTED 16-bit code, then the kernel itself speaks on serial.
- `rung9/BM902_FIELD_PLAN.md` — the whitelist contract transfers unchanged.
- `rung9/bm902_stage2_construct.py` — the construction stage2 must reproduce.

## Goal

Our own stage1+stage2 (pixel-encoded medium, int13h read, rung-4/5 discipline)
loads vmlinuz64 + initrd, constructs the protected-mode handoff per BM902, and
the kernel reaches serial output through the standard protocol-2.13 handoff —
ending at the TinyCore shell marker. Payload (measured this tick):
`rung9/vmlinuz64.extracted` 4,295,328 B + `rung7/core.gz` 9,260,807 B ≈ 13.6 MiB
— inside the row's "10–30 MiB: capacity measured sufficient" letter, and the
initrd fields the BM902 whitelist classified LOADER-SPECIFIC (ramdisk_image
0x1f6ea000 / size 0x8d4f07) become fields WE construct per protocol.

## Method (staged — one gate-able step = one run = one commit)

1. **Step 1 — executed handoff (differential):** assemble a real 16-bit stage2
   that performs the BM902 construction (zero-page, cmdline, GDT 0x10/0x18,
   initrd resident + pointers, jump to 0x100000). Kernel+initrd load
   conventionally for this step (file or raw medium via int13h). Capture with
   the SAME probe34 GDB technique (hw-bp at 0x100000, regs pre-first-instruction,
   dump zp 4 KB + cmdline 512 B + initrd pointer fields). Diff vs BM902
   artifacts; only field-plan whitelist offsets may differ; `type_of_loader`
   is ours (NOT 0x33 — that is isolinux's identity; use the protocol's
   "_own_ loader" classification and record it in the field-plan addendum).
   Kernel choice unchanged: vmlinuz64, same as oracle. Kernel swap = oracle
   re-run first, cheap by design.
2. **Step 2 — pixel medium:** encode kernel+initrd into the PXC1-convention
   medium (rung-4 streaming/de-interleave pattern EXTENDED to the bank walk at
   13.6 MiB scale — copy rung4/rung5 asm, never edit rung trees in place);
   CRC32 gate v2 on the only path to the handoff (rung-4 discipline verbatim);
   boot reaches the serial anchor.
3. **Step 3 — end-to-end gate:** ×2 byte-identical boots (serial transcripts
   compared modulo timestamps), full RED leg set, receipt.

## Verification (row gate — falsifiable)

Step gates are per-step; the row closes on Step 3:

```bash
bash tools/bare_metal_poc/rung9/run_bm903_e2e.sh
```

PASS requires ALL of:

- [x] **L1 executed-vs-constructed identity:** stage2's handoff memory
      (zeropage + cmdline) byte-compares EQUAL to `bm902_zp.bin` /
      `bm902_cmdline.bin` except ONLY offsets in the BM902 field-plan whitelist
      UNION the step-1 addendum rows (type_of_loader, initrd pointers now
      constructed). A diff outside whitelist offsets FAILS, naming the offset.
- [x] **L2 registers:** GPRs/segs/CR0/EFLAGS at 0x100000 match the oracle
      values (rsp may differ — named in the variability addendum if so).
- [x] **L3 serial anchor:** kernel produces serial output through the standard
      handoff and reaches the TinyCore shell marker (`tc@box` or the boot
      completion banner — the exact anchor string is pinned in the gate script,
      chosen in step 2 and never re-chosen silently) inside a stated timeout.
- [x] **L4 ×2 byte-identical:** two boots, serial transcripts byte-identical
      modulo timestamps; handoff dumps byte-identical.
- [x] **L5 RED single-byte:** flipping one zeropage byte outside whitelist
      offsets makes the differ exit NON-ZERO naming the offset (proven in-gate).
- [x] **L6 RED medium corruption:** one corrupted medium byte → CRC refusal
      with host-arithmetic cross-check, NO handoff jump (rung-4 refusal format
      `CRC=<computed> EXP=<expected>`), proven in-gate.
- [x] Every boot leg runs under a wall-clock timeout; a hang is a FAIL with
      the timeout named, never a stuck gate.

Closed 2026-09-19: `bash tools/bare_metal_poc/rung9/run_bm903_e2e.sh` →
`BM903 E2E TALLY: 42 pass, 0 red`, twice in a row. Receipt:
`rung9/RECEIPT_BM903_E2E.md` (RED legs pasted verbatim from a green run).

Amendment recorded against L3/L4, measured not assumed: Tiny Core's
`/sbin/autologin` lets the tty1 and ttyS0 getties race for one flag file, so
which console draws the prompt is a coin flip **on both BM903 media** (19 timed
pixel boots → 11 anchors, 8 step-1 boots → 3, `-vga none` → 6/8, and a longer
single budget rescues a lost boot not at all). L3 and L4 therefore allow up to 8
boots at 45 s each — the same worst-case wall clock as one 180 s boot, each
losing attempt printed — instead of asserting a boot-to-boot determinism the
guest does not possess. The anchor string is exactly the one chosen in step 2
(`tc@box`); no leg was OR'd, relabelled or dropped. See the receipt for the two
gate-rig bugs this surfaced (a probe path and a substring collision) and for the
T4 cut-position fix that a double-login boot forced.

## Failure evidence (RED-first requirement)

L5 and L6 must be shown RED in the same clean gate run that goes green; their
output is pasted literally in the receipt. If any leg cannot be made to fail,
the gate is decoration and the row is NOT done.

## Files in scope

`tools/bare_metal_poc/rung9/` ONLY (new files: `bm903_stage2.asm/S`,
`bm903_stage1*` if needed, `run_bm903_e2e.sh`, `bm903_*.{py,bin,json,txt}`,
`RECEIPT_BM903_E2E.md`, field-plan addendum file), plus the TASK_BM903 cell in
`tools/bare_metal_poc/ROADMAP.md` and this brief.

## Must-not-touch

`rung1`..`rung7` trees (read-only; reuse by copy, never in-place edit),
`rung9/oracle_*` dumps + `ORACLE_BOOT_PARAMS.md` + `BM902_FIELD_PLAN.md`
whitelist (frozen; addendum file instead), `rung9/vmlinuz64.extracted`
(pin-verified, read-only), `tools/glyph_gpt/**`, `glyph_dispatch/**`,
WGSL shaders, `voicebook/`, `.rts/`, `rs_fixtures.json`.

## Boundary

QEMU/TCG software rung. No physical hardware (Rung 8 stays BLOCKED-EXTERNAL).
TASK_BM001 (landing bare_metal_poc) stays HOLD; this brief lands only its own
artifacts + receipt + roadmap cell, per the house pattern.

## Definition of done

All gate legs green in one clean run of `run_bm903_e2e.sh`, RED legs
demonstrated in the same run, ×2 determinism satisfied, receipt + pins
committed, ROADMAP cell TASK_BM903 marked ✅ with the pasted GREEN tail, and
`git status --short` confirms only in-scope files changed.

## Never weaken a live guard

If a verification leg (differ comparison, whitelist count assertion, CRC gate,
pin check) blocks the step, the step is wrong — do not weaken or delete the leg
to reach green. Interfaces are LOCKED: `probe34_capture.py` capture structure,
the oracle artifact formats, and the BM902 whitelist contract are fixed; if a
locked signature looks wrong, file `REPAIR_PENDING_BM903_<topic>.md` with
options cheapest-first and HOLD, per the skeleton contract.
