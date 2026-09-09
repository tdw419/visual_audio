# RCA: GPUValidationError - decoded_ops buffer exceeds 128MB limit

**Date:** 2026-08-29 00:45
**Symptom:** Alpine boot supervisor daemon stuck at 0 steps, monitor script fails with GPUValidationError

## Root Cause

The `decoded_ops` pre-decoded instruction buffer is allocated for the entire 64MB RAM address space:

```python
# In spatial_rv64i_cpu.py line 145-146
n_halfwords = mem_len_words * 2  # 16,777,216 * 2 = 33,554,432
self.decoded_ops_buffer = self.device.create_buffer(
    size=n_halfwords * 9 * 4,  # 33,554,432 * 9 * 4 = 1,207,959,552 bytes (~1.2GB)
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
)
```

This creates a 1.2GB buffer that exceeds the GPU's `max_*_buffer_binding_size` limit of 134,217,728 bytes (128MB):

```
wgpu._classes.GPUValidationError: Buffer binding 6 range 1207959552 exceeds max_*_buffer_binding_size limit 134217728
```

## Why This Happens

The decoded_ops buffer is designed for **basic-block threading optimization**:
- Each instruction (2 or 4 bytes) gets a `DecodedOp` structure (9 u32s = 36 bytes)
- Pre-decoding all instructions avoids runtime bitfield extraction in the WGSL shader
- Works well for CPU-bound systems but wastes GPU memory

The allocation assumes all of RAM could be code, but:
- ~24MB of the 64MB is the Alpine boot image (kernel + initrd)
- The rest is data/heap that never needs pre-decoded instructions
- ~1GB of GPU VRAM is wasted on zero-initialized DecodedOp entries

## Impact

- **Critical:** Alpine boot daemon cannot run any iterations
- All boot attempts fail immediately with exit code 1
- Monitor reports "no_data" stall reason
- Daemon loops forever with 0 steps progress

## Fix Strategy

### Option 1: Windowed Decoded Ops Buffer (Chosen)

Limit the buffer to a practical code window (e.g., first 16MB of address space):

```python
# Before: 64MB RAM → 1.2GB decoded_ops
# After: 16MB code window → 128MB decoded_ops

CODE_WINDOW_BYTES = 16 * 1024 * 1024  # First 16MB for kernel/initrd
CODE_WINDOW_HALFWORDS = CODE_WINDOW_BYTES // 2  # 8M halfwords
DECODED_OPS_SIZE = CODE_WINDOW_HALFWORDS * 9 * 4  # 8M * 9 * 4 = 288MB

# But need to stay under 128MB limit:
# 16MB code window → 288MB decoded_ops (still too large!)
CODE_WINDOW_BYTES = 8 * 1024 * 1024  # First 8MB for kernel
CODE_WINDOW_HALFWORDS = CODE_WINDOW_BYTES // 2  # 4M halfwords
DECODED_OPS_SIZE = CODE_WINDOW_HALFWORDS * 9 * 4  # 4M * 9 * 4 = 144MB

# Still slightly over. Try 6MB:
CODE_WINDOW_BYTES = 6 * 1024 * 1024  # 6M bytes
CODE_WINDOW_HALFWORDS = 3 * 1024 * 1024  # 3M halfwords
DECODED_OPS_SIZE = 3 * 1024 * 1024 * 9 * 4 = 108MB ✓ (under 128MB)
```

Runtime fallback for addresses outside the window:
- WGSL shader checks if `slot < MAX_CODE_SLOT`
- If in window: use pre-decoded `DecodedOp`
- If outside window: use runtime `decode_step()` fallback

### Option 2: Split Buffer into Multiple Bindings

Divide the buffer into 8 smaller bindings (128MB / 8 = 16MB each):
- Add more @binding slots to SPATIAL_RV64I.wgsl
- Use array indexing modulo 8 to route to correct binding
- Higher complexity, harder to maintain

### Option 3: On-Demand Decoded Ops Upload

Only upload decoded ops for recently-executed pages:
- Track which code pages are active
- Upload decoded ops in chunks
- Adds runtime complexity and synchronization overhead

## Implementation Steps

### 1. Fix Python Buffer Allocation (spatial_rv64i_cpu.py)

```python
# Line 138-153: Limit decoded_ops buffer size
CODE_WINDOW_BYTES = 6 * 1024 * 1024  # First 6MB for kernel code
CODE_WINDOW_HALFWORDS = CODE_WINDOW_BYTES // 2

self.decoded_ops_buffer = self.device.create_buffer(
    size=CODE_WINDOW_HALFWORDS * 9 * 4,  # 108MB under 128MB limit
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
)
self._decoded_ops_size = CODE_WINDOW_HALFWORDS  # Track for bounds checking
```

### 2. Update WGSL Shader (SPATIAL_RV64I.wgsl)

Add window check before using pre-decoded ops:

```wgsl
// After line 97: Add constants
const MAX_CODE_SLOT = 3145728u;  // 6MB / 2 = 3M halfwords

// Around line 2762: Add bounds check before lookup
if (cur_slot < MAX_CODE_SLOT) {
    let tdop = decoded_ops[cur_slot];
    let t_epoch_valid = (tdop.epoch == decoded_ops_epoch);
    if (t_epoch_valid && tdop.op != 0xFFFFFFFFu) {
        // Use pre-decoded op
        ...
    } else {
        // Fall back to runtime decode
        ...
    }
} else {
    // Outside window: always runtime decode
    ...
}
```

### 3. Update Sync Logic

Ensure only addresses within the window are synced:

```python
# In _sync_decoded_ops(): Clip ranges to code window
start_slot = max(start_byte >> 1, 0)
end_slot = min((end_byte + 1) >> 1, self._decoded_ops_size)

if start_slot >= self._decoded_ops_size:
    return  # Entire range outside window
```

## Verification

1. Test with Alpine boot - should not fail with GPUValidationError
2. Verify boot progresses beyond 0 steps
3. Confirm kernel code (typically in first 4-6MB) uses pre-decoded ops
4. Verify runtime fallback works for higher addresses (user space)

## Trade-offs

**Pros:**
- Immediate unblocks Alpine boot daemon
- Minimal GPU memory footprint (108MB vs 1.2GB)
- Simpler than multi-binding approach
- Decoding cost only paid once at boot (cached)

**Cons:**
- User space code (loaded above 6MB) uses runtime decode path
- Potential performance hit for user space execution
- Need to monitor if 6MB window is sufficient for kernel
- May need to adjust window size if kernel grows

## Files Modified

1. `/home/jericho/projects/zion/projects/visual_audio/tools/spatial_rv64i_cpu.py`
   - Add CODE_WINDOW_BYTES constant
   - Limit decoded_ops_buffer size
   - Clip ranges in _sync_decoded_ops()

2. `/home/jericho/projects/zion/projects/visual_audio/tools/SPATIAL_RV64I.wgsl`
   - Add MAX_CODE_SLOT constant
   - Add bounds check before decoded_ops lookup

## Rollback

If performance is unacceptable, can:
- Increase window size (but may need multi-binding approach for >128MB)
- Revert to full-buffer with multi-binding split (Option 2)
- Implement on-demand upload (Option 3)