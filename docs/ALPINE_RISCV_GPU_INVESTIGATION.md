# Alpine RISC-V on GPU — Investigation Results

## Attempted Kernels

| Kernel | Type | GPU Result | CPU Result |
|--------|------|------------|------------|
| `alpine_riscv64.lnx.bin` | Unknown (not ELF, not PE32+) | ❌ Not ELF (EI_CLASS=0) | ❌ No output |
| `alpine_Image` | PE32+ EFI application | ❌ Not ELF (EI_CLASS=96) | ✅ Boots to OpenSBI |
| `alpine_vmlinuz` | Unknown | Not tested | Not tested |
| `alpine-standard-3.24.1-riscv64-serial.iso` | ISO | Not tested | ✅ Boots to OpenSBI |

## The Problem

**GPU emulator (`boot_xv6_gpu.py`) only accepts ELF64 kernels.**

It uses a custom `ELF64Loader` class that expects a standard ELF64 header:
```python
# tools/boot_xv6_gpu.py line 56
if self.ei_class != 2:  # 2 = ELF64
    raise ValueError(f"Not ELF64 (EI_CLASS={self.ei_class})")
```

## Alpine Kernel Formats

### `alpine_Image` (PE32+ EFI)
```
file boot_images/alpine_Image:
  PE32+ executable (EFI application) RISC-V 64-bit (stripped to external PDB)
```

This is a UEFI bootloader, not a raw ELF kernel. It needs:
- UEFI firmware (EDK2)
- EFI stub loader
- ACPI tables

### `alpine_riscv64.lnx.bin` (Unknown format)
```
file boot_images/alpine_riscv64.lnx.bin:
  data (no recognizable header)
```

This appears to be a binary blob, possibly:
- Extracted from the ISO
- Custom kernel image
- Legacy boot format

### `alpine_vmlinuz` (Unknown)
```
file boot_images/alpine_vmlinuz:
  [not checked yet]
```

Most likely a vmlinuz (compressed kernel), which may need decompression.

## CPU QEMU Works

Alpine boots successfully on CPU QEMU with ISO:
```
qemu-system-riscv64 -machine virt -cdrom alpine-standard-3.24.1-riscv64-serial.iso

Output:
  OpenSBI v1.3
  Platform Name: riscv-virtio,qemu
  Boot HART ID: 0
  Domain0 Next Mode: S-mode
  ✓ Boot to OpenSBI
```

But OpenSBI hangs (timeout) — likely waiting for bootable kernel from ISO.

## Solutions

### Option 1: Use CPU QEMU for Alpine ✅ RECOMMENDED

Alpine works on CPU QEMU. Use signed audio with `riscv64` (not `riscv64-gpu`):

```python
ops = [
    ["boot", "riscv64", "alpine-standard-3.24.1-riscv64-serial.iso", {"cdrom": True}]
]
```

This boots Alpine via:
```
Signed Audio → CPU QEMU → OpenSBI → Alpine
```

### Option 2: Extract ELF64 from Alpine Image

Alpine ISO contains a vmlinuz (compressed kernel). Extract it:

```bash
# Mount ISO
sudo mount -o loop boot_images/alpine-standard-3.24.1-riscv64-serial.iso /mnt/iso

# Extract vmlinuz
sudo cp /mnt/iso/boot/vmlinuz-riscv64 boot_images/alpine_vmlinuz

# Decompress (may need objcopy or extract-ikconfig)
gunzip -c boot_images/alpine_vmlinuz > boot_images/alpine_vmlinuz_uncompressed
```

Then test with GPU:
```bash
python3 tools/boot_xv6_gpu.py boot_images/alpine_vmlinuz_uncompressed
```

### Option 3: Build Alpine for GPU Emulator

The GPU emulator expects:
- RV64I kernel (no MMU or simple MMU)
- ELF64 format
- No UEFI firmware
- Direct kernel boot

Alpine is a full Linux distro with:
- Complex device tree
- Full MMU (SV39)
- Drivers for real hardware

May need to configure Alpine with minimal kernel:
```
make menuconfig
  → Disable complex MMU (use simple direct mapping)
  → Disable complex device drivers
  → Keep basic RISC-V support
```

### Option 4: Extend GPU Emulator for PE32+ EFI

Add PE32+ EFI support to `boot_xv6_gpu.py`:

```python
# tools/boot_xv6_gpu.py
class PE32Loader:
    """Load PE32+ EFI applications."""

    def __init__(self, path: Path):
        self.path = path
        self._parse()

    def _parse(self):
        # Read PE32+ header
        with open(self.path, 'rb') as f:
            dos_header = f.read(64)
            if dos_header[:2] != b'MZ':
                raise ValueError("Not PE32+")

            pe_offset = int.from_bytes(dos_header[60:64], 'little')
            f.seek(pe_offset)

            pe_header = f.read(24)
            if pe_header[:2] != b'PE':
                raise ValueError("Not PE32+")

            # Parse PE32+ header...
```

This is a major undertaking — PE32+ is complex.

## Recommendation

**Use CPU QEMU for Alpine** (Option 1). The GPU emulator is designed for:
- xv6 (teaching OS, simple)
- Minimal kernels
- Research/testing

Alpine is a full Linux distro, not a good fit for the current GPU emulator.

## What Works Now

| OS | Format | Boot Method | Result |
|----|--------|-------------|--------|
| xv6-riscv | ELF64 | GPU (`riscv64-gpu`) | ✅ 100% GPU utilization |
| Alpine Linux | ISO | CPU (`riscv64`) | ✅ Boots to OpenSBI |
| Alpine Linux | ISO | CPU with initrd | 🟡 Boots to OpenSBI |
| Alpine Linux | PE32+ EFI | GPU | ❌ Not ELF |

## Files Generated

- `alpine_gpu_signed.wav` — Failed (not ELF)
- `alpine_efi_gpu_signed.wav` — Failed (not ELF)
- `test_alpine_cpu.py` — CPU boot tester

## Next Steps

1. Try CPU QEMU with Alpine ISO (with initrd) — see if it boots fully
2. If successful, use `riscv64` (not `riscv64-gpu`) for Alpine
3. Keep `riscv64-gpu` for xv6 and minimal kernels
4. Consider adding PE32+ support to GPU emulator (future work)