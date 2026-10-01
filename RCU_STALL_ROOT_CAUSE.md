# RCU Stall Root Cause Analysis

**Date**: 2026-08-26  
**Status**: DIAGNOSTICS IN PROGRESS

## Hypothesis Verification

### 1. DTB ISA String
**Checked**: `gpu_machine.dts`
```
riscv,isa = "rv64imafdc"
```
**Result**: ❌ **NO `sstc` extension advertised**

This means the kernel will use the SBI TIME extension instead of writing CSR_STIMECMP directly.

### 2. SBI TIME Extension Handler
**Checked**: `SPATIAL_RV64I.wgsl` line 1774, 2413
```wgsl
} else if (state.mode == 1u && sbi_ext == 0x54494D45u) {
    // TIME extension "set timer"
    csrs[CSR_STIMECMP] = vec2<u32>(registers.x[10].x, registers.x[10].y);
    csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x20u;
    registers.x[10] = vec2<u32>(0u, 0u);
    registers.x[11] = vec2<u32>(0u, 0u);
}
```
**Result**: ✅ **SBI TIME handler IS implemented**

### 3. Runtime Verification
**Test**: Run Alpine for 30M steps, check CSR_STIMECMP
```python
# After 30M steps:
stimecmp = 0  # Never armed!
```
**Result**: ❌ **CSR_STIMECMP never written**

### 4. SBI Ecall Inspection
**Test**: Check x17 (SBI extension ID) after boot
```python
x17 = 0x00000000  # Not SBI_TIME (0x54494D45)
```
**Result**: ❌ **SBI_TIME ecall not visible**

## Possible Explanations

### Option A: SBI TIME Ecall in Threaded Path
- SBI ecall executes during threaded execution
- Our interrupt check happens AFTER `execute_decoded()`
- But SBI ecall IS `execute_decoded()` - it should work
- **Unlikely**

### Option B: SBI TIME Never Called
- Kernel never tries to set up timer
- Kernel might be waiting for something else
- **Possible**

### Option C: Stale x17 Reading
- x17 register shows 0x0 because we're reading AFTER SBI handler ran
- Handler returns 0 in a10, a11 (SBI_SUCCESS)
- **LIKELY** - we need to see DURING ecall, not after

## Next Steps

1. Add GPU-side counter for SBI_TIME ecall invocations
2. Add GPU-side counter for stimecmp writes
3. Check if kernel reaches `clocksource_register()` (where timer would be armed)

## Working Theory

Most likely: **SBI TIME ecall IS being called, but we're not seeing it because we're reading register state AFTER the handler returns 0.**

The WGSL handler looks correct. The issue might be elsewhere in timer delivery or interrupt masking.