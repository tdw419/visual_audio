# PE32+ GPU Boot Stepladder

**Goal:** Enable Ubuntu/Alpine RISC-V kernels to boot on GPU via PE32+ EFI format.

**Why:** Currently only ELF64 kernels work (xv6, hello, bare). Ubuntu/Alpine use PE32+ EFI format and can't boot on GPU.

**Success Criteria:**
- Ubuntu RISC-V boots on GPU (serial console output visible)
- Alpine RISC-V boots on GPU (serial console output visible)
- Performance: <5 seconds to boot (baseline: xv6 = 0.5s)
- No regressions: xv6 still boots in 0.5s

---

## Phase 0: Validation (1 day)

**Goal:** Confirm PE32+ loader works and kernels are loadable.

**Tasks:**
- [x] Create `tools/hybrid_kernel_loader.py` (done)
- [x] Test with xv6.img (ELF64) → works ✓
- [x] Test with alpine_Image (PE32+) → works ✓
- [x] Test with hello.img (ELF64) → works ✓

**Verification:**
```bash
python3 tools/hybrid_kernel_loader.py boot_images/xv6.img
python3 tools/hybrid_kernel_loader.py boot_images/alpine_Image
python3 tools/hybrid_kernel_loader.py boot_images/hello.img
```

**Status:** ✅ COMPLETE

---

## Phase 1: Hybrid Loader Integration (3-5 days)

**Goal:** Integrate `HybridKernelLoader` into `boot_xv6_gpu.py`.

**Tasks:**

### 1.1 Import Hybrid Loader
- [ ] Add `from hybrid_kernel_loader import HybridKernelLoader` to `boot_xv6_gpu.py`
- [ ] Remove old `ELF64Loader` import (optional, keep for reference)

### 1.2 Replace Loader Initialization
```python
# Before
elf = ELF64Loader(elf_path)

# After
loader, fmt = HybridKernelLoader.load(elf_path)
```

### 1.3 Update Segment Loading Loop
```python
# Handle both ELF64 and PE32+ formats
for segment in loader.get_loadable_segments():
    data = loader.get_segment_data(segment)

    # Calculate address based on format
    if fmt == "ELF64":
        addr = segment['p_vaddr']
        size = segment['p_memsz']
    else:  # PE32+
        addr = segment['virtual_address']
        size = segment['virtual_size']

    # Upload to GPU
    upload_to_gpu(data, addr, size)
```

### 1.4 Update Entry Point
```python
# Set PC for both formats
pc = loader.entry_point
cpu_state['pc_low'] = pc & 0xFFFFFFFF
cpu_state['pc_high'] = (pc >> 32) & 0xFFFFFFFF
```

### 1.5 Add Format Logging
```python
print(f"[1] Loading kernel...")
print(f"    Format: {fmt}")
print(f"    Path: {elf_path}")
print(f"    Entry point: 0x{loader.entry_point:016x}")
```

**Verification:**
```bash
# Test xv6 (ELF64) - should still work
python3 tools/boot_xv6_gpu.py boot_images/xv6.img

# Test hello (ELF64) - should still work
python3 tools/boot_xv6_gpu.py boot_images/hello.img

# Test Alpine (PE32+) - should load but won't boot (needs UEFI)
python3 tools/boot_xv6_gpu.py boot_images/alpine_Image
```

**Expected Output:**
```
[1] Loading kernel...
    Format: ELF64
    Path: boot_images/xv6.img
    Entry point: 0x80000000
```

**Status:** ⏳ PENDING

---

## Phase 2: Minimal UEFI Runtime (5-7 days)

**Goal:** Add basic UEFI runtime services to `RISCV_CPU_MMU.wgsl`.

**Why:** PE32+ kernels call UEFI services during boot (memory allocation, console I/O, etc.).

**Tasks:**

### 2.1 Add UEFI CSR Fields to RiscvCPU
```wgsl
// UEFI Runtime State (add to RiscvCPU struct)
uefi_memory_pool: u32,        // UEFI memory pool pointer
uefi_heap_ptr: u32,           // UEFI heap pointer
uefi_console_out: u32,        // Console output flag
```

### 2.2 Implement AllocatePool
```wgsl
// UEFI AllocatePool (allocate memory)
fn uefi_allocate_pool(size: u32, pool_ptr: ptr<u32>) -> u32 {
    let addr = cpu.uefi_heap_ptr;
    cpu.uefi_heap_ptr = cpu.uefi_heap_ptr + size;
    *pool_ptr = addr;
    return 0;  // EFI_SUCCESS
}
```

### 2.3 Implement FreePool
```wgsl
// UEFI FreePool (no-op for now, heap grows forward only)
fn uefi_free_pool(ptr: u32) -> u32 {
    return 0;  // EFI_SUCCESS (ignore for now)
}
```

### 2.4 Implement Console Output
```wgsl
// UEFI Console Output (write to UART)
fn uefi_console_output(str: ptr<u8>, len: u32) -> u32 {
    for (var i = 0u; i < len; i = i + 1u) {
        uart_putchar(load_u8(str + i));
    }
    return 0;  // EFI_SUCCESS
}
```

### 2.5 Add UEFI Dispatch Table
```wgsl
// UEFI Runtime Services Dispatch Table
fn uefi_dispatch_call(service_id: u32, arg1: u32, arg2: u32) -> u32 {
    switch (service_id) {
        case 0x10: return uefi_allocate_pool(arg1, arg2);  // AllocatePool
        case 0x11: return uefi_free_pool(arg1);            // FreePool
        case 0x15: return uefi_console_output(arg1, arg2); // OutputString
        default: return 0x80000003u;  // EFI_UNSUPPORTED
    }
}
```

### 2.6 Hook into RISC-V SBI Calls
```wgsl
// Map UEFI calls to SBI extension 0x50 (custom)
fn sbi_ecall(extension: u32, function: u32, args: vec4<u32>) -> vec2<u32> {
    if (extension == 0x50) {
        // UEFI runtime services
        let result = uefi_dispatch_call(args.x, args.y, args.z);
        return vec2<u32>(result, 0);
    }
    // ... existing SBI code ...
}
```

**Verification:**
```bash
# Recompile WGSL shader
python3 tools/boot_xv6_gpu.py boot_images/alpine_Image

# Check for UEFI calls in console output
# Should see: "EFI_SUCCESS" or similar
```

**Status:** ⏳ PENDING

---

## Phase 3: UEFI Boot Services (5-7 days)

**Goal:** Add UEFI boot services (LoadImage, StartImage).

**Why:** UEFI firmware loads the kernel and hands control to it via boot services.

**Tasks:**

### 3.1 Create `tools/uefi_boot_services.py`
```python
class UEFIBootServices:
    """Emulate UEFI boot services."""

    def __init__(self, gpu_memory):
        self.memory = gpu_memory
        self.loaded_images = []

    def load_image(self, pe: PE32Loader):
        """Load PE32+ image into GPU memory."""
        for section in pe.get_loadable_segments():
            data = pe.get_section_data(section)
            addr = section['virtual_address']

            # Upload to GPU
            upload_to_gpu(data, addr)

            self.loaded_images.append({
                'name': pe.path,
                'entry': pe.entry_point,
                'handle': len(self.loaded_images),
            })

        return len(self.loaded_images) - 1  # Handle

    def start_image(self, handle):
        """Start a loaded image."""
        image = self.loaded_images[handle]

        # Set PC to entry point
        cpu_state['pc_low'] = image['entry'] & 0xFFFFFFFF
        cpu_state['pc_high'] = (image['entry'] >> 32) & 0xFFFFFFFF

        # Run dispatch
        return 0  # EFI_SUCCESS
```

### 3.2 Integrate into `boot_xv6_gpu.py`
```python
# After loading kernel
if fmt == "PE32+":
    boot_services = UEFIBootServices(gpu_memory)
    handle = boot_services.load_image(loader)
    boot_services.start_image(handle)
```

### 3.3 Add Boot Parameters
```python
# UEFI boot parameters (passed in a0, a1)
# a0 = device tree pointer
# a1 = UEFI system table pointer

dtb_ptr = 0x82000000  # Device tree blob address
efi_table_ptr = 0x82001000  # UEFI system table address

cpu_state['regs'][10] = dtb_ptr  # a0 (x10)
cpu_state['regs'][11] = efi_table_ptr  # a1 (x11)
```

### 3.4 Create Minimal Device Tree
```python
# Create minimal device tree blob for UEFI
dtb = create_device_tree_blob({
    'model': 'qemu,virt',
    'compatible': 'riscv-virtio',
    'cpus': {'#address-cells': 1, '#size-cells': 0},
    'cpu@0': {'compatible': 'riscv'},
    'memory@80000000': {'device_type': 'memory', 'reg': [0x80000000, 0x8000000]},
})

upload_to_gpu(dtb, 0x82000000)
```

**Verification:**
```bash
python3 tools/boot_xv6_gpu.py boot_images/alpine_Image

# Should see:
# - Kernel loads
# - UEFI services called
# - Early boot messages
```

**Status:** ⏳ PENDING

---

## Phase 4: Alpine RISC-V Boot (3-5 days)

**Goal:** Boot Alpine RISC-V on GPU with serial console output.

**Why:** Alpine is simpler than Ubuntu (smaller kernel, fewer dependencies). Test with Alpine first.

**Tasks:**

### 4.1 Test Alpine Load
```bash
python3 tools/boot_xv6_gpu.py boot_images/alpine_Image

# Expected:
# - PE32+ loads
# - UEFI services called
# - Alpine kernel starts
```

### 4.2 Debug UEFI Calls
```python
# Add logging to UEFI dispatch
def uefi_dispatch_call(service_id, arg1, arg2):
    print(f"[UEFI] Service 0x{service_id:02x} called")
    # ... implementation
```

### 4.3 Debug Memory Layout
```python
# Print memory map after load
print(f"[MEMORY] Entry point: 0x{loader.entry_point:016x}")
print(f"[MEMORY] .text: 0x00001000 - 0x00c00000")
print(f"[MEMORY] .data: 0x00c00000 - 0x01800000")
```

### 4.4 Add More UEFI Services
```wgsl
// GetVariable (configuration)
fn uefi_get_variable(...) -> u32 { ... }

// SetVariable (configuration)
fn uefi_set_variable(...) -> u32 { ... }

// GetTime (system time)
fn uefi_get_time(...) -> u32 { ... }

// ResetSystem (reboot/shutdown)
fn uefi_reset_system(...) -> u32 { ... }
```

### 4.5 Fix Boot Failures
- [ ] Debug "UEFI service not supported" errors
- [ ] Add missing UEFI services
- [ ] Fix memory allocation issues
- [ ] Fix console output buffering

**Verification:**
```bash
python3 tools/boot_xv6_gpu.py boot_images/alpine_Image

# Should see Alpine boot messages:
# - "Linux version ..."
# - "bootconsole [uart0] enabled"
# - "early console in setup code"
```

**Status:** ⏳ PENDING

---

## Phase 5: Ubuntu RISC-V Boot (5-7 days)

**Goal:** Boot Ubuntu RISC-V on GPU with serial console output.

**Why:** Ubuntu is the target distro (full Linux, not minimal like Alpine).

**Tasks:**

### 5.1 Extract Ubuntu Kernel
```bash
# Mount Ubuntu ISO
sudo mount ubuntu-24.04.2-live-server-riscv64.img /mnt/ubuntu

# Extract kernel
cp /mnt/ubuntu/casper/vmlinux /tmp/ubuntu_vmlinux
```

### 5.2 Test Ubuntu Load
```bash
python3 tools/boot_xv6_gpu.py /tmp/ubuntu_vmlinux

# Expected:
# - PE32+ loads (22 MB)
# - UEFI services called
# - Ubuntu kernel starts
```

### 5.3 Debug Ubuntu-Specific UEFI Calls
```python
# Ubuntu may call different UEFI services than Alpine
# Add logging to see what's needed
```

### 5.4 Add Ubuntu-Specific Services
```wgsl
// Ubuntu may need these:
fn uefi_get_next_monotonic_count(...) -> u32 { ... }
fn uefi_query_capsule_capabilities(...) -> u32 { ... }
fn uefi_update_capsule(...) -> u32 { ... }
```

### 5.5 Fix Ubuntu Boot Failures
- [ ] Debug "kernel panic - not syncing"
- [ ] Add missing UEFI services
- [ ] Fix device tree issues
- [ ] Fix ACPI table issues (if needed)

**Verification:**
```bash
python3 tools/boot_xv6_gpu.py /tmp/ubuntu_vmlinux

# Should see Ubuntu boot messages:
# - "Ubuntu 24.04.2 LTS riscv64"
# - "Linux version 6.8.0-41-generic"
# - "Boot command line: ..."
```

**Status:** ⏳ PENDING

---

## Phase 6: Regression Testing (1-2 days)

**Goal:** Ensure xv6 and hello still work after adding PE32+ support.

**Tasks:**

### 6.1 Test xv6 Baseline
```bash
python3 tools/boot_xv6_gpu.py boot_images/xv6.img

# Expected:
# - Boot time: ~0.5s
# - Output: "init: starting sh"
```

### 6.2 Test hello Baseline
```bash
python3 tools/boot_xv6_gpu.py boot_images/hello.img

# Expected:
# - Boot time: <0.1s
# - Output: "Hello, world!"
```

### 6.3 Performance Benchmark
```bash
# Measure boot times
time python3 tools/boot_xv6_gpu.py boot_images/xv6.img
time python3 tools/boot_xv6_gpu.py boot_images/alpine_Image
time python3 tools/boot_xv6_gpu.py /tmp/ubuntu_vmlinux

# Expected:
# - xv6: <0.5s (no regression)
# - Alpine: <3s (acceptable)
# - Ubuntu: <5s (acceptable)
```

### 6.4 Fix Regressions
- [ ] If xv6 slowed down, optimize shared code
- [ ] If hello broke, fix ELF64 path
- [ ] If performance degraded, profile and optimize

**Status:** ⏳ PENDING

---

## Phase 7: Signed Audio Integration (1-2 days)

**Goal:** Generate signed audio files for PE32+ boots.

**Tasks:**

### 7.1 Update boot_manifest.py
```python
# Add riscv64-gpu support for PE32+ kernels
ARCH_QEMU = {
    "riscv64-gpu": ("python3", ["tools/boot_xv6_gpu.py"]),
    # ... other arches
}
```

### 7.2 Create Alpine GPU Audio
```python
# generate_alpine_gpu_pe32_signed.py
ops = ["boot", "riscv64-gpu", "alpine_Image"]
narration = "Booting Alpine Linux RISC-V on GPU via PE32+"
utter(narration, ops, "alpine_gpu_pe32_signed.wav", priv_path)
```

### 7.3 Create Ubuntu GPU Audio
```python
# generate_ubuntu_gpu_pe32_signed.py
ops = ["boot", "riscv64-gpu", "ubuntu_vmlinux"]
narration = "Booting Ubuntu Server RISC-V on GPU via PE32+"
utter(narration, ops, "ubuntu_gpu_pe32_signed.wav", priv_path)
```

### 7.4 Test Signed Audio
```bash
python3 boot_single.py alpine_gpu_pe32_signed.wav /tmp/alpine_key.pub boot_images
python3 boot_single.py ubuntu_gpu_pe32_signed.wav /tmp/ubuntu_key.pub /tmp
```

**Status:** ⏳ PENDING

---

## Phase 8: Documentation (1 day)

**Goal:** Document PE32+ GPU boot usage and architecture.

**Tasks:**

### 8.1 Update README.md
```markdown
## GPU Boot

### Supported Kernels

| Format | Examples | Status |
|--------|----------|--------|
| ELF64 | xv6.img, hello.img, bare.img | ✅ Works |
| PE32+ | alpine_Image, ubuntu_vmlinux | ✅ Works |

### Usage

```bash
# Boot ELF64 kernel
python3 tools/boot_xv6_gpu.py boot_images/xv6.img

# Boot PE32+ kernel
python3 tools/boot_xv6_gpu.py boot_images/alpine_Image
```
```

### 8.2 Create Architecture Document
```markdown
# PE32+ GPU Boot Architecture

## Format Detection

The hybrid loader auto-detects kernel format:
- ELF64: `\x7fELF` magic bytes
- PE32+: `MZ` header + `PE\x00\x00` signature

## UEFI Services

Implemented UEFI runtime services:
- AllocatePool
- FreePool
- OutputString
- GetVariable
- SetVariable

## Boot Flow

1. Detect format (ELF64 vs PE32+)
2. Load kernel into GPU memory
3. Set entry point (PC)
4. If PE32+, initialize UEFI runtime
5. Start GPU dispatch loop
```

### 8.3 Update docs/PE32_EFI_VS_SELF_HOSTING_ANALYSIS.md
```markdown
## Status: ✅ COMPLETE

PE32+ GPU boot is now fully implemented.

### What Works

- ✅ xv6.img (ELF64) - 0.5s boot
- ✅ alpine_Image (PE32+) - 2.1s boot
- ✅ ubuntu_vmlinux (PE32+) - 3.8s boot
```

**Status:** ⏳ PENDING

---

## Summary

### Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| 0: Validation | 1 day | ✅ COMPLETE |
| 1: Hybrid Loader | 3-5 days | ⏳ PENDING |
| 2: UEFI Runtime | 5-7 days | ⏳ PENDING |
| 3: Boot Services | 5-7 days | ⏳ PENDING |
| 4: Alpine Boot | 3-5 days | ⏳ PENDING |
| 5: Ubuntu Boot | 5-7 days | ⏳ PENDING |
| 6: Regression Testing | 1-2 days | ⏳ PENDING |
| 7: Signed Audio | 1-2 days | ⏳ PENDING |
| 8: Documentation | 1 day | ⏳ PENDING |

**Total: 25-37 days (5-7 weeks)**

### Success Criteria

- [x] Phase 0: Hybrid loader parses both formats
- [ ] Phase 1: xv6 still boots after integration
- [ ] Phase 2: UEFI services work on GPU
- [ ] Phase 3: Alpine kernel loads and starts
- [ ] Phase 4: Alpine boots with console output
- [ ] Phase 5: Ubuntu boots with console output
- [ ] Phase 6: No performance regression in xv6
- [ ] Phase 7: Signed audio boots work
- [ ] Phase 8: Documentation complete

### Next Steps

1. Start Phase 1: Integrate hybrid loader into `boot_xv6_gpu.py`
2. Test with xv6 (prove no regression)
3. Test with Alpine (prove PE32+ loads)
4. Add UEFI services (Phase 2)

---

**Last Updated:** 2026-07-25
**Status:** Phase 0 complete, Phase 1 pending