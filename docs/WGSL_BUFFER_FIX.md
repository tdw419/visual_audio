# WGSL Buffer Format Mismatch Bug Fix

## Summary

**Issue**: GPU shader was receiving garbage data, causing opcode matching to fail despite mathematically perfect input from the collapse bridge.

**Root Cause**: Buffer format mismatch between Python CPU (`uint8`) and WGSL shader (`u32`).

**Impact**: Silent execution failure - GPU ran dispatches but produced no output.

## Technical Details

### Expected Data Flow

```
Font-Atomic (320×160) → Collapse Bridge → Dense (10×5) → GPU Buffer → Shader
```

### The Bug

**WGSL Shader Structure**:
```wgsl
struct Pixel {
    r: u32,  // 4 bytes
    g: u32,  // 4 bytes
    b: u32,  // 4 bytes
    a: u32,  // 4 bytes
}  // Total: 16 bytes per pixel

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
```

**Python Upload (BROKEN)**:
```python
rgba = np.array(img)  # shape: (5, 10, 3) of uint8
if rgba.shape[2] == 3:
    rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, dtype=rgba.dtype)])
    # shape: (5, 10, 4) of uint8

flat_data = rgba.reshape(-1, 4)  # shape: (50, 4) of uint8

# Buffer written: 50 pixels × 4 channels × 1 byte = 200 bytes
# Shader expects: 50 pixels × 4 channels × 4 bytes = 800 bytes
```

**What Happened**:
1. GPU created 800-byte buffer for shader
2. Python wrote only 200 bytes (uninitialized padding)
3. Shader read 200 bytes as `u32` array: 50 values
4. But `Pixel` struct interprets each `u32` as one channel
5. Result: Garbage data, no opcode matches

### The Fix

```python
rgba = np.array(img)  # shape: (5, 10, 3) of uint8
if rgba.shape[2] == 3:
    rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, dtype=rgba.dtype)])
    # shape: (5, 10, 4) of uint8

# CONVERT TO u32
rgba_u32 = rgba.astype(np.uint32)  # shape: (5, 10, 4) of u32
flat_data = rgba_u32.reshape(-1)   # shape: (200,) of u32

# Buffer written: 200 values × 4 bytes = 800 bytes
# Shader expects: 200 u32 values = 800 bytes ✓
```

## Verification

**Before Fix**:
```
Output values: []
```

**After Fix**:
```
Output values: [9, 9, 9, 9, 9, 9, 9, 9, 9, 9]
```

**Program Execution**:
1. `LDI r0 5` → r0 = 5
2. `LDI r1 4` → r1 = 4
3. `ADD r0 r1` → r0 = 9
4. `PRT r0` → output 9
5. `HLT` → stop

All 10 spatial CPUs correctly computed 5 + 4 = 9.

## Lessons Learned

### 1. Always Verify Buffer Sizes

The WGSL validation error was the real clue:
```
Buffer is bound with size 12 where the shader expects 16
```

This appeared in `test_ldi_only.py` when we tried to bind a 3-pixel buffer (12 bytes) but the shader expected 16 bytes per pixel.

### 2. Type Alignment Matters

| Language | Type | Size |
|----------|------|------|
| WGSL | `u32` | 4 bytes |
| Python | `uint8` | 1 byte |
| Python | `uint32` | 4 bytes |

When crossing language boundaries, always verify type sizes match.

### 3. Silent Failures are Dangerous

The GPU didn't crash - it just executed garbage code:
- Opcode matching failed (no `(236, 80, 80)` in garbage data)
- CPU looped infinitely over empty pixels
- Output buffer remained empty

**Detection Strategy**:
- Add trace output (RGB values read at each dispatch)
- Verify expected opcodes appear in trace
- Use collapse bridge for deterministic inputs

### 4. Diagnostic Test Files Pay Off

Each test file isolated one aspect:
- `test_pc_traversal.py`: Verified PC advancement ✓
- `test_basic_write.py`: Verified GPU output writes ✓
- `test_buffer_size.py`: Found size mismatch error ✓
- `test_ldi_only.py`: Revealed validation error ✓

**Pattern**: When debugging complex GPU pipelines, build incremental tests.

## Prevention Checklist

- [ ] Verify WGSL struct sizes match Python buffer sizes
- [ ] Convert pixel data to target type (uint32) before upload
- [ ] Check `wgpu-native` validation errors for size mismatches
- [ ] Add trace output for first few dispatches
- [ ] Test with minimal programs (1-2 opcodes) before full programs

## Related Files

- `tools/wgsl_spatial_glyph_working.py`: Fixed engine
- `tools/tri_modal_collapse_bridge.py`: Creates dense images
- `tools/test_*.py`: Diagnostic tests
- `docs/TRI_MODAL_VISUAL_SUBSTRATE.md`: Architecture documentation
- `docs/FONT_ATOMIC_SPATIAL_EXECUTION.md`: GPU integration guide

## Timeline

1. **2026-07-19 04:20**: Handoff - dense image generated, GPU returns empty
2. **2026-07-19 04:30**: Suspected PC advancement issue, wrote 2D traversal fix
3. **2026-07-19 04:45**: PC traversal test revealed CPU reading correct pixels
4. **2026-07-19 05:00**: Full trace test showed uninitialized memory in output
5. **2026-07-19 05:15**: Basic write test proved output buffer mechanism works
6. **2026-07-19 05:30**: LDI-only test triggered GPU validation error
7. **2026-07-19 05:45**: Root cause identified: uint8 vs u32 mismatch
8. **2026-07-19 06:00**: Fix implemented, GPU executes correctly ✓

## Status

✅ **RESOLVED** - Tri-modal execution pipeline fully working.

---

**Date**: 2026-07-19
**Files Modified**: `tools/wgsl_spatial_glyph_working.py`
**Tests Added**: 11 diagnostic test files
**Verification**: `Output: [9, 9, 9, 9, 9, 9, 9, 9, 9, 9]`