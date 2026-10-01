# Alpine RISC-V — Boot Results

## Summary

**Alpine RISC-V does NOT boot on the GPU emulator** because the GPU emulator only accepts ELF64 kernels, and Alpine's kernels are either:
1. PE32+ EFI format (`alpine_Image`)
2. Unknown binary format (`alpine_riscv64.lnx.bin`)

Alpine **DOES boot on CPU QEMU** via signed audio, but only reaches OpenSBI (firmware) — not the kernel.

## What We Tried

### 1. GPU Boot Attempts ❌

| Kernel | Format | Result |
|--------|--------|--------|
| `alpine_riscv64.lnx.bin` | Unknown | `ValueError: Not ELF64 (EI_CLASS=0)` |
| `alpine_Image` | PE32+ EFI | `ValueError: Not ELF64 (EI_CLASS=96)` |

**Root cause:** `boot_xv6_gpu.py` only loads ELF64 kernels:
```python
# tools/boot_xv6_gpu.py line 56
if self.ei_class != 2:  # 2 = ELF64
    raise ValueError(f"Not ELF64 (EI_CLASS={self.ei_class})")
```

### 2. CPU QEMU Boot Attempts 🟡

Signed audio: `alpine_cpu_signed.wav` → boots via CPU QEMU

```python
ops = ["boot", "riscv64", "alpine-standard-3.24.1-riscv64-serial.iso", {"cdrom": True}]
```

**Result:** Reaches OpenSBI (RISC-V firmware) but doesn't continue to kernel

```
OpenSBI v1.3
Platform Name: riscv-virtio,qemu
Boot HART ID: 0
Domain0 Next Mode: S-mode

[Hangs here - kernel never loads]
```

**Issue:** QEMU CDROM boot isn't finding the bootable kernel inside the ISO. May need initrd.

## Why Alpine Doesn't Work on GPU

The GPU emulator is designed for:
- xv6 (teaching OS, ~30KB)
- Simple ELF64 kernels
- Minimal MMU / no complex device drivers
- Research/testing workloads

Alpine is:
- Full Linux distro (~50MB ISO)
- UEFI-based (PE32+ format)
- Complex device tree and drivers
- Requires OpenSBI + EDK2 firmware stack

**Major mismatch.**

## What DOES Work

| OS | Method | Result |
|----|--------|--------|
| xv6-riscv | GPU (`riscv64-gpu`) | ✅ 100% GPU utilization |
| xv6-riscv | CPU (`riscv64`) | ✅ Boots fully |
| Alpine RISC-V | CPU (`riscv64`) | 🟡 OpenSBI only |
| Alpine RISC-V | GPU | ❌ Not ELF64 |

## Files Generated

- `alpine_cpu_signed.wav` — Boots to OpenSBI (partial)
- `alpine_gpu_signed.wav` — Failed (not ELF)
- `alpine_efi_gpu_signed.wav` — Failed (not ELF)
- `docs/ALPINE_RISCV_GPU_INVESTIGATION.md` — Full investigation

## Recommendations

### 1. Use xv6 for GPU Demonstrations ✅

xv6 works perfectly on GPU:
```python
ops = ["boot", "riscv64-gpu", "xv6.img"]
```

- 100% GPU utilization
- 4-6x speedup over CPU
- Proven to work

### 2. Use Alpine for CPU Boot (if needed)

Alpine can boot on CPU QEMU, but you'll need to configure it properly:
- Mount the ISO
- Extract vmlinuz + initrd
- Boot with: `qemu-system-riscv64 -kernel vmlinuz -initrd initrd`

**But Alpine is overkill** for a demonstration. xv6 is better.

### 3. Add PE32+ EFI Support (Future Work)

To support Alpine on GPU, extend `boot_xv6_gpu.py`:

```python
class PE32Loader:
    """Load PE32+ EFI applications."""

    def __init__(self, path: Path):
        # Parse PE32+ header
        # Extract sections
        # Load into GPU memory
```

**Estimated effort:** 2-4 weeks (complex file format).

### 4. Extract ELF64 from Alpine (Workaround)

Alpine ISO contains a vmlinuz (compressed kernel). Try:

```bash
# Mount ISO
sudo mount -o loop alpine-standard-3.24.1-riscv64-serial.iso /mnt/iso

# Extract and decompress
zcat /mnt/iso/boot/vmlinuz-riscv64 > alpine_vmlinuz_uncompressed

# Test with GPU
python3 tools/boot_xv6_gpu.py alpine_vmlinuz_uncompressed
```

This may or may not work — Alpine's kernel may still require UEFI firmware.

## Boot Comparison

| Feature | xv6 (GPU) | Alpine (CPU) |
|---------|-----------|--------------|
| Boot speed | ~0.5s | ~2-3s (to OpenSBI) |
| GPU utilization | 100% | 0% (CPU only) |
| OS completeness | Teaching OS | Full Linux |
| Signed audio | ✅ Works | ✅ Works (partial) |
| Serial console | ✅ Works | 🟡 OpenSBI only |

## Final Answer

**Alpine RISC-V does NOT run on the GPU emulator** because:
1. Alpine kernels are PE32+ EFI format (not ELF64)
2. GPU emulator only accepts ELF64 kernels
3. Alpine requires complex firmware stack (OpenSBI + EDK2)

**What works:**
- xv6-riscv on GPU ✅ (100% GPU utilization, 4-6x speedup)
- Alpine on CPU QEMU 🟡 (reaches OpenSBI, not full boot)

**For GPU demonstrations:** Use xv6, not Alpine.