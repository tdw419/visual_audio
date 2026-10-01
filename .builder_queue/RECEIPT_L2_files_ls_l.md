# RECEIPT — L2-FILES sub-step 1: `ls -l` columns (size/mtime)

**Status:** LANDED
**Commit:** 8afbb69a
**Date:** 2026-09-24 ~00:4x CDT
**Builder:** af3e62239ce2 (product lane, tick after BK-15 landing 5d2f1265)

## Authority

SUPPLY_ROUND8.json layer L2-FILES; ledger NEXT line and RECEIPT_BK15
order: "ls -l columns (FSTAB size/mtime) → `files`/`ls` verb migration
over 0x13 → mkdir/rmdir → `>>` append". This landing is sub-step 1 only;
one gate-able step = one run = one commit.

## What landed

- `experiments/glyph_l1_shell.py`: `_ls(arg)` — `ls -l` / `-la` / `-al`
  render `SIZE ISO-MTIME NAME` rows over the same sorted listing as the
  bare form; `size`/`mtime` are `os.stat` facts about the files the
  landed 0x03/0x04 arms wrote. Plain `ls` output is byte-unchanged.
- `tests/test_l2_files.py` (new, force-added past the .gitignore
  test_*.py rule): F1 (3 files, sorted, byte-exact sizes, parseable
  epoch-adjacent mtimes), F2 (plain ls unchanged), F3 (non-vacuity:
  long form differs from bare; every long line carries size+mtime),
  F4 (empty root → "").

## Gates (real runs)

- RED first (HEAD 5d2f1265, pre-implementation): `ls -l` ignored its
  argument — 2 failed (F1, F3), 2 passed (F2/F4 unchanged-behavior legs).
- GREEN (post-implementation): tests/test_l2_files.py 4 passed.
- Regression: L1 personality + BK-15 + interactive shell = 32 passed;
  BK-7 + text console + syscall integration = 20 passed.
- Non-vacuity (probe_l2_red.py): mutated formatter (ignores `-l`) →
  1 failed (F1 RED); restored tree → 4 passed.

## What the PASS does NOT prove

- `ls` is STILL the host-side personality shim (os.stat on the session
  root). Migration of the listing over SYSCALL_FILE_LIST 0x13 is the
  NEXT sub-step per the order line.
- No engine/GPU changes: sizes/mtimes come from the host FS the 0x03
  arms wrote, not engine-side FSTAB entries (BK-15's 0x13 contract is
  names-only by design; FSTAB created-ts is later sub-step work).
- No mkdir/rmdir/append legs yet — later sub-steps of this layer.
- Payload-size convention disclosed: the write verb forwards the echo
  body, so files are written with one leading space (" a" = 2 bytes) —
  the gate asserts sizes under that convention (F1 comment documents it).

## Next (order line)

`files`/`ls` verb migration over 0x13 → mkdir/rmdir under allow-scoped
root → `>>` append (BK-7 shell flag) → BK-21 after L2.
