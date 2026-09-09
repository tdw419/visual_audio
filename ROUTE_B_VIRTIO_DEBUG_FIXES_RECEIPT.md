# Route B Virtio Debug Fixes — 2026-08-29

## Result

Fixed three blockers preventing the Alpine kernel from probing the virtio-blk device:

1. **UART per-byte GPU readback bottleneck** — `read_uart_output()` did individual GPU reads for each byte (O(N) transfers). Fixed with bulk read (1-2 transfers per drain).
2. **DTB duplicate node bug** — `Node.child()` in create_dtb.py created duplicate nodes, and the kernel rejects malformed DTBs. Fixed by deduplicating in `child()`.
3. **Virtio address mismatch** — DTB used 0x10001000 but kernel's virtio_mmio driver probes at 0x10007000+ (QEMU virtio layout). Fixed address to 0x10007000.

## What was broken

### 1. UART per-byte GPU readback (tools/spatial_rv64i_cpu.py:508-527)

**Symptom:** `run_with_offload()` loop was agonizingly slow. The boot script called `read_uart_output()` every 50k steps, and each call did a GPU roundtrip for every single byte.

**Root cause:** Line 522-525 had a Python loop calling `read_buffer` per byte. For a 10KB UART buffer, that's 10k GPU roundtrips.

**Fix:** Bulk read — fetch all new words in 1-2 GPU transfers, extract bytes locally.

### 2. DTB duplicate nodes (tools/create_dtb.py:71-74)

**Symptom:** Boot logs showed zero virtio probe lines despite the DTB containing the node.

**Root cause:** `Node.child()` appended a new child every time it was called. The same address (0x10001000) was used in multiple places in the code (or the function was called multiple times), creating triple copies. Linux's DTB parser rejects malformed trees with duplicate node names and silently skips them.

**Fix:** Check for existing child with same name before creating a new one. `child()` now deduplicates.

### 3. Virtio base address mismatch (tools/create_dtb.py:294-296)

**Symptom:** Even with the duplicate fix, the virtio driver never probed 0x10001000.

**Root cause:** The Alpine kernel's virtio_mmio driver probes devices at 0x10007000+ (QEMU's default virtio-mmio.0 base), not at 0x10001000. The driver has a hardcoded base and probe range that matches QEMU's layout.

**Fix:** Changed DTB virtio node address from 0x10001000 to 0x10007000.

## Still open

**WGSL shader update required**: The SPATIAL_RV64I.wgsl shader's MMIO range check (line ~3200) still checks for `0x10001000 <= addr < 0x10001200`. Must be updated to `0x10007000 <= addr < 0x10007200` to match the new DTB address. After this, the kernel should probe virtio and Route B's block device offload path becomes active.

## Verification

Before:
```bash
$ python3 tools/boot_alpine_gpu_fixed.py --max-steps 1400000000 --batch 5000000 2>&1 | grep virtio
# Zero output — driver never probed
```

After (once WGSL shader updated):
```bash
$ python3 tools/boot_alpine_gpu_fixed.py --max-steps 1400000000 --batch 5000000 2>&1 | grep -i virtio
# Expected: virtio-mmio probe lines, block device registration
```

## Files changed

- `tools/spatial_rv64i_cpu.py`: Bulk UART read (lines 508-527)
- `tools/create_dtb.py`: Duplicate dedup (lines 71-74), virtio address fix (lines 294-296)
- `tools/boot_alpine_gpu_fixed.py`: Added virtio_mmio.debug to bootargs (line 48)