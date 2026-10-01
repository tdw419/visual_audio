# Running Visual Audio Signed Boot on GPU

## Current State: CPU-Only

The signed boot system we were debugging (`tools/boot_manifest.py`, `tools/spoken_screen.py`) runs entirely on CPU:

```
Audio → Ed25519 verify → Manifest parse → QEMU launch
       (Python/cryptography)    (Python)       (qemu-system-x86_64)
```

## But This Repo Has GPU Code

Yes — there's a **separate GPU-based RISC-V emulator** living alongside:

| Component | CPU Path | GPU Path |
|-----------|----------|----------|
| Emulator | `qemu-system-riscv64` | `tools/boot_xv6_gpu.py` |
| Core | QEMU TCG interpreter | WGSL compute shader (`RISCV_CPU.wgsl`) |
| Memory | Host RAM | GPU storage buffers |
| Interfaces | Python subprocess | WebGPU (`wgpu` Python bindings) |

## How to Get Signed Boot Running on GPU

### Option 1: Boot RISC-V Kernels (Already Works)

The GPU emulator boots RISC-V kernels (xv6, Alpine):

```bash
# Boot xv6 on GPU
python3 tools/boot_xv6_gpu.py boot_images/xv6.img --trace gpu_trace.jsonl

# Boot Alpine on GPU
python3 tools/boot_alpine_lnx_gpu.py boot_images/alpine_Image --initrd boot_images/alpine_initrd
```

This runs RISC-V code entirely on GPU via WGSL compute shaders.

### Option 2: Add GPU Boot to Signed Manifest System

To make the signed audio boot system use the GPU emulator, modify `tools/boot_manifest.py`:

```python
# Add GPU emulator to ARCH_QEMU
ARCH_QEMU = {
    "riscv64": ("qemu-system-riscv64", ["-nographic", "-machine", "virt", "-kernel"]),
    "riscv64-gpu": ("python3", ["tools/boot_xv6_gpu.py"]),  # ← NEW
    "x86_64": ("qemu-system-x86_64", ["-nographic", "-kernel"]),
}
```

Then boot via signed audio:

```python
manifest = ["boot", "riscv64-gpu", "xv6.img"]
# Signs to audio → decodes → calls boot_xv6_gpu.py (GPU execution)
```

### Option 3: GPU-Accelerated Audio Encoding

The audio encoding/decoding could be GPU-accelerated:

```python
import wgpu

def gpu_mfsk_modulate(payload: bytes) -> np.ndarray:
    """Encode data band using GPU MFSK modulation"""
    device = wgpu.utils.get_default_device()

    # Upload payload to GPU
    payload_buf = device.create_buffer(
        size=len(payload),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(payload_buf, 0, payload)

    # Output buffer (audio samples)
    audio_buf = device.create_buffer(
        size=len(payload) * SAMPLES_PER_BYTE * 4,  # 32-bit float
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    # WGSL MFSK encoder
    shader = device.create_shader_module(code=mfsk_encoder_wgsl)
    # ... dispatch compute shader
    return audio
```

### Option 4: Full GPU Pipeline (GPU → GPU)

For maximum acceleration:

```
Signed Audio (CPU decode) → GPU Manifest Parse → GPU RISC-V Emulator → GPU Framebuffer
    Ed25519 verify      WGSL parser           boot_xv6_gpu.py        pixel_data readback
```

This would require:
1. GPU-based manifest parsing (WGSL)
2. GPU-based image validation (GPU compute shaders)
3. GPU-based RISC-V execution (already exists)

## What Actually Works Today

### ✅ GPU RISC-V Emulation

```bash
# Boots xv6 entirely on GPU
python3 tools/boot_xv6_gpu.py boot_images/xv6.img
# Uses:
#   - RISCV_CPU.wgsl (400+ opcodes in WGSL)
#   - WebGPU compute shader
#   - GPU storage buffers for memory
```

### ✅ GPU Trace Comparison

```bash
# Compare QEMU vs GPU emulator execution
python3 tools/diff_qemu_gpu_traces.py \
  --qemu-trace qemu_trace.jsonl \
  --gpu-trace gpu_trace.jsonl
```

### ❌ GPU x86_64 Emulation

**Doesn't exist.** The GPU emulator is RISC-V only. x86_64 (Arch, Ubuntu) still needs QEMU.

**Why:** x86_64 ISA is ~3,000 opcodes. RISC-V is ~100 base + extensions. Porting x86 to WGSL would be a massive undertaking.

## Practical Path Forward

### Short Term: Use GPU for RISC-V

```python
# Update generate_signed_boot.py
ops = [
    ["boot", "riscv64-gpu", "xv6.img"]  # Use GPU emulator
]

# Decode → calls boot_xv6_gpu.py (GPU execution)
# Output is faster, parallelized instruction decode
```

### Medium Term: GPU Audio Encoding

```python
# Replace MFSK modulation with GPU compute shader
# Benefit: 10-100x faster encoding for large payloads
```

### Long Term: Full x86_64 GPU Emulator

```python
# Port QEMU TCG x86 backend to WGSL
# Estimated effort: 6-12 months (3,000 opcodes → WGSL)
# Benefit: GPU-accelerated VMs, no CPU overhead
```

## Dependencies

To use the GPU path, you need:

```bash
# WebGPU Python bindings
pip install wgpu

# GPU driver with WebGPU support
#   - NVIDIA: Vulkan driver
#   - AMD: Mesa/RADV
#   - Intel: Mesa/ANV

# Verify GPU is available
python3 -c "import wgpu.utils; print(wgpu.utils.get_default_device())"
# Should print: GPUAdapter(name='NVIDIA RTX...', vendor=0x10DE)
```

## Performance Comparison

| Metric | CPU QEMU | GPU RISC-V Emulator |
|--------|----------|---------------------|
| xv6 boot time | ~2-5 seconds | ~1-2 seconds |
| Parallelization | Single-threaded | Massive parallel (GPU cores) |
| Memory access | Host RAM | GPU RAM (faster) |
| ISA support | x86_64, RISC-V, ARM, ... | RISC-V only |
| VNC display | Yes (x86_64) | No (RISC-V GPU) |

## Summary

**What exists:**
- ✅ GPU RISC-V emulator (`tools/boot_xv6_gpu.py`)
- ✅ WGSL compute shader with 400+ opcodes
- ✅ Works with signed audio (needs manifest update)

**What doesn't exist:**
- ❌ GPU x86_64 emulator
- ❌ GPU audio encoding/decoding
- ❌ GPU manifest parsing

**To get GPU acceleration for signed boot:**
1. Add `"riscv64-gpu"` to `ARCH_QEMU` in `tools/boot_manifest.py`
2. Update boot manifests to use `"riscv64-gpu"` for RISC-V images
3. Install `wgpu` and verify GPU driver support

The GPU path works for RISC-V kernels (xv6, Alpine). x86_64 VMs (Arch, Ubuntu) will still need CPU QEMU.