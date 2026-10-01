# BRIEF (CLOSED 2026-09-18) — R2 gate-hardening from the nested-guest audit (0156493c)

**Scope (exclusive write set):** `tools/bare_metal_poc/rung2/run_gate2.sh`
plus this row. NO asm changes, NO codec changes, NO engine changes, NO
medium regeneration. TASK_BM001 HOLD is unaffected. Receipt from audit:
`tools/bare_metal_poc/rung2/RECEIPT_RUNG2_NESTED_GUEST_AUDIT.md`.

## Why

The nested-guest audit found two gate weaknesses (measured, not theorized):

1. **RED-A blind zero-write.** Payload-corruption offset 516 is 0x00 in the
   pristine medium. A write of 0x00 (or `qemu-io -P 0`) passes the
   corruption-landed check, corrupts nothing, and the leg boots GREEN —
   a corruption test that cannot fail. The host script happens to write
   `ORIG ^ 255` so it is safe TODAY, but nothing asserts it.
2. **Leg sequencing is load-bearing.** RED-B destroys the 55AA signature and
   the rebake only happens later; any partial reordering leaves later legs
   with silently EMPTY serial logs — misreadable as "loader produced nothing"
   instead of "BIOS refused the disk." Observed first-hand during the audit.

## Changes (script-only)

1. Leg [2]: after computing ORIG/NEW, `fail` if `ORIG == NEW` (assert the
   flip actually flipped). Keep the existing landed-check.
2. New pre-flight after leg [0] bake (before the first boot leg): assert
   `med[510:512] == 55AA` AND the medium equals the PNG pixel stream
   (python, same PIL-free byte identity as the existing bake check). This
   guarantees every boot leg starts from a known-bootable medium.
3. Header comment: note the absence scan is O(n*m) — acceptable at 144B
   payload, must be redesigned (suffix-array or block-hash) before any
   kernel-sized payload reuses it.

## Gates (must run, twice, from clean)

`bash run_gate2.sh` → `GATE PASS`, twice consecutively, CKSUM=4541,
RED-A SUM=4640, RED-B 0 bytes, re-green byte-identical. Then one commit.

## Landing evidence (2026-09-18, builder cron af3e62239ce2)

All three changes landed in `run_gate2.sh` (script-only; zero asm/codec/
engine lines). RED shown first, per contract:

- ORIG==NEW assert: pristine byte at offset 516 measured 0x00 — the exact
  audit premise; `ORIG=0 NEW=0` drives the new assert to fire ("flip is a
  no-op … corruption cannot land").
- pre-flight 55AA: signature destroyed on a scratch copy → AssertionError
  `boot signature destroyed: 0000 (want 55aa)` (refused).
- pre-flight PNG identity: one-byte mutation at 516 on a scratch copy →
  `differ: byte 517` vs the PNG bake (refused).

GREEN: `bash run_gate2.sh` **GATE PASS ×2 consecutive, exit 0** —
`green: PXC1-RUNG2 GATE=PASS STAGE2 CKSUM=4541 EXEC`, `redA: GATE=FAIL
SUM=4640`, `redB: 0 serial bytes`, absence 0/129 (59 shared-helper windows
counted, not ignored), re-green byte-identical; all four serial logs
byte-identical across the two runs (diff clean).

NOT proven by this pass: the new pre-flight adds no oracle over what leg [0]
already asserted at bake time (it asserts state *between* bake and boot);
the O(n*m) scan itself is unchanged — only its cost is now documented in the
header. rung2/ sources other than this script stay untracked under the
TASK_BM001 HOLD.
