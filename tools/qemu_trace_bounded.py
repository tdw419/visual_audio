#!/usr/bin/env python3
"""
Bounded QEMU tracer for GPU RISC-V emulator debugging

Captures a bounded instruction trace from QEMU to compare against our WGSL emulator.
Avoids disk exhaustion by limiting trace length to a specific window around known bugs.

Usage:
    qemu_trace_bounded.py <kernel.elf> --start-pc 0x80001000 --max-instructions 10000 --output qemu_trace.log
"""

import subprocess
import sys
import argparse
import re
import struct
from pathlib import Path


class QEMUBoundedTracer:
    """Run QEMU with bounded instruction count and capture CPU state"""

    def __init__(self, kernel_path: Path, max_instructions: int = 10000):
        self.kernel_path = Path(kernel_path)
        self.max_instructions = max_instructions
        self.trace = []

    def parse_qemu_trace(self, trace_log: str):
        """Parse QEMU -d cpu,in_asm -singlestep output"""
        entries = []
        
        with open(trace_log, 'r') as f:
            current_pc = None
            current_instr = None
            regs = {}
            
            for line in f:
                # Look for disassembly line: "0x80001000:  ..."
                disasm_match = re.match(r'^\s*(0x[0-9a-f]+):\s+(.*)$', line)
                if disasm_match:
                    if current_pc is not None:
                        # Save previous entry
                        entries.append({
                            'pc': current_pc,
                            'instr': current_instr,
                            'regs': regs.copy()
                        })
                    
                    current_pc = int(disasm_match.group(1), 16)
                    current_instr = disasm_match.group(2).strip()
                    regs = {}
                    continue
                
                # Look for register lines: "x0=0x0000000000000000"
                reg_match = re.match(r'^\s*(x\d+|pc)\s*=\s*(0x[0-9a-f]+)', line)
                if reg_match:
                    reg_name = reg_match.group(1)
                    reg_val = int(reg_match.group(2), 16)
                    regs[reg_name] = reg_val
            
            # Don't forget the last entry
            if current_pc is not None:
                entries.append({
                    'pc': current_pc,
                    'instr': current_instr,
                    'regs': regs.copy()
                })
        
        return entries

    def trace_window(self, start_pc: int = None, window_size: int = 1000):
        """
        Trace a bounded window around a specific PC.
        
        Uses GDB to:
        1. Run until we reach start_pc (if specified)
        2. Singlestep for window_size instructions
        3. Capture state at each step
        """
        # Build GDB script
        gdb_script = [
            'target remote :1234',
            'set pagination off',
            'set confirm off',
        ]
        
        if start_pc is not None:
            gdb_script.extend([
                f'break *{start_pc:#x}',
                'continue',
            ])
        
        # Singlestep and capture state
        for i in range(window_size):
            gdb_script.extend([
                'si',
                f'echo --- INSTRUCTION {i} ---\\n',
                'info registers',
                'x/i $pc',
            ])
        
        gdb_script.append('quit')
        
        gdb_script_path = Path('/tmp/qemu_trace.gdb')
        with open(gdb_script_path, 'w') as f:
            f.write('\n'.join(gdb_script))
        
        # Start QEMU in background with GDB server
        qemu_cmd = [
            'qemu-system-riscv64',
            '-M', 'virt',
            '-bios', 'none',
            '-kernel', str(self.kernel_path),
            '-m', '128M',
            '-nographic',
            '-s',  # -s shorthand for -gdb tcp::1234
            '-S',  # Start frozen, wait for GDB
        ]
        
        print(f"Starting QEMU: {' '.join(qemu_cmd)}")
        qemu_proc = subprocess.Popen(
            qemu_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        # Give QEMU time to start GDB server
        import time
        time.sleep(1)
        
        # Run GDB script
        gdb_cmd = [
            'riscv64-unknown-elf-gdb',
            '-batch',
            '-x', str(gdb_script_path),
        ]
        
        print(f"Running GDB trace: {' '.join(gdb_cmd)}")
        try:
            gdb_result = subprocess.run(
                gdb_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            print("GDB timed out - killing QEMU")
            qemu_proc.kill()
            qemu_proc.wait()
            return None
        
        # Clean up QEMU
        qemu_proc.kill()
        qemu_proc.wait()
        
        # Parse GDB output
        return self.parse_gdb_output(gdb_result.stdout)

    def parse_gdb_output(self, gdb_output: str):
        """Parse GDB's info registers and disassembly output"""
        entries = []
        lines = gdb_output.split('\n')
        
        current_entry = None
        for line in lines:
            # Instruction marker
            instr_match = re.match(r'^--- INSTRUCTION (\d+) ---$', line)
            if instr_match:
                if current_entry is not None:
                    entries.append(current_entry)
                current_entry = {'instr_num': int(instr_match.group(1)), 'regs': {}, 'instr': None}
                continue
            
            if current_entry is None:
                continue
            
            # Disassembly: "=> 0x80001000:  opcode"
            disasm_match = re.match(r'^=>\s+(0x[0-9a-f]+):\s+(.*)', line)
            if disasm_match:
                current_entry['pc'] = int(disasm_match.group(1), 16)
                current_entry['instr'] = disasm_match.group(2).strip()
                continue
            
            # Register: "x0             0x0                 0"
            reg_match = re.match(r'^\s*(x\d+|pc|sp|ra)\s+(0x[0-9a-f]+)', line)
            if reg_match:
                reg_name = reg_match.group(1)
                reg_val = int(reg_match.group(2), 16)
                current_entry['regs'][reg_name] = reg_val
        
        # Don't forget last entry
        if current_entry is not None:
            entries.append(current_entry)
        
        return entries

    def write_trace(self, entries: list, output_path: Path):
        """Write trace to JSONL file"""
        import json
        
        with open(output_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        
        print(f"Wrote {len(entries)} trace entries to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Bounded QEMU tracer for GPU RISC-V debugging')
    parser.add_argument('kernel', help='Path to RISC-V ELF kernel')
    parser.add_argument('--max-instructions', type=int, default=10000,
                        help='Maximum instructions to trace (default: 10000)')
    parser.add_argument('--start-pc', type=lambda x: int(x, 0),
                        help='Start tracing at this PC (default: entry point)')
    parser.add_argument('--output', '-o', default='/tmp/qemu_trace.jsonl',
                        help='Output trace file (default: /tmp/qemu_trace.jsonl)')
    parser.add_argument('--window-size', type=int, default=1000,
                        help='Instruction window size after start-pc (default: 1000)')
    
    args = parser.parse_args()
    
    tracer = QEMUBoundedTracer(args.kernel, args.max_instructions)
    
    print(f"Tracing {args.kernel}...")
    if args.start_pc:
        print(f"Starting at PC={args.start_pc:#x}, window={args.window_size}")
    else:
        print(f"Tracing from entry point, max={args.max_instructions}")
    
    entries = tracer.trace_window(args.start_pc, args.window_size)
    
    if entries is None:
        print("Failed to generate trace", file=sys.stderr)
        sys.exit(1)
    
    tracer.write_trace(entries, Path(args.output))
    print(f"Done: {len(entries)} instructions traced")


if __name__ == '__main__':
    main()