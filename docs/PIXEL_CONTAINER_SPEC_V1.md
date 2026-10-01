# Pixel Container Format v1 (working name: PXC1)

Status: draft, not yet implemented. Written to close out a class of bugs found
2026-08-15 debugging `ubuntu_cognitive_vac2_v3_full.nut`: the encoder
(`tools/encode_spatial_container.py`), the Rust backend
(`systems/virtio_pixel_rs`), and the guest `init` script each held a
different, undocumented assumption about byte packing and section offsets.
None of those three components disagreed on purpose — there was simply no
written spec to disagree *with*. This document is that spec. Any code that
reads or writes this format must match it exactly; if a change is needed,
change this file first, then the code, then bump the version.

## 1. Goals / non-goals

- Goal: one unambiguous byte layout, implemented once, shared by encoder and
  decoder (ideally the *same* Rust crate, not two independent reimplementations).
- Goal: no dependency on ffmpeg or any video codec. Root cause of the
  2026-08-15 corruption was ffmpeg silently reordering channels between a
  declared `rgb24` input and an actual BGR write order.
- Goal: fixed-offset metadata (frame 0), so a reader never scans the disk
  looking for a magic string.
- Non-goal (for v1): compression. Sections are stored uncompressed. If
  density becomes a real constraint, that's a v2 concern layered on top of
  a working v1, not solved by guessing now.
- Non-goal (for v1): the "visual/inspectable" property is preserved (each
  frame is a valid PNG you can open and look at), but nothing in v1 depends
  on a human or vision model actually looking at it. That's future work.

## 2. Byte packing

Each pixel stores 4 raw, independent bytes — no offset, no bit-splitting,
no derived "id" value:

```
pixel.R = data_byte[4*i + 0]
pixel.G = data_byte[4*i + 1]
pixel.B = data_byte[4*i + 2]
pixel.A = data_byte[4*i + 3]
```

where `i` is the pixel's linear index within the frame (see §4 for
byte-index-to-pixel-position mapping). Decoding a pixel back to bytes is
`[pixel.R, pixel.G, pixel.B, pixel.A]` — nothing else. This directly
replaces the old `id_val = byte + 16` scheme, which required reconstructing
byte order empirically (see 2026-08-15 debugging notes) because it was never
written down anywhere.

This gives exactly 4 bytes of payload per pixel — a real 4x density
improvement over the old 1-byte-per-pixel scheme, not just a format change.

## 3. Frame geometry

- Frame size: 4096 × 4096 pixels (fixed for v1; not configurable per-file).
- Bytes per frame: `4096 * 4096 * 4 = 67,108,864` (64 MiB exactly).
- Pixel format: RGBA8888, stored as a PNG (8-bit depth, no palette, no
  interlacing, no gamma/color-profile chunks — those are irrelevant to raw
  data and must not be allowed to perturb pixel values on decode).

## 4. Byte-index-to-pixel mapping

v1 uses **row-major order**, not the Hilbert curve:

```
pixel_index = byte_group_index   (byte_group = 4 consecutive payload bytes)
y = pixel_index / 4096
x = pixel_index % 4096
```

Rationale: the Hilbert mapping bought spatial locality for a future
vision-model consumer, but every real bug this session was a *disagreement
about where bytes are*, and row-major is trivially invertible by inspection
(useful for exactly the kind of manual forensic decode this session needed
to do by hand). If spatial locality is needed later, it can be a v2 opt-in
without touching the byte-packing rules in §2 — don't couple them again.

## 5. File layout

One file per frame, not one multi-frame container. This removes an entire
class of "which offset is frame N at" bugs, and lets a reader/writer treat
each frame as an independent, ordinarily-openable PNG file.

```
<container_dir>/
  header.json          <- see §6, describes total layout
  frame_00000.png       <- metadata frame (§6 duplicates header.json's
                            content INTO this frame too, so the guest can
                            read it from the block device without host
                            filesystem access)
  frame_00001.png
  frame_00002.png
  ...
  frame_NNNNN.png
```

Frame filenames are zero-padded to 5 digits (supports up to 99,999 frames =
6.1 TB at 64MiB/frame, well beyond any current use case; widen the padding
before that becomes a real limit, don't work around it).

## 6. Header (frame 0)

Frame 0 is reserved for metadata and is never counted as payload data.
Bytes 0..N of frame 0 (in the §4 mapping) hold a UTF-8 JSON document,
length-prefixed:

```
[8 bytes: little-endian u64 JSON length]
[JSON bytes]
[zero padding to end of frame]
```

JSON schema:

```json
{
  "format": "PXC1",
  "frame_size": 4096,
  "bytes_per_frame": 67108864,
  "sections": [
    {
      "name": "rootfs",
      "start_frame": 1,
      "byte_length": 3758096384,
      "sha256": "<hex>"
    },
    {
      "name": "initramfs",
      "start_frame": 57,
      "byte_length": 289780671,
      "sha256": "<hex>"
    },
    {
      "name": "gguf",
      "start_frame": 62,
      "byte_length": 668788096,
      "sha256": "<hex>"
    }
  ],
  "total_frames": 283
}
```

Rules:
- `sections` is an ordered list; consumers MUST locate a section by name
  (`"gguf"`, `"rootfs"`, etc.), never by hardcoding a byte offset. This is
  the direct fix for the 2026-08-15 bug where `init`'s
  `COGNITIVE_OFFSET_BYTES` was a hardcoded constant that silently went
  stale every time the encoder's layout changed.
- Every section's `start_frame` is where its first byte lives; a section
  never starts mid-frame. If a section's actual data doesn't fill its last
  frame, the remainder of that frame is zero-padded, and the *next*
  section starts at the next frame boundary. This costs at most one wasted
  frame (64 MiB) per section — acceptable for v1's non-goal of density
  optimization (§1), and it means "does this section fit in the frames
  I've read" is never a partial-frame arithmetic problem.
- `sha256` is mandatory. A reader MUST verify it after extracting a section
  and MUST treat a mismatch as fatal, not log-and-continue — the
  2026-08-15 session's silent corruption is exactly the failure mode
  hashing here is meant to catch immediately instead of three debugging
  rounds later.

## 7. Guest-side contract

The guest (`init` / `extract_cognitive.py` equivalents) MUST:
1. Read frame 0, parse the header, locate the wanted section by name.
2. Read exactly `byte_length` bytes starting at `start_frame`'s first byte
   (spanning into subsequent frames as needed — a section is not
   guaranteed to fit in one frame).
3. Verify against `sha256` before use.
4. Never scan for a magic string, and never hardcode a byte offset as a
   constant in a shell script. If the layout changes, only the encoder and
   this spec need updating — every consumer already reads the layout from
   frame 0.

## 8. What this replaces

| Old (`ubuntu_cognitive_vac2_v3_full.nut`) | New (PXC1) |
|---|---|
| ffmpeg NUT container, rawvideo BGR24 | Plain PNG per frame, no video codec |
| `id_val = byte + 16` split across R/G/B | 4 raw bytes per pixel, RGBA |
| Hilbert curve byte ordering | Row-major (§4) |
| `init` hardcodes `COGNITIVE_OFFSET_BYTES` | Sections located by name via frame-0 header |
| `extract_cognitive.py` scans for `"payload_size"` string | Direct read, no scanning |
| No integrity check | Mandatory SHA-256 per section |

## 9. Implementation plan (not yet started)

1. Single Rust crate (`tools/pxc1/` or similar) implementing both encode and
   decode against this spec — not a Python encoder + separate Rust decoder,
   which is exactly how encoder/backend drifted apart last time.
2. `virtio_pixel_rs` backend reads the whole container into an in-memory
   buffer at startup (total size is a few GB, host has 60+ GB RAM — see
   2026-08-15 session notes) and serves block reads as slices of that
   buffer. PNG decode cost is paid once at startup, not per block request.
3. A `pxc1-verify` CLI that checks every section's hash against the header
   without booting anything — this is the fast, cheap sanity check that
   should have existed before any of the 2026-08-15 boot attempts.
4. Update `init` and `extract_cognitive.py` (or their replacements) to the
   §7 contract.
5. Only after (1)-(4) are working and tested: consider whether Hilbert
   ordering or compression are worth adding as an opt-in v2 layer.
