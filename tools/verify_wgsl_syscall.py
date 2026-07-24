#!/usr/bin/env python3
"""Verify SYSCALL (WRITE/EXIT/UNKNOWN) WGSL port against GlyphCPUv2 ground truth."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
from tools.verify_wgsl_glyph_isa_v2 import run_python_ground_truth, run_wgsl

# WRITE: write 3 bytes starting at scratch addr 300, result in r4.
PROGRAM_WRITE = [
    "LDI r1 300",     # 0: r1 = addr
    "LDI r2 3",       # 1: r2 = length
    "LDI r5 111",     # 2: value to store at addr
    "ST  r1 r5",      # 3: mem[300] = 111
    "SYSCALL r4 1",   # 4: WRITE syscall, result -> r4
    "HALT",           # 5
]

# EXIT: status in r1, result mirrored into r4, CPU halts.
PROGRAM_EXIT = [
    "LDI r1 42",      # 0: exit status
    "SYSCALL r4 5",   # 1: EXIT syscall, result -> r4 (should mirror r1)
    "LDI r4 999",     # 2: should NOT execute (EXIT halts immediately)
    "HALT",           # 3
]

# UNKNOWN: syscall 8 - not WRITE/READ/FILE_*/DEBUG/EXIT (0x01-0x06) and
# below the GeOS MMIO range (0x10-0xFF), so it should hit the true
# "unknown syscall" fallback (-1 / 0xFFFFFFFF).
PROGRAM_UNKNOWN = [
    "SYSCALL r4 8",   # 0: unknown syscall -> -1 / 0xFFFFFFFF
    "HALT",           # 1
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
        print(f"  r{r}: python={py_val} (0x{py_val:08x}) gpu={gpu_val} (0x{gpu_val:08x}) {'OK' if match else 'MISMATCH'}")
    print(f"  python output: {py_cpu.output}")
    print(f"  python running: {py_cpu.running}, gpu running: {int(gpu_cpu['running'])}")

    opcode_map.close()
    return ok


def main():
    ok1 = check("SYSCALL WRITE", PROGRAM_WRITE, [1, 2, 4])
    ok2 = check("SYSCALL EXIT", PROGRAM_EXIT, [1, 4])
    ok3 = check("SYSCALL UNKNOWN", PROGRAM_UNKNOWN, [4])

    if ok1 and ok2 and ok3:
        print("\nALL MATCH")
        return 0
    print("\nMISMATCH DETECTED")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
