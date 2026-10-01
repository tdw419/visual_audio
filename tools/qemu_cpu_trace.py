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
    # IMPORTANT: QEMU's `-d in_asm` prints a disassembly line only once per
    # translation block *translation* (cached across repeated dynamic visits,
    # e.g. loop bodies), while the per-instruction register dump (driven by
    # `-singlestep` + `-d cpu`) genuinely prints fresh on every dynamic
    # execution, including loop revisits, just without a new disasm marker
    # preceding it. Delimiting entries by the disasm marker (as this used to)
    # silently collapses every revisit of a PC into one entry, overwriting
    # its regs with whichever dynamic pass happened to be parsed last -
    # invisible for straight-line code, silently wrong for any loop/branch.
    # Each register block includes its own 'pc' field, which IS accurate per
    # dynamic execution, so that - not the disasm marker - must delimit entries.
    entries = []
    instr_by_pc = {}  # pc -> disassembly text, filled in at translation time
    regs = {}

    with open(trace_file, 'r') as f:
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
                pc_here = int(disasm.group(1), 16)
                full_instr = f"{disasm.group(2)} {disasm.group(3)}"
                instr_by_pc[pc_here] = full_instr.strip()
                continue

            # Parse registers - formats:
            #   CSR:   " pc       0000000000001000"
            #          " mhartid  0000000000000002"
            #   GPRs:  " x0/zero  0000000000000000 x1/ra    0000000000000000 ..."
            # Hex values have NO 0x prefix in the raw QEMU output.
            for match in re.finditer(r'([a-z0-9_]+(?:/[a-z0-9_]+)?)\s+([0-9a-f]{16})', line):
                reg_name = match.group(1).split('/')[0]  # Remove aliases like /zero
                reg_val = int(match.group(2), 16)
                if reg_name == 'pc' and 'pc' in regs:
                    # A repeated 'pc' key marks the start of a new
                    # per-instruction register block; flush the previous one.
                    # QEMU's singlestep logging sometimes emits two identical
                    # back-to-back blocks at the same PC (observed at TB
                    # boundaries) with no state change between them - that
                    # can't be two real dynamic executions of a straight-line
                    # instruction, so collapse an exact duplicate of the
                    # immediately preceding entry rather than double-counting it.
                    if not entries or entries[-1]['pc'] != regs['pc'] or entries[-1]['regs'] != regs:
                        entries.append({
                            'pc': regs['pc'],
                            'instr': instr_by_pc.get(regs['pc']),
                            'regs': regs.copy()
                        })
                    regs = {}
                regs[reg_name] = reg_val

        # Don't forget last entry
        if 'pc' in regs:
            if not entries or entries[-1]['pc'] != regs['pc'] or entries[-1]['regs'] != regs:
                entries.append({'pc': regs['pc'], 'instr': instr_by_pc.get(regs['pc']), 'regs': regs})
    
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


INSTRUCTION_RE = re.compile(r'^\s*(0x[0-9a-f]+):\s+([0-9a-f]+)\s+')

# Disassembly markers (INSTRUCTION_RE) only appear once per translation
# block *translation* (cached across loop revisits), so counting them
# undercounts real dynamic instructions for any looping code. Each
# per-instruction register dump's own 'pc' line prints fresh on every
# dynamic execution and must be used instead to bound/count real progress.
PC_LINE_RE = re.compile(r'^\s*pc\s+[0-9a-f]{16}\s*$')


def _count_instructions_in_trace(file_path: Path) -> int:
    """Count actual instruction markers (disassembly lines) in a QEMU trace file."""
    if not file_path.exists():
        return 0
    count = 0
    with open(file_path, 'r') as f:
        for line in f:
            if PC_LINE_RE.match(line):
                count += 1
    return count


def bounded_qemu_trace(kernel_path: Path, max_instructions: int = 10000,
                       output_trace: str = '/tmp/qemu_cpu_trace.log',
                       trace_name: str = 'qemu'):
    """
    Run QEMU with bounded instruction count, counting actual instruction
    markers (disassembly lines) in the trace file rather than estimating
    from file size.
    """
    import time

    trace_file = Path(output_trace)
    # Ensure clean file
    trace_file.unlink(missing_ok=True)

    qemu_cmd = [
        'qemu-system-riscv64',
        '-M', 'virt',
        '-bios', 'none',
        '-kernel', str(kernel_path),
        '-m', '128M',
        '-smp', '1',  # Single hart to match GPU emulator
        '-nographic',
        '-global', 'virtio-mmio.force-legacy=false',
        '-drive', 'file=/tmp/xv6-riscv/fs.img,if=none,format=raw,id=x0',
        '-device', 'virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0',
        '-d', 'cpu,in_asm',
        '-D', str(trace_file),
        '-singlestep',
    ]

    print(f"Running: {' '.join(qemu_cmd)}")
    print(f"Will stop after {max_instructions} instructions")

    qemu_proc = subprocess.Popen(
        qemu_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Track file reading position so we don't re-read the whole file each poll
    file_pos = 0
    instruction_count = 0
    stuck_count = 0

    try:
        for _ in range(600):  # Max 10 minutes
            time.sleep(0.5)

            if not trace_file.exists():
                continue

            # Read only new bytes and count instruction markers
            current_size = trace_file.stat().st_size
            if current_size > file_pos:
                with open(trace_file, 'r') as f:
                    f.seek(file_pos)
                    for line in f:
                        if PC_LINE_RE.match(line):
                            instruction_count += 1
                file_pos = current_size
                stuck_count = 0
            else:
                stuck_count += 1
                if stuck_count >= 10:  # Stuck for 5 seconds
                    print("QEMU appears stuck, killing")
                    break

            if instruction_count >= max_instructions:
                print(f"Reached {instruction_count} instructions, stopping")
                break

            # Progress every 5K
            if instruction_count % 5000 == 0 and instruction_count > 0:
                print(f"  [{trace_name}] {instruction_count} instructions traced...")
    finally:
        qemu_proc.kill()
        qemu_proc.wait()

    print(f"Trace written to {trace_file} ({instruction_count} instructions)")
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
    parser.add_argument('--jsonl', '-j', type=lambda x: None if x is None else x,
                        const='/tmp/qemu_diff_trace.jsonl', nargs='?',
                        help='Save parsed trace as JSONL for diff tool (default: /tmp/qemu_diff_trace.jsonl)')
    
    args = parser.parse_args()
    
    jsonl_output = args.jsonl
    if jsonl_output is None:
        # When --jsonl is used without arg, or not at all
        jsonl_output = '/tmp/qemu_diff_trace.jsonl' if args.jsonl is not None else None
    
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
    
    # Save as JSONL for diff tool if requested
    if jsonl_output:
        import json
        with open(jsonl_output, 'w') as f:
            for e in entries:
                f.write(json.dumps(e) + '\n')
        print(f"Saved parsed trace as JSONL: {jsonl_output} ({len(entries)} entries)")


if __name__ == '__main__':
    main()