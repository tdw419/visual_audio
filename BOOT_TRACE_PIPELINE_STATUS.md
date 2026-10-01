# Boot Trace Pipeline — Status Report

**Date**: 2026-08-15
**Status**: VERIFIED OPERATIONAL

## What Works (Verified)

### 1. QMP Memory Dump Pipeline
- QEMU boot with ELF64 kernels (hello.img)
- QMP socket connection with exponential backoff retry
- `dump-guest-memory` → full RAM snapshots
- Hilbert curve mapping → pixel grids
- FFV1 lossless encoding → MKV containers
- Hash-verified round-trip integrity

**Artifacts:**
- `/tmp/hello_boot_trace.mkv` (1.4 MB) — 3 captures, 22 tiles each, 64MB/capture
- `/tmp/hello_frame0.mem` (66 MB) — Extracted frame 0
- Overall hash: `48f43c3f2604209ee08c86903242fb77`

### 2. Kernel Image Verification
```
hello.img:
- Type: ELF64 RISC-V executable
- Entry point: 0x80200000
- Code sections: .text (starts at offset 0)
- Instructions verified via riscv64-unknown-elf-objdump

First instructions at 0x80200000:
  80200000: auipc sp,0x2
  80200004: mv sp,sp
  80200008: jal 80200014 <kmain>

Function kmain (0x80200014):
  SBI call to print "Hello from..."
  Waits in hang loop
```

### 3. Fixed Bugs

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Interval scaling | `sleep(0.1)` hardcoded | `interval * 1e-5` scaling |
| Alpine no boot | PE32+ EFI format (not ELF64) | Documented limitation, uses EDK2/UEFI |
| xv6 no boot | Load address 0x80000000 overlaps OpenSBI | Linker fix needed (use 0x80200000) |
| Duplicate disk param | Kernel file added as disk | Deduplication check |
| QMP connection flaky | Socket race condition | Exponential backoff retry |

## What DOES NOT Work

### Alpine RISC-V Boot
- Kernel format: PE32+ EFI (not ELF64)
- Required firmware: EDK2/UEFI stack
- Symptoms: OpenSBI loads, ignores kernel
- Status: BLOCKED — requires firmware integration

### xv6.img Boot
- Load address: 0x80000000 (overlaps OpenSBI at 0x80000000-0x8004180)
- QEMU error: "Some ROM regions are overlapping"
- Fix: Rebuild with linker address 0x80200000

### Disassembly Overlay
- Challenge: Reverse Hilbert mapping to get linear RAM bytes
- Status: Blocked on coordinate transformation complexity
- Alternative: Disassemble from original hello.img file, not captured frames

## Two Tracks, Not One

**Track 1: Boot Trace Visualization (Working)**
- Capture: hello.img → Hilbert → FFV1 → MKV ✅
- Extract: MKV frame → memory dump → QEMU resume ✅
- Use: Checkpoint/replay, debugging, temporal navigation
- Next: Add simple timestamp/capture annotations

**Track 2: Spatial Assembly VM (.glyph)**
- From-scratch interpreter: shapes ARE opcodes ✅
- GPU compute shader: deterministic execution ✅
- ASCII World: 2D spatial programming language ✅
- Next: VAC3 container integration

## Conflated Claims (Clarified)

**False equivalency flagged:**
- "MKV file is the computer" — NO. FFV1 has no execution semantics. QEMU still runs.
- "GPU blits shapes and executes" — NO. Requires a .glyph interpreter. Shapes don't magically run RISC-V.
- "Drawing boxes around Alpine makes it GPU-native" — NO. Cosmetic rendering, still needs emulator.

**Grounded reality:**
- MKV = storage/visualization format (not execution substrate)
- VCC compliance = GPU memory region hashes preserved (not native execution)
- Disassembly overlay = visualization aid (not compiler)

## Next Concrete Steps

### Immediate (doable now)
1. Add capture timestamps/sequence numbers to MKV metadata
2. Generate a trace comparison video (frame 0 vs frame 1 vs frame 2)
3. Document the verified hello.img boot trace pattern

### Short-term
1. Rebuild xv6.img at 0x80200000 (fix OpenSBI overlap)
2. Create simple delta heatmap (showing which RAM regions changed)
3. Integrate hello.img trace into VAC3 (Z=1 = RAM substrate)

### Long-term (separate project)
1. EDK2/UEFI firmware for Alpine boot traces
2. Disassembly overlay with reverse Hilbert mapping
3. .glyph VM with visual debugging

## Verification Commands

Capture hello.img trace:
```bash
python3 tools/qemu_to_mkv.py boot_images/hello.img \
  --arch riscv64 \
  --output /tmp/hello_boot_trace.mkv \
  --interval 100000 \
  --max-frames 10 \
  --memory 64M
```

Verify MKV integrity:
```bash
python3 tools/qemu_to_mkv.py /tmp/hello_boot_trace.mkv \
  --extract-frame 0 \
  --output /tmp/hello_frame0.mem
```

Disassemble hello.img directly:
```bash
riscv64-unknown-elf-objdump -d boot_images/hello.img | head -30
```

## Summary

The boot trace pipeline is VERIFIED OPERATIONAL for ELF64 RISC-V kernels. hello.img boots, captures, extracts, and round-trips correctly. Alpine is blocked by kernel format (PE32+ EFI). xv6 needs linker fix. Disassembly overlay is complex but not critical for the core checkpoint/replay functionality.

We have successfully converted execution time into spatial video dimensions and proved it can be rewound and extracted bit-for-bit. That's the proof-of-concept for Hyper-Dimensional Video Boot.