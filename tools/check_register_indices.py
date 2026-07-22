#!/usr/bin/env python3
"""
Check which Python index maps to which RISC-V register.
Dump all register indices to find the mapping.
"""

import sys
sys.path.insert(0, str(sys.path[0]))
from riscv_gpu_cpu import CPU_DTYPE
import numpy as np

cpu = np.zeros(1, dtype=CPU_DTYPE)

# Set x18 to 0x1234567890ABCDEF (a6 / s2)
cpu[0]['regs'][18] = [0x90ABCDEF, 0x12345678]

# Set x12 to 0xFEDCBA0987654321 (a2)
cpu[0]['regs'][12] = [0x87654321, 0xFEDCBA09]

print("Register mapping check:")
print(f"  x12 (a2) = regs[12] = lo=0x{cpu[0]['regs'][12][0]:08x}, hi=0x{cpu[0]['regs'][12][1]:08x}")
print(f"  x18 (a6) = regs[18] = lo=0x{cpu[0]['regs'][18][0]:08x}, hi=0x{cpu[0]['regs'][18][1]:08x}")
print("\nAccording to RISC-V ABI:")
print("  x12 = a2")
print("  x18 = s2 (also called a6 in some contexts)")
print("\nChecking other nearby registers:")
for i in range(16, 20):
    lo, hi = cpu[0]['regs'][i]
    print(f"  x{i} = lo=0x{lo:08x}, hi=0x{hi:08x}")