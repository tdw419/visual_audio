#!/usr/bin/env python3
"""
Helper to inspect CSR values in the WGSL emulator.

This creates a minimal xv6 test that dumps mstatus/sstatus on each
intr_get()/intr_off() call to diagnose the "pop_off - interruptible" panic.
"""

import struct
import numpy as np

# ============================================================================  
# RISC-V Test Binary with CSR Inspection
# ============================================================================

def build_csr_test():
    """
    Build a minimal test that exercises push_off/pop_off
    and dumps CSR values.
    """
    
    # Simple assembly to test interrupt tracking:
    # 1. Read mstatus (check MIE, SIE bits)
    # 2. Read sstatus
    # 3. Call push_off (read sstatus, write sstatus with SIE cleared)
    # 4. Read sstatus again
    # 5. Check if SIE is actually cleared
    # 6. Call pop_off (should panic if SIE is set)
    
    test = []
    
    # Read initial mstatus (store to scratchpad offset 0)
    test.extend([
        0x30002273,  # csrr t0, mstatus
        0x34102223,  # sw t0, 820(gp)  # scratchpad at gp+820
    ])
    
    # Read initial sstatus (store to scratchpad offset 8)
    test.extend([
        0x10002273,  # csrr t0, sstatus  
        0x34102423,  # sw t0, 824(gp)  # scratchpad at gp+824
    ])
    
    # Simulate push_off/intr_off:
    # - Read sstatus (save to t0)
    # - Clear SIE bit
    # - Write back
    test.extend([
        0x10002e73,  # csrr t0, sstatus
        0xffeff0f3,  # andi t0, t0, -3  # Clear bit 1 (SIE)
        0x10029273,  # csrw sstatus, t0
    ])
    
    # Read sstatus again after intr_off (store to scratchpad offset 16)
    test.extend([
        0x10002273,  # csrr t0, sstatus
        0x34102623,  # sw t0, 828(gp)  # scratchpad at gp+828
    ])
    
    # Check SIE bit (bit 1) in mstatus after intr_off (store to scratchpad offset 24)
    test.extend([
        0x30002273,  # csrr t0, mstatus
        0x0022f293,  # andi t0, t0, 2  # Extract bit 1
        0x34102823,  # sw t0, 832(gp)
    ])
    
    # Check MIE bit (bit 3) in mstatus after intr_off (store to scratchpad offset 32)
    test.extend([
        0x30002273,  # csrr t0, mstatus
        0x0082f293,  # andi t0, t0, 8  # Extract bit 3
        0x34102a23,  # sw t0, 836(gp)
    ])
    
    # Halt
    test.append(0x00100073)  # ebreak
    
    # Pad to 64 instructions (256 bytes)
    test.extend([0x00000000] * (64 - len(test)))
    
    # Convert to RGBA pixels
    pixels = np.zeros((64, 4), dtype=np.uint8)
    for i, instr in enumerate(test):
        pixels[i] = [
            instr & 0xFF,
            (instr >> 8) & 0xFF,
            (instr >> 16) & 0xFF,
            (instr >> 24) & 0xFF,
        ]
    
    return pixels

def main():
    print("=" * 70)
    print("CSR Dump Test - Diagnose push_off/pop_off Issue")
    print("=" * 70)
    
    pixels = build_csr_test()
    
    print(f"\nBuilt test binary: {pixels.shape}")
    print("\nThis test:")
    print("1. Reads initial mstatus")
    print("2. Reads initial sstatus")
    print("3. Simulates intr_off() (clears SIE via sstatus)")
    print("4. Reads sstatus again")
    print("5. Checks if SIE bit is cleared in mstatus")
    print("6. Checks if MIE bit is still set in mstatus")
    print("\nExpected behavior:")
    print("- Before intr_off(): SIE bit (1) should be whatever state")
    print("- After intr_off(): SIE bit (1) should be 0")
    print("- MIE bit (3) controls actual interrupt enable")
    print("- If MIE=1, interrupts are enabled even if SIE=0!")
    
    np.save('csr_test_pixels.npy', pixels)
    print(f"\nSaved: csr_test_pixels.npy")
    print("\nTo run:")
    print("  python3 boot_gpu_execute.py csr_test_pixels.npy 0 0")

if __name__ == '__main__':
    main()