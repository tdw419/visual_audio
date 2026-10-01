#!/usr/bin/env python3
"""
Decode the sw instruction manually.
"""

instr = 0x6f27ac23

print(f"Instruction: 0x{instr:08x}")
print(f"Binary: {instr:032b}")

opcode = instr & 0x7F
funct3 = (instr >> 12) & 0x7
rs1 = (instr >> 15) & 0x1F
rs2 = (instr >> 20) & 0x1F
imm_11_5 = (instr >> 25) & 0x7F
imm_4_0 = (instr >> 7) & 0x1F

print(f"\nOpcode: {opcode} (0b{opcode:07b})")
print(f"funct3: {funct3} (0b{funct3:03b})")
print(f"rs1: {rs1} (x{rs1})")
print(f"rs2: {rs2} (x{rs2})")
print(f"imm[11:5]: {imm_11_5} (0b{imm_11_5:07b})")
print(f"imm[4:0]: {imm_4_0} (0b{imm_4_0:05b})")

imm = (imm_11_5 << 5) | imm_4_0
# Sign extend from 12 bits
if imm & 0x800:
    imm = imm | 0xFFFFF000

print(f"\nimm: {imm} (signed)")

print("\nS-type format check:")
print("  imm[11:5] = bits [31:25]")
print("  rs2 = bits [24:20]")
print("  rs1 = bits [19:15]")
print("  funct3 = bits [14:12]")
print("  imm[4:0] = bits [11:7]")
print("  opcode = bits [6:0]")

# Verify with disassembly
import subprocess
result = subprocess.run(
    ['riscv64-linux-gnu-objdump', '-d', '/tmp/xv6-riscv/kernel/kernel'],
    capture_output=True, text=True
)
for line in result.stdout.split('\n'):
    if '80000abc:' in line:
        print(f"\nDisassembly: {line.strip()}")