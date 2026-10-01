#!/usr/bin/env python3
"""
tools/verify_virtio_offload.py
Pure, no-GPU host-side verification test for QueueConfig layout arithmetic.
Asserts correct address calculations and handles regression regression checks.
"""

import sys
import numpy as np
from qemu_gpu_offload import QueueConfig

def test_ring_address_calculation():
    """Step 2 Verification: Asserts PFN to ring mapping calculations without GPU dependency."""
    print("=== Step 2: Verifying QueueConfig PFN/Byte Address Ring Mapping ===")
    
    # Mock CPUState array as it would be read from core.state_buffer
    # Size 46 u32 elements
    state_arr = np.zeros(46, dtype=np.uint32)
    
    # Mock legacy virtio configuration registers
    # num = 256 (offset 44), align = 4096 (offset 45)
    state_arr[44] = 256
    state_arr[45] = 4096
    
    # Mock val written to vq_desc_low (offset 36).
    # Since the WGSL shader multiplies PFN by 4096 on write:
    # state.vq_desc_low = val * 4096u;
    pfn = 0x100
    desc_pa = pfn * 4096  # 0x100000 (1MB)
    state_arr[36] = desc_pa
    
    # Available ring contiguous layout starts right after descriptors
    # avail = desc + num * 16 = 0x100000 + 256 * 16 = 0x101000
    avail_pa = desc_pa + 256 * 16
    
    # Used ring contiguous layout starts on align (4096) boundary after avail
    # used = align_up(avail + 6 + num * 2, align)
    # used = align_up(0x101000 + 6 + 512, 4096) = 0x102000
    used_pa = (avail_pa + 6 + 256 * 2 + 4095) & ~4095
    
    print(f"Mocked Desc Byte Address (vq_desc_low): 0x{desc_pa:x}")
    print(f"Expected Avail Ring Address: 0x{avail_pa:x}")
    print(f"Expected Used Ring Address:  0x{used_pa:x}")
    
    # Parse via QueueConfig
    cfg = QueueConfig(state_arr)
    
    assert cfg.desc == desc_pa, f"Descriptor address mismatch: 0x{cfg.desc:x} vs 0x{desc_pa:x}"
    assert cfg.avail == avail_pa, f"Avail ring address mismatch: 0x{cfg.avail:x} vs 0x{avail_pa:x}"
    assert cfg.used == used_pa, f"Used ring address mismatch: 0x{cfg.used:x} vs 0x{used_pa:x}"
    
    print("✓ Host-side QueueConfig correctly reads byte address and computes ring layout layout.")

if __name__ == "__main__":
    try:
        test_ring_address_calculation()
        print("\nAll host-side structural assertions PASSED.")
    except AssertionError as e:
        print(f"\nAssertion FAILED: {e}")
        sys.exit(1)
