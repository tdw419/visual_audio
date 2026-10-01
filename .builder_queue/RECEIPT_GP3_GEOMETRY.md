# RECEIPT — GP-3 Extent-Geometry Classes (locate/verify chain)

**Builder:** orchestrator cron `af3e62239ce2`, run 2026-09-17 03:0x–03:4x CDT
**Branch:** `glyph-transpiler-autoloop` (main checkout; new data/docs only)
**Spec:** `HERMES_GUEST_PROMPTING_ROADMAP.md` §GP-3; brief `.builder_queue/brief_gp3_geometry.md`
**Status:** ✅ DONE — 4/4 classes evidenced; gate exit 0; 1 live finding ticketed

## Gate (RED-first)

```
/usr/bin/python3 .builder_queue/gate_gp3_geometry.py   # 12 checks, exit 0
```

RED legs run BEFORE trusting green (outputs in `corpus_build/gp3/`):
- `gp3_verify_sparse_wrongsha.json` — wrong sha rejected (`match: false`)
- `gp3_v_trunc_pre.json` — pre-rewrite sha rejected after truncate+rewrite
- `gp3_v_big3_red.json` — wrong sha on 256MB file rejected
- dense-control leg — dense file maps 16384 data blocks vs sparse's 3
  (block-coverage discriminator; NOTE: first draft asserted on extent COUNT
  and failed GREEN-run because ext4 coalesced the dense control to 3 extents —
  a real validator lesson, recorded here, fixed in the gate, not routed around)

## Classes (guest base `/var/tmp/gp3_1789615295/`)

| class | file | geometry (measured) | locate | container verify |
|---|---|---|---|---|
| sparse | `sparse/sparse.bin` | 64MiB logical, 3×4KiB blocks @ logical 0/8192/16383, rest holes | 3 single-block extents, frames 131+132 | **match: false** → FINDING (ticket GP3-sparse-verify-holebytes) |
| dense control | `dense_control/dense.bin` | 64MiB fully written, 3 multi-block extents, frames 132–134 | 16384 blocks mapped | ✅ match: true |
| hardlink | `hardlink/{orig,alias}.txt` | inode 268623, 2 paths | — | ✅ match: true at BOTH paths |
| truncate_rewrite | `truncrw/f.bin` | 100KB random → truncated → 28B new content | — | ✅ post-sha match; ✅ pre-sha REJECTED (stale pixels not served) |
| multiframe | `multiframe3/big3.bin` | 256MiB, 1 contiguous extent, disk bytes → frames 136..140 = 4 boundaries | spans confirm | ✅ match: true end-to-end |

Intermediates kept: `locate_big_40mb.json` (2 frames/2 extents), `locate_big2_140mb.json`
(140MiB contiguous → frames 134..136 — physical contiguity, not size, drives frame count).

## The finding

Sparse-file container verify cannot match: reconstruction reads hole regions
from container frames, which hold pre-image bytes — guest reads holes as zeros.
`locate` is exact; dense control proves the rest of the chain healthy.
Ticket: `.builder_queue/TICKET_GP3_sparse_verify_holebytes.md` (options a/b/c,
recommendation (a) doc-trap now; tool semantics are shared → not self-changed).

## Trap hit this run

- `rm -rf` in the first construction attempt was blocked by the agent guard —
  restructured to timestamped dirs, nothing deleted. Correct outcome.
- Function-definition scoping made 4 verify calls silently rc=127 in an early
  leg-script draft; `bash -x` caught it before any verdict was drawn.
- First brief draft's "≥8x du vs stat" sparseness assertion was UNSOUND:
  ext4 delalloc reported apparent-size until sync; replaced by the
  block-coverage assertion the gate now uses.

## What this PASS does NOT prove

- 4 classes on n=1 file each — geometry classes are confirmed for THESE files,
  not exhaustively characterized (e.g. no reflink/swapfile/compress classes).
- The sparse mismatch is CONSISTENT with hole-region garbage but hole bytes
  were not individually probed (dense-control discrimination is indirect).
- Guest disk now has ~600MB of test files (`/var/tmp/gp3_1789615295/`,
  df 48%); not cleaned (no rm authority) — cleanup needs Jericho or a guest-side
  explicit instruction.
- GP-3's "find the next real bug" outcome is the hole-bytes ticket; the chain
  itself (locate + barrier verify) held on every non-hole class.
