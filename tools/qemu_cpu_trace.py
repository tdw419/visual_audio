#!/usr/bin/env python3
"""
QEMU CPU trace parser - uses QEMU's -d cpu,in_asm flag.

This avoids GDB entirely by parsing QEMU's native trace output.
"""

import subprocess
import sys
import argparse
import re
from pathlib import Path


def parse_qemu_trace(trace_file: str, target_pc: int = None, window: int = 1000):
    """
    Parse QEMU -d cpu,in_asm trace file.
    
    QEMU output format:
    ----------------
    IN: <bytes>
    Priv: 3; Virt: 0
    0x<pc>:  <bytes>  <opcode> <operands>  # comment
    
    <reg1>   <value> <reg2> <value> ...
    (all x0..x31, pc, and many CSRs)
    
    ----------------
    
    Returns list of entries: {pc, instr, regs: {x0..x31, pc, csrs}}
    
    Note: QEMU's virt machine starts at 0x1000 (reset vector) even with -bios none.
    The actual kernel entry point (e.g., 0x80000000) is reached later.
    """
    entries = []
    
    with open(trace_file, 'r') as f:
        current_pc = None
        current_instr = None
        regs = {}
        
        for line in f:
            # Skip separators
            if line.strip() == '----------------':
                continue
            
            # Skip Priv/Virt/IN: lines
            if line.startswith('Priv:') or line.startswith('IN:') or line.strip().startswith('IN:'):
                continue
            
            # Disassembly: "0x80000000:  00000097  auipc    ra,0  # 0x0"
            disasm = re.match(r'^\s*(0x[0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$', line)
            if disasm:
                # Save previous entry if we have one
                if current_pc is not None:
                    entries.append({
                        'pc': current_pc,
                        'instr': current_instr,
                        'regs': regs.copy()
                    })
                
                current_pc = int(disasm.group(1), 16)
                # Full instruction includes bytes and disassembly
                full_instr = f"{disasm.group(2)} {disasm.group(3)}"
                current_instr = full_instr.strip()
                regs = {}
                continue
            
            # Parse registers - line format: "x0/zero  0x0000000000000000 x1/ra    ..."
            # Also CSR lines: "mstatus  0x0000000a00000000"
            reg_match = re.match(r'^\s*([a-z0-9_/]+)\s+(0x[0-9a-f]+)', line)
            if reg_match:
                reg_name = reg_match.group(1).split('/')[0]  # Remove aliases like /zero
                reg_val = int(reg_match.group(2), 16)
                regs[reg_name] = reg_val
        
        # Don't forget last entry
        if current_pc is not None:
            entries.append({'pc': current_pc, 'instr': current_instr, 'regs': regs})
    
    # Filter to window around target PC if specified
    if target_pc is not None:
        # Find index where PC is closest to target
        for i, entry in enumerate(entries):
            if entry['pc'] == target_pc:
                start = max(0, i - window // 2)
                end = min(len(entries), i + window // 2)
                return entries[start:end], i
            # Or find first PC >= target
            if entry['pc'] >= target_pc:
                start = max(0, i - window // 2)
                end = min(len(entries), i + window // 2)
                return entries[start:end], i
    
    return entries, None


def bounded_qemu_trace(kernel_path: Path, max_instructions: int = 10000, 
                       output_trace: str = '/tmp/qemu_cpu_trace.log'):
    """
    Run QEMU with bounded instruction count using -icount.
    """
    # Use -icount with auto option and monitor via QMP
    # Strategy: run with -d cpu,in_asm, kill after N instructions via simple timeout
    
    trace_file = Path(output_trace)
    
    qemu_cmd = [
        'qemu-system-riscv64',
        '-M', 'virt',
        '-bios', 'none',
        '-kernel', str(kernel_path),
        '-m', '128M',
        '-nographic',
        '-d', 'cpu,in_asm',  # Dump CPU state and disassembly
        '-D', str(trace_file),
        '-singlestep',  # Trace every instruction
    ]
    
    print(f"Running: {' '.join(qemu_cmd)}")
    print(f"Will kill after ~{max_instructions} instructions")
    
    with open(trace_file, 'w') as trace_f:
        qemu_proc = subprocess.Popen(
            qemu_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        # Wait for trace to grow, then kill
        import time
        last_size = 0
        stuck_count = 0
        
        for _ in range(300):  # Max 5 minutes
            time.sleep(1)
            if not trace_file.exists():
                continue
            
            current_size = trace_file.stat().st_size
            if current_size == last_size:
                stuck_count += 1
                if stuck_count >= 5:  # Stuck for 5 seconds
                    print("QEMU appears stuck, killing")
                    break
            else:
                stuck_count = 0
                last_size = current_size
            
            # Rough estimate: ~100 bytes per instruction in trace
            estimated_instructions = current_size // 100
            if estimated_instructions >= max_instructions:
                print(f"Reached ~{estimated_instructions} instructions, stopping")
                break
        
        qemu_proc.kill()
        qemu_proc.wait()
    
    print(f"Trace written to {trace_file}")
    return trace_file


def main():
    parser = argparse.ArgumentParser(description='QEMU CPU trace parser')
    parser.add_argument('kernel', help='RISC-V ELF kernel')
    parser.add_argument('--max-instructions', type=int, default=10000,
                        help='Max instructions to trace (default: 10000)')
    parser.add_argument('--target-pc', type=lambda x: int(x, 0),
                        help='Target PC for window extraction')
    parser.add_argument('--window', type=int, default=1000,
                        help='Instruction window size (default: 1000)')
    parser.add_argument('--output', '-o', default='/tmp/qemu_cpu_trace.log',
                        help='Trace output file')
    parser.add_argument('--parse-only', action='store_true',
                        help='Only parse existing trace, do not run QEMU')
    
    args = parser.parse_args()
    
    if not args.parse_only:
        bounded_qemu_trace(
            Path(args.kernel),
            args.max_instructions,
            args.output
        )
    
    # Parse trace
    print(f"\nParsing {args.output}...")
    entries, target_idx = parse_qemu_trace(args.output, args.target_pc, args.window)
    
    if target_idx is not None:
        print(f"Found target PC at instruction {target_idx}")
    
    # Print sample
    print(f"\nFirst 5 instructions:")
    for i, entry in enumerate(entries[:5]):
        print(f"{i}: PC={entry['pc']:016x}  {entry['instr']}")
        if entry['regs']:
            # Show first few regs
            sample_regs = list(entry['regs'].items())[:5]
            for reg, val in sample_regs:
                print(f"   {reg}={val:016x}")
            if len(entry['regs']) > 5:
                print(f"   ... and {len(entry['regs'])-5} more")
    
    print(f"\nTotal entries: {len(entries)}")


if __name__ == '__main__':
    main()