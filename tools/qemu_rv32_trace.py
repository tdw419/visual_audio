#!/usr/bin/env python3
"""
Capture execution traces from QEMU xv6 boot for RV64 development.

This uses QEMU's RV64 emulator as the reference to capture ground truth.
QEMU is mature and correct - its traces are authoritative.

Usage:
    python3 tools/qemu_rv32_trace.py --capture --steps 5000
    python3 tools/qemu_rv32_trace.py --analyze trace.json
"""

import subprocess
import time
import json
import re
import argparse
from pathlib import Path


def boot_xv6_qemu_trace(kernel_path: str, steps: int = 5000, output: str = "tools/qemu_rv32_trace.json"):
    """
    Boot xv6 on QEMU and capture instruction trace.

    Uses QEMU's -d in_asm,cpu,exec flags to dump execution.
    """
    print("=" * 70)
    print("CAPTURING QEMU XV6 EXECUTION TRACE")
    print("=" * 70)

    # Check kernel exists
    if not Path(kernel_path).exists():
        print(f"✗ Kernel not found: {kernel_path}")
        print("\nBuild xv6 first:")
        print("  cd vendor/xv6-riscv && make kernel")
        return None

    # Check if QEMU supports RISC-V
    try:
        subprocess.run(["qemu-system-riscv64", "--version"],
                      capture_output=True, check=True)
    except:
        print("✗ qemu-system-riscv64 not found")
        return None

    # Prepare trace file
    trace_file = Path("/tmp/qemu_xv6_trace.txt")
    trace_file.unlink(missing_ok=True)

    # Boot xv6 with execution trace
    print(f"Booting xv6: {kernel_path}")
    print(f"Trace output: {trace_file}")

    # Use QEMU with -d exec,cpu,in_asm to dump execution
    # Note: This is very verbose, so we'll use a custom script to parse it
    cmd = [
        "qemu-system-riscv64",
        "-nographic",
        "-machine", "virt",
        "-bios", "none",
        "-kernel", kernel_path,
        "-m", "128M",
        "-smp", "1",
        "-d", "exec,cpu,in_asm",  # Dump execution, CPU state, assembly
        "-D", str(trace_file),
    ]

    print(f"Starting QEMU (will run for {steps} instructions)...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait a bit for boot, then terminate
    time.sleep(2)

    # Send Ctrl+A, X to quit
    try:
        proc.send_signal(2)  # SIGINT
        proc.wait(timeout=5)
    except:
        proc.kill()
        proc.wait()

    print(f"✓ QEMU stopped")

    # Parse QEMU trace
    trace = parse_qemu_trace(trace_file, steps)

    # Save as JSON
    data = {
        'metadata': {
            'kernel': kernel_path,
            'qemu_version': get_qemu_version(),
            'steps_captured': len(trace),
            'isa': 'RV64IMAC',
            'purpose': 'RV64 development ground truth from QEMU'
        },
        'trace': trace
    }

    with open(output, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved trace to: {output}")
    print(f"  Instructions: {len(trace)}")

    return output


def parse_qemu_trace(trace_file: Path, max_steps: int):
    """
    Parse QEMU -d exec trace into structured format.

    QEMU trace format (roughly):
    Trace 0x80000000 [0x80000000] 00000097  auipc ra, 0
    R00=0x00000000 R01=0x00000000 ...
    """
    if not trace_file.exists():
        print(f"✗ Trace file not found: {trace_file}")
        return []

    with open(trace_file) as f:
        content = f.read()

    trace = []
    lines = content.split('\n')

    current_pc = None
    current_instr = None
    current_decoded = None
    current_regs = {}

    for line in lines[:max_steps * 3]:  # Rough estimate
        # Look for instruction trace lines
        match = re.search(r'Trace\s+0x([0-9a-fA-F]+)\s+\[0x([0-9a-fA-F]+)\]\s+([0-9a-fA-F]+)\s+(.+)', line)
        if match:
            # Save previous entry
            if current_pc is not None:
                trace.append({
                    'pc': int(current_pc, 16),
                    'instruction': int(current_instr, 16),
                    'decoded': current_decoded,
                    'registers': current_regs.copy(),
                })

            # Start new entry
            current_pc = match.group(1)
            current_instr = match.group(3)
            current_decoded = match.group(4).strip()
            current_regs = {}

        # Look for register state
        reg_match = re.search(r'R(\d+)=0x([0-9a-fA-F]+)', line)
        if reg_match:
            reg_num = int(reg_match.group(1))
            reg_val = int(reg_match.group(2), 16)
            current_regs[reg_num] = reg_val

        if len(trace) >= max_steps:
            break

    return trace


def get_qemu_version():
    """Get QEMU version."""
    try:
        result = subprocess.run(["qemu-system-riscv64", "--version"],
                              capture_output=True, text=True)
        return result.stdout.strip()
    except:
        return "unknown"


def analyze_for_rv64(trace_path: str):
    """Analyze QEMU trace for RV64 development."""
    print("=" * 70)
    print("RV64 DEVELOPMENT ANALYSIS (FROM QEMU)")
    print("=" * 70)

    with open(trace_path) as f:
        data = json.load(f)

    trace = data['trace']
    print(f"\nLoaded {len(trace)} instructions from QEMU trace")
    print(f"QEMU version: {data['metadata'].get('qemu_version', 'unknown')}")

    # Analyze instruction types
    inst_types = {}
    for entry in trace:
        inst = entry['decoded'].split()[0]
        inst_types[inst] = inst_types.get(inst, 0) + 1

    print("\nTop 15 instruction types:")
    for inst, count in sorted(inst_types.items(), key=lambda x: -x[1])[:15]:
        print(f"  {inst:12s}: {count:5d} ({count/len(trace)*100:.1f}%)")

    # Find arithmetic operations
    arith = [e for e in trace if any(op in e['decoded'] for op in ['add', 'sub', 'and', 'or', 'xor', 'sll', 'srl', 'sra'])]
    print(f"\nArithmetic operations: {len(arith)}")
    if arith:
        print(f"  Sample: {arith[0]['decoded']}")
        print(f"    PC: 0x{arith[0]['pc']:08x}")
        print(f"    Registers: x5=0x{arith[0]['registers'].get(5, 0):08x}, x10=0x{arith[0]['registers'].get(10, 0):08x}")

    # Find memory operations
    mem_ops = [e for e in trace if any(op in e['decoded'] for op in ['lw', 'sw', 'lb', 'sb', 'lh', 'sh', 'ld', 'sd'])]
    print(f"\nMemory operations: {len(mem_ops)}")
    if mem_ops:
        print(f"  Sample: {mem_ops[0]['decoded']}")
        print(f"    PC: 0x{mem_ops[0]['pc']:08x}")
        print(f"    Base register value: x{next(iter(mem_ops[0]['registers'].values())):08x}")

    # Find control flow
    control = [e for e in trace if any(op in e['decoded'] for op in ['jal', 'jalr', 'beq', 'bne', 'blt', 'bge', 'call', 'ret'])]
    print(f"\nControl flow: {len(control)}")
    if control:
        print(f"  Sample: {control[0]['decoded']}")

    # Find CSR operations
    csr = [e for e in trace if 'csr' in e['decoded'].lower() or 'mret' in e['decoded'] or 'sret' in e['decoded']]
    print(f"\nCSR operations: {len(csr)}")
    if csr:
        print(f"  Sample: {csr[0]['decoded']}")

    print(f"\nFirst 10 instructions:")
    for entry in trace[:10]:
        print(f"  0x{entry['pc']:08x}: {entry['decoded']}")


def show_verification_example(trace_path: str):
    """Show how to use QEMU traces to verify RV64."""
    print("\n" + "=" * 70)
    print("VERIFICATION EXAMPLE")
    print("=" * 70)

    with open(trace_path) as f:
        data = json.load(f)

    trace = data['trace']

    print("""
How to use this trace for RV64 development:

1. Load trace:
    with open('""" + trace_path + """') as f:
        qemu_trace = json.load(f)

2. For each instruction, verify RV64 produces identical result:

    for entry in qemu_trace['trace'][:100]:
        pc = entry['pc']
        instr = entry['instruction']
        regs_before = entry['registers']

        # Execute on RV64
        rv64_cpu.set_registers(regs_before)
        rv64_cpu.execute(instr)
        regs_after = rv64_cpu.get_registers()

        # For ADD/SUB/AND/OR: low 32 bits must match
        for reg in regs_before.keys():
            qemu_val = entry['registers'].get(reg, 0)
            rv64_val = regs_after[reg] & 0xFFFFFFFF

            if qemu_val != rv64_val:
                print(f"✗ MISMATCH at PC=0x{pc:08x}")
                print(f"  QEMU: {hex(qemu_val)}")
                print(f"  RV64: {hex(rv64_val)}")
                break

3. For LW/SW: physical address translation must match

4. For CSR operations: CSR values must be identical
""")


def main():
    parser = argparse.ArgumentParser(description="Capture QEMU xv6 traces for RV64 development")
    parser.add_argument('--capture', action='store_true', help="Capture trace from QEMU")
    parser.add_argument('--steps', type=int, default=5000, help="Instructions to capture")
    parser.add_argument('--kernel', default="vendor/xv6-riscv/kernel/kernel", help="Kernel path")
    parser.add_argument('--output', '-o', default="tools/qemu_rv32_trace.json", help="Output path")
    parser.add_argument('--analyze', help="Analyze existing trace")
    parser.add_argument('--verify', help="Show verification example")

    args = parser.parse_args()

    if args.analyze:
        analyze_for_rv64(args.analyze)
    elif args.verify:
        show_verification_example(args.verify)
    elif args.capture:
        result = boot_xv6_qemu_trace(args.kernel, args.steps, args.output)
        if result:
            analyze_for_rv64(result)
            show_verification_example(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()