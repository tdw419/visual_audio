# Visual Audio Pixel Programs Library

**Container**: `visual_audio.mkv` (2.0MB, 157 frames, 133 entries)
**Role**: `programs/` — All pixel-native software in one file
**Status**: All verified (CRC32 + sha256)

---

## Complete Programs Inventory

### Pixel OS & LM
- `pixel_os_listener.py` (20,357 bytes) — Listener daemon for pixel LM input
- `pixel_os_output.py` (2,939 bytes) — Pixel OS output channel
- `pixel_lm_generate.py` (14,668 bytes) — Generate pixel programs via LLM
- `pixel_lm_generate_placeholder.py` (2,064 bytes) — Placeholder generator
- `train_pixel_lm.py` (23,800 bytes) — Train pixel LM models
- `build_pixel_corpus.py` (718 bytes) — Build pixel training corpus
- `pixel_screen.py` (11,015 bytes) — Pixel display and interaction

### Dense Encoding (3 bytes/pixel)
- `dense_encoder.py` (10,775 bytes) — Core dense codec
- `dense_encoder_multitile.py` (11,226 bytes) — Multi-tile dense encoding
- `dense_encoder_sandbox.py` (10,562 bytes) — Sandboxed dense encoding
- `dense_encoder_video.py` (20,352 bytes) — Video-based dense encoding

### Binary/Pixel Conversion
- `bin_to_pixels.py` (1,056 bytes) — Binary to pixel grid
- `elf_to_pixel_loader.py` (16,708 bytes) — ELF loader to pixel format

### Glyph ISA (Spatial Instruction Set)
- `glyph_isa_v2.py` (24,278 bytes) — Glyph ISA v2 implementation
- `glyph_isa_ecc.py` (7,058 bytes) — Error correction for glyphs
- `glyph_isa_ecc_demo.py` (2,908 bytes) — ECC demo
- `glyph_atomic_emulator.py` (6,342 bytes) — Atomic emulator

### Spatial Systems
- `spatial_compiler.py` (16,214 bytes) — Spatial circuit compiler
- `spatial_compiler_new.py` (5,525 bytes) — New spatial compiler
- `spatial_vm.py` (12,107 bytes) — Spatial virtual machine
- `spatial_os_kernel.py` (10,038 bytes) — Spatial OS kernel
- `spatial_os_kernel_3d.py` (17,317 bytes) — 3D spatial OS kernel

### Geometry OS Integration
- `geos_pixel_software.json` (1,729 bytes) — GeOS pixel software spec

---

## Usage

### List all programs
```bash
python3 tools/va_container.py ls visual_audio.mkv | grep "programs"
```

### Extract and run a program
```bash
python3 tools/va_container.py cat visual_audio.mkv pixel_os_listener -o /tmp/listener.py
python3 /tmp/listener.py
```

### Verify container integrity
```bash
python3 tools/va_container.py verify visual_audio.mkv
# Output: all 133 entries verified (CRC32 + sha256)
```

### Add new program
```bash
python3 tools/va_container.py add visual_audio.mkv new_program.py --role programs --name new_program
```

---

## Container Structure Summary

```
visual_audio.mkv (2.0MB, 157 frames)
├── bootstrap/     — Self-hosting tools (va_container.py, dense_encoder.py)
├── spec/          — Architecture specs (ROADMAP, 485 research)
├── codec/         — Codec tables (phonemes, MFSK)
├── state/         — Global state registers
├── cache/         — Voicebook allocation bitmap
├── content/       — Test content and demos
├── engine/        — World generation engine
├── programs/      — All pixel software (22 entries, 283KB)
├── test/          — Test suites
└── analysis/      — Audit and analysis reports
```

---

**Generated**: 2026-07-24
**Total Programs**: 22
**Total Program Bytes**: ~283KB