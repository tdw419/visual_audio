# Alpine PE32+ Kernel EFI Inventory Report

**Date**: 2026-07-25
**Kernel**: `/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_Image`
**Format**: PE32+ RISC-V (0x020b)

## Summary

- **BootServices functions referenced**: 31
- **RuntimeServices functions referenced**: 0
- **ecall instructions (SBI/EFI extensions)**: 2

## Root Cause of Boot Failure

The kernel crashes due to **NULL-pointer dereferences in .data globals**. These globals are:
1. Compiled as zero-initialized in .data section
2. Expected to be populated by UEFI runtime initialization
3. **Not initialized by our stubs** (they just return without side effects)

The memory model fix (NULL derefs now fault instead of aliasing into EFI table) correctly exposes this - it's not a silent bug anymore.

## BootServices Functions Accessed

The kernel accesses these functions via table offsets. Critical ones are marked **[CRITICAL]**.

### Load/Start (Table 0)
- `LoadImage` (offset 0x00)
- `StartImage` (offset 0x08) **[CRITICAL]** - Called from 0x00a42a62
- `Exit` (offset 0x10) **[CRITICAL]** - Called from 0x00a42a62  
- `UnloadImage` (offset 0x18)
- `ExitBootServices` (offset 0x20) **[CRITICAL]** - Required for kernel handoff
- `GetNextMonotonicCount` (offset 0x28)
- `Stall` (offset 0x30)
- `WatchdogTimer` (offset 0x38)

### Controller/Protocol (Table 1)
- `ConnectController` (offset 0x40) - Called from 0x00a42982
- `DisconnectController` (offset 0x48) - Called from 0x00a42fba
- `OpenProtocol` (offset 0x50)
- `CloseProtocol` (offset 0x58) - Called from 0x00a424cc
- `OpenProtocolInformation` (offset 0x60) - Called from 0x00a43256
- `ProtocolsPerHandle` (offset 0x68)
- `LocateHandleBuffer` (offset 0x70) - Called from 0x00a4306c
- `LocateProtocol` (offset 0x78)

### Install/Manage (Table 2)
- `InstallProtocolInterface` (offset 0x80)
- `ReinstallProtocolInterface` (offset 0x88)
- `UninstallProtocolInterface` (offset 0x90)
- `HandleProtocol` (offset 0x98) - Already stubbed in WGSL
- `RegisterProtocolNotify` (offset 0xA0)
- `LocateHandle` (offset 0xA8)
- `InstallMultipleProtocolInterfaces` (offset 0xB0)
- `UninstallMultipleProtocolInterfaces` (offset 0xB8) - Called from 0x00a427da

### Memory (Table 3)
- `AllocatePool` (offset 0xC0) - **Already implemented** in WGSL
- `FreePool` (offset 0xC8) - Already stubbed (no-op)
- `SetWatchdogTimer` (offset 0xD0)
- Additional ConnectController/DisconnectController/OpenProtocol (duplicate offsets?)

## ecall Sites (SBI Extensions)

Two ecall instructions found (likely SBI-style calls):
1. `0x0001984c: ecall` - Trampoline entry
2. `0x00019890: ecall` - Trampoline entry

These are part of UEFI extension calls we already handle via `SBI_EXT_UEFI`.

## Analysis

### What's Working
- ✅ AllocatePool/FreePool implemented (UEFI heap)
- ✅ HandleProtocol stub returns zeroed interface
- ✅ Memory model now faults on NULL derefs (exposes real bugs)

### What's Missing
1. **GP-relative globals initialization** - .data section loaded, but runtime initialization never runs
2. **Critical BootServices** - StartImage, Exit, ExitBootServices need real implementations
3. **Protocol discovery** - LoadImage/StartImage sequence not mocked
4. **Device tree/ACPI tables** - Kernel expects these from firmware

### Boot Path (Based on Entry Point Analysis)

```
1. Entry: PE32+ entry point at 0x600000bff0001402
2. Load base: 0x80000000 (our emulator loads here)
3. Early boot setup:
   - Set stvec (trap vector)
   - Configure SATP (MMU)
   - Set GP register: auipc gp,0x1557 + addi gp,2036
4. Call into runtime initialization (expects SystemTable in a1)
5. Allocate memory from UEFI
6. Load drivers/modules via LoadImage/StartImage
7. Call ExitBootServices to hand off to kernel
```

**The problem**: At step 4, runtime initialization tries to access NULL-initialized .data globals and crashes.

## Implementation Strategy

### Phase 1: Stub Out All 31 Functions (IN PROGRESS)

Create safe stubs for every accessed BS function. Each stub returns a sane default without crashing:
- Pointer-return functions: return zeroed struct
- Status-return functions: return EFI_SUCCESS (0)
- Boolean functions: return TRUE (1)

This fixes the "immediate crash" - kernel runs further.

### Phase 2: Implement Critical Path

Real implementations for:
- **AllocatePool** ✅ Already done
- **LoadImage/StartImage** - Stub returns success, marks driver as "loaded"
- **ExitBootServices** - Handoff from UEFI mode to bare-metal kernel
- **LocateProtocol** - Return pre-canned interfaces for required protocols

### Phase 3: Runtime Initialization Hook

Before jumping to kernel entry, pre-initialize known .data globals:
- Set GP pointer targets to valid addresses
- Initialize device tree pointer (required by Linux)
- Reserve ACPI region

### Phase 4: Real Boot Services

If needed, implement a simple image loader for Linux kernel modules.

## Recommendations

1. **Do Phase 1 first** - Create all 31 stubs, verify kernel runs further
2. **Identify which .data globals are accessed** - After stubs, new crashes will show what's needed
3. **Selective implementation** - Only implement functions that affect boot path
4. **Keep simple** - We don't need full UEFI; just enough for Linux to boot

## Files to Modify

1. `tools/boot_xv6_gpu.py` - Add .data pre-initialization before jumping to entry
2. `tools/RISCV_CPU_MMU.wgsl` - Add remaining UEFI stubs (31 total)
3. `tools/inventory_efi_calls.py` - Script we just created for inventory

## Next Steps

1. ✅ Memory model fix (NULL derefs fault)
2. ✅ EFI service inventory (this document)
3. ❌ Add all 31 BootServices stubs to WGSL
4. ❌ Pre-initialize .data globals before kernel entry
5. ❌ Test boot progression

## Verification

After Phase 1:
- [ ] Boot should not crash on first instruction
- [ ] Should progress past early setup
- [ ] UART should output early boot messages

After Phase 2:
- [ ] StartImage runs without crashing
- [ ] ExitBootServices completes
- [ ] Kernel handoff succeeds

After Phase 3:
- [ ] GP-relative loads return valid data
- [ ] Device tree accessible
- [ ] Linux decompresses kernel

---

**Status**: 🔄 IN PROGRESS - Phase 1 stub creation pending