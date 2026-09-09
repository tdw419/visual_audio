#!/usr/bin/env python3
"""
Capture GPU emulator state at PC = 0x80201048 for comparison with QEMU.
"""
import sys
import numpy as np
from pathlib import Path

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from tools.spatial_rv64i_cpu import SpatialRV64ICore
from tools.hybrid_kernel_loader import HybridKernelLoader, ELF64Loader, PE32Loader

TARGET_PC = 0x80201048
MAX_STEPS = 20_000_000  # Should reach this PC well before this

def load_pe32_kernel(core, kernel_path):
    """Load PE32+ kernel (Alpine)."""
    print(f"Loading PE32+ kernel from {kernel_path}...")
    loader = PE32Loader(kernel_path)

    for seg in loader.get_loadable_segments():
        data = loader.get_segment_data(seg)
        va = loader.image_base + seg['virtual_address']

        # Convert VA to physical address offset (kernel runs at 0x80200000)
        phys_offset = va - 0x80200000

        print(f"  Section: {seg['name']:<10} VA=0x{va:08x} PA=0x{phys_offset:08x} size={seg['size_of_raw_data']:,} flags={'R' if seg['characteristics'] & 0x40000000 else ''}{'W' if seg['characteristics'] & 0x80000000 else ''}{'X' if seg['characteristics'] & 0x20000000 else ''}")

        # Pad to 4-byte alignment
        padded_data = data + b'\x00' * ((4 - len(data) % 4) % 4)

        # Write to memory (we need to map VA to physical offset)
        # For PE32+, image_base is where the kernel expects to run
        # Our emulator's memory starts at 0, so we need to write at phys_offset
        core.write_mem_bytes(phys_offset, padded_data)

    return loader.entry_point

def capture_gpu_state():
    print("Initializing GPU emulator (512MB memory)...")
    core = SpatialRV64ICore(
        memory_size_bytes=512 * 1024 * 1024,  # 512MB
        trace_file=None
    )

    # Detect and load kernel
    print("\nDetecting kernel format...")
    fmt = HybridKernelLoader.detect_format('boot_images/alpine_Image')
    print(f"  Format: {fmt}")

    if fmt == "PE32+":
        entry_point = load_pe32_kernel(core, 'boot_images/alpine_Image')
    elif fmt == "ELF64":
        print("  Using ELF64 loader...")
        loader = ELF64Loader('boot_images/alpine_Image')
        entry_point = loader.entry_point
        for seg in loader.get_loadable_segments():
            data = loader.get_segment_data(seg)
            va = seg['p_vaddr']
            phys = va - 0x80200000  # Convert to physical offset
            print(f"  Segment: VA=0x{va:08x} PA=0x{phys:08x} size={seg['p_memsz']:,}")

            padded_data = data + b'\x00' * ((4 - len(data) % 4) % 4)
            core.write_mem_bytes(phys, padded_data)
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    # Set initial state (PE32+ kernels expect to start at entry_point)
    # For Alpine, entry_point should be 0x80201000 (kernel start)
    print(f"\nSetting entry point to 0x{entry_point:08x}")

    # Set up initial CSRs
    # satp: initially disabled (mode=0), will be set by kernel
    core.write_csr(0x180, 0)  # satp
    # mstatus: M-mode, interrupts disabled
    core.write_csr(0x300, 0x00001800)  # mstatus (MPP=M, MPIE=0)
    # mtvec: direct mode, points to kernel entry
    core.write_csr(0x305, entry_point)

    # Load initrd
    print("Loading initrd...")
    with open('boot_images/alpine_initrd', 'rb') as f:
        initrd_data = f.read()

    # Initrd typically goes at 0x82200000 for Alpine
    initrd_offset = 0x82200000 - 0x80200000
    padded_initrd = initrd_data + b'\x00' * ((4 - len(initrd_data) % 4) % 4)
    core.write_mem_bytes(initrd_offset, padded_initrd)
    print(f"  Initrd: {len(initrd_data):,} bytes at 0x82200000")

    # Load device tree blob
    print("Loading device tree...")
    try:
        with open('boot_images/alpine.dtb', 'rb') as f:
            dtb_data = f.read()

        # DTB typically goes at 0x82000000
        dtb_offset = 0x82000000 - 0x80200000
        padded_dtb = dtb_data + b'\x00' * ((4 - len(dtb_data) % 4) % 4)
        core.write_mem_bytes(dtb_offset, padded_dtb)
        print(f"  DTB: {len(dtb_data):,} bytes at 0x82000000")
    except FileNotFoundError:
        print("  DTB not found (alpine.dtb), skipping...")

    print(f"\nStepping until PC = {hex(TARGET_PC)}...")

    steps = 0
    pc_seen = set()
    last_ten_pcs = []

    while steps < MAX_STEPS:
        core.step(steps=1000)  # Batch steps
        state = core.get_state()

        pc = state['pc']
        steps += 1000

        # Track last 10 PCs for loop detection
        last_ten_pcs.append(pc)
        if len(last_ten_pcs) > 10:
            last_ten_pcs.pop(0)

        # Check if we've looped (stuck)
        if len(set(last_ten_pcs)) < 3:
            print(f"  Loop detected! Last 10 PCs: {[hex(p) for p in last_ten_pcs]}")
            print(f"  State: halted={state['halted']}, mode={state['mode']}, trap_pending={state['trap_pending']}")
            break

        # Check if we hit target
        if pc == TARGET_PC:
            print(f"  ✓ Reached target PC {hex(TARGET_PC)} after {steps:,} steps!")
            break

        # Progress indicator
        if steps % 100000 == 0:
            print(f"  Steps: {steps:,}, PC: {hex(pc)}, halted={state['halted']}")

    # Capture final state
    final_state = core.get_state()

    # Save registers
    with open("gpu_regs_at_0x80201048.txt", "w") as f:
        f.write(f"PC: 0x{final_state['pc']:016x}\n")
        f.write(f"Mode: {final_state['mode']} (0=U, 1=S, 3=M)\n")
        f.write(f"Halted: {final_state['halted']}\n")
        f.write(f"Trap Pending: {final_state['trap_pending']}\n")
        f.write(f"Steps: {steps:,}\n")
        f.write(f"\nGeneral Purpose Registers:\n")
        for i in range(32):
            val_lo, val_hi = final_state['regs'][i]
            val = val_lo | (val_hi << 32)
            f.write(f"  x{i:2d}: 0x{val:016x}\n")

    print(f"  Saved registers to gpu_regs_at_0x80201048.txt")

    # Capture CSRs
    csr_data = core.queue.read_buffer(core.csr_buffer)
    csr_arr = np.frombuffer(csr_data, dtype=np.uint32).reshape((4096, 2))

    with open("gpu_csr_at_0x80201048.txt", "w") as f:
        satp_lo = csr_arr[0x180][0]
        satp_hi = csr_arr[0x180][1]
        satp = satp_lo | (satp_hi << 32)

        mstatus_lo = csr_arr[0x300][0]
        mstatus_hi = csr_arr[0x300][1]
        mstatus = mstatus_lo | (mstatus_hi << 32)

        mtvec_lo = csr_arr[0x305][0]
        mtvec_hi = csr_arr[0x305][1]
        mtvec = mtvec_lo | (mtvec_hi << 32)

        mcause_lo = csr_arr[0x342][0]
        mcause_hi = csr_arr[0x342][1]
        mcause = mcause_lo | (mcause_hi << 32)

        mepc_lo = csr_arr[0x341][0]
        mepc_hi = csr_arr[0x341][1]
        mepc = mepc_lo | (mepc_hi << 32)

        f.write(f"satp:   0x{satp:016x}\n")
        f.write(f"mstatus: 0x{mstatus:016x}\n")
        f.write(f"mtvec:  0x{mtvec:016x}\n")
        f.write(f"mcause: 0x{mcause:016x}\n")
        f.write(f"mepc:   0x{mepc:016x}\n")

    print(f"  Saved CSRs to gpu_csr_at_0x80201048.txt")

    # Capture page table (from satp)
    satp = satp_lo | (satp_hi << 32)
    root_ppn = satp & 0xFFFFFFFFF  # Sv39: 44-bit PPN
    satp_mode = (satp >> 31) & 0xF

    print(f"  satp = 0x{satp:016x}, mode={satp_mode}, root_ppn = 0x{root_ppn:08x}")

    if satp_mode == 8:  # Sv39 enabled
        # Read page table entries (level 2 has 512 entries)
        pt_offset = root_ppn * 4096
        try:
            pt_data = core.queue.read_buffer(
                core.memory.buffer,
                buffer_offset=pt_offset,
                size=512 * 8
            )
            pt_arr = np.frombuffer(pt_data, dtype=np.uint32).reshape((512, 2))

            with open("gpu_pt_at_0x80201048.txt", "w") as f:
                f.write(f"Root Page Table (L2) at PPN 0x{root_ppn:08x}:\n")
                f.write(f"VA 0x{TARGET_PC:016x} breakdown:\n")
                f.write(f"  VPN2 = {(TARGET_PC >> 30) & 0x1FF}\n")
                f.write(f"  VPN1 = {(TARGET_PC >> 21) & 0x1FF}\n")
                f.write(f"  VPN0 = {(TARGET_PC >> 12) & 0x1FF}\n")
                f.write(f"  Offset = {TARGET_PC & 0xFFF}\n")
                f.write(f"\nRoot Table Entries:\n")

                for i in range(512):
                    pte_lo = pt_arr[i][0]
                    pte_hi = pt_arr[i][1]
                    pte = pte_lo | (pte_hi << 32)
                    if pte != 0:
                        f.write(f"  [{i:3d}]: 0x{pte:016x}")
                        if pte & 1:
                            f.write(" V")
                            if pte & 2: f.write(" R")
                            if pte & 4: f.write(" W")
                            if pte & 8: f.write(" X")
                            if pte & 16: f.write(" U")
                            if pte & 32: f.write(" G")
                            if pte & 64: f.write(" A")
                            if pte & 128: f.write(" D")
                        f.write("\n")

            print(f"  Saved page table to gpu_pt_at_0x80201048.txt")

            # Walk the page table for the target VA
            vpn2 = (TARGET_PC >> 30) & 0x1FF
            pte_lo = pt_arr[vpn2][0]
            pte_hi = pt_arr[vpn2][1]
            pte = pte_lo | (pte_hi << 32)

            print(f"\n  Page walk for VA 0x{TARGET_PC:016x}:")
            print(f"    L2[{vpn2}] = 0x{pte:016x}")

            if pte & 1:  # Valid
                l1_ppn = (pte >> 10) & 0x3FFFFFFFFF
                l1_offset = l1_ppn * 4096 + ((TARGET_PC >> 21) & 0x1FF) * 8

                try:
                    l1_data = core.queue.read_buffer(
                        core.memory.buffer,
                        buffer_offset=l1_offset,
                        size=8
                    )
                    l1_lo = np.frombuffer(l1_data[:4], dtype=np.uint32)[0]
                    l1_hi = np.frombuffer(l1_data[4:8], dtype=np.uint32)[0]
                    l1_pte = l1_lo | (l1_hi << 32)

                    print(f"    L1 PTE = 0x{l1_pte:016x}")

                    if l1_pte & 1:
                        l0_ppn = (l1_pte >> 10) & 0x3FFFFFFFFF
                        l0_offset = l0_ppn * 4096 + ((TARGET_PC >> 12) & 0x1FF) * 8

                        try:
                            l0_data = core.queue.read_buffer(
                                core.memory.buffer,
                                buffer_offset=l0_offset,
                                size=8
                            )
                            l0_lo = np.frombuffer(l0_data[:4], dtype=np.uint32)[0]
                            l0_hi = np.frombuffer(l0_data[4:8], dtype=np.uint32)[0]
                            l0_pte = l0_lo | (l0_hi << 32)

                            print(f"    L0 PTE = 0x{l0_pte:016x}")

                            if l0_pte & 1:
                                phys_ppn = (l0_pte >> 10) & 0x3FFFFFFFFF
                                phys_addr = phys_ppn * 4096 + (TARGET_PC & 0xFFF)
                                print(f"    PA = 0x{phys_addr:016x}")
                            else:
                                print(f"    L0 PTE INVALID!")
                        except Exception as e:
                            print(f"    Could not read L0 PTE: {e}")
                    else:
                        print(f"    L1 PTE INVALID!")
                except Exception as e:
                    print(f"    Could not read L1 PTE: {e}")
            else:
                print(f"    L2 PTE INVALID!")

        except Exception as e:
            print(f"  Could not read page table: {e}")
    else:
        print(f"  satp mode = {satp_mode} (MMU disabled)")

    # Capture memory around the faulting instruction
    try:
        # Read 16 bytes starting at PC
        phys_offset = TARGET_PC - 0x80200000
        mem_data = core.queue.read_buffer(
            core.memory.buffer,
            buffer_offset=phys_offset,
            size=16
        )
        with open("gpu_mem_at_0x80201048.bin", "wb") as f:
            f.write(mem_data)
        print(f"  Saved 16 bytes of memory to gpu_mem_at_0x80201048.bin")

        # Disassemble the instruction
        instr = int.from_bytes(mem_data[:4], 'little')
        print(f"  Instruction at PC: 0x{instr:08x}")
    except Exception as e:
        print(f"  Note: Could not read memory at PC: {e}")

    print("\n✓ GPU state captured!")
    print("Now run compare_qemu_gpu_state.py to compare with QEMU.")

if __name__ == "__main__":
    capture_gpu_state()