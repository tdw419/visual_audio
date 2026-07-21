# Vendor Source: xv6-riscv for GPU Emulator

## Why This Exists

The xv6-riscv kernel running on the GPU emulator requires specific build configurations that differ from upstream:

1. **No C Extension** - The WGSL shader implements RV64IMA only. Compressed 16-bit instructions are not supported.
2. **16MB Memory Limit** - GPU memory constraints require a smaller PHYSTOP.

## Directory Structure

```
vendor/xv6-riscv/
├── README.md           # This file
├── build.sh           # Automated clone + patch + build script
└── patches/           # Diffs against upstream
    ├── 0001-reduce-phystop-to-16mb.patch
    └── 0002-remove-c-extension.patch
```

## Building from Scratch

```bash
cd vendor/xv6-riscv
./build.sh
```

This will:
1. Clone upstream xv6-riscv to `/tmp/xv6-riscv`
2. Apply the patches
3. Build the kernel

The kernel binary will be at `/tmp/xv6-riscv/kernel/kernel`.

## Running on GPU

From the visual_audio project root:

```bash
python3 tools/boot_xv6_gpu.py /tmp/xv6-riscv/kernel/kernel
```

## Version

Based on MIT xv6-riscv (commit: upstream master, 2024)

## See Also

- The patches in `patches/` document exactly what's changed
- `tools/boot_xv6_gpu.py` - GPU boot harness
- `tools/RISCV_CPU_MMU.wgsl` - GPU-native RISC-V emulator