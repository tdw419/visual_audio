#!/usr/bin/env python3
"""
Watch page table writes in real-time during boot to catch the EFAULT moment.

This uses the linear memory view (de-Hilbert-mapped) to detect page table
modifications without needing complex GPU instrumentation.
"""
import sys
import os
import struct
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))

from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE
from spatial_rv64i_cpu import SpatialRV64ICore
import sqlite3
from pathlib import Path

# Load symbol DB for PC resolution
SYMBOL_DB = Path(__file__).parent.parent / "boot_images" / "alpine_riscv64_semantic.db"

def resolve_pc(pc: int) -> str:
    """Resolve a PC to a symbol name."""
    try:
        conn = sqlite3.connect(str(SYMBOL_DB))
        cursor = conn.cursor()
        
        signed_pc = pc - (1 << 64) if pc >= (1 << 63) else pc
        cursor.execute("""
            SELECT name, addr FROM kernel_symbols 
            WHERE addr <= ? ORDER BY addr DESC LIMIT 1
        """, (signed_pc,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            name, sym_addr = result
            offset = pc - (sym_addr + (1 << 64) if sym_addr < 0 else sym_addr)
            return f"{name}+0x{offset:x}"
        return f"<unknown>"
    except Exception as e:
        return f"<error: {e}>"

def linearize_gpu_memory(core):
    """De-Hilbert-map GPU memory to linear bytes."""
    memory_spatial = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(memory_spatial, dtype=np.uint32)
    linear_words = spatial[core.hilbert_lut_np]
    return linear_words.tobytes()

def read_pte(linear_mem, pa):
    """Read a 64-bit PTE from linear memory at physical address."""
    if pa >= 0x80000000 and pa < 0x80000000 + len(linear_mem):
        offset = pa - 0x80000000
        if offset + 8 <= len(linear_mem):
            return struct.unpack('<Q', linear_mem[offset:offset+8])[0]
    return None

def read_satp(core):
    """Read the current satp CSR."""
    return core.read_csr(0x180)

def check_pt_entry(linear_mem, satp, va):
    """Check if a specific VA is mapped in the page table."""
    satp_ppn = satp & 0x3FFFFF
    root_pa = (satp_ppn << 12)
    
    vpn2 = (va >> 30) & 0x1FF
    vpn1 = (va >> 21) & 0x1FF
    vpn0 = (va >> 12) & 0x1FF
    
    # Level 2
    l2_pte = read_pte(linear_mem, root_pa + (vpn2 << 3))
    if l2_pte is None or not (l2_pte & 1):
        return None, "L2 unmapped"
    
    if l2_pte & 8 or l2_pte & 2:  # Leaf
        return l2_pte, "L2 leaf"
    
    # Level 1
    ppn2 = l2_pte >> 10
    l1_pte = read_pte(linear_mem, (ppn2 << 12) + (vpn1 << 3))
    if l1_pte is None or not (l1_pte & 1):
        return None, "L1 unmapped"
    
    if l1_pte & 8 or l1_pte & 2:  # Leaf
        return l1_pte, "L1 leaf"
    
    # Level 0
    ppn1 = l1_pte >> 10
    l0_pte = read_pte(linear_mem, (ppn1 << 12) + (vpn0 << 3))
    if l0_pte is None or not (l0_pte & 1):
        return None, "L0 unmapped"
    
    return l0_pte, "L0 leaf"

def main():
    print('[1] Initializing GPU core...')
    core = SpatialRV64ICore(RAM_SIZE)
    
    print('[2] Loading boot components...')
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    print('[3] Setting boot registers...')
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    
    print('[4] Starting page table watch...')
    
    # Monitor the faulting address from EFAULT analysis
    fault_va = 0x2ada15603d
    print(f"   Watching VA: 0x{fault_va:016x}")
    
    # Snapshot initial linear memory for diffing
    initial_linear = linearize_gpu_memory(core)
    
    steps = 0
    batch_size = 100_000  # Smaller batches for more frequent checks
    last_satp = None
    last_pte = None
    
    # Wait until we enter S-mode and MMU is active
    in_s_mode = False
    
    while steps < 2_000_000_000:  # 2B steps max
        core.step(steps=batch_size)
        steps += batch_size
        
        # Check state every 100K steps
        if steps % 100_000 == 0:
            state = core.get_state()
            pc = state['pc']
            mode = state['mode']
            
            # Wait for S-mode (MMU active)
            if mode == 1:  # S-mode
                if not in_s_mode:
                    print(f"\n[!] Entered S-mode at {steps:,} steps, PC=0x{pc:016x}")
                    in_s_mode = True
                    initial_linear = linearize_gpu_memory(core)  # Re-snapshot
                
                # Check satp for changes
                satp = read_satp(core)
                if satp != last_satp:
                    print(f"\n[{steps:,}] SATP changed: 0x{last_satp:016x} -> 0x{satp:016x}")
                    last_satp = satp
                
                # Get current linear memory
                current_linear = linearize_gpu_memory(core)
                
                # Check if fault VA is mapped
                pte, level = check_pt_entry(current_linear, satp, fault_va)
                
                if pte != last_pte:
                    if pte:
                        print(f"\n[{steps:,}] PTE CREATED! 0x{pte:016x} at {level}")
                        print(f"  PC at creation: 0x{pc:016x} ({resolve_pc(pc)})")
                        
                        # Show the PTE bits
                        v = pte & 1
                        r = (pte >> 1) & 1
                        w = (pte >> 2) & 1
                        x = (pte >> 3) & 1
                        u = (pte >> 4) & 1
                        ppn = pte >> 10
                        print(f"  V={v} R={r} W={w} X={x} U={u} PPN=0x{ppn:x}")
                        
                        # Keep stepping to see what happens next
                    else:
                        print(f"\n[{steps:,}] PTE became unmapped at {level}")
                        print(f"  PC: 0x{pc:016x} ({resolve_pc(pc)})")
                    
                    last_pte = pte
                
                # Check for UART output indicating EFAULT
                uart = core.read_uart_output()
                if uart:
                    uart_str = uart.decode('latin-1', errors='replace')
                    if "couldn't execute" in uart_str or "Failed to execute" in uart_str:
                        print(f"\n[!!!] EFAULT DETECTED at {steps:,} steps!")
                        print(f"     Last PC: 0x{pc:016x} ({resolve_pc(pc)})")
                        print(f"     VA 0x{fault_va:016x} PTE: {pte or 'unmapped'} ({level})")
                        print(f"     Current SATP: 0x{satp:016x}")
                        
                        # Check page table
                        if pte is None:
                            print("\n[!!!] ROOT CAUSE CONFIRMED: PTE never created!")
                            print("      The kernel did not map page 0x{fault_va:016x}")
                        
                        break
            
            # Periodic progress
            if steps % 10_000_000 == 0:
                print(f"[{steps//1_000_000}M] PC=0x{pc:016x} ({resolve_pc(pc)}) mode={mode}")

if __name__ == '__main__':
    main()