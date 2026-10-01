# GH-22 Gate Receipt — Device Driver ABI (Spatial Microkernel Protocol)

**Date:** 2026-09-09
**Branch:** glyph-transpiler-autoloop
**Gate:** `tests/test_gh22_device_driver_abi.py` — 5/5 green
**Arc regression:** ALL GH tests (test_gh1..test_gh22) 179 passed / 0 failed
(78.7s). Pre-existing failures outside the GH arc (audio/WGSL legacy files,
3 collection errors + scattered fails) reproduce at HEAD~ without my
changes; they are not GH-arc items and were left untouched.
**RED receipt:** output/gh22_gate_run1_red.txt (ImportError — collection
fails at the missing `driver_abi_kernel_image`), then runs 2-9 document the
fix chain below.

## Mechanism

`tools/glyph_gpt/gh22_driver_abi.py` bakes a resident driver-ABI microkernel
(GH-13's proven two-pass round-robin pattern, 2 boxes):

- BOX0 = application task [700..717), BOX1 = driver task [718..735).
- **The box bound IS the MMIO bound.** The DEV-U1 device registers
  (DEV_DATA=733, DEV_STATUS=734) live INSIDE BOX1; a store outside
  [718*4, 735*4) bytes vectors E-K1. No new engine mechanism was added —
  isolation reuses the existing E-K1 predicate unchanged.
- **Non-blocking mailbox protocol (GH-13 SYS 6/7/8 numbers, per-image
  selector):** SYS 6 = app request -> mailbox 754; SYS 7 = mailbox ->
  driver read-out 720; SYS 8 = driver verdict 724 -> app read-out 714.
  Every slice copies-and-continues; nobody polls or waits. The kernel is
  the POSTMAN only — it never interprets the message.
- **No monolithic kernel driver:** the kernel program never touches words
  733/734. The device PUT sequence executes entirely in the driver's USER
  slice. Leg 3's step_trace proves the driver phases run in USER mode.
- **SOURCE RULE (GPLv2):** the protocol is written from the DEV-U1 fixture
  datasheet (documented in the test module docstring); no Linux source was
  read or transcribed. Trusted-unproven boundary: the host `_device_model()`
  mirrors the datasheet; the oracle (leg 3) proves driver == model
  word-exact. The model is fixture code, not proven against silicon.

## Message format (1 word — corrupted packet = one flipped field)

    bits [31:24] checksum = (opcode + payload) & 0xFF
    bits [15:8]  opcode   (1 = DEV_PUT)
    bits [7:0]   payload

## Fix chain (receipts output/gh22_gate_run*.txt)

1. run1/run2: RED — missing baker symbol, then circular import. Fix:
   deferred `from glyph_gpt.baker import ...` inside the bake/text
   functions (fs_v2.py's established pattern for baker-re-exported
   modules).
2. run5: SYS 7 stored the request into SYS_A0 but the driver read word
   720 — the marshaled-arg path was the wrong contract. Fix: kernel-
   mediated copy into the read-out word (exactly GH-13's SYS 7 shape),
   no SYS_A0 round-trip for receive slices.
3. run6: driver verdict 'E' on a GOOD packet. Root cause: `SHR r7 r4`
   / `AND r6 r4` are IN-PLACE on rd (rd = rd op rs2) — the byte extracts
   were shifting/masking stale register garbage, not the request word.
   Fix: explicit zero+OR copies of r2 into r5/r6/r7 before each
   shift/mask (`_gh22_checksum_check`), same discipline in the payload
   extraction. This is the GH-19 divmod lesson (in-place ALU forms)
   resurfacing in a new tile.
4. run8: fault-leg test asserted `EXIT_APP == 0`, but app slice 1
   legitimately completes (including its exit write) BEFORE the driver
   is scheduled. Fix: assert the correct cut — slice 1 exit written,
   slice-2 verdict/exit + driver exit + verdict all zero.

## Landed ABI facts for downstream (GH-23+)

- Driver-in-a-box pattern: put device registers INSIDE the driver's box
  range; E-K1 then bounds MMIO for free. No engine change needed.
- Per-image syscall selectors may reuse 6/7/8 (GH-13 numbers) — the
  :__ksys selector is baked per-image, not global.
- In-place ALU forms (AND/OR/XOR/SHL/SHR rd, rs2): ALWAYS zero+OR-copy
  before extract. Third occurrence of this lesson (GH-19 divmod, GH-19
  strcmp, GH-22 checksum).
- Mailbox verdict pattern: producer writes a verdict word; consumer
  reads it in its OWN next slice — never read the producer's box.
- Status IDs: GH-22 uses 0xCAFE0000|26 (0xCAFE001A); exit words
  0xFEED0000|22 (app) / |23 (driver).
