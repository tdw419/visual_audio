#!/usr/bin/env python3
"""
Direct GPU Boot without MMU (identity mapping, SATP=off)
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


def build_memory_image_no_mmu(elf_path: str) -> Tuple[np.ndarray, int]:
    """Build memory image without MMU (direct physical mapping, 1MB for test)."""
    print("[1] Loading ELF64 kernel...")
    elf = ELF64Loader(elf_path)

    print(f"  Entry point: 0x{elf.entry_point:016x}")

    # 16MB memory (sufficient for test kernel)
    memory_size = 16 * 1024 * 1024
    memory = bytearray(memory_size)

    print("\n[2] Loading kernel segments (no MMU)...")
    entry_point_low = 0

    for seg in elf.program_headers:
        data = elf.data[seg['offset']:seg['offset'] + seg['filesz']]

        # Remap 0x7ffff000 -> 0 (segment start)
        addr = seg['vaddr'] - 0x7ffff000

        # Check if this is the entry point segment
        if elf.entry_point >= seg['vaddr'] and elf.entry_point < seg['vaddr'] + seg['memsz']:
            entry_point_low = addr + (elf.entry_point - seg['vaddr'])

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
            print(f"  WARNING: Segment exceeds 1MB memory")

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
    print(f"  Entry point (remapped): 0x{entry_point_low:016x}")

    return pixels, entry_point_low


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
    np.save('test_kernel_no_mmu.npy', pixels)
    print(f"\n[5] Saved pixel dump: test_kernel_no_mmu.npy")

    print("\nTo boot on GPU without MMU:")
    print(f"  python3 boot_gpu_execute_no_mmu.py test_kernel_no_mmu.npy 0x{entry_point:x}")