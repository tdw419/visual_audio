# Software-to-Video (MKV) Pipeline

How this project turns a running program's execution state into a lossless
`.mkv` video file — and back again. This document supersedes the scattered
narrative in `HYPER_DIMENSIONAL_VIDEO_BOOT_RECEIPT.md` for the mechanics; that
file still has the original design conversation if you want the "why."

Status legend used throughout: **VERIFIED** (re-run and confirmed working
today), **PARTIAL** (core primitive verified, wrapper script not yet run
clean end-to-end), **UNVERIFIED** (implemented, never exercised against real
data — synthetic demo only).

## The core idea

A running QEMU guest is just a block of RAM changing over time. If you pause
it, dump that RAM to a file, and turn the bytes into pixels, you get an
image. Do that repeatedly and encode the images as a lossless video codec
(FFV1) and you get a video file that **is** a bit-exact recording of
execution state — not a screen capture, an actual memory dump per frame.
Because it's lossless, any frame can be decoded back into the exact bytes
that were dumped, and (in principle) fed back to QEMU to resume from that
point.

## Pipeline, step by step

```
QEMU guest (running)
      │  QMP: {"execute": "stop"}                 ← pause the vCPU
      ▼
QMP: {"execute": "dump-guest-memory",
      "arguments": {"protocol": "file:/path"}}     ← VERIFIED: real 512MB
      │                                               ELF core dump, structured
      ▼                                               non-zero content
raw memory bytes (ELF core format)
      │  hilbert_d2xy() — tools/qemu_capture_simple.py, tools/qemu_to_mkv.py
      ▼
2D pixel grid (Hilbert curve mapping preserves spatial locality:
a contiguous memory region stays visually contiguous instead of
scattering across the image the way a raster/row-major mapping would)
      │
      ▼
dense_encoder_video.encode_mkv()
      │  - splits the byte payload into 65,531-byte chunks
      │  - each chunk → one 450×450 RGB24 PNG frame
      │  - ffmpeg encodes frames as FFV1 (mathematically lossless)
      │  - writes manifest.json (per-frame CRC32 + MD5, overall hash)
      │    as an MKV attachment
      ▼
output.mkv  (video track = state, attachment = integrity manifest)
```

Extraction reverses this exactly: `decode_mkv()` pulls the FFV1 frames back
to bytes (verified bit-exact via CRC/MD5 in the manifest), and
`extract_frame_from_mkv()` in `qemu_to_mkv.py` slices out one logical
capture's worth of bytes and writes it back out as a raw memory dump.

## Important nuance: "one frame" is ambiguous, and the scripts conflate two meanings

`encode_mkv()` doesn't know or care about boot iterations — it just slices
whatever byte payload it's given into fixed 65,531-byte chunks and makes one
*video* frame per chunk. The capture scripts build up a "logical frame" per
QMP poll (a CPU-state snapshot or a memory-dump snapshot) and concatenate
all of them before handing the whole thing to `encode_mkv()` once, at the
end.

That means the earlier claim "every frame in the MKV is exactly one CPU
dispatch iteration" (from `boot_xv6_gpu.py --trace-mkv`) is **not literally
true**: each CPU-state snapshot is 582 bytes, so ~112 of them get packed into
a single 65,531-byte FFV1 video frame. Similarly in `qemu_capture_simple.py`,
each logical capture is a 256×256×3 = 196,608-byte pixel buffer, which spans
~3 video frames. If you want strict 1-video-frame-per-logical-snapshot, the
per-snapshot payload needs to be padded/aligned to exactly 65,531 bytes (or
`encode_mkv` needs a per-item boundary flag) — not done yet.

## Known limitation: only a slice of RAM is actually visualized

`map_ram_to_pixels()` in `qemu_capture_simple.py` requires exactly
`width * height * 3` bytes and **truncates** anything larger:

```python
if len(ram_data) < required_bytes:
    ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
else:
    ram_data = ram_data[:required_bytes]   # <-- truncation
```

With a 256×256 grid that's 196,608 bytes — so today's pipeline visualizes
only the **first ~192KB** of a 512MB guest-memory dump, not the whole
address space. Fine as a proof of concept (you do see real, structured,
non-zero kernel data), but "watch the whole kernel decompress across the
frame" is not yet true — that would need either a much larger grid or tiling
across multiple frames.

## Two capture implementations

- **`tools/qemu_capture_simple.py`** — synchronous, QMP-only, single-file.
  Simpler, easier to debug. **PARTIAL**: today I fixed two real bugs in it
  (below) and confirmed the underlying QMP dump primitive works against a
  live Alpine RISC-V boot; a full clean run through to a written `.mkv` was
  not confirmed this session due to unrelated environment flakiness
  (concurrent processes colliding on the same `/tmp/qemu_simple.sock` path).
- **`tools/qemu_to_mkv.py`** — async (QMP over `asyncio`), more features
  (frame extraction back to a memory dump). Currently has uncommitted
  in-progress fixes for the QMP greeting handshake and the RISC-V boot
  command line (disk+firmware instead of direct kernel boot). **PARTIAL**,
  same reason.
- **`tools/boot_xv6_gpu.py --trace-mkv`** — different data source: instead
  of QEMU/QMP, this reads the 528-byte GPU `RiscvCPU` struct (see
  `tools/riscv_gpu_cpu.py`) after every WGSL compute dispatch and pads it to
  582 bytes per frame. This is the GPU-native xv6 boot, not QEMU. Status:
  see `[[gpu-riscv-xv6-boots-to-shell]]` — the underlying boot is verified
  real; the `--trace-mkv` flag itself (added this session, before the
  current conversation) has not been independently re-verified.

### Bugs found and fixed today in `qemu_capture_simple.py`

1. **Wrong QEMU flag.** It launched QEMU with `-monitor unix:...` (QEMU's
   plain-text Human Monitor Protocol) but the Python client spoke JSON QMP
   to that socket. Fixed to `-qmp unix:...`.
2. **Missing stdin redirect.** `subprocess.Popen(...)` for the QEMU child
   didn't set `stdin=subprocess.DEVNULL`. With `-nographic`, an inherited
   controlling-terminal stdin risks QEMU putting the shared tty into raw
   mode. Fixed by explicitly redirecting stdin.

Independent of the script, I confirmed the raw QMP sequence works end to
end by hand: connect → `qmp_capabilities` → `stop` → `dump-guest-memory`
→ real 536,932,352-byte ELF core dump with structured (non-zero, non-random)
content. **This is the primitive the entire architecture depends on, and
it's real.**

## VAC3: frames as a Z-axis instead of a timeline

Separate, newer idea layered on top of the same MKV container:
instead of frame N meaning "time step N," treat frames as depth slices of a
3D texture:

- Z=0 — display/framebuffer (what a human/UI would render)
- Z=1 — RAM substrate (what the GPU CPU emulator reads/writes)
- Z=2 — diagnostics (crash codes, written by compute shaders without
  disturbing what's on screen)

Spec: `VAC3_SPEC.md`. Implementation: `tools/vac3_demo.py` (fully synthetic
demo, all 3 layers are mockups), `tools/vac3_inspect.py` (generic
layer-extraction/inspection, source-agnostic), `tools/vac3_visualize.py`.

**Z=1 wired to real data — VERIFIED.** `tools/vac3_real_capture.py` builds a
VAC3 bundle where Z=1 (`ram_substrate`) is real: booted a live 64MB Alpine
RISC-V guest, paused it via QMP, ran `dump-guest-memory` for a genuine
67,171,071-byte dump, and Hilbert-mapped the first 196,608 bytes into the
Z=1 layer using the same `map_ram_to_pixels` already verified in
`qemu_to_mkv.py`. Z=0 (display) and Z=2 (diagnostics) are still synthetic
placeholders — this project doesn't render an actual framebuffer or detect
real crashes yet, so those stay honest mockups; the manifest now tags each
layer's `source` (`real_qemu_dump_guest_memory` vs `synthetic_placeholder`)
so it's inspectable which is which.

Extracted and visually confirmed `demo_vac3_z1.png`: large solid-black
regions (zeroed/reserved memory) and high-entropy colored regions
(populated memory) form clean, contiguous rectangular/L-shaped blocks — the
Hilbert curve's spatial-locality property showing up exactly as claimed —
and it's visually distinct from `vac3_demo.py`'s synthetic 4-quadrant
pattern, confirming this isn't accidentally reusing the synthetic
generator.

**Full-RAM tiling wired into VAC3 Z=1 — VERIFIED.** `vac3_real_capture.py`
now uses the same tile-and-Hilbert-map loop as `qemu_to_mkv.py` instead of
truncating to one grid's worth of bytes. Live run: 64MB guest → real
67,171,071-byte dump → 1367 tiles of 128×128 → Z=1 layer of exactly
67,190,784 bytes (1367 × 49,152, tile-padded). Decoded the resulting MKV
back and confirmed: manifest offsets line up exactly (`Z=1 offset 49152,
size 67190784`, `Z=2 offset` immediately after), decoded payload length
matches byte-for-byte, and per-tile content is real — tiles 0–2 hold dense
structured data (132 nonzero bytes in tile 0, matching the same-magnitude
ELF-header content confirmed in this session's very first direct-QMP test),
while the rest of the 64MB is legitimately zero — expected for a guest
paused this early (right after firmware handoff, before Alpine's rootfs is
loaded into most of RAM), not a tiling artifact.

## Practical recipe (once the wrapper scripts are confirmed clean)

```bash
# Capture ~10 QMP-polled memory snapshots from a real Alpine RISC-V boot
python3 tools/qemu_capture_simple.py boot_images/alpine_riscv64.qcow2 \
    --output alpine_boot.mkv --max-frames 10

# Inspect / decode
python3 -c "
from tools.dense_encoder_video import decode_mkv
payload, manifest = decode_mkv('alpine_boot.mkv')
print(manifest['metadata'])
"
```

Manual (verified-working) primitive, if you just want to confirm the QMP
side without the Python wrapper:

```bash
qemu-system-riscv64 -m 512M -nographic \
    -qmp unix:/tmp/live.sock,server,nowait \
    -M virt -drive file=boot_images/alpine_riscv64.qcow2,format=qcow2,if=virtio \
    -bios default &

python3 -c "
import socket, json, time
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect('/tmp/live.sock')
s.recv(65536); s.send(json.dumps({'execute':'qmp_capabilities'}).encode()+b'\n'); s.recv(4096)
s.send(json.dumps({'execute':'stop'}).encode()+b'\n'); s.recv(4096)
s.send(json.dumps({'execute':'dump-guest-memory','arguments':{'paging':False,'protocol':'file:/tmp/mem.raw'}}).encode()+b'\n')
time.sleep(2); print(s.recv(65536))
"
```

## Inter-frame delta encoding — VERIFIED end-to-end against a real boot

Both `qemu_capture_simple.py` and `qemu_to_mkv.py` store each captured
frame as `pixels[i] XOR pixels[i-1]` instead of the raw pixel grid (frame 0
stays raw). Since most of RAM is unchanged between successive polls, the
delta is mostly zeros, which FFV1 compresses much further than the raw
grid. Extraction (`extract_frame_from_mkv`) reconstructs frame N by
cumulatively XOR-ing frames `0..N`. The same capture loop also does instant
hang detection: 3 consecutive identical raw frames (`np.array_equal`)
aborts the capture early instead of writing redundant frames.

I ran this against a real Alpine RISC-V boot (`qemu_capture_simple.py`,
`--max-frames 5`) and confirmed, end to end:

- QEMU booted, QMP paused/resumed/dumped memory 3 times before tripping the
  new hang detector (expected — see the truncation caveat below).
- `encode_mkv` wrote a real `/tmp/alpine_delta.mkv` (195,675 bytes).
- `decode_mkv` reconstructed the exact original 589,824-byte payload
  (overall MD5 hash matched; every FFV1 frame's per-chunk CRC32 verified).
- Splitting the decoded payload back into its 3 logical 196,608-byte
  snapshots showed frame 0 was genuine ELF-header memory content (same
  structure as the raw dump from the earlier manual QMP test) and frames 1
  and 2 decoded to exactly all-zero — correct, since the hang detector had
  flagged those as identical to their predecessor, so their XOR delta
  should be zero. The math checks out against real captured bytes, not
  just in isolation.
- The zero-delta frames compressed to identical, repeating FFV1 frame CRCs
  — the compression benefit is real, not just theoretical.

### Bug found and fixed along the way

`dense_encoder_video.py`'s `decode_mkv()` extracts the `manifest.json`
attachment via ffmpeg, but passed `-dump_attachment:t` and `0` as two
separate argv tokens; ffmpeg requires them combined as a single
`-dump_attachment:t:0`. This silently broke manifest recovery (metadata,
including `delta_encoding: xor`, was unrecoverable — `extract_frame_from_mkv`
would have crashed on `manifest['metadata']` being `None`). Pre-existing
bug, unrelated to today's delta-encoding work, but it sat directly in the
round-trip path this document recommends. Fixed by combining the flag into
one token; manifest metadata now recovers correctly.

### Why the hang detector tripped so fast

Not a bug — a direct consequence of the truncation limitation below. The
256×256 grid only samples the first ~192KB of the 512MB dump, which is
firmware/already-loaded kernel code — static once loaded, so 1-second polls
of that region legitimately look identical. Fixing the truncation (item 3
below) should also make hang detection meaningful again for a full boot,
since it would then be watching a representative slice of RAM instead of
just the static header region.

## Full-RAM tiling (VERIFIED end-to-end against a real boot)

To get past the ~192KB truncation limit, `qemu_to_mkv.py` now slices each
`dump-guest-memory` capture into fixed-size tiles (`--memory-width` /
`--memory-height`, default 512×512) instead of sampling only the first
grid's worth of bytes. Each tile keeps its own Hilbert mapping (spatial
locality preserved per-tile) and its own delta chain against the same tile
in the previous capture, so hang detection now requires *every* tile to be
unchanged, not just a single static header region. The Hilbert coordinate
computation is cached and vectorized (`_hilbert_cache` + NumPy fancy
indexing) instead of calling `hilbert_d2xy` per pixel in a Python loop —
necessary once tile counts run into the thousands.

I verified this two ways:

- **Synthetic, isolated**: fed known random bytes through the exact
  tiling+Hilbert forward mapping and the exact reverse mapping used by
  `extract_frame_from_mkv`, for both the raw (single-capture) and XOR-delta
  (multi-capture) cases. Byte-exact match both times — this validates the
  math independent of QEMU/ffmpeg flakiness.
- **Live**: captured 3 real tiles-per-frame snapshots from a 64MB Alpine
  RISC-V boot (`--memory-width 128 --memory-height 128`, 1367 tiles/capture)
  into a real MKV, then ran `--extract-frame 2` back through the full
  ffmpeg decode + manifest + per-frame CRC verification + cumulative-XOR
  reconstruction path. Output: 67,190,784 bytes reassembled, every FFV1
  frame CRC-verified, overall hash verified, and the final 64.1MB raw dump
  size matches `128×128×3×1367` exactly.

### Bugs found and fixed while getting there

1. **Same QMP event-desync bug as `qemu_capture_simple.py`, in the async
   client.** `QMPClient.execute()` read exactly one line and assumed it was
   the command's reply; an unsolicited event (e.g. RESUME after `cont()`)
   arriving first would desync every later read. Fixed by looping past
   `'event'` messages, mirroring the sync-client fix.
2. **Read-only dump file blocked every capture after the first.** QEMU
   writes `dump-guest-memory` output as mode `0400` (verified by inspecting
   a real dump file's permissions). The capture loop reused the same
   `guest_memory.dump` path every iteration without removing the previous
   (now-read-only) file, so QEMU's second `dump-guest-memory` call failed
   with `Permission denied` and silently truncated every run to 1 capture —
   this is the bug that would have quietly capped every tiled/delta run at
   a single frame, no matter how many were requested. Fixed by unlinking
   the stale dump file before each capture.

## What's left before the bigger claims are true

1. ~~Confirm `qemu_capture_simple.py` / `qemu_to_mkv.py` complete a full run
   producing a real (non-synthetic) `.mkv`, decode it back, and diff the
   result against the original dump byte-for-byte.~~ **Done** — see above.
2. Decide on and implement a real per-snapshot frame alignment so "frame N"
   has one consistent meaning instead of splitting mid-snapshot.
3. ~~Either raise the pixel grid size or tile across multiple frames so more
   than the first ~192KB of RAM is represented.~~ **Done** — see tiling
   section above. Not yet tried at the full 512MB / 512×512-tile scale
   (~683 tiles/capture) that would actually show "kernel decompression
   entropy waves" — only smoke-tested at 64MB / 128×128 tiles for speed.
4. ~~Feed a real capture into VAC3's Z=1 layer instead of the synthetic
   demo, combined with full-RAM tiling.~~ **Done** — see VAC3 section
   above.
