#!/usr/bin/env python3
"""
Simple QEMU GDB tracer - captures CPU state at specific instruction points.

Usage:
    simple_qemu_trace.py <kernel.elf> --pc 0x8000103c --before 10 --after 10
"""

import subprocess
import sys
import argparse
import re
import time
from pathlib import Path


def parse_gdb_registers(output: str) -> dict:
    """Parse 'info registers' output from GDB"""
    regs = {}
    for line in output.split('\n'):
        # Match: "x0             0x0000000000000000      0"
        match = re.match(r'^\s*(x\d+|pc|ra|sp|gp|tp)\s+(0x[0-9a-f]+)', line)
        if match:
            regs[match.group(1)] = int(match.group(2), 16)
    return regs


def trace_at_pc(kernel_path: Path, target_pc: int, before: int = 10, after: int = 10):
    """
    Trace around a specific PC using GDB.
    
    Strategy:
    1. Set breakpoint at target PC
    2. Continue to breakpoint
    3. Singlestep N times (before + after)
    4. Capture register state at each step
    """
    
    # Build GDB script
    script_lines = [
        'target remote :1234',
        'set pagination off',
        'set confirm off',
        f'break *{target_pc:#x}',
        'continue',
    ]
    
    # Singlestep and capture
    total_steps = before + after
    for i in range(total_steps):
        script_lines.append('si')
        script_lines.append(f'echo --- STEP {i-before} ---')
        script_lines.append('')  # Empty line for echo's \n
        script_lines.append('info registers')
        script_lines.append('echo ---')
        script_lines.append('')
    
    script_lines.append('quit')
    
    # Write script
    script_path = Path('/tmp/qemu_trace_script.gdb')
    with open(script_path, 'w') as f:
        f.write('\n'.join(script_lines))
    
    # Start QEMU with GDB server
    qemu_cmd = [
        'qemu-system-riscv64',
        '-M', 'virt',
        '-bios', 'none',
        '-kernel', str(kernel_path),
        '-m', '128M',
        '-nographic',
        '-s',  # GDB on :1234
        '-S',  # Wait for GDB
    ]
    
    print(f"Starting QEMU: {' '.join(qemu_cmd)}")
    qemu_proc = subprocess.Popen(
        qemu_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    time.sleep(2)  # Let QEMU start
    
    # Run GDB - use system gdb with --interpreter=mi2 for machine-readable output
    print(f"Running GDB to trace around {target_pc:#x}")
    try:
        gdb_result = subprocess.run(
            ['gdb', '-batch', '-x', str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("GDB timed out")
        qemu_proc.kill()
        qemu_proc.wait()
        return None
    except FileNotFoundError:
        print("Error: gdb not found in PATH")
        qemu_proc.kill()
        qemu_proc.wait()
        return None
    
    # Cleanup
    qemu_proc.kill()
    qemu_proc.wait()
    
    # Parse output
    entries = []
    lines = gdb_result.stdout.split('\n')
    current_step = None
    
    for line in lines:
        step_match = re.match(r'^--- STEP ([-\d]+) ---$', line)
        if step_match:
            if current_step is not None:
                entries.append(current_step)
            current_step = {'step': int(step_match.group(1)), 'regs': {}}
            continue
        
        if current_step is None:
            continue
        
        # Look for separator
        if line.strip() == '---':
            continue
        
        # Parse register
        reg_match = re.match(r'^\s*(x\d+|pc|ra|sp|gp|tp)\s+(0x[0-9a-f]+)', line)
        if reg_match:
            current_step['regs'][reg_match.group(1)] = int(reg_match.group(2), 16)
    
    if current_step is not None:
        entries.append(current_step)
    
    return entries


def main():
    parser = argparse.ArgumentParser(description='Simple QEMU tracer for PC window')
    parser.add_argument('kernel', help='Path to RISC-V ELF kernel')
    parser.add_argument('--pc', type=lambda x: int(x, 0), required=True,
                        help='Target PC to trace around')
    parser.add_argument('--before', type=int, default=10,
                        help='Instructions before target PC (default: 10)')
    parser.add_argument('--after', type=int, default=10,
                        help='Instructions after target PC (default: 10)')
    parser.add_argument('--output', '-o', default='/tmp/qemu_trace.txt',
                        help='Output file (default: /tmp/qemu_trace.txt)')
    
    args = parser.parse_args()
    
    entries = trace_at_pc(Path(args.kernel), args.pc, args.before, args.after)
    
    if entries is None:
        sys.exit(1)
    
    # Write human-readable trace
    with open(args.output, 'w') as f:
        for entry in entries:
            f.write(f"Step {entry['step']}: PC={entry['regs'].get('pc', 'N/A'):016x}\n")
            for reg in sorted(entry['regs'].keys()):
                if reg != 'pc':
                    f.write(f"  {reg:3s} = {entry['regs'][reg]:016x}\n")
            f.write('\n')
    
    print(f"Wrote {len(entries)} steps to {args.output}")


if __name__ == '__main__':
    main()