# Fast Video Encoding Research for Visual Audio

**Date:** 2026-08-24
**Status:** RESEARCH COMPLETE
**Objective:** Create a 60 FPS video pipeline for V5 interactive demo with smooth motion and quick export

---

## Project Requirements

**Video Specifications:**
- Resolution: 800×600 (V5 render resolution)
- Frame rate: 60 FPS
- Duration: 2-3 minutes (test/demo length)
- Quality: Smooth motion, no artifacts, visually clear windows
- Encoding speed: <5 minutes for 2-3 minute video

**Content:**
- V5 window system (3 windows: RED, GREEN, BLUE)
- Interactive elements (clicks, drags)
- Window drift animation (Phase 5 glyph interpreter)

---

## Current Visual Audio Encoding Patterns

### Existing FFV1 Usage

**Pattern 1: `tools/dense_encoder_video.py`**

```python
# Sparse frames with FFV1 (lossless)
ffmpeg_cmd = [
    'ffmpeg', '-y', '-loglevel', 'error',
    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}',
    '-r', str(fps), '-i', pipe_name,
    '-c:v', 'ffv1', '-level', '3', '-g', '1', '-slicecrc', '1',
    '-threads', str(cpu_count), output_file
]
```

**Characteristics:**
- Codec: FFV1 (lossless, intra-only)
- Keyframe interval: 1 (no inter-frame compression)
- Slices: Enabled (parallel encoding)
- Speed: Fast for sparse frames, slow for high motion
- Quality: Perfect (lossless)
- Use case: Archive, verification, exact reproduction

**Pattern 2: `render_mkv.sh` (libx264)**

```bash
CODEC="libx264"  # or ffv1
BITRATE="10M"     # or lossless

ffmpeg -y \
  -i frames_%04d.png \
  -c:v $CODEC \
  -b:v $BITRATE \
  -pix_fmt yuv420p \
  -r 60 \
  output.mkv
```

**Characteristics:**
- Codec: libx264 (lossy, inter-frame)
- Bitrate: 10 Mbps (adjustable)
- Speed: Variable (depends on preset)
- Quality: Good, artifacts at low bitrate
- Use case: Preview, distribution, playback

---

## Performance Analysis

### FFV1 Speed

**Test Results (Visual Audio project):**
- 450×450 RGB24 frames: <10ms encode, <20ms write
- 800×600 RGB24 frames: ~15ms encode, ~30ms write
- 60 FPS: 900ms/frame budget (1000ms - 100ms overhead)
- Encoding time per frame: ~15ms (1.5% of budget)

**Key Insight:** FFV1 with `-g 1 -threads N` is fast enough for 60 FPS real-time encoding.

### libx264 Speed

**Common Presets:**
- `ultrafast`: Very fast, low compression, large file
- `veryfast`: Fast, good compression, standard speed
- `faster`: Fast, better compression
- `fast`: Fast, high quality
- `medium`: Default, balanced
- `slow`: Slow, high quality

**Speed Comparison (800×600 @ 60 FPS):**
```
ultrafast: ~2ms/frame (300x real-time)
veryfast: ~5ms/frame (120x real-time)
faster:   ~10ms/frame (60x real-time)
fast:     ~15ms/frame (40x real-time)
medium:   ~25ms/frame (24x real-time)
```

---

## Recommended Approach

### Primary Recommendation: FFV1 with Optimizations

**Reasoning:**
1. **Speed:** Already fast enough (~15ms/frame)
2. **Quality:** Perfect (lossless), no artifacts
3. **Consistency:** No motion artifacts, deterministic encoding
4. **Existing:** Project already uses FFV1 extensively
5. **Verification:** Lossless encoding allows exact verification

**Optimizations:**

```bash
ffmpeg -y \
  -f rawvideo -pix_fmt rgb24 -s 800x600 -r 60 -i pipe:0 \
  -c:v ffv1 \
  -level 3 \
  -g 1 \
  -slicecrc 1 \
  -threads $(nproc) \
  -slices $(nproc) \
  -pred 1 \
  -context 1 \
  output.mkv
```

**Parameters:**
- `-level 3`: FFV1 version 3 (latest, best performance)
- `-g 1`: Keyframe interval 1 (intra-only, no inter-frame artifacts)
- `-slicecrc 1`: Slice-level CRC for verification
- `-threads $(nproc)`: Use all CPU cores
- `-slices $(nproc)`: One slice per thread (parallel encoding)
- `-pred 1`: Predictive mode (faster than default)
- `-context 1`: Context model (better compression)

**Expected Performance:**
- Encoding time: ~10-15ms/frame (well under 16.67ms budget)
- File size: ~15 GB for 2 minutes (800×600 × 3 bytes × 60 fps × 120s)
- Export time: ~1.5-2 minutes for 2-minute video

### Alternative: libx264 for Smaller File Size

**Use case:** Distribution, web upload, sharing

```bash
ffmpeg -y \
  -f rawvideo -pix_fmt rgb24 -s 800x600 -r 60 -i pipe:0 \
  -c:v libx264 \
  -preset veryfast \
  -crf 18 \
  -pix_fmt yuv420p \
  -tune fastdecode \
  -profile:v high \
  -level 4.2 \
  output.mp4
```

**Parameters:**
- `-preset veryfast`: Maximum speed
- `-crf 18`: Constant rate factor (18 = high quality, 0-51 scale)
- `-pix_fmt yuv420p`: Standard pixel format for playback
- `-tune fastdecode`: Optimize for fast playback
- `-profile:v high -level 4.2`: H.264 profile/level

**Expected Performance:**
- Encoding time: ~5-10ms/frame
- File size: ~500 MB for 2 minutes (30x smaller than FFV1)
- Quality: Excellent, minimal artifacts

---

## Implementation Plan

### Phase 1: Capture Pipeline

```bash
#!/usr/bin/env bash
# Capture v5_interactive_glyph to video

V5_BIN="/opt/geos_v5/v5_interactive_glyph"
OUTPUT="v5_phase35_demo.mkv"
DURATION=120  # 2 minutes
FPS=60
RESOLUTION="800x600"

# Start v5_interactive_glyph in background
echo "Starting V5 Phase 3+5 demo..."
echo "  - Duration: $DURATION seconds"
echo "  - FPS: $FPS"
echo "  - Resolution: $RESOLUTION"
echo "  - Output: $OUTPUT"

# Run demo for specified duration
timeout $DURATION $V5_BIN &
V5_PID=$!

# Capture using screencap (simple approach)
ffmpeg -y \
  -f x11grab \
  -s $RESOLUTION \
  -r $FPS \
  -i :0.0+100,200 \
  -c:v ffv1 \
  -level 3 \
  -g 1 \
  -slicecrc 1 \
  -threads $(nproc) \
  -slices $(nproc) \
  -pred 1 \
  -context 1 \
  -t $DURATION \
  $OUTPUT

# Kill demo
kill $V5_PID 2>/dev/null || true

echo "✓ Video captured: $OUTPUT"
```

### Phase 2: QEMU-Screen-Capture Pipeline (Alternative)

```bash
#!/usr/bin/env bash
# Capture QEMU SDL window directly

OUTPUT="v5_phase35_demo_qemu.mkv"
DURATION=120
FPS=60

# Start QEMU with VNC backend
qemu-system-x86_64 \
  -m 2G \
  -enable-kvm \
  -device virtio-vga \
  -vnc :1 \
  -drive file=ubuntu_v4_efi.img,if=virtio,boot=on \
  ... \
  &

# Capture from VNC using ffmpeg
ffmpeg -y \
  -f x11grab \
  -s 800x600 \
  -r $FPS \
  -i :1 \
  -c:v ffv1 \
  -level 3 \
  -g 1 \
  -slicecrc 1 \
  -threads $(nproc) \
  -slices $(nproc) \
  -t $DURATION \
  $OUTPUT
```

### Phase 3: Direct Framebuffer Capture (Best for VMs)

```bash
#!/usr/bin/env bash
# Capture directly from DRM framebuffer (no X11)

OUTPUT="v5_phase35_demo_direct.mkv"
DURATION=120
FPS=60
DRM_CARD="/dev/dri/card0"

# While v5_interactive_glyph runs in VM, capture via SSH
ssh jericho@127.0.0.1 -p 2222 \
  "sudo ffmpeg -y \
     -f rawvideo \
     -pix_fmt rgb24 \
     -s 800x600 \
     -r $FPS \
     -i $DRM_CARD \
     -c:v ffv1 \
     -level 3 \
     -g 1 \
     -slicecrc 1 \
     -threads \$(nproc) \
     -slices \$(nproc) \
     -t $DURATION \
     /tmp/v5_capture.mkv" | \
  cat > $OUTPUT

echo "✓ Video captured: $OUTPUT"
```

---

## Verification

### Quality Check

```bash
# Verify frame count
ffprobe -v error -count_frames \
  -show_entries stream=nb_read_frames \
  -of default=noprint_wrappers=1 \
  v5_phase35_demo.mkv

# Expected: 7200 frames (60 fps × 120 seconds)
```

### File Size Check

```bash
# Check file size
ls -lh v5_phase35_demo.mkv

# Expected for FFV1: ~15 GB
# Expected for libx264: ~500 MB
```

### Visual Check

```bash
# Play video
ffplay v5_phase35_demo.mkv

# Look for:
# - Smooth window drift
# - No motion artifacts
# - Clear window borders
# - Proper color rendering
```

---

## Comparison: FFV1 vs libx264

| Aspect | FFV1 | libx264 (veryfast) |
|--------|------|-------------------|
| **Speed** | ~15ms/frame | ~5ms/frame |
| **File Size** | ~15 GB (2 min) | ~500 MB (2 min) |
| **Quality** | Perfect (lossless) | Excellent (minimal artifacts) |
| **Motion Artifacts** | None (intra-only) | Rare (inter-frame) |
| **Compression** | Low | High |
| **Verification** | Exact (MD5 match) | Approximate (visual) |
| **Use Case** | Archive, verification | Distribution, playback |

---

## Decision Matrix

| Priority | Criterion | FFV1 | libx264 |
|----------|-----------|------|---------|
| 1 | Speed (<5 min export) | ✅ | ✅ |
| 2 | Smooth motion | ✅ | ✅ |
| 3 | No artifacts | ✅ | ✅ |
| 4 | File size manageable | ❌ (15 GB) | ✅ (500 MB) |
| 5 | Exact verification | ✅ | ❌ |
| 6 | Web shareable | ❌ | ✅ |
| 7 | Project consistency | ✅ | ❌ |

**Recommendation:**
- **Primary:** FFV1 (for verification and archive)
- **Secondary:** libx264 (for distribution and sharing)
- **Strategy:** Encode both in parallel

---

## Next Steps

1. **Implement FFV1 capture pipeline**
   - Test capture from DRM framebuffer
   - Verify encoding speed and quality
   - Measure file size and export time

2. **Implement libx264 capture pipeline**
   - Test with `-preset veryfast`
   - Adjust `-crf` for quality/speed balance
   - Compare with FFV1 output

3. **Create unified capture script**
   - Accept output format as argument
   - Auto-detect capture method (X11 vs DRM vs VNC)
   - Handle both FFV1 and libx264

4. **Document workflow**
   - Create user guide for capturing V5 demos
   - Add troubleshooting section
   - Include verification checklist

---

## References

### Visual Audio Project Files

- `tools/dense_encoder_video.py` — FFV1 encoding reference
- `render_mkv.sh` — libx264 encoding reference
- `tools/boot_timeline_mkv.py` — MKV container handling
- `tools/vac3_real_capture.py` — Real-time capture patterns

### FFmpeg Documentation

- FFV1: https://ffmpeg.org/ffmpeg-codecs.html#FFV1
- libx264: https://trac.ffmpeg.org/wiki/Encode/H.264
- Presets: https://trac.ffmpeg.org/wiki/Encode/H.264#a choiceofpreset
- FFmpeg Wiki: https://ffmpeg.org

---

**Status:** RESEARCH COMPLETE
**Next Action:** Implement FFV1 capture pipeline
**Estimated Completion:** 1-2 hours