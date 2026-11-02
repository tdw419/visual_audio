#!/usr/bin/env python3
"""
Compare QEMU and GPU emulator states at PC = 0x80201048.
"""
import os

def compare_registers():
    """Compare register dumps."""
    print("="*70)
    print("REGISTER COMPARISON")
    print("="*70)

    qemu_regs = {}
    gpu_regs = {}

    # Parse QEMU registers
    if os.path.exists("qemu_regs_at_0x80201048.txt"):
        with open("qemu_regs_at_0x80201048.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and "x" in line and not "x0" in line:  # Skip x0 header
                    parts = line.split()
                    if len(parts) >= 2:
                        reg = parts[0]
                        val = parts[1]
                        qemu_regs[reg] = val
    else:
        print("✗ QEMU register file not found")
        return

    # Parse GPU registers
    if os.path.exists("gpu_regs_at_0x80201048.txt"):
        with open("gpu_regs_at_0x80201048.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("x") and ":" in line:
                    parts = line.split(":")
                    if len(parts) == 2:
                        reg = parts[0].strip()
                        val = parts[1].strip()
                        gpu_regs[reg] = val
    else:
        print("✗ GPU register file not found")
        return

    # Compare
    matches = 0
    mismatches = 0
    missing = 0

    for i in range(32):
        reg = f"x{i}"
        if reg in qemu_regs and reg in gpu_regs:
            qemu_val = qemu_regs[reg]
            gpu_val = gpu_regs[reg]

            # Normalize format
            if not qemu_val.startswith("0x"):
                qemu_val = f"0x{int(qemu_val, 10):08x}"

            if not gpu_val.startswith("0x"):
                gpu_val = f"0x{int(gpu_val, 10):08x}"

            if qemu_val == gpu_val:
                matches += 1
                print(f"  {reg}: ✓ {qemu_val}")
            else:
                mismatches += 1
                print(f"  {reg}: ✗ QEMU={qemu_val}, GPU={gpu_val}")
        else:
            missing += 1
            if reg not in qemu_regs:
                print(f"  {reg}: ✗ Missing in QEMU")
            if reg not in gpu_regs:
                print(f"  {reg}: ✗ Missing in GPU")

    print(f"\nSummary: {matches} matches, {mismatches} mismatches, {missing} missing")

def compare_csrs():
    """Compare CSR dumps."""
    print("\n" + "="*70)
    print("CSR COMPARISON")
    print("="*70)

    qemu_csrs = {}
    gpu_csrs = {}

    # Parse QEMU CSRs
    if os.path.exists("qemu_csr_at_0x80201048.txt"):
        with open("qemu_csr_at_0x80201048.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("="):
                    parts = line.split()
                    if len(parts) >= 2:
                        name = parts[0]
                        val = parts[1]
                        qemu_csrs[name] = val

        # Extract key CSRs
        print("QEMU CSRs:")
        for csr in ['satp', 'mstatus', 'mepc', 'mcause', 'mtvec', 'pc']:
            if csr in qemu_csrs:
                print(f"  {csr}: {qemu_csrs[csr]}")
    else:
        print("✗ QEMU CSR file not found")
        return

    # Parse GPU CSRs
    if os.path.exists("gpu_csr_at_0x80201048.txt"):
        with open("gpu_csr_at_0x80201048.txt", "r") as f:
            print("\nGPU CSRs:")
            for line in f:
                line = line.strip()
                if line:
                    print(f"  {line}")

        # Extract key CSRs for comparison
        with open("gpu_csr_at_0x80201048.txt", "r") as f:
            for line in f:
                if "satp" in line:
                    gpu_csrs['satp'] = line.split()[-1]
                elif "mstatus" in line:
                    gpu_csrs['mstatus'] = line.split()[-1]
                elif "mepc" in line:
                    gpu_csrs['mepc'] = line.split()[-1]
                elif "mcause" in line:
                    gpu_csrs['mcause'] = line.split()[-1]
                elif "mtvec" in line:
                    gpu_csrs['mtvec'] = line.split()[-1]
    else:
        print("✗ GPU CSR file not found")
        return

    # Compare key CSRs
    print("\nKey CSR Comparison:")
    for csr in ['satp', 'mstatus', 'mepc', 'mcause', 'mtvec']:
        if csr in qemu_csrs and csr in gpu_csrs:
            qemu_val = qemu_csrs[csr]
            gpu_val = gpu_csrs[csr]

            if qemu_val == gpu_val:
                print(f"  {csr}: ✓ {qemu_val}")
            else:
                print(f"  {csr}: ✗ QEMU={qemu_val}, GPU={gpu_val}")

def compare_memory():
    """Compare memory dumps."""
    print("\n" + "="*70)
    print("MEMORY COMPARISON")
    print("="*70)

    if os.path.exists("qemu_mem_at_0x80201048.bin"):
        with open("qemu_mem_at_0x80201048.bin", "rb") as f:
            qemu_mem = f.read()
        print(f"QEMU memory: {len(qemu_mem)} bytes")
        print(f"  {' '.join(f'{b:02x}' for b in qemu_mem[:16])}")
    else:
        print("✗ QEMU memory file not found")
        return

    if os.path.exists("gpu_mem_at_0x80201048.bin"):
        with open("gpu_mem_at_0x80201048.bin", "rb") as f:
            gpu_mem = f.read()
        print(f"\nGPU memory: {len(gpu_mem)} bytes")
        print(f"  {' '.join(f'{b:02x}' for b in gpu_mem[:16])}")
    else:
        print("✗ GPU memory file not found")
        return

    if qemu_mem == gpu_mem:
        print("\n✓ Memory matches exactly!")
    else:
        print("\n✗ Memory mismatch!")

        # Find differences
        for i, (q, g) in enumerate(zip(qemu_mem, gpu_mem)):
            if q != g:
                print(f"  Byte {i}: QEMU=0x{q:02x}, GPU=0x{g:02x}")

def compare_page_tables():
    """Compare page table dumps."""
    print("\n" + "="*70)
    print("PAGE TABLE COMPARISON")
    print("="*70)

    if os.path.exists("gpu_pt_at_0x80201048.txt"):
        with open("gpu_pt_at_0x80201048.txt", "r") as f:
            print("GPU Page Table:")
            print(f.read()[:500])
    else:
        print("✗ GPU page table file not found")

    print("\nNote: QEMU page table not captured by this script (would need")
    print("      manual GDB commands to extract page table memory)")

def main():
    print("Comparing QEMU and GPU emulator states at PC = 0x80201048\n")

    compare_registers()
    compare_csrs()
    compare_memory()
    compare_page_tables()

    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)

if __name__ == "__main__":
    main()