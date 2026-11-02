#!/usr/bin/env python3
"""
Diff QEMU trace against GPU emulator trace.

Compares instruction-by-instruction CPU state between QEMU (reference) 
and our WGSL GPU emulator (implementation).
"""

import sys
import json
import argparse
from pathlib import Path


def load_qemu_trace(trace_file: str):
    """Load parsed QEMU trace from JSON"""
    entries = []
    with open(trace_file, 'r') as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def load_gpu_trace(trace_file: str):
    """
    Load GPU emulator trace.
    
    Expected format: JSONL with entries like:
    {pc: 0x80000000, instr: "0x00000097", regs: {x0: 0, ..., pc: 0x80000000}}
    """
    entries = []
    with open(trace_file, 'r') as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def compare_state(qemu_regs: dict, gpu_regs: dict, ignore_regs=None):
    """
    Compare register states. Only compares registers present in BOTH sides.
    
    Returns: (match, differences_dict)
    """
    if ignore_regs is None:
        ignore_regs = set()
    
    differences = {}
    
    # Only compare regs that exist in both traces
    common_regs = set(qemu_regs.keys()) & set(gpu_regs.keys()) - ignore_regs
    
    for reg in sorted(common_regs):
        qemu_val = qemu_regs.get(reg, None)
        gpu_val = gpu_regs.get(reg, None)
        
        if qemu_val != gpu_val:
            differences[reg] = {
                'qemu': qemu_val,
                'gpu': gpu_val
            }
    
    return len(differences) == 0, differences


def find_alignment_point(qemu_trace, gpu_trace, pc: int):
    """
    Find the instruction index where both traces reach PC.
    
    Returns: (qemu_idx, gpu_idx) or (None, None) if not found
    """
    qemu_idx = None
    gpu_idx = None
    
    for i, entry in enumerate(qemu_trace):
        if entry.get('pc') == pc:
            qemu_idx = i
            break
    
    for i, entry in enumerate(gpu_trace):
        if entry.get('pc') == pc:
            gpu_idx = i
            break
    
    return qemu_idx, gpu_idx


def diff_traces(qemu_trace, gpu_trace, start_pc: int = None, 
                 max_instructions: int = 100, ignore_regs: set = None):
    """
    Diff two traces and report first mismatch.
    
    Args:
        qemu_trace: List of QEMU trace entries
        gpu_trace: List of GPU trace entries
        start_pc: Align at this PC (if None, start from beginning)
        max_instructions: Max instructions to compare
    """
    print(f"QEMU trace: {len(qemu_trace)} instructions")
    print(f"GPU trace: {len(gpu_trace)} instructions")
    
    # Allow extracting QEMU's initial state for GPU initialization
    # Find first kernel entry (PC >= KERNEL_BASE)
    for qemu_entry in qemu_trace:
        if qemu_entry['pc'] >= 0x80000000:
            # Save as reference init state
            import json
            ref_path = '/tmp/qemu_kernel_init_state.json'
            init_state = {
                'pc': qemu_entry['pc'],
                'regs': {k: v for k, v in qemu_entry['regs'].items() 
                         if not k.startswith('h')}  # Skip h-mode CSRs
            }
            with open(ref_path, 'w') as f:
                json.dump(init_state, f)
            print(f"Saved QEMU init state (at PC=0x{qemu_entry['pc']:016x}) to {ref_path}")
            break
    
    # Find alignment point
    start_qemu, start_gpu = 0, 0
    
    if start_pc is not None:
        start_qemu, start_gpu = find_alignment_point(qemu_trace, gpu_trace, start_pc)
        if start_qemu is None:
            print(f"Warning: Could not find PC {start_pc:#x} in QEMU trace")
        if start_gpu is None:
            print(f"Warning: Could not find PC {start_pc:#x} in GPU trace")
        print(f"Aligned at PC={start_pc:#x}: QEMU idx={start_qemu}, GPU idx={start_gpu}")
    
    # Compare from alignment point
    qemu_pos = start_qemu if start_qemu is not None else 0
    gpu_pos = start_gpu if start_gpu is not None else 0
    
    compared = 0
    while compared < max_instructions:
        if qemu_pos >= len(qemu_trace):
            print(f"QEMU trace exhausted at instruction {compared}")
            break
        if gpu_pos >= len(gpu_trace):
            print(f"GPU trace exhausted at instruction {compared}")
            break
        
        qemu_entry = qemu_trace[qemu_pos]
        gpu_entry = gpu_trace[gpu_pos]
        
        # Check PC matches
        if qemu_entry['pc'] != gpu_entry['pc']:
            print(f"\nMismatch at instruction {compared}:")
            print(f"  QEMU PC: {qemu_entry['pc']:016x}")
            print(f"  GPU  PC: {gpu_entry['pc']:016x}")
            return False
        
        # Compare registers (ignore boot ROM regs)
        effective_ignore = ignore_regs | {'mhartid'} if ignore_regs else {'mhartid'}
        match, diffs = compare_state(qemu_entry['regs'], gpu_entry['regs'], 
                                     effective_ignore)
        
        if not match:
            print(f"\nFirst mismatch at instruction {compared} (PC={qemu_entry['pc']:016x}):")
            print(f"  QEMU instr: {qemu_entry.get('instr', 'N/A')}")
            print(f"  GPU  instr: {gpu_entry.get('instr', 'N/A')}")
            print(f"\n  Register differences:")
            for reg, values in sorted(diffs.items())[:5]:  # Show first 5
                qv = values['qemu']
                gv = values['gpu']
                if qv is not None and gv is not None:
                    print(f"    {reg}: QEMU={qv:016x}, GPU={gv:016x}")
                else:
                    print(f"    {reg}: QEMU={qv}, GPU={gv}")
            if len(diffs) > 5:
                print(f"    ... and {len(diffs)-5} more")
            return False
        
        compared += 1
        qemu_pos += 1
        gpu_pos += 1
    
    print(f"\n✓ Compared {compared} instructions - all matched!")
    return True


def main():
    parser = argparse.ArgumentParser(description='Diff QEMU vs GPU RISC-V traces')
    parser.add_argument('--qemu-trace', required=True,
                        help='QEMU trace file (JSONL from qemu_cpu_trace.py)')
    parser.add_argument('--gpu-trace', required=True,
                        help='GPU emulator trace file (JSONL)')
    parser.add_argument('--start-pc', type=lambda x: int(x, 0),
                        help='Align at this PC (default: start from beginning)')
    parser.add_argument('--max-instructions', type=int, default=100,
                        help='Max instructions to compare (default: 100)')
    parser.add_argument('--ignore-regs', type=str, default='',
                        help='Comma-separated registers to ignore (e.g. x2,x3,x10,x11)')
    
    args = parser.parse_args()
    
    ignore_regs = set()
    if args.ignore_regs:
        ignore_regs = set(r.strip() for r in args.ignore_regs.split(','))
    
    qemu_trace = load_qemu_trace(args.qemu_trace)
    gpu_trace = load_gpu_trace(args.gpu_trace)
    
    success = diff_traces(qemu_trace, gpu_trace, args.start_pc, args.max_instructions, ignore_regs)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()