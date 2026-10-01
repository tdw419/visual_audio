# TASK_BL005 — MKV-as-Disk: Boot Alpine from a Visual Audio MKV Container

**Date**: 2026-09-04
**Status**: PASS (live browser receipt)
**Phase**: 27 (Browser-Native Boot from Visual Audio Containers), extension task
**Predecessor**: BL004 (WAV-as-disk) — this task replaces the opaque WAV with a real VAC1 MKV container.

## Claim

A v86 guest in a stock headless Chrome can boot Alpine Linux from a disk
image that lives inside a Visual Audio Matroska container, where the browser
recovers every frame of the image purely via HTTP Range GETs against the
.mkv file plus in-browser byte manipulation — no ffmpeg, no video decoder,
no disk-image fetch in the boot path.

## Receipt chain

1. **Offline roundtrip** (`mkv_sector_container.py encode/verify/decode`):
   16MB Alpine disk (`sha256 3089f7df…`) → 258-frame MKV (1 VAC1 directory
   frame + 257 disk frames) → decode → sha256 identical. All 257 per-frame
   CRC32s match the manifest.
2. **Offline browser-recipe simulation** (Python, before any browser run):
   for all 257 frames — slice `[ffprobe_packet_pos+4, +frame_bytes)` from the
   file, BGR-unswap, unframe dense_encoder framing, CRC-check against
   manifest — assembled buffer sha256 matches. This simulation is the exact
   recipe the JS later executed.
3. **Live CDP run** (`receipts/receipt_run2.json`, headless Chrome 152,
   `BL005_PASS`):
   - 257 Range GETs against `disk.mkv`, 1 manifest fetch
   - zero `.img`/`.wav` requests (gate in driver; only v86's own
     kernel/initrd/BIOS/wasm fetched as files, same as BL004)
   - 0 CRC failures; browser-assembled sha256 == manifest sha256
   - fetch phase 1.5s (257 sequential fetches, avg 3.97ms/frame, localhost)
   - `BL002_ROOT_MOUNTED` → userspace shell in 18.7s

## Design findings (each was a potential dead end, tested empirically)

### FFV1 is unusable for the Range path
The obvious design — encode the VAC1 frames with FFV1 (the project standard,
used by `va_container.py`) and Range-fetch frame bytes — fails because FFV1
compresses: the file's on-disk bytes are coded data, not pixels. There is no
JS FFV1 decoder, so the browser cannot recover the frame from a Range GET.
Verified by attempting the fetch+unframe against an FFV1-encoded container
(magic bytes were `\x81\x00…`, not `UA` framing).

### rawvideo V_UNCOMPRESSED is the workable encoding
`-c:v rawvideo -pix_fmt bgr24 -f matroska -allow_raw_vfw 1` stores pixel
bytes verbatim in the Matroska packet (at `packet_pos + 4`, after the
SimpleBlock header), so a Range GET returns usable bytes directly. Two
properties verified:
- ffmpeg's rgb24 decode of the container recovers the original RGB bytes
  exactly → the file stays readable by `va_container.py` as a VAC1 container
  (directory in frame 0, `disk/image` entry, dense_encoder framing).
- The stored bytes are the BGR swap of the original frame; the browser
  unswaps with a 3-byte-stride R/B exchange. Pure byte shuffling.

### Cost accounting
Uncompressed MKV: 150MB for the 16MB test image (258 × 607500B frames).
FFV1 gave 8.1MB. That ~2.7× vs the raw image and ~18× vs FFV1 is the honest
price of "no decode in the browser." A JS FFV1 decoder would collapse it —
future work, tracked below.

### Frame-offset capture
Per-frame byte offsets come from `ffprobe -show_entries packet=pos,size`
(PTS-sorted), embedded in the manifest. The browser does no Matroska
demuxing — it trusts the manifest and does offset arithmetic.

## Files

- `mkv_sector_container.py` — encode/verify/decode (offline; ffmpeg allowed here)
- `bl005.html` — browser-side assembly + v86 boot
- `bl005_drive.mjs` — CDP driver + gates (sha256, CRC, request exclusivity, userspace marker)
- `range_server.py` — 206-capable static server (copied from BL004)
- `receipts/receipt_run1.json` — first full live run (passed all gates except
  an over-broad forbidden-request regex that flagged the initramfs `.gz`;
  gate corrected, see run2)
- `receipts/receipt_run2.json` — clean PASS receipt

## Falsifiable follow-ons (not claims)

- JS FFV1 (or similar) decoder in the boot path → 150MB → 8MB container.
- Mount the container as `visual_audio.mkv`'s disk entry via
  `va_container.py add` instead of a standalone MKV, then read the disk back
  out with `cat` as the roundtrip gate.
- ALTS lru: range-fetch lazily per v86 sector read instead of full
  pre-assembly (would make boot time independent of image size).
