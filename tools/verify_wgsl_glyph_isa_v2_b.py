#!/usr/bin/env python3
"""Second verification pass: OR/XOR/SHR/LD/ST + the JMP/JZ/CMP loop demo,
to cover every opcode the first verification script didn't touch."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
from tools.verify_wgsl_glyph_isa_v2 import run_python_ground_truth, run_wgsl

# Exercises OR, XOR, SHR, LD, ST (LD/ST round-trip through image memory
# at a fixed scratch address via LDI-loaded pointers).
PROGRAM_A = [
    "LDI r1 240",    # 0: r1 = 0xF0
    "LDI r2 15",     # 1: r2 = 0x0F
    "OR  r1 r2",     # 2: r1 = 0xFF (255)
    "LDI r3 255",    # 3: r3 = 0xFF (compare target)
    "XOR r1 r3",     # 4: r1 = 0x00 (0)
    "LDI r4 200",    # 5: r4 = 200 (scratch address)
    "LDI r5 42",     # 6: r5 = 42 (value to store)
    "ST  r4 r5",     # 7: mem[200] = 42
    "LD  r6 r4",     # 8: r6 = mem[200] = 42
    "LDI r7 1",      # 9: r7 = 1
    "SHR r6 r7",     # 10: r6 = 42 >> 1 = 21
    "HALT",          # 11
]

# Loop using CMP/JZ/JMP - counts 0..4 then halts.
PROGRAM_B = [
    "LDI r5 0",       # 0: counter = 0
    "LDI r1 5",       # 1: limit = 5
    "CMP r5 r1",      # 2: r0 = (counter == limit)
    "JZ 0,1",         # 3: if equal, jump to HALT
    "PRT r5",         # 4: print counter
    "LDI r2 1",       # 5: r2 = 1
    "ADD r5 r2",      # 6: counter += 1
    "JMP 2,0",        # 7: jump back to CMP
    "HALT",           # 8
]


def check(name, program, reg_indices, width_instrs=8):
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    image = assembler.assemble(program, width_instrs=width_instrs)

    py_cpu = run_python_ground_truth(opcode_map, image)
    gpu_cpu = run_wgsl(opcode_map, image)

    ok = True
    print(f"--- {name} ---")
    for r in reg_indices:
        py_val = py_cpu.registers[r] & 0xFFFFFFFF
        gpu_val = int(gpu_cpu['registers'][r])
        match = py_val == gpu_val
        ok = ok and match
        print(f"  r{r}: python={py_val} gpu={gpu_val} {'OK' if match else 'MISMATCH'}")

    print(f"  output: python={py_cpu.output}")
    opcode_map.close()
    return ok


def main():
    ok_a = check("PROGRAM_A (OR/XOR/SHR/LD/ST)", PROGRAM_A, [1, 6], width_instrs=len(PROGRAM_A))
    ok_b = check("PROGRAM_B (CMP/JZ/JMP loop)", PROGRAM_B, [5])

    if ok_a and ok_b:
        print("\nALL MATCH")
        return 0
    print("\nMISMATCH DETECTED")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
