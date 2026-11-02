#!/usr/bin/env python3
"""
Diff QEMU reference trace against GPU emulator trace.

Finds the exact point where GPU emulator diverges from QEMU during execve.
This is the debugging tool for the EFAULT blocker.

Usage:
    python3 tools/diff_execve_traces.py \
        --qemu tools/qemu_execve_trace.json \
        --gpu tools/gpu_execve_trace.json
"""

import json
import sys
import argparse
from pathlib import Path


def load_trace(trace_path: str):
    """Load execution trace from JSON file."""
    with open(trace_path) as f:
        data = json.load(f)
    return data


def compare_instructions(qemu_entry, gpu_entry):
    """
    Compare two instruction entries and report differences.

    Returns:
        dict: Differences found, or None if identical
    """
    differences = {}

    # Compare PC
    if qemu_entry['pc'] != gpu_entry['pc']:
        differences['pc'] = {
            'qemu': qemu_entry['pc'],
            'gpu': gpu_entry['pc'],
        }

    # Compare instruction encoding
    if qemu_entry['instruction'] != gpu_entry['instruction']:
        differences['instruction'] = {
            'qemu': hex(qemu_entry['instruction']),
            'gpu': hex(gpu_entry['instruction']),
        }

    # Compare decoded instruction
    if qemu_entry['decoded'] != gpu_entry['decoded']:
        differences['decoded'] = {
            'qemu': qemu_entry['decoded'],
            'gpu': gpu_entry['decoded'],
        }

    # Compare registers (focus on key registers)
    key_regs = [8, 9, 10]  # SATP (x8), SP (x2), A0 (x10) - add x2 later

    for reg in key_regs:
        qemu_val = qemu_entry['registers'].get(reg, 0)
        gpu_val = gpu_entry['registers'].get(reg, 0)

        if qemu_val != gpu_val:
            differences[f'x{reg}'] = {
                'qemu': hex(qemu_val),
                'gpu': hex(gpu_val),
            }

    # Compare all registers if we already have differences
    if differences:
        for reg in range(32):
            qemu_val = qemu_entry['registers'].get(reg, 0)
            gpu_val = gpu_entry['registers'].get(reg, 0)

            if qemu_val != gpu_val:
                differences[f'x{reg}'] = {
                    'qemu': hex(qemu_val),
                    'gpu': hex(gpu_val),
                }

    return differences if differences else None


def diff_traces(qemu_trace, gpu_trace, max_divergences: int = 10):
    """
    Diff QEMU and GPU traces, finding divergence points.

    Returns:
        list: Divergence points found
    """
    print("=" * 70)
    print("DIFFING QEMU REFERENCE vs GPU EMULATOR")
    print("=" * 70)

    qemu_instructions = qemu_trace['trace']
    gpu_instructions = gpu_trace['trace']

    print(f"\nQEMU trace: {len(qemu_instructions)} instructions")
    print(f"GPU trace: {len(gpu_instructions)} instructions")

    divergences = []
    max_instructions = min(len(qemu_instructions), len(gpu_instructions))

    print(f"\nComparing {max_instructions} instructions...")

    for i in range(max_instructions):
        qemu_entry = qemu_instructions[i]
        gpu_entry = gpu_instructions[i]

        # Compare entries
        differences = compare_instructions(qemu_entry, gpu_entry)

        if differences:
            divergences.append({
                'instruction_index': i,
                'pc_qemu': qemu_entry['pc'],
                'pc_gpu': gpu_entry['pc'],
                'decoded_qemu': qemu_entry['decoded'],
                'decoded_gpu': gpu_entry['decoded'],
                'differences': differences,
            })

            print(f"✗ Divergence at instruction {i}: 0x{qemu_entry['pc']:08x}")

            # Stop at first divergence for focused debugging
            break

    # If no divergences found in matching region
    if not divergences:
        # Check if GPU trace is shorter
        if len(gpu_instructions) < len(qemu_instructions):
            print(f"\n✗ GPU trace shorter: {len(gpu_instructions)} vs {len(qemu_instructions)}")
            print(f"  GPU may have crashed or halted early")
            divergences.append({
                'type': 'trace_length_mismatch',
                'qemu_length': len(qemu_instructions),
                'gpu_length': len(gpu_instructions),
            })
        elif len(qemu_instructions) < len(gpu_instructions):
            print(f"\n✗ QEMU trace shorter: {len(qemu_instructions)} vs {len(gpu_instructions)}")
            print(f"  (This is unexpected - QEMU is the reference)")
        else:
            print(f"\n✓ Traces are identical!")

    return divergences


def analyze_divergence(divergence):
    """
    Analyze a divergence point and suggest debugging focus.

    Returns:
        dict: Analysis with suggestions
    """
    analysis = {
        'type': 'unknown',
        'suggestion': 'Manual investigation required',
    }

    differences = divergence.get('differences', {})

    # Check for PC mismatch
    if 'pc' in differences:
        analysis['type'] = 'pc_mismatch'
        analysis['suggestion'] = """
GPU emulator took different code path.

Debugging focus:
1. Check branch condition (BEQ, BNE, BLT, BGE) at previous instruction
2. Compare condition registers (rs1, rs2) - did GPU compute differently?
3. Check if previous arithmetic instruction produced different result
4. May indicate bug in ALU or condition codes
"""
        return analysis

    # Check for SATP mismatch (page table base)
    if 'x8' in differences:
        analysis['type'] = 'satp_mismatch'
        analysis['suggestion'] = """
SATP (page table base) differs between QEMU and GPU.

Debugging focus:
1. Find where SATP was written (CSRRW instruction)
2. Check if GPU emulator's CSR write handling is correct
3. Verify SATP format: [MODE=8:PPN=44]
4. GPU may not be updating page table base correctly during execve

This is LIKELY the cause of EFAULT during execve!
"""
        return analysis

    # Check for memory access followed by divergence
    decoded_qemu = divergence.get('decoded_qemu', '').lower()
    if decoded_qemu.startswith(('lw', 'sw', 'ld', 'sd')):
        analysis['type'] = 'memory_access_divergence'
        analysis['suggestion'] = """
Divergence occurred during or after memory access.

Debugging focus:
1. Did memory access complete on both?
2. Compare physical addresses after translation (Sv39 page table walk)
3. Check if GPU's page table walk found the same PTE as QEMU
4. Look for unmapped pages in GPU's page tables

If GPU failed to translate address → EFAULT!
"""
        return analysis

    # Check for CSR operation
    if 'csr' in decoded_qemu or 'mret' in decoded_qemu or 'sret' in decoded_qemu:
        analysis['type'] = 'csr_divergence'
        analysis['suggestion'] = """
Divergence during CSR operation or privilege transition.

Debugging focus:
1. Check CSR read/write handling
2. Verify privilege mode transitions (M → S → U)
3. Compare CSR values (mstatus, mtvec, mepc, mcause)
4. May indicate bug in CSR handling or privilege mode
"""
        return analysis

    # Check for control flow
    if decoded_qemu.startswith(('jal', 'jalr', 'beq', 'bne', 'blt', 'bge')):
        analysis['type'] = 'control_flow_divergence'
        analysis['suggestion'] = """
Divergence during control flow instruction.

Debugging focus:
1. Check if target address calculation is correct
2. For JALR: verify base register + offset
3. For branches: verify condition and target
4. May indicate bug in address calculation or condition codes
"""
        return analysis

    return analysis


def print_divergence_report(divergences):
    """Print detailed divergence report with analysis."""
    print("\n" + "=" * 70)
    print("DIVERGENCE REPORT")
    print("=" * 70)

    if not divergences:
        print("\n✓ No divergences found - traces are identical!")
        return

    for i, div in enumerate(divergences):
        print(f"\n{'='*70}")
        print(f"DIVERGENCE {i+1}")
        print(f"{'='*70}")

        if div.get('type') == 'trace_length_mismatch':
            print(f"\nType: Trace Length Mismatch")
            print(f"  QEMU length: {div['qemu_length']}")
            print(f"  GPU length:  {div['gpu_length']}")
            continue

        print(f"\nInstruction index: {div['instruction_index']}")
        print(f"  QEMU PC:  0x{div['pc_qemu']:08x}")
        print(f"  GPU PC:   0x{div['pc_gpu']:08x}")
        print(f"  QEMU:     {div['decoded_qemu']}")
        print(f"  GPU:      {div['decoded_gpu']}")

        print(f"\nDifferences:")
        for key, values in div['differences'].items():
            print(f"  {key}:")
            print(f"    QEMU: {values['qemu']}")
            print(f"    GPU:  {values['gpu']}")

        # Analyze
        analysis = analyze_divergence(div)
        print(f"\nAnalysis:")
        print(f"  Type: {analysis['type']}")
        print(f"  Suggestion:")
        for line in analysis['suggestion'].strip().split('\n'):
            print(f"    {line}")


def print_verification_steps():
    """Print suggested next steps for debugging."""
    print("\n" + "=" * 70)
    print("NEXT STEPS FOR DEBUGGING")
    print("=" * 70)

    print("""
1. Focus on first divergence point

2. If SATP mismatch (x8 differs):
   - Find CSRRW instruction that wrote SATP
   - Verify GPU's CSR write handling
   - Check SATP format: [MODE=8:PPN=44]
   - GPU may not be setting page table base correctly

3. If memory access divergence:
   - Compare virtual addresses (should be identical)
   - Compare physical addresses after translation
   - Check page table walk: did GPU find the PTE?
   - Look for unmapped pages in GPU's page tables

4. If PC mismatch (different code path):
   - Check previous branch instruction
   - Compare condition registers
   - May indicate ALU bug

5. Verify page table structure:
   - QEMU's Sv39: 3-level page tables (9 bits per level)
   - GPU's Sv39: must be identical
   - Check PTE format: [V,R,W,X,U,G,A,D,PPN]
   - Look for missing PTE entries

6. Check TLB invalidation:
   - Does GPU invalidate TLB on SFENCE.VMA?
   - Does GPU update SATP before TLB walk?
   - Timing issue may cause stale TLB entry

7. Once bug found:
   - Fix in GPU emulator (WGSL compute shader)
   - Re-run capture/diff cycle
   - Verify divergence moves or disappears
""")


def main():
    parser = argparse.ArgumentParser(
        description="Diff QEMU and GPU emulator traces for EFAULT debugging"
    )
    parser.add_argument('--qemu', required=True, help="QEMU reference trace JSON")
    parser.add_argument('--gpu', required=True, help="GPU emulator trace JSON")
    parser.add_argument('--output', '-o', help="Output divergence report to file")

    args = parser.parse_args()

    # Load traces
    print(f"Loading QEMU trace: {args.qemu}")
    qemu_trace = load_trace(args.qemu)

    print(f"Loading GPU trace: {args.gpu}")
    gpu_trace = load_trace(args.gpu)

    # Diff traces
    divergences = diff_traces(qemu_trace, gpu_trace)

    # Print report
    print_divergence_report(divergences)
    print_verification_steps()

    # Save report
    if args.output:
        report = {
            'metadata': {
                'qemu_trace': args.qemu,
                'gpu_trace': args.gpu,
                'divergences_found': len(divergences),
            },
            'divergences': divergences,
        }

        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n✓ Saved divergence report to: {args.output}")

    # Exit with error if divergences found
    sys.exit(1 if divergences else 0)


if __name__ == "__main__":
    main()