# V4: Blob-Table PDB for Bootable Payloads

## Goal

Address a bootable Linux payload (bootloader, kernel, initramfs, rootfs) spatially,
by reusing the existing PDB1 format (`systems/geos_pixel/src/pdb/`) rather than
inventing a new one. No changes to Ubuntu itself — this only changes how Geometry OS
stores and locates the bytes that make up a bootable system.

This is a narrower claim than "encode Ubuntu as a database": PDB1 today is a
row/column format for SQLite tables. V4 asks whether the same header + bounding-box
+ Hilbert-encoding machinery can carry opaque binary blobs instead of typed rows.
The answer is yes with no format changes, because `TableMetadata` (`mod.rs:54`) only
tracks `(name, bbox, row_count, row_length)` — a table doesn't have to mean "SQL rows."
A blob is just a table with `row_length = 3` (one RGB triplet) and
`row_count = ceil(blob_bytes / 3)`.

## Why this is a real PoC and not a reach

- `PdbHeader::add_table` (`mod.rs:110`) already enforces disjoint bounding boxes and a
  16-byte name limit — `bootloader`, `kernel_vmlinuz`, `initramfs_cognitive` all fit.
- The encoder/decoder path is already exercised end-to-end for Phase 1 (19/19
  round-trip tests passing per the 2026-08-21 commit) — v4 doesn't need new codec
  logic, just a caller that skips SQLite and writes raw bytes as one table.
- The Rust bootloader or a WGSL shader can find `kernel_vmlinuz`'s bounding box from
  the header alone and extract it on fixed offsets — same lookup path Phase 2's GPU
  scanner already uses for row data.

## Where it breaks: table size

`PdbConfig` (`mod.rs:127`) requires power-of-2 width/height but has no other ceiling.
That's a problem for `ext4_rootfs`, not a solved one:

| Table | Typical size | Pixels needed (3B/px) | Frame side (square) |
|---|---|---|---|
| bootloader | ~5–50 KB | ~2–17K | fits in existing 512×512 |
| kernel_vmlinuz | ~10–15 MB | ~3.5–5M | ~2048×2048 |
| initramfs_cognitive | tens of MB | tens of M | ~4096×4096 |
| ext4_rootfs (full Ubuntu) | 1–4+ GB | 350M–1.4B+ | 32768×32768 territory, multi-GB PNG |

A multi-GB single PNG is real but impractical to move, diff, or decode incrementally.
**Scope decision: v4 PoC covers bootloader + kernel + initramfs as embedded blob-tables.
`ext4_rootfs` stays a referenced table (path + size + hash recorded in the header
metadata) rather than an embedded one**, until a tiled/multi-frame PDB extension
exists. That's a real follow-up (see below), not a caveat to gloss over.

## v4 PoC Plan

1. **`compile_v4_pdb.rs`** (new example alongside `sqlite_to_pdb.rs`): takes N
   `(name, file_path)` pairs, computes `row_length=3`, `row_count=ceil(len/3)`,
   allocates bounding boxes via the existing packing logic in `compiler.rs:124`
   (stacking tables by `current_y`), and writes the PNG. No SQLite involved.
2. **`extract_v4_pdb.rs`**: given a `.pdb.png` and a table name, walk the Hilbert
   curve inside that table's bounding box (reusing `decoder.rs`) and write the raw
   bytes back out. Round-trip-diff against the source files — this is the actual
   verification gate, not a "trust me" claim.
3. **VCC hash**: reuse `vcc.rs` per-table SHA-256 unchanged — it already operates on
   bounding-box pixels regardless of what's semantically inside them.
4. **Rootfs table**: add a `TableMetadata`-compatible reference record (name, on-disk
   path, byte length, SHA-256) — not a bounding box — for `ext4_rootfs`. Decide during
   implementation whether that lives in the same header or a sidecar; either is fine
   as long as it's addressed from the PDB header, matching the "GPU/bootloader finds
   everything from one header" goal.

## Explicit non-goals for v4

- No dconf / live-OS mutation (that's the v5 "semantic OS" idea from earlier — separate
  and higher-risk; not started here).
- No tiled/multi-frame format yet — that's the natural v4.1 once the rootfs question
  above forces it.
- Does not touch `virtio_pixel_rs_v3_*` — this is `systems/geos_pixel` only, no
  bootloader code changes, consistent with the current hands-off boundary on that tree.

## Test plan

- `cargo run --example compile_v4_pdb -- boot_images/hello.img /tmp/boot.pdb.png bootloader`
- `cargo run --example extract_v4_pdb -- /tmp/boot.pdb.png bootloader /tmp/out.img`
- `diff boot_images/hello.img /tmp/out.img` — must be byte-identical
- Repeat for a real `vmlinuz` + `initramfs` once bootloader round-trip is clean
- VCC hash must be stable across two compiles of the same input
