#!/usr/bin/env python3
"""
Simplified Alpine Linux GPU Boot - Identity Mapping
"""

import struct
import numpy as np
from pathlib import Path
from typing import List, Tuple
import sys


# ============================================================================
# ELF64 LOADER
# ============================================================================

class ELF64Loader:
    """Parse and load RISC-V ELF64 binaries."""

    EI_CLASS_64 = 2
    EI_DATA_LITTLE = 1
    ET_EXEC = 2
    EM_RISCV = 243

    def __init__(self, elf_path: str):
        self.path = Path(elf_path)
        self.data: bytes = b''
        self.entry_point: int = 0
        self.program_headers: List[dict] = []
        self._parse()

    def _parse(self):
        """Parse ELF64 header and program headers."""
        with open(self.path, 'rb') as f:
            self.data = f.read()

        if self.data[:4] != b'\x7fELF':
            raise ValueError(f"Invalid ELF file: {self.path}")

        e_class = self.data[4]
        e_data = self.data[5]
        e_type = struct.unpack('<H', self.data[16:18])[0]
        e_machine = struct.unpack('<H', self.data[18:20])[0]
        e_entry = struct.unpack('<Q', self.data[24:32])[0]
        e_phoff = struct.unpack('<Q', self.data[32:40])[0]
        e_phentsize = struct.unpack('<H', self.data[54:56])[0]
        e_phnum = struct.unpack('<H', self.data[56:58])[0]

        if e_class != self.EI_CLASS_64:
            raise ValueError(f"Only ELF64 supported (got class {e_class})")
        if e_data != self.EI_DATA_LITTLE:
            raise ValueError("Only little-endian ELF supported")
        if e_machine != self.EM_RISCV:
            raise ValueError(f"Only RISC-V ELF supported (got machine {e_machine})")

        self.entry_point = e_entry

        for i in range(e_phnum):
            ph_offset = e_phoff + i * e_phentsize
            p_type = struct.unpack('<I', self.data[ph_offset:ph_offset+4])[0]

            if p_type == 1:  # PT_LOAD
                p_flags = struct.unpack('<I', self.data[ph_offset+4:ph_offset+8])[0]
                p_offset = struct.unpack('<Q', self.data[ph_offset+8:ph_offset+16])[0]
                p_vaddr = struct.unpack('<Q', self.data[ph_offset+16:ph_offset+24])[0]
                p_paddr = struct.unpack('<Q', self.data[ph_offset+24:ph_offset+32])[0]
                p_filesz = struct.unpack('<Q', self.data[ph_offset+32:ph_offset+40])[0]
                p_memsz = struct.unpack('<Q', self.data[ph_offset+40:ph_offset+48])[0]

                self.program_headers.append({
                    'offset': p_offset,
                    'vaddr': p_vaddr,
                    'paddr': p_paddr,
                    'filesz': p_filesz,
                    'memsz': p_memsz,
                    'flags': p_flags,
                })


# ============================================================================
# SIMPLIFIED SV39 PAGE TABLES (Identity Mapping)
# ============================================================================

def build_sv39_page_tables_simple(vaddr_start: int, vaddr_end: int) -> Tuple[bytes, int]:
    """
    Build minimal SV39 page tables for identity mapping.

    Returns: (page_table_bytes, root_ppn)
    """
    PAGE_SIZE = 4096

    # Map the entire 256MB with L1 megapages (2MB each)
    # We need 128 megapages for 256MB, which fits in a single L1 table (512 entries)

    num_megapages = 128  # 256MB / 2MB

    print(f"  Region: 0x{vaddr_start:016x} - 0x{vaddr_end:016x}")
    print(f"  Mapping entire 256MB via L1 megapages")

    # Allocate L1 root page table
    root_table = bytearray(4096)

    root_ppn = 0x10000000 >> 12  # Put root table at 256MB physical

    # Fill L1 entries pointing to megapages
    for i in range(num_megapages):
        # L1 index: VPN2 (bits [38:30])
        # For identity mapping, each 2MB chunk gets a direct PTE

        megapage_addr = i * 0x200000
        ppn = megapage_addr >> 12  # Identity mapping

        # L1 megapage PTE: [PPN, reserved, D, A, G, U, X, W, R, V]
        # For kernel: X=1, W=1, R=1, V=1, A=1, D=1
        pte = (ppn << 10) | 0xCF  # V=1, R=1, W=1, X=1, A=1, D=1

        entry_offset = i * 4
        if entry_offset + 4 <= 4096:
            root_table[entry_offset:entry_offset+4] = pte.to_bytes(4, 'little')

    return bytes(root_table), root_ppn


# ============================================================================
# MEMORY IMAGE BUILDER
# ============================================================================

def build_memory_image(elf_path: str) -> Tuple[np.ndarray, int, int]:
    """Build memory image with identity mapping (256MB)."""
    print("[1] Loading ELF64 kernel...")
    elf = ELF64Loader(elf_path)

    print(f"  Entry point: 0x{elf.entry_point:016x}")

    # 256MB memory
    memory_size = 256 * 1024 * 1024
    memory = bytearray(memory_size)

    print("\n[2] Loading kernel segments...")
    for seg in elf.program_headers:
        data = elf.data[seg['offset']:seg['offset'] + seg['filesz']]

        # For identity mapping, store segment at its virtual address
        # But kernel uses high addresses (0x80000000+), which don't fit in 256MB
        # Solution: Remap high addresses to low addresses
        addr = seg['vaddr'] & 0x0FFFFFFF  # Mask to 256MB range

        flags_str = []
        if seg['flags'] & 0x1: flags_str.append('X')
        if seg['flags'] & 0x2: flags_str.append('W')
        if seg['flags'] & 0x4: flags_str.append('R')
        flags_str = ''.join(flags_str) or '---'

        print(f"  Segment: 0x{seg['vaddr']:016x} -> 0x{addr:016x} ({len(data)} bytes) [{flags_str}]")

        if addr + len(data) <= memory_size:
            memory[addr:addr + len(data)] = data

            # Zero-fill BSS
            if seg['memsz'] > seg['filesz']:
                bss_start = addr + seg['filesz']
                bss_end = addr + seg['memsz']
                if bss_end <= memory_size:
                    memory[bss_start:bss_end] = b'\x00' * (bss_end - bss_start)
        else:
            print(f"  WARNING: Segment exceeds 256MB memory")

    # Build page tables
    print("\n[3] Building SV39 page tables (identity mapping)...")

    pt_data, root_ppn = build_sv39_page_tables_simple(0, memory_size)

    # Store page tables at 256MB end
    pt_addr = memory_size - 4096
    memory[pt_addr:pt_addr + len(pt_data)] = pt_data
    root_ppn = pt_addr >> 12
    print(f"  Page tables at: 0x{pt_addr:016x} (PPN={root_ppn})")

    # Convert to RGBA pixels
    print(f"\n[4] Converting to RGBA pixels...")
    num_pixels = memory_size // 4
    pixels = np.zeros((num_pixels, 4), dtype=np.uint8)

    for i in range(num_pixels):
        word = struct.unpack('<I', memory[i*4:i*4+4])[0]
        pixels[i] = [
            word & 0xFF,
            (word >> 8) & 0xFF,
            (word >> 16) & 0xFF,
            (word >> 24) & 0xFF,
        ]

    satp_value = (8 << 22) | root_ppn
    print(f"  Memory: {memory_size // (1024*1024)}MB ({num_pixels} pixels)")
    print(f"  SATP: 0x{satp_value:08x} (SV39 mode, root PPN={root_ppn})")

    return pixels, root_ppn, elf.entry_point


# ============================================================================
# GPU EXECUTION
# ============================================================================

def boot_on_gpu(elf_path: str):
    """Boot ELF on GPU."""
    print("=" * 70)
    print("GPU BOOT - Simplified Identity Mapping")
    print("=" * 70)

    pixels, root_ppn, entry_point = build_memory_image(elf_path)

    print("\n[5] Setup complete!")
    print(f"  Pixels: {pixels.shape}")
    print(f"  Entry: 0x{entry_point:016x}")
    print(f"  Root PPN: {root_ppn}")

    # Save pixel dump for inspection
    np.save('alpine_gpu_pixels.npy', pixels)
    print(f"\n[6] Saved pixel dump: alpine_gpu_pixels.npy")

    print("\nTo boot on GPU, run:")
    print(f"  python3 boot_gpu_execute.py alpine_gpu_pixels.npy {root_ppn} 0x{entry_point:x}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <elf64_binary>")
        sys.exit(1)

    boot_on_gpu(sys.argv[1])