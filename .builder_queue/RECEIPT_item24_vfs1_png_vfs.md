# RECEIPT — CLAIM QUEUE item 24: VFS-1 png_vfs.py (builder af3e62239ce2, 2026-09-25 ~11:2x CDT)

## What landed

- `tools/png_vfs.py` — standalone PNG disk transport module (173 lines).
  PNG = TRANSPORT, ext2 = CONTENT, per the PRE-VFS-1 RULING
  (PRODUCT_LANE_STATE.md, 2026-09-25 ~08:4x CDT). API:
  - `wrap(disk_bytes, out_path, block_px=8)` — raw disk -> PNG. 28-byte
    header (magic `PVFSIMG1`, version, flags, disk_sectors, block_px, pad)
    at Hilbert byte offset 0. Loud `PngVfsError` on non-512-multiple sizes.
  - `unwrap(png_path)` — PNG -> raw disk bytes. Header block_px is
    self-describing (power-of-two candidate scan against the magic);
    loud failure on bad magic/version/flags/geometry/short payload.
  - Byte<->pixel convention: pixel k holds payload bytes 3k/3k+1/3k+2 in
    R/G/B; row-major within a Hilbert block; blocks ordered by d2xy from
    `tools/hilbert_reference_verify.py` (the independent reference impl).
- `tests/test_png_vfs.py` — the amended item-24 gate (5 legs).
- Probe driver: `.builder_queue/dbg_v1_hdr_af3e.py` (throwaway header
  inspector, committed for provenance of the byte-convention bugfix).

## SPEC citation (standing CITATION GATE)

SPEC: fs/ext2/ + Documentation/filesystems/ext2.rst +
include/uapi/linux/magic.h (EXT2_SUPER_MAGIC 0xEF53, magic.h:24) read
2026-09-25 (paths verified present: /home/jericho/kbuild-work/fs/ext2/,
/home/jericho/kbuild-work/Documentation/filesystems/ext2.rst);
implementation ours from contract — png_vfs.py never parses or emits
ext2 structures; ext2 content is produced/validated by host
mke2fs/e2fsck/debugfs/dumpe2fs (e2fsprogs). No Linux code vendored.

## RED legs (gate shown able to fail, shown FIRST)

1. Module-absent import (pre-landing + re-proven via `git stash -u`):
   `.venv/bin/python -c "import tools.png_vfs"` ->
   `ModuleNotFoundError: No module named 'tools.png_vfs'`, exit 1.
2. First full gate run (before fixes): **5 failed in 3.69s** —
   expected-size mismatch (4096x4096 vs 2048x2048), struct.error
   (HEADER_FMT pack is 28B, HEADER_LEN was 32), no-magic at offset 0,
   fixture geometry wrong.
3. Mid-fix RED: **4 failed, 1 passed** after the packing rewrite
   (encode/decode convention mismatch still corrupting header).
4. Non-vacuity (leg 3c): corrupted ext2 superblock (magic 0xEF53 ->
   0x1234 at sb+56) -> `e2fsck -fn` returncode != 0 — the checker is
   proven able to reject.
5. RED magic leg: flipped pixel (0,0) red channel -> unwrap raises
   `PngVfsError: no png_vfs header magic at Hilbert offset 0`.

## GREEN legs (final, this process, HEAD+worktree)

`.venv/bin/python -m pytest tests/test_png_vfs.py -v` — **5 passed in
4.69s**, exit 0 (twice: pre-stash and post-stash-pop; tail in
/tmp/item24_gate_green2.txt):
1. `test_item24_mke2fs_wrap_unwrap_fsck_byteexact` — mke2fs -b 1024
   12,581,888 B disk -> debugfs -w write A.txt/B.bin/C.txt -> fsck clean
   -> wrap -> PNG is exactly 2048x2048 -> unwrap byte-identical to
   original disk -> e2fsck -fn clean on unwrapped copy -> all 3 files
   read back via debugfs byte-exact.
2. `test_item24_hilbert_mapping_independent` — probe bytes
   {0, 28, mid, last}: d2xy/xy2d_ref agree with the packing AND the
   stored pixel's red channel equals the disk byte at that offset.
3. `test_item24_red_corrupted_png_magic` — loud PngVfsError.
4. `test_item24_red_corrupted_ext2_superblock` — e2fsck rejects loudly.
5. `test_item24_fixture_sanity_dumpe2fs` — re-measured in-gate: 1024 B
   blocks, magic 0xEF53, Block count 12284.

## Measured geometry (corrects the addendum's numbers)

- 2048x2048 RGB24 canvas = 12,582,912 raw bytes — NOT "16.7MB" as the
  09:0x addendum sized it. The addendum's 16MB figure implies a
  ~2332-px canvas. Fixture therefore uses disk = 12 MiB - 512 B =
  12,581,888 B so header+disk fit exactly in one 2048² PNG.
- mke2fs rounds the fs to whole 8192-block groups: 12,581,888 B device
  -> Block count 12284 (not 12287). Measured via dumpe2fs twice
  (standalone probe + in-gate leg 5).
- Full 4.3-4.7s wall for all 5 legs (host-only, no GPU involved).

## What this PASS does NOT prove

- No GPU OS component reads this format yet — VFS-2/VFS-3 (syscall
  re-route, writeback persistence) are RESERVED pending operator
  sign-off; until then this is a host-side standalone transport.
- Only block_px=8 exercised end-to-end; larger blocks decode via the
  candidate scan but no gate leg wraps/reads one.
- Guest-side ext2 driver equivalence untested (nothing in-guest mounts
  the unwrapped image in this item).
- PNG pixel fidelity relies on PIL lossless RGB round-trip; no
  adversarial codec/optimizer legs.
- wrap() caps at one canvas of data; multi-PNG spanning is out of scope.

## Files touched (git scope check done)

- NEW tools/png_vfs.py, tests/test_png_vfs.py (force-added past
  .gitignore test_*.py rule), .builder_queue/dbg_v1_hdr_af3e.py,
  this receipt. Ledger/CURRENT_TICKET/QUEUE_STATE updated same commit.
- NOT touched: engine/codec/WGSL, protected assets, guest_state.json
  (external monitor's, left dirty as found).
