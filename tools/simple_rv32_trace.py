#!/usr/bin/env python3
"""
Simple RV32 trace capturer for RV64 development.

Captures PC, register state, and basic execution info from RV32 emulator.
This is ground truth for verifying RV64 behavior.

Usage:
    python3 tools/simple_rv32_trace.py --capture boot --steps 5000
    python3 tools/simple_rv32_trace.py --verify rv64_output.json
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore


def capture_boot_trace(steps: int = 5000, output_path: str = "tools/rv32_boot_trace.json"):
    """Capture execution trace during xv6 boot."""
    print("=" * 70)
    print("CAPTURING RV32 BOOT TRACE")
    print("=" * 70)

    kernel_path = "boot_images/xv6.img"

    # Load kernel
    print(f"Loading kernel: {kernel_path}")
    with open(kernel_path, 'rb') as f:
        kernel = f.read()

    core = SpatialRV32ICore(memory_size_bytes=64 * 1024 * 1024)
    RAM_BASE = 0x80000000
    core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)
    print("✓ Kernel loaded")

    # Capture trace
    trace = []
    for i in range(steps):
        # Get state before
        state = core.get_state()
        pc = state.get('pc', 0)

        # Read instruction
        try:
            instr = core.read_mem_word(pc)
        except:
            instr = 0

        # Get registers
        regs = state.get('registers', {})

        # Get CSRs
        csr = {
            'mstatus': state.get('mstatus', 0),
            'mtvec': state.get('mtvec', 0),
            'satp': state.get('satp', 0),
            'mepc': state.get('mepc', 0),
            'mcause': state.get('mcause', 0),
        }

        # Decode instruction
        decoded = decode_instruction(instr)

        # Step
        core.step(steps=1)

        # Save trace entry (convert numpy types to int for JSON)
        entry = {
            'step': i,
            'pc': int(pc),
            'instruction': int(instr),
            'decoded': decoded,
            'registers': {int(k): int(v) for k, v in regs.items()},
            'csr': {k: int(v) for k, v in csr.items()},
        }

        trace.append(entry)

        if i % 1000 == 0:
            print(f"  Captured {i}/{steps} instructions")

    # Save trace
    data = {
        'metadata': {
            'kernel': kernel_path,
            'steps_captured': steps,
            'isa': 'RV32IMAC',
            'purpose': 'RV64 development ground truth'
        },
        'trace': trace
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved trace to: {output_path}")
    print(f"  Instructions: {len(trace)}")

    return output_path


def decode_instruction(instr: int) -> str:
    """Simple RISC-V instruction decoder."""
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F

    # R-type
    if opcode == 0x33:
        name = "unknown"
        if funct7 == 0x00:
            if funct3 == 0x00: name = "add"
            elif funct3 == 0x07: name = "and"
            elif funct3 == 0x06: name = "or"
            elif funct3 == 0x04: name = "xor"
        elif funct7 == 0x20 and funct3 == 0x00:
            name = "sub"
        return f"{name} x{rd}, x{rs1}, x{rs2}"

    # I-type (arithmetic)
    elif opcode == 0x13:
        imm = instr >> 20
        imm = imm if imm < 0x800 else imm - 0x1000
        name = "unknown"
        if funct3 == 0x00: name = "addi"
        elif funct3 == 0x07: name = "andi"
        elif funct3 == 0x06: name = "ori"
        elif funct3 == 0x04: name = "xori"
        elif funct3 == 0x03: name = "slti"
        return f"{name} x{rd}, x{rs1}, {imm}"

    # Load
    elif opcode == 0x03:
        imm = instr >> 20
        imm = imm if imm < 0x800 else imm - 0x1000
        name = "unknown"
        if funct3 == 0x00: name = "lb"
        elif funct3 == 0x01: name = "lh"
        elif funct3 == 0x02: name = "lw"
        elif funct3 == 0x04: name = "lbu"
        elif funct3 == 0x05: name = "lhu"
        return f"{name} x{rd}, {imm}(x{rs1})"

    # Store
    elif opcode == 0x23:
        imm = ((instr >> 7) & 0x1F) | ((instr >> 25) & 0x7F) << 5
        imm = imm if imm < 0x1000 else imm - 0x2000
        name = "unknown"
        if funct3 == 0x00: name = "sb"
        elif funct3 == 0x01: name = "sh"
        elif funct3 == 0x02: name = "sw"
        return f"{name} x{rs2}, {imm}(x{rs1})"

    # Branch
    elif opcode == 0x63:
        imm = ((instr >> 8) & 0xF) << 1 | ((instr >> 25) & 0x3F) << 5 | \
               ((instr >> 7) & 0x1) << 11 | ((instr >> 31) & 0x1) << 12
        imm = imm if imm < 0x1000 else imm - 0x2000
        name = "unknown"
        if funct3 == 0x00: name = "beq"
        elif funct3 == 0x01: name = "bne"
        elif funct3 == 0x04: name = "blt"
        elif funct3 == 0x05: name = "bge"
        return f"{name} x{rs1}, x{rs2}, {pc + imm}"

    # JAL
    elif opcode == 0x6F:
        imm = ((instr >> 21) & 0x3FF) << 1 | ((instr >> 20) & 0x1) << 11 | \
               ((instr >> 12) & 0xFF) << 12 | ((instr >> 31) & 0x1) << 20
        imm = imm if imm < 0x100000 else imm - 0x200000
        return f"jal x{rd}, {pc + imm}"

    # JALR
    elif opcode == 0x67:
        imm = instr >> 20
        imm = imm if imm < 0x800 else imm - 0x1000
        return f"jalr x{rd}, {imm}(x{rs1})"

    # LUI
    elif opcode == 0x37:
        imm = instr & 0xFFFFF000
        return f"lui x{rd}, {imm >> 12}"

    # AUIPC
    elif opcode == 0x17:
        imm = instr & 0xFFFFF000
        return f"auipc x{rd}, {pc + (imm >> 12)}"

    # SYSTEM
    elif opcode == 0x73:
        if funct3 == 0x000:
            return "ecall"
        elif funct3 == 0x001:
            csr_num = (instr >> 20) & 0xFFF
            return f"csrrw x{rd}, 0x{csr_num:x}, x{rs1}"
        elif funct3 == 0x002:
            csr_num = (instr >> 20) & 0xFFF
            return f"csrrs x{rd}, 0x{csr_num:x}, x{rs1}"
        elif funct3 == 0x003:
            csr_num = (instr >> 20) & 0xFFF
            return f"csrrc x{rd}, 0x{csr_num:x}, x{rs1}"
        elif funct3 == 0x005:
            csr_num = (instr >> 20) & 0xFFF
            return f"csrrwi x{rd}, 0x{csr_num:x}, {rs1}"

    # FENCE
    elif opcode == 0x0F:
        if funct3 == 0x000:
            return "fence"
        elif funct3 == 0x001:
            return "fence.i"

    # MRET/SRET
    elif opcode == 0x73:
        if instr == 0x30200073:
            return "mret"
        elif instr == 0x10200073:
            return "sret"

    return f"unknown_{hex(instr)}"


def analyze_for_rv64(trace_path: str):
    """Analyze trace to extract patterns useful for RV64."""
    print("=" * 70)
    print("RV64 DEVELOPMENT ANALYSIS")
    print("=" * 70)

    with open(trace_path) as f:
        data = json.load(f)

    trace = data['trace']
    print(f"\nLoaded {len(trace)} instructions from trace")

    # Analyze instruction types
    inst_types = {}
    for entry in trace:
        inst = entry['decoded'].split()[0]
        inst_types[inst] = inst_types.get(inst, 0) + 1

    print("\nTop 10 instruction types:")
    for inst, count in sorted(inst_types.items(), key=lambda x: -x[1])[:10]:
        print(f"  {inst:12s}: {count:5d} ({count/len(trace)*100:.1f}%)")

    # Find arithmetic operations (critical for RV64 verification)
    arith = [e for e in trace if any(op in e['decoded'] for op in ['add', 'sub', 'and', 'or', 'xor', 'sll', 'srl', 'sra'])]
    print(f"\nArithmetic operations: {len(arith)}")
    if arith:
        print(f"  Sample: {arith[0]['decoded']}")
        print(f"    PC: 0x{arith[0]['pc']:08x}")
        print(f"    Registers: x5={hex(arith[0]['registers'].get(5, 0))}, x10={hex(arith[0]['registers'].get(10, 0))}")

    # Find memory operations (critical for Sv39 verification)
    mem_ops = [e for e in trace if any(op in e['decoded'] for op in ['lw', 'sw', 'lb', 'sb', 'lh', 'sh'])]
    print(f"\nMemory operations: {len(mem_ops)}")
    if mem_ops:
        print(f"  Sample: {mem_ops[0]['decoded']}")
        print(f"    PC: 0x{mem_ops[0]['pc']:08x}")
        print(f"    SATP: 0x{mem_ops[0]['csr'].get('satp', 0):08x}")

    # Find CSR operations (critical for privilege verification)
    csr_ops = [e for e in trace if 'csr' in e['decoded'] or 'ecall' in e['decoded']]
    print(f"\nCSR operations: {len(csr_ops)}")
    if csr_ops:
        print(f"  Sample: {csr_ops[0]['decoded']}")
        print(f"    PC: 0x{csr_ops[0]['pc']:08x}")
        print(f"    MSTATUS: 0x{csr_ops[0]['csr'].get('mstatus', 0):08x}")
        print(f"    SATP: 0x{csr_ops[0]['csr'].get('satp', 0):08x}")

    print(f"\nFirst 5 instructions:")
    for entry in trace[:5]:
        print(f"  0x{entry['pc']:08x}: {entry['decoded']}")


def main():
    parser = argparse.ArgumentParser(description="Simple RV32 trace capture for RV64 development")
    parser.add_argument('--capture', choices=['boot'], help="What to capture")
    parser.add_argument('--steps', type=int, default=5000, help="Number of instructions to capture")
    parser.add_argument('--output', '-o', default="tools/rv32_boot_trace.json", help="Output trace path")
    parser.add_argument('--analyze', help="Analyze existing trace file")

    args = parser.parse_args()

    if args.analyze:
        analyze_for_rv64(args.analyze)
    elif args.capture:
        capture_boot_trace(args.steps, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()