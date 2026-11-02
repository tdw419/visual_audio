#!/usr/bin/env python3
"""
Demonstrate cross-validation between GPU and Python (QEMU-like) emulators.

This script:
1. Runs the same RV32I program on both emulators
2. Generates trace files in the format expected by diff_qemu_gpu_traces.py
3. Runs the diff tool to verify they produce identical results

For a true QEMU comparison, replace the Python emulator trace with actual
QEMU trace output from tools/qemu_cpu_trace.py.
"""

import sys
import json
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))

import benchmark_spatial_cpu
from rv32i_asm import assemble

def simple_rv32i_emulator(binary_data: bytes, entry_point: int = 0, max_instructions: int = 100000):
    """
    Simple Python RV32I emulator for comparison.
    This mimics QEMU behavior for the subset we use.
    """
    import struct

    # Parse binary into instructions
    padded = binary_data + b'\x00' * ((4 - len(binary_data) % 4) % 4)
    instructions = list(struct.unpack(f'<{len(padded)//4}I', padded))

    # Initialize CPU state
    regs = [0] * 32
    pc = entry_point

    trace = []

    def fetch(addr):
        idx = (addr - entry_point) // 4
        if 0 <= idx < len(instructions):
            return instructions[idx]
        return 0

    def sign_extend(val, bits):
        sign_bit = 1 << (bits - 1)
        return (val & (sign_bit - 1)) - (val & sign_bit)

    while True:
        instr = fetch(pc)
        if instr == 0:
            # Stop at null instruction or end of code
            break

        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F

        # Trace before execution
        trace.append({
            'pc': pc,
            'regs': {f'x{i}': int(regs[i]) for i in range(32)},
        })

        halted = False

        if opcode == 0x37:  # lui
            imm = instr & 0xFFFFF000
            regs[rd] = imm
            pc += 4

        elif opcode == 0x13:  # I-type ALU
            imm = sign_extend(instr >> 20, 12)
            if funct3 == 0:  # addi
                regs[rd] = (regs[rs1] + imm) & 0xFFFFFFFF
            elif funct3 == 1 and funct7 == 0:  # slli
                shamt = (instr >> 20) & 0x1F
                regs[rd] = (regs[rs1] << shamt) & 0xFFFFFFFF
            elif funct3 == 5 and funct7 == 0:  # srli
                shamt = (instr >> 20) & 0x1F
                regs[rd] = regs[rs1] >> shamt
            elif funct3 == 5 and funct7 == 0x20:  # srai
                shamt = (instr >> 20) & 0x1F
                val = regs[rs1]
                # Arithmetic right shift
                if val & 0x80000000:
                    val = val | 0xFFFFFFFF00000000
                regs[rd] = (val >> shamt) & 0xFFFFFFFF
            else:
                print(f'Unhandled I-type: funct3={funct3}, funct7={funct7}')
                break
            pc += 4

        elif opcode == 0x33:  # R-type ALU
            if funct7 == 1:  # M-extension
                if funct3 == 0:  # mul
                    a = regs[rs1]
                    b = regs[rs2]
                    if a & 0x80000000:
                        a = a | 0xFFFFFFFF00000000
                    if b & 0x80000000:
                        b = b | 0xFFFFFFFF00000000
                    regs[rd] = (a * b) & 0xFFFFFFFF
                elif funct3 == 1:  # mulh
                    a = regs[rs1]
                    b = regs[rs2]
                    if a & 0x80000000:
                        a = a | 0xFFFFFFFF00000000
                    if b & 0x80000000:
                        b = b | 0xFFFFFFFF00000000
                    product = a * b
                    regs[rd] = (product >> 32) & 0xFFFFFFFF
                elif funct3 == 3:  # mulhu
                    product = regs[rs1] * regs[rs2]
                    regs[rd] = (product >> 32) & 0xFFFFFFFF
                else:
                    print(f'Unhandled M-extension: funct3={funct3}')
                    break
            else:
                if funct3 == 0 and funct7 == 0:  # add
                    regs[rd] = (regs[rs1] + regs[rs2]) & 0xFFFFFFFF
                elif funct3 == 0 and funct7 == 0x20:  # sub
                    regs[rd] = (regs[rs1] - regs[rs2]) & 0xFFFFFFFF
                elif funct3 == 6 and funct7 == 0:  # or
                    regs[rd] = regs[rs1] | regs[rs2]
                elif funct3 == 7 and funct7 == 0:  # and
                    regs[rd] = regs[rs1] & regs[rs2]
                elif funct3 == 4 and funct7 == 0:  # xor
                    regs[rd] = regs[rs1] ^ regs[rs2]
                elif funct3 == 2 and funct7 == 0:  # slt
                    a = regs[rs1]
                    b = regs[rs2]
                    if a & 0x80000000:
                        a = a | 0xFFFFFFFF00000000
                    if b & 0x80000000:
                        b = b | 0xFFFFFFFF00000000
                    regs[rd] = 1 if a < b else 0
                elif funct3 == 1 and funct7 == 0:  # sll
                    regs[rd] = (regs[rs1] << (regs[rs2] & 0x1F)) & 0xFFFFFFFF
                elif funct3 == 5 and funct7 == 0:  # srl
                    regs[rd] = regs[rs1] >> (regs[rs2] & 0x1F)
                elif funct3 == 5 and funct7 == 0x20:  # sra
                    val = regs[rs1]
                    if val & 0x80000000:
                        val = val | 0xFFFFFFFF00000000
                    regs[rd] = (val >> (regs[rs2] & 0x1F)) & 0xFFFFFFFF
                else:
                    print(f'Unhandled R-type: funct3={funct3}, funct7={funct7}')
                    break
            pc += 4

        elif opcode == 0x63:  # Branch
            imm12 = (instr >> 31) & 0x1
            imm11 = (instr >> 7) & 0x1
            imm10_5 = (instr >> 25) & 0x3F
            imm4_1 = (instr >> 8) & 0xF
            imm = sign_extend((imm12 << 12) | (imm11 << 11) | (imm10_5 << 5) | (imm4_1 << 1), 13)

            taken = False
            if funct3 == 0:  # beq
                taken = (regs[rs1] == regs[rs2])
            elif funct3 == 1:  # bne
                taken = (regs[rs1] != regs[rs2])
            elif funct3 == 4:  # blt
                a = regs[rs1]
                b = regs[rs2]
                if a & 0x80000000:
                    a = a | 0xFFFFFFFF00000000
                if b & 0x80000000:
                    b = b | 0xFFFFFFFF00000000
                taken = (a < b)
            elif funct3 == 5:  # bge
                a = regs[rs1]
                b = regs[rs2]
                if a & 0x80000000:
                    a = a | 0xFFFFFFFF00000000
                if b & 0x80000000:
                    b = b | 0xFFFFFFFF00000000
                taken = (a >= b)
            else:
                print(f'Unhandled branch: funct3={funct3}')
                break

            if taken:
                pc = pc + imm
            else:
                pc += 4

        elif opcode == 0x6F:  # jal
            imm20 = (instr >> 31) & 0x1
            imm19_12 = (instr >> 12) & 0xFF
            imm11 = (instr >> 20) & 0x1
            imm10_1 = (instr >> 21) & 0x3FF
            imm = sign_extend((imm20 << 20) | (imm19_12 << 12) | (imm11 << 11) | (imm10_1 << 1), 21)

            regs[rd] = (pc + 4) & 0xFFFFFFFF
            new_pc = pc + imm

            # Detect infinite loop: self-jump to same PC
            if new_pc == pc:
                halted = True
            pc = new_pc

        else:
            print(f'Unhandled opcode: {opcode:02x} at PC={pc:08x}')
            break

        # x0 is always zero
        regs[0] = 0

        if halted:
            break

        # Safety limit
        if len(trace) > max_instructions:
            print(f'Hit trace limit ({len(trace)} entries)')
            break

    return trace

def main():
    print("=" * 60)
    print("GPU Emulator Cross-Validation Demo")
    print("=" * 60)

    # Compile test program
    print("\n1. Compiling Fibonacci loop program...")
    program = benchmark_spatial_cpu.compile_fibonacci_loop(10)
    expected_instructions = 4 + (10 * 6) + 1
    print(f"   Expected {expected_instructions} instructions")

    # Run on GPU emulator with tracing
    print("\n2. Running on GPU emulator (WGSL)...")
    gpu_trace_file = '/tmp/gpu_trace_demo.jsonl'
    gpu_core = benchmark_spatial_cpu.SpatialRV32ICore(
        1024 * 1024,
        trace_file=gpu_trace_file
    )
    gpu_core.load_program(program)

    # Execute one instruction at a time for proper trace
    for _ in range(expected_instructions):
        gpu_core.step(1)

    gpu_state = gpu_core.get_state()
    print(f"   Final PC: 0x{gpu_state['pc']:08x}")
    print(f"   Final x1: {gpu_state['regs'][1]}, x2: {gpu_state['regs'][2]}, x3: {gpu_state['regs'][3]}")
    print(f"   Trace: {len(open(gpu_trace_file).readlines())} entries")

    # Run on Python (QEMU-like) emulator
    print("\n3. Running on Python emulator (QEMU-like)...")
    py_trace = simple_rv32i_emulator(program, entry_point=0)
    py_trace_file = '/tmp/py_trace_demo.jsonl'
    with open(py_trace_file, 'w') as f:
        for entry in py_trace:
            f.write(json.dumps(entry) + '\n')

    if py_trace:
        last_entry = py_trace[-1]
        print(f"   Final PC: 0x{last_entry['pc']:08x}")
        print(f"   Final x1: {last_entry['regs']['x1']}, x2: {last_entry['regs']['x2']}, x3: {last_entry['regs']['x3']}")
        print(f"   Trace: {len(py_trace)} entries")

    # Run diff tool
    print("\n4. Comparing traces with diff_qemu_gpu_traces.py...")
    import subprocess
    result = subprocess.run([
        'python3', 'tools/diff_qemu_gpu_traces.py',
        '--qemu-trace', py_trace_file,
        '--gpu-trace', gpu_trace_file,
        '--max-instructions', str(expected_instructions)
    ], capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    print("\n" + "=" * 60)
    if result.returncode == 0:
        print("✓ CROSS-VALIDATION PASSED")
        print("  GPU emulator produces identical results to QEMU-like reference")
    else:
        print("✗ CROSS-VALIDATION FAILED")
        print("  GPU emulator behavior differs from reference")
    print("=" * 60)

    return result.returncode

if __name__ == '__main__':
    sys.exit(main())