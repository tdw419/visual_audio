# BM903_FIELD_PLAN_ADDENDUM.md — TASK_BM903 step 1 addendum

**Status:** addendum to the frozen `BM902_FIELD_PLAN.md` (that file is
must-not-touch; this one carries the delta). Machine-consumed: the fenced
block below is parsed by `bm903_differ.py` with the same grammar as the BM902
plan's block, and the differ ASSERTS that this addendum licenses no offset the
BM902 plan does not already whitelist. **It widens nothing.** Union size after
the merge is therefore identical to BM902's (517 offsets).

**Why an addendum exists at all:** BM902's construction shipped NO initrd, so
`ramdisk_image`/`ramdisk_size` were whitelisted on the grounds "loader may set
these". BM903's stage2 actually does. The values are now inputs to the boot,
not blanks, so the rows are re-declared with their measured content and the
verification that pins them (differ leg L2b).

## What changed in kind, not in extent

| Offsets | Field | BM902 (constructed) | BM903 (executed) | Class |
|---|---|---|---|---|
| 0x218-0x21b | `ramdisk_image` | 0x00000000 | 0x10000000 (our chosen load address, 256 MiB, inside `-m 512` and below the kernel's `initrd_addr_max` 0x7fffffff) | LOADER-SPECIFIC (already whitelisted) |
| 0x21c-0x21f | `ramdisk_size` | 0x00000000 | 0x8d4f07 = 9,260,807 B = `rung7/core.gz` exactly | LOADER-SPECIFIC (already whitelisted) |
| 0x210 | `type_of_loader` | 0xff | 0xff (unchanged — 0x33 is isolinux's identity and we are not it) | LOADER-SPECIFIC (already whitelisted) |

`loadflags` 0x211 stays 0x81 (bit0 LOADED_HIGH | bit7 CAN_USE_HEAP).
Deliberate: 0x211 is a MUST-MATCH row in BM902's plan, and the protocol's
other loadflags bits are not initrd flags anyway — bit1 is QUIET, bit2 is
KEEP_SEGMENTS — the kernel learns of an initrd purely from
`ramdisk_image`/`ramdisk_size`. Whether 0x81 is actually enough for
TinyCore to unpack `core.gz` was a MEASUREMENT question for step 3's serial
anchor (no shell without a populated rootfs), not a reason to touch a
MUST-MATCH row here. **ANSWERED 2026-09-19:** it is enough — the pixel medium
reaches `tc@box` on serial with loadflags 0x81 and nothing else set
(`run_bm903_e2e.sh` L3/L4, `RECEIPT_BM903_E2E.md`), so the frozen bar held.

`heap_end_ptr` 0x224-0x225 stays 0xefff (MUST-MATCH class: LOADER-SPECIFIC in
BM902, identical value here).

## Machine block (the differ reads this; BM902's own block is unchanged)

```
0x218-0x21f   ramdisk_image + ramdisk_size   (re-declared: now CARRY OUR NUMBERS, verified by differ leg L2b)
0x210         type_of_loader                 (re-declared: 0xff confirmed executed, not just planned)
```

## Register variability

**None.** BM902's plan whitelisted `rsp` as LOADER-SPECIFIC because a future
stage2 might land it elsewhere. The executed stage2 sets `esp = 0x1f784` as the
last stack mutation before the far return — `retf` pops both dwords, so the
value the kernel observes is exactly the oracle's. `bm903_differ.py` therefore
compares `rsp` too: its L3 leg checks 25 registers — BM902's table has the same
25 but its L3 loop `continue`s past `rsp`, checking 24. Nothing is excused
here that BM902 excused and BM903 fails.

## Measured executed-vs-constructed diff (this tick, leg 0 == leg 1)

Against `bm902_zp.bin` (the constructed artifact): 4 bytes —
`0x21b 0x10`, `0x21c 0x07`, `0x21d 0x4f`, `0x21e 0x8d`. All four are the
initrd pair above; nothing else in 4096 bytes moved. Against
`oracle_zp_leg0.bin`: the same 4 plus BM902's already-whitelisted loader rows
(0x1f2, 0x1fd, 0x210, 0x213, 0x219-0x21b, 0x224-0x225) and the zeroed
0x000-0x1e7 STAGE2-CHOICE band — every one of them inside the union.

## What this addendum does NOT license

- No new offsets, ever (asserted by the differ, not by prose).
- No change to any MUST-MATCH row: the kernel-baked band 0x1f1-0x268 is copied
  by EXECUTED code from the bytes it read off the medium, which is the point of
  step 1 — the band's correctness is now proven by a running CPU, not by a host
  `fseek`.
- No change to the e820 table (7 entries, 140 B, pinned blob) or the cmdline
  (byte-exact oracle string, all 512 B compared).
