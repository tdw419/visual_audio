# Alpine Boot Trace — Software-to-Video Pipeline Verification

**Status**: VERIFIED — Capture and extraction both confirmed working (hash-verified round-trip, re-run 2026-08-15)

**Date**: 2026-08-15

## What Works

1. **QMP Memory Dump Captured**:
   - Alpine RISC-V booted with 64MB RAM
   - 3 capture snapshots before hang detection (expected — 256×256 only samples first ~192KB)
   - 64.1 MB dumps captured and Hilbert-mapped
   - FFV1 MKV encoding successful (1.31 MB)

2. **MKV Creation Verified**:
   ```
   /tmp/alpine_boot_trace.mkv (1.31 MB)
   - 3079 FFV1 RGB24 frames
   - 201,719,808 bytes total payload
   - Overall hash: e17dc0d79e6cfd759c3cb154d2f4babd
   - Compression ratio: 0.01x
   - Manifest.json attachment
   ```

3. **Frame Extraction Working**:
   ```
   /tmp/alpine_frame1.mem (65 MB)
   - Extracted from frame 1
   - Contains full 64MB memory dump
   ```

## Fixed (2026-08-15)

1. **Manifest Extraction** — was failing:
   - `dense_encoder` import fixed: `tools/dense_encoder_video.py` now inserts its own directory into `sys.path` instead of a nonexistent `src/` two levels up.
   - `ffmpeg -dump_attachment:t:0` was implicitly decoding the entire video stream before exiting; added `-map 0:v -c copy` so it dumps the manifest and exits without decoding payload frames.
   - Re-ran `decode_mkv()` directly against `/tmp/alpine_boot_trace.mkv`: manifest extracted (3079 frames, 201,719,808 bytes), all frames reassembled, overall hash verified (`e17dc0d79e6cfd759c3cb154d2f4babd`) matching the manifest.

2. **Hang Detection Trips Early** — mitigated:
   - `tools/qemu_to_mkv.py` defaults changed: `--interval` 10000→50000, `--memory-width`/`--memory-height` 512→1024, to sample beyond the static ~192KB firmware region on a 64MB dump.
   - Not yet re-validated against a live QEMU capture with these new defaults (see Next Steps).

## Remaining Gap

- The hang-detection/tiling fix above changes defaults but hasn't been exercised end-to-end against a fresh Alpine boot capture — only the extraction path was re-verified against the existing `/tmp/alpine_boot_trace.mkv`.

## Verification Commands

**Capture Alpine boot trace:**
```bash
python3 tools/qemu_to_mkv.py boot_images/alpine_riscv64.qcow2 \
    --arch riscv64 \
    --output /tmp/alpine_boot_trace.mkv \
    --interval 5000 \
    --max-frames 50 \
    --memory-width 256 \
    --memory-height 256 \
    --memory 64M
```

**Extract frame back to memory dump:**
```bash
python3 tools/qemu_to_mkv.py /tmp/alpine_boot_trace.mkv \
    --extract-frame 1 \
    --output /tmp/alpine_frame1.mem
```

**Verify extracted memory:**
```bash
file /tmp/alpine_frame1.mem
xxd /tmp/alpine_frame1.mem | head -20
```

## Next Steps

1. Re-run a fresh capture with the new 1024×1024/50000-interval defaults to confirm hang detection no longer trips early on real hardware.
2. Integrate trace into VAC3 container (Z=1 = RAM substrate, Z=0 = display)

## Comparison: Static Disk vs Boot Trace

| Aspect | Alpine MKV (disk) | Boot Trace (software-to-video) |
|--------|------------------|-------------------------------|
| Content | Rootfs disk image (17MB qcow2) | Execution state snapshots (64MB dumps) |
| Captured | Static storage | Dynamic memory over time |
| Frame meaning | N/A | Memory state at capture point |
| Can boot? | NO (needs kernel+firmware) | YES (temporal trace of boot) |
| Verified | FALSE (unverified claim) | VERIFIED (capture + hash-verified extraction) |

---

**Software-to-video pipeline is operational for Alpine RISC-V boot capture.** The QMP dump-guest-memory primitive works, Hilbert mapping preserves spatial locality, FFV1 encoding is lossless, and round-trip extraction is hash-verified. The hang-detection/tiling defaults were updated but not yet re-validated against a fresh capture.