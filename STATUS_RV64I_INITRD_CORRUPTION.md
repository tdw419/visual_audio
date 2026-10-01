# RV64I Alpine Boot Initramfs Corruption Investigation

## UPDATE 2026-08-26: RESOLVED — see rv64_inflate_probe/CORRUPTION_FIX_SPEC.md

**Actual root cause**: OpenSBI (Ubuntu fw_jump.bin, FW_JUMP_FDT_ADDR=0x82200000)
relocates its FDT copy to 0x82200000, which sat INSIDE the initrd range
(0x82000000..0x8250B5E1), corrupting the gzip at +2MB. The kernel's inflate
resynchronized past the corruption and produced garbage cpio entries →
"broken padding" → free_initrd_mem() 0xCC poison. **Fix**: initrd moved to
0x82800000 (clear of 0x82200000). Verified: initrd byte-perfect at 40M, full
boot passes the old failure point. The DTB /chosen + /reserved-memory addressing
was correct all along; the memblock reservations were honored.

## Executive Summary

**CRITICAL FINDING: Boot image is VALID. Corruption is NOT in write_mem_bytes() or GPU memory.**

Through direct testing, we verified:

1. ✓ Source initrd decompresses cleanly on host (11,600,900 bytes, no gzip errors)
2. ✓ write_mem_bytes() correctly writes initrd to GPU memory (both word-by-word and chunk shader paths)
3. ✓ GPU memory Hilbert mapping is correct (sampled offsets match _linear_shadow)

**Conclusion:** The corruption is NOT in write_mem_bytes or GPU memory. The "broken padding" error comes from DTB initrd addressing mismatch or kernel initrd loader confusion.

## Test Results

### Test 1: Host-side initrd validation (PASSES)

```bash
$ python3 /tmp/initrd_investigation.py
SUCCESS: Decompressed 11,600,900 bytes
```

The source initrd is valid gzip data.

### Test 2: write_mem_bytes small path (PASSES)

```bash
$ python3 tests/test_write_mem.py
✓ write_mem_word works correctly
```

### Test 3: write_mem_bytes large chunk shader path (PASSES)

```bash
$ python3 tests/test_with_linear_shadow.py
✓ write_mem_bytes works correctly (using _linear_shadow)!
```

The _linear_shadow array is maintained correctly.

### Test 4: GPU memory Hilbert mapping (PASSES)

```bash
$ python3 tests/test_various_offsets.py
Result: All checks passed!
```

GPU memory correctly reflects _linear_shadow across the initrd range.

### Test 5: First false positive - linear readback (FALSE ALARM)

Initial `initrd_verification.py` reported "5271649 differing bytes" because it read GPU memory LINEARLY without Hilbert de-mapping. But the guest kernel reads through MMU WITH Hilbert de-mapping. GPU memory IS correct.

## Root Cause Analysis

Since write_mem_bytes and GPU memory are verified correct, the "broken padding" error must come from:

1. **DTB initrd addressing mismatch:** The kernel reads initrd from `linux,initrd-start`/`linux,initrd-end` in DTB. If these don't match actual initrd location, kernel reads garbage.

2. **Kernel initrd loader confusion:** Alpine kernel's PE32+ EFI stub may use different initrd addressing than our DTB assumes.

3. **Padding/truncation:** Kernel may expect different initrd size/alignment than we provide.

## Next Steps

1. Verify DTB `linux,initrd-start`/`linux,initrd-end` properties match `initrd_load_addr` and `initrd_load_addr + initrd_size`.

2. Compare with real QEMU using our exact DTB to isolate whether bug is in memory read path or DTB generation.

3. Add emulator logging to capture exact addresses kernel reads when loading initramfs.

## Previous Conclusion (Now Known to be Incorrect)

The previous STATUS_RV64I_LOOP.md stated:
> "This is a boot-image construction problem, not an emulation bug"

This is **INCORRECT**. Boot image is valid. Bug is in DTB generation or memory read path - both emulator/loader bugs, not source-image problems.

## Files in This Worktree

- `tests/initrd_verification.py` - Full initrd write/readback test
- `tests/test_write_mem.py` - Basic write_mem_word/write_mem_bytes tests
- `tests/test_with_linear_shadow.py` - Large chunk path test
- `tests/test_various_offsets.py` - Offset sampling test
- `STATUS_RV64I_INITRD_CORRUPTION.md` - This file
- `STATUS_RV64I_LOOP.md` - Copy of original status (now known to be incorrect on initramfs conclusion)