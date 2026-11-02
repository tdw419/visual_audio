#!/usr/bin/env python3
"""
Simplified Alpine Linux GPU Boot - No MMU, Correct segment loading
"""

import struct
import numpy as np
from pathlib import Path
from typing import List, Tuple
import sys


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
            ph_data = self.data[ph_offset:ph_offset + e_phentsize]
            
            p_type = struct.unpack('<I', ph_data[0:4])[0]

            if p_type == 1:  # PT_LOAD
                p_flags = struct.unpack('<I', ph_data[4:8])[0]
                p_offset = struct.unpack('<Q', ph_data[8:16])[0]
                p_vaddr = struct.unpack('<Q', ph_data[16:24])[0]
                p_paddr = struct.unpack('<Q', ph_data[24:32])[0]
                p_filesz = struct.unpack('<Q', ph_data[32:40])[0]
                p_memsz = struct.unpack('<Q', ph_data[40:48])[0]

                self.program_headers.append({
                    'offset': p_offset,
                    'vaddr': p_vaddr,
                    'paddr': p_paddr,
                    'filesz': p_filesz,
                    'memsz': p_memsz,
                    'flags': p_flags,
                })


def build_memory_image_no_mmu(elf_path: str) -> Tuple[np.ndarray, int]:
    """Build memory image without MMU (direct physical mapping)."""
    print("[1] Loading ELF64 kernel...")
    elf = ELF64Loader(elf_path)

    print(f"  Entry point: 0x{elf.entry_point:016x}")

    # 16MB memory
    memory_size = 16 * 1024 * 1024
    memory = bytearray(memory_size)

    print("\n[2] Loading kernel segments (no MMU)...")
    
    # Find LOAD segment containing entry point
    entry_seg_vaddr = 0
    entry_seg_offset = 0
    for seg in elf.program_headers:
        if elf.entry_point >= seg['vaddr'] and elf.entry_point < seg['vaddr'] + seg['memsz']:
            entry_seg_vaddr = seg['vaddr']
            entry_seg_offset = seg['offset']
            print(f"  Entry point in segment at 0x{entry_seg_vaddr:016x} (file offset 0x{entry_seg_offset:x})")
            break
    
    # Calculate where entry point sits within the segment file data
    entry_offset_in_seg_data = elf.entry_point - entry_seg_vaddr
    entry_file_offset = entry_seg_offset + entry_offset_in_seg_data
    print(f"  Entry point at file offset 0x{entry_file_offset:x}")
    
    # Read the entry point instruction
    entry_word = struct.unpack('<I', elf.data[entry_file_offset:entry_file_offset+4])[0]
    print(f"  Entry instruction: 0x{entry_word:08x}")
    
    # Calculate remapping: segment at virtual 0x7ffff000 loads at physical 0x1000
    # So entry (0x80000000) maps to physical 0x1000
    seg_phys_offset = 0x1000  # Start LOAD segment at 0x1000
    entry_phys = seg_phys_offset + entry_offset_in_seg_data
    
    for seg in elf.program_headers:
        # Read segment data from file
        seg_data = elf.data[seg['offset']:seg['offset'] + seg['filesz']]
        
        print(f"  Segment: offset=0x{seg['offset']:04x} vaddr=0x{seg['vaddr']:016x} ({len(seg_data)} bytes)")

        # Remap LOAD segments to physical addresses
        if seg['vaddr'] == entry_seg_vaddr:
            seg_start = seg_phys_offset
        else:
            seg_start = seg['vaddr'] - entry_seg_vaddr + seg_phys_offset

        flags_str = []
        if seg['flags'] & 0x1: flags_str.append('X')
        if seg['flags'] & 0x2: flags_str.append('W')
        if seg['flags'] & 0x4: flags_str.append('R')
        flags_str = ''.join(flags_str) or '---'
        
        print(f'  -> Mapped to 0x{seg_start:016x} [{flags_str}]')

        if seg_start + len(seg_data) <= memory_size:
            memory[seg_start:seg_start + len(seg_data)] = seg_data

            # Zero-fill BSS
            if seg['memsz'] > seg['filesz']:
                bss_start = seg_start + seg['filesz']
                bss_end = seg_start + seg['memsz']
                if bss_end <= memory_size:
                    memory[bss_start:bss_end] = b'\x00' * (bss_end - bss_start)
        else:
            print(f"  WARNING: Segment exceeds 16MB memory")

    # Convert to RGBA pixels
    print(f"\n[3] Converting to RGBA pixels...")
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

    print(f"  Memory: {memory_size // 1024}KB ({num_pixels} pixels)")
    print(f"  Entry point (physical): 0x{entry_phys:016x}")

    return pixels, entry_phys


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <elf64_binary>")
        sys.exit(1)

    print("=" * 70)
    print("GPU BOOT - No MMU (Direct Physical Mapping)")
    print("=" * 70)

    pixels, entry_point = build_memory_image_no_mmu(sys.argv[1])

    print("\n[4] Setup complete!")
    print(f"  Pixels: {pixels.shape}")
    print(f"  Entry: 0x{entry_point:016x}")

    # Save pixel dump
    np.save('test_kernel_no_mmu_v3.npy', pixels)
    print(f"\n[5] Saved pixel dump: test_kernel_no_mmu_v3.npy")

    print("\nTo boot on GPU without MMU:")
    print(f"  python3 boot_gpu_execute_no_mmu.py test_kernel_no_mmu_v3.npy 0x{entry_point:x}")