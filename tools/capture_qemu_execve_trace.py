#!/usr/bin/env python3
"""
Capture focused QEMU trace around /bin/sh execve for diffing against GPU emulator.

This is targeted specifically at the EFAULT blocker during execve at ~945M steps.
Instead of tracing everything, we:
1. Boot QEMU to just before /bin/sh execve
2. Use -d exec,cpu,inasm to capture trusted reference
3. Focus on page table walk/TLB operations
4. Save structured JSON for diffing against GPU emulator trace

Usage:
    python3 tools/capture_qemu_execve_trace.py \
        --kernel boot_images/alpine_riscv64.lnx.bin \
        --initrd boot_images/alpine_initrd \
        --output tools/qemu_execve_trace.json
"""

import subprocess
import time
import json
import re
import argparse
from pathlib import Path


def boot_qemu_to_execve(kernel_path: str, initrd_path: str, output_path: str):
    """
    Boot QEMU to /bin/sh execve point and capture trace.

    Strategy:
    1. Boot QEMU with -d exec,cpu,inasm
    2. Send 'sh' command via monitor to trigger execve
    3. Capture trace around execve execution
    4. Parse and structure for diffing
    """
    print("=" * 70)
    print("CAPTURING QEMU EXECVE REFERENCE TRACE")
    print("=" * 70)

    kernel = Path(kernel_path)
    initrd = Path(initrd_path)

    if not kernel.exists():
        print(f"✗ Kernel not found: {kernel_path}")
        return None

    if not initrd.exists():
        print(f"✗ Initrd not found: {initrd_path}")
        return None

    # Prepare trace file
    trace_file = Path("/tmp/qemu_execve_trace.txt")
    trace_file.unlink(missing_ok=True)

    # Boot QEMU with detailed trace
    print(f"Kernel: {kernel_path}")
    print(f"Initrd: {initrd_path}")
    print(f"Trace output: {trace_file}")

    # Use QEMU monitor socket to send commands
    monitor_socket = Path("/tmp/qemu_execve_monitor.sock")
    monitor_socket.unlink(missing_ok=True)

    cmd = [
        "qemu-system-riscv64",
        "-nographic",
        "-machine", "virt",
        "-bios", "/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin",
        "-kernel", str(kernel),
        "-initrd", str(initrd),
        "-append", "console=ttyS0 root=/dev/ram rw rdinit=/sbin/init",
        "-m", "512M",
        "-smp", "1",
        "-d", "exec,cpu,in_asm",  # Critical: execution trace + CPU state + disassembly
        "-D", str(trace_file),
        "-chardev", f"socket,id=mon,path={monitor_socket},server,nowait",
        "-mon", "chardev=mon,mode=control",
    ]

    print(f"\nStarting QEMU...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for boot to shell
    print("Waiting for boot to shell prompt...")
    time.sleep(20)

    # Send 'sh' command to trigger execve
    print("Sending 'sh' command to trigger execve...")
    try:
        # Open QEMU monitor connection
        import socket
        mon = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        mon.connect(str(monitor_socket))

        # Wait for shell prompt in serial
        time.sleep(2)

        # Send 'sh' command via monitor (this triggers execve)
        # We use "sendkey" to type into the serial console
        mon.sendall(b'sendkey s\n')
        time.sleep(0.05)
        mon.sendall(b'sendkey h\n')
        time.sleep(0.05)
        mon.sendall(b'sendkey ret\n')
        time.sleep(0.05)

        # Let execve execute and capture trace
        time.sleep(3)

        # Quit QEMU
        mon.sendall(b'quit\n')
        mon.close()

    except Exception as e:
        print(f"Monitor interaction failed: {e}")
        proc.kill()
        proc.wait()
        return None

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    print("✓ QEMU stopped")

    # Parse trace
    trace = parse_qemu_trace(trace_file)

    # Save as JSON
    data = {
        'metadata': {
            'kernel': str(kernel),
            'initrd': str(initrd),
            'capture_time': time.time(),
            'qemu_version': get_qemu_version(),
            'target': '/bin/sh execve',
            'purpose': 'EFAULT debugging - QEMU reference trace'
        },
        'trace': trace
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved trace to: {output_path}")
    print(f"  Instructions captured: {len(trace)}")

    return output_path


def parse_qemu_trace(trace_file: Path):
    """
    Parse QEMU -d exec,cpu,inasm trace into structured format.

    QEMU trace format (actual):
    Trace 0: 0x7da294000440 [00000000/0000000080000000/0b024003/ff020000]
     V      =   0
     pc       0000000080000000
     mhartid  0000000000000000
     mstatus  0000000a00000000
     satp     0000000000000000
     x0/zero  0000000000000000 x1/ra    0000000000000000 x2/sp    0000000000000000 ...

    Then instruction:
    0x80000000:  00050433          add                     s0,a0,zero

    We parse:
    - Trace header with CSRs
    - Instruction with PC and encoding
    - Register state from x0/x1/x2/... lines
    """
    if not trace_file.exists():
        print(f"✗ Trace file not found: {trace_file}")
        return []

    with open(trace_file) as f:
        content = f.read()

    trace = []
    lines = content.split('\n')

    # Parse state
    current_pc = None
    current_instr = None
    current_decoded = None
    current_regs = {}
    current_csrs = {}
    in_trace_block = False

    for line in lines:
        # Detect trace header
        if line.startswith('Trace 0:'):
            # Save previous entry
            if current_pc is not None:
                is_relevant = is_instruction_relevant(current_decoded, current_csrs)
                if is_relevant:
                    entry = {
                        'pc': current_pc,
                        'instruction': current_instr,
                        'decoded': current_decoded,
                        'registers': current_regs.copy(),
                        'csr': current_csrs.copy(),
                        'is_page_table_op': is_page_table_operation(current_decoded),
                        'is_memory_access': is_memory_access(current_decoded),
                        'is_csr_op': is_csr_operation(current_decoded),
                    }
                    trace.append(entry)

            # Reset state
            current_pc = None
            current_instr = None
            current_decoded = None
            current_regs = {}
            current_csrs = {}
            in_trace_block = True
            continue

        if not in_trace_block:
            continue

        # Parse CSRs
        if 'satp     ' in line:
            # satp     0000000000000000
            parts = line.split()
            if len(parts) >= 2:
                current_csrs['satp'] = int(parts[1], 16)
        elif 'mstatus  ' in line:
            parts = line.split()
            if len(parts) >= 2:
                current_csrs['mstatus'] = int(parts[1], 16)
        elif 'mepc     ' in line:
            parts = line.split()
            if len(parts) >= 2:
                current_csrs['mepc'] = int(parts[1], 16)
        elif 'mcause   ' in line:
            parts = line.split()
            if len(parts) >= 2:
                current_csrs['mcause'] = int(parts[1], 16)
        elif 'mtvec    ' in line:
            parts = line.split()
            if len(parts) >= 2:
                current_csrs['mtvec'] = int(parts[1], 16)

        # Parse registers (x0/x1/x2/... format)
        if 'x0/zero' in line or 'x1/ra' in line:
            # x0/zero  0000000000000000 x1/ra    0000000000000000 x2/sp    0000000000000000 ...
            parts = line.split()
            i = 0
            while i + 1 < len(parts):
                reg_part = parts[i]
                val_part = parts[i + 1]

                # Check if this is a register (x0/x1/x2/...)
                if '/' in reg_part and reg_part.startswith('x'):
                    reg_name = reg_part.split('/')[0]  # x0, x1, etc.
                    if reg_name.startswith('x'):
                        try:
                            reg_num = int(reg_name[1:])
                            current_regs[reg_num] = int(val_part, 16)
                        except:
                            pass

                i += 2

        # Parse instruction line
        # 0x80000000:  00050433          add                     s0,a0,zero
        match = re.search(r'0x([0-9a-fA-F]+):\s+([0-9a-fA-F]+)\s+(.+)', line)
        if match:
            current_pc = int(match.group(1), 16)
            current_instr = int(match.group(2), 16)
            current_decoded = match.group(3).strip()

            # Check if we've reached the execve point (heuristic)
            # We'll want to capture around execve, not everything
            if 'execve' in current_decoded.lower() or current_pc > 0xffffffff80000000:
                # Execve path - capture more aggressively
                pass

    # Save last entry
    if current_pc is not None:
        is_relevant = is_instruction_relevant(current_decoded, current_csrs)
        if is_relevant:
            entry = {
                'pc': current_pc,
                'instruction': current_instr,
                'decoded': current_decoded,
                'registers': current_regs.copy(),
                'csr': current_csrs.copy(),
                'is_page_table_op': is_page_table_operation(current_decoded),
                'is_memory_access': is_memory_access(current_decoded),
                'is_csr_op': is_csr_operation(current_decoded),
            }
            trace.append(entry)

    return trace


def is_instruction_relevant(decoded: str, regs: dict) -> bool:
    """Filter to instructions relevant to execve EFAULT debugging."""
    decoded_lower = decoded.lower()

    # Page table operations
    if 'sfence.vma' in decoded_lower:
        return True

    # Memory accesses (trigger page walks)
    if decoded_lower.startswith(('lw', 'sw', 'lb', 'sb', 'ld', 'sd')):
        return True

    # CSR operations (SATP modifications)
    if 'csr' in decoded_lower or 'satp' in decoded_lower:
        return True

    # System calls (ECALL)
    if 'ecall' in decoded_lower:
        return True

    # Returns (indicate context switches)
    if 'mret' in decoded_lower or 'sret' in decoded_lower:
        return True

    # If in execve region, capture everything
    # (This is coarse - could be refined by tracking execve depth)
    return False


def is_page_table_operation(decoded: str) -> bool:
    """Check if instruction is a page table operation."""
    decoded_lower = decoded.lower()
    return 'sfence.vma' in decoded_lower or 'satp' in decoded_lower


def is_memory_access(decoded: str) -> bool:
    """Check if instruction is a memory access (triggers page walk)."""
    decoded_lower = decoded.lower()
    return decoded_lower.startswith(('lw', 'sw', 'lb', 'sb', 'ld', 'sd'))


def is_csr_operation(decoded: str) -> bool:
    """Check if instruction is a CSR operation."""
    decoded_lower = decoded.lower()
    return 'csr' in decoded_lower or 'mret' in decoded_lower or 'sret' in decoded_lower


def get_qemu_version():
    """Get QEMU version."""
    try:
        result = subprocess.run(["qemu-system-riscv64", "--version"],
                              capture_output=True, text=True)
        return result.stdout.strip()
    except:
        return "unknown"


def analyze_trace_for_efault(trace_path: str):
    """
    Analyze captured trace for EFAULT-specific patterns.

    Look for:
    1. SFENCE.VMA calls (TLB invalidation)
    2. SATP writes (page table switch)
    3. Memory accesses just before EFAULT
    4. Page table walk operations
    """
    print("=" * 70)
    print("EFAUlT DEBUGGING ANALYSIS")
    print("=" * 70)

    with open(trace_path) as f:
        data = json.load(f)

    trace = data['trace']
    print(f"\nLoaded {len(trace)} instructions from QEMU trace")

    # Find page table operations
    pt_ops = [e for e in trace if e['is_page_table_op']]
    print(f"\nPage table operations: {len(pt_ops)}")
    if pt_ops:
        print(f"  Sample: {pt_ops[0]['decoded']} at 0x{pt_ops[0]['pc']:08x}")

    # Find memory accesses (potential page walks)
    mem_accesses = [e for e in trace if e['is_memory_access']]
    print(f"\nMemory accesses (trigger page walks): {len(mem_accesses)}")
    if mem_accesses:
        print(f"  Sample: {mem_accesses[0]['decoded']} at 0x{mem_accesses[0]['pc']:08x}")
        print(f"    SATP: 0x{mem_accesses[0]['registers'].get(8, 0):08x}")

    # Find CSR operations
    csr_ops = [e for e in trace if e['is_csr_op']]
    print(f"\nCSR operations: {len(csr_ops)}")
    if csr_ops:
        print(f"  Sample: {csr_ops[0]['decoded']} at 0x{csr_ops[0]['pc']:08x}")

    # Show region around execve
    ecall_entries = [i for i, e in enumerate(trace) if 'ecall' in e['decoded'].lower()]
    if ecall_entries:
        print(f"\nFound ECALL at instruction {ecall_entries[0]}")
        print(f"Instructions around ECALL:")
        for i in range(max(0, ecall_entries[0]-5), min(len(trace), ecall_entries[0]+5)):
            entry = trace[i]
            marker = " >>>" if i == ecall_entries[0] else "    "
            print(f"{marker} {i:5d}: 0x{entry['pc']:08x}: {entry['decoded']}")


def show_diff_example(trace_path: str):
    """Show how to diff QEMU trace against GPU emulator trace."""
    print("\n" + "=" * 70)
    print("HOW TO DIFF AGAINST GPU EMULATOR")
    print("=" * 70)

    print("""
Once efault-v5 completes with its GPU trace:

1. Load QEMU reference trace:
    with open('""" + trace_path + """') as f:
        qemu_trace = json.load(f)

2. Load GPU emulator trace (from efault-v5 output):
    with open('tools/gpu_execve_trace.json') as f:
        gpu_trace = json.load(f)

3. Diff at matched instruction count:

    for i in range(min(len(qemu_trace['trace']), len(gpu_trace['trace']))):
        qemu_entry = qemu_trace['trace'][i]
        gpu_entry = gpu_trace['trace'][i]

        # Compare PC (must be identical)
        if qemu_entry['pc'] != gpu_entry['pc']:
            print(f"PC mismatch at instruction {i}:")
            print(f"  QEMU: 0x{qemu_entry['pc']:08x}: {qemu_entry['decoded']}")
            print(f"  GPU:  0x{gpu_entry['pc']:08x}: {gpu_entry['decoded']}")
            print(f"  ^^ This is the divergence point!")
            break

        # Compare SATP (page table base)
        qemu_satp = qemu_entry['registers'].get(8, 0)
        gpu_satp = gpu_entry['registers'].get(8, 0)
        if qemu_satp != gpu_satp:
            print(f"SATP mismatch at instruction {i}:")
            print(f"  QEMU: 0x{qemu_satp:08x}")
            print(f"  GPU:  0x{gpu_satp:08x}")
            print(f"  ^^ GPU didn't update page table correctly!")
            break

        # Compare memory access addresses
        if qemu_entry['is_memory_access'] and gpu_entry['is_memory_access']:
            # Extract base register and offset from decoded
            # (This requires parsing the instruction)
            # Then compare physical addresses after translation
            pass

4. Focus on first divergence - that's the bug!

Where we expect divergence for EFAULT:
    - QEMU: Memory access succeeds (page mapped)
    - GPU:  Memory access fails (page not mapped)
    - Cause: GPU's page table walk missed a PTE entry
""")


def main():
    parser = argparse.ArgumentParser(
        description="Capture QEMU execve trace for EFAULT debugging"
    )
    parser.add_argument('--kernel', default="boot_images/alpine_riscv64.lnx.bin",
                       help="Kernel image path")
    parser.add_argument('--initrd', default="boot_images/alpine_initrd",
                       help="Initrd path")
    parser.add_argument('--output', '-o', default="tools/qemu_execve_trace.json",
                       help="Output JSON path")
    parser.add_argument('--analyze', help="Analyze existing trace file")
    parser.add_argument('--diff', help="Show diff example for given trace")

    args = parser.parse_args()

    if args.analyze:
        analyze_trace_for_efault(args.analyze)
    elif args.diff:
        show_diff_example(args.diff)
    else:
        result = boot_qemu_to_execve(args.kernel, args.initrd, args.output)
        if result:
            analyze_trace_for_efault(result)
            show_diff_example(result)


if __name__ == "__main__":
    main()