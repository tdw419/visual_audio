# Level 5c GPU Timeout Investigation (2026-07-28)

## Root Cause Found (Updated 2026-07-28T16:20)

**State buffer layout mismatch** (FIXED):
- Level 5c tests were writing only 18 fields when `SpatialRV64ICore` requires 23 fields
- Fixed by updating all test files to write full 23-field state buffer

**Performance bottleneck identified** (CURRENT ISSUE):
- GPU execution itself is fast (~300K+ steps/sec for small batches)
- `get_state()` causes full GPU sync (~500ms-1s per call) due to buffer reads
- Tests calling `get_state()` in loop (e.g., for UART progress) become 50x-1000x slower
- First run warmup cost: ~50ms for initial shader compilation/validation

### Impact
- `ram_base_low` (field 14) was reading garbage instead of 0x80000000
- MMU translation failed immediately for all addresses
- CPU halted with silent failure (no trap, just PC stuck)

### Fix Applied
Updated state initialization in all Level 5c tests:
```python
state_data = np.array(
    [pc_low, pc_high, halted, steps_remaining, mode, trap_pending,
     reservation_valid, reservation_addr_low, reservation_addr_high,
     uart_tx_len, mtime_low, mtime_high, mtimecmp_low, mtimecmp_high,
     ram_base_low, ram_base_high,
     uart_rx_data_pending, uart_rx_byte,
     instr_len, last_d2idx_d, last_d2idx_result, _pad[2]],
    dtype=np.uint32
).tobytes()
```

## Verification

### Before Fix
```
$ python3 tests/level5c_debug_test.py
PC=0x0000000080000004, halted=1  # Halted immediately
```

### After Fix
```
$ python3 tests/level5c_debug_test.py
PC=0x0000000080000004, halted=0
PC=0x0000000080000008, halted=0
PC=0x000000008000000c, halted=0
...  # CPU advances correctly
```

## Remaining Issues

### Performance Gap
- **QEMU**: ~90K steps/sec
- **GPU**: ~1.8K steps/sec (50x slower)

### Test Results
| Test | Status | Notes |
|------|--------|-------|
| level5c_debug_test.py | PASS | 5 steps, minimal sync overhead |
| level5c_gpu_test.py | TIMEOUT | 30k steps, still times out |
| level5c_progress_test.py | TIMEOUT | 200k steps, still times out |
| level5c_batch_test.py | UNKNOWN | Not yet tested after fix |

### Potential Causes
1. **WGSL instruction decode overhead**: Complex switch-case may be slower than QEMU's optimized interpreter
2. **GPU sync overhead**: Each dispatch adds overhead
3. **Hilbert mapping**: Every memory access requires `d2xy()` coordinate transformation
4. **Batch size**: GPU may need different optimal batch size than expected

## Next Steps

### High Priority
- [ ] Run level5c_batch_test.py after fix to see if batching helps
- [ ] Profile WGSL execution time per instruction type
- [ ] Investigate Hilbert mapping optimization (already has d2idx cache)
- [ ] Test with smaller step counts (1k-5k) to establish baseline

### Medium Priority
- [ ] Consider preprocessing to precompute Hilbert mapping for hot code paths
- [ ] Add GPU timing diagnostics to `step()` method
- [ ] Compare with OpenSBI boot performance (~145s for full boot)

### Low Priority
- [ ] Optimize WGSL instruction decode loop (early exit for common ops)
- [ ] Consider async execution for non-blocking dispatches

## Files Modified

- `tests/level5c_debug_test.py` - Fixed state buffer layout
- `tests/level5c_gpu_test.py` - Fixed state buffer layout
- `tests/level5c_progress_test.py` - Fixed state buffer layout

## References

- WGSL CPUState struct: `tools/SPATIAL_RV64I.wgsl` lines 6-46
- Python state layout: `tools/spatial_rv64i_cpu.py` lines 48-58
- Level 5c source: `tests/bare_metal/level5c/level5c.c` (builds to level5c.elf)