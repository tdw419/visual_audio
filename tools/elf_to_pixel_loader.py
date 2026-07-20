#!/usr/bin/env python3
"""
ELF-to-Pixel Loader

Converts RISC-V ELF binaries to RGBA pixel arrays for GPU execution.

Architecture:
- 1 Pixel = 1 32-bit instruction (RGBA = little-endian bytes)
- Pixel layout: [Byte0, Byte1, Byte2, Byte3] = [R, G, B, A]
- Supports RV32 ELF loading (loadable sections: .text, .data, .rodata)

Usage:
    python3 elf_to_pixel_loader.py kernel.elf kernel_pixels.png
    python3 elf_to_pixel_loader.py kernel.elf -o kernel_pixels.npy
"""

import struct
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np


class ELFLoader:
    """Parse and load RISC-V ELF binaries."""

    # ELF constants
    EI_CLASS_32 = 1
    EI_DATA_LITTLE = 1
    ET_EXEC = 2
    EM_RISCV = 243

    # Section types
    SHT_NULL = 0
    SHT_PROGBITS = 1
    SHT_SYMTAB = 2
    SHT_STRTAB = 3
    SHT_RELA = 4
    SHT_NOBITS = 8

    def __init__(self, elf_path: str):
        self.path = Path(elf_path)
        self.data: bytes = b''
        self.entry_point: int = 0
        self.sections: List[dict] = []
        self._parse()

    def _parse(self):
        """Parse ELF header and program/section headers."""
        with open(self.path, 'rb') as f:
            self.data = f.read()

        # Validate ELF magic
        if self.data[:4] != b'\x7fELF':
            raise ValueError(f"Invalid ELF file: {self.path}")

        # Parse ELF header
        ei_class = self.data[4]
        ei_data = self.data[5]
        e_type = struct.unpack('<H', self.data[16:18])[0]
        e_machine = struct.unpack('<H', self.data[18:20])[0]
        e_entry = struct.unpack('<I', self.data[24:28])[0]
        e_phoff = struct.unpack('<I', self.data[28:32])[0]
        e_phentsize = struct.unpack('<H', self.data[42:44])[0]
        e_phnum = struct.unpack('<H', self.data[44:46])[0]
        e_shoff = struct.unpack('<I', self.data[32:36])[0]
        e_shentsize = struct.unpack('<H', self.data[46:48])[0]
        e_shnum = struct.unpack('<H', self.data[48:50])[0]

        # Validate ELF32 RISC-V
        if ei_class != self.EI_CLASS_32:
            raise ValueError(f"Only ELF32 supported (got class {ei_class})")
        if ei_data != self.EI_DATA_LITTLE:
            raise ValueError(f"Only little-endian ELF supported")
        if e_machine != self.EM_RISCV:
            raise ValueError(f"Only RISC-V ELF supported (got machine {e_machine})")

        self.entry_point = e_entry

        # Parse section headers
        for i in range(e_shnum):
            sh_offset = e_shoff + i * e_shentsize
            sh_name = struct.unpack('<I', self.data[sh_offset:sh_offset+4])[0]
            sh_type = struct.unpack('<I', self.data[sh_offset+4:sh_offset+8])[0]
            sh_flags = struct.unpack('<I', self.data[sh_offset+8:sh_offset+12])[0]
            sh_addr = struct.unpack('<I', self.data[sh_offset+12:sh_offset+16])[0]
            sh_offset_data = struct.unpack('<I', self.data[sh_offset+16:sh_offset+20])[0]
            sh_size = struct.unpack('<I', self.data[sh_offset+20:sh_offset+24])[0]

            # String table for section names
            strtab_offset = e_shoff + e_shentsize * struct.unpack('<H', self.data[sh_offset+24:sh_offset+26])[0]
            strtab_data_offset = struct.unpack('<I', self.data[strtab_offset+16:strtab_offset+20])[0]
            name_str = self._get_string(strtab_data_offset + sh_name)

            self.sections.append({
                'name': name_str,
                'type': sh_type,
                'flags': sh_flags,
                'addr': sh_addr,
                'offset': sh_offset_data,
                'size': sh_size,
            })

    def _get_string(self, offset: int) -> str:
        """Extract null-terminated string from ELF data."""
        end = offset
        while end < len(self.data) and self.data[end] != 0:
            end += 1
        return self.data[offset:end].decode('utf-8', errors='replace')

    def get_loadable_sections(self) -> List[dict]:
        """Return list of PROGBITS sections that should be loaded."""
        return [s for s in self.sections if s['type'] in (self.SHT_PROGBITS, self.SHT_NOBITS)]

    def get_section_data(self, section: dict) -> bytes:
        """Extract raw section data from ELF."""
        if section['type'] == self.SHT_NOBITS:
            return b'\x00' * section['size']  # BSS sections are zero-filled
        return self.data[section['offset']:section['offset'] + section['size']]

    def print_info(self):
        """Print ELF information."""
        print(f"ELF File: {self.path}")
        print(f"Entry Point: 0x{self.entry_point:08x}")
        print(f"\nLoadable Sections:")
        for sec in self.get_loadable_sections():
            print(f"  {sec['name']:20s} 0x{sec['addr']:08x} - 0x{sec['addr'] + sec['size']:08x} ({sec['size']} bytes)")


def word_to_rgba(word: int) -> Tuple[int, int, int, int]:
    """Convert 32-bit word to RGBA tuple (little-endian)."""
    return (
        word & 0xFF,           # R: byte 0
        (word >> 8) & 0xFF,    # G: byte 1
        (word >> 16) & 0xFF,   # B: byte 2
        (word >> 24) & 0xFF,   # A: byte 3
    )


def load_elf_to_pixels(
    elf_path: str,
    image_width: int = 4096,
    image_height: int = 4096,
    base_addr: int = 0x00000000,
) -> Tuple[np.ndarray, int]:
    """
    Load ELF binary into RGBA pixel array.

    Args:
        elf_path: Path to RISC-V ELF binary (or raw binary)
        image_width: Width of output pixel array
        image_height: Height of output pixel array
        base_addr: Base memory address (default: 0x00000000)

    Returns:
        (pixel_array, entry_point): RGBA pixel array and ELF entry point

    Pixel Mapping:
        pixel_index = (vaddr - base_addr) / 4
        pixel[x, y] = RGBA(word) where x = pixel_index % width, y = pixel_index // width
    """
    # Check if this is a valid ELF file
    try:
        elf = ELFLoader(elf_path)
        is_elf = True
    except ValueError:
        is_elf = False

    # Create pixel array (initialized to zeros)
    total_pixels = image_width * image_height
    pixels = np.zeros((image_height, image_width, 4), dtype=np.uint8)

    entry_point = base_addr

    if is_elf:
        # Load ELF sections
        entry_point = elf.entry_point

        for section in elf.get_loadable_sections():
            section_data = elf.get_section_data(section)

            # Calculate pixel offset for this section
            section_base = section['addr'] - base_addr

            # Load data as 32-bit words into pixels
            word_count = (len(section_data) + 3) // 4

            for word_idx in range(word_count):
                # Extract 32-bit word (little-endian)
                word_bytes = section_data[word_idx*4:word_idx*4+4]
                if len(word_bytes) < 4:
                    word_bytes += b'\x00' * (4 - len(word_bytes))
                word = struct.unpack('<I', word_bytes)[0]

                # Calculate pixel position
                pixel_idx = section_base // 4 + word_idx

                if pixel_idx >= total_pixels:
                    print(f"Warning: Section {section['name']} exceeds pixel array size")
                    break

                # Calculate 2D coordinates
                x = pixel_idx % image_width
                y = pixel_idx // image_width

                # Write pixel (RGBA = word bytes)
                pixels[y, x] = word_to_rgba(word)
    else:
        # Load raw binary (treat as starting at base_addr)
        print(f"Loading raw binary (not ELF)")
        with open(elf_path, 'rb') as f:
            raw_data = f.read()

        word_count = (len(raw_data) + 3) // 4

        for word_idx in range(word_count):
            # Extract 32-bit word (little-endian)
            word_bytes = raw_data[word_idx*4:word_idx*4+4]
            if len(word_bytes) < 4:
                word_bytes += b'\x00' * (4 - len(word_bytes))
            word = struct.unpack('<I', word_bytes)[0]

            # Calculate pixel position
            pixel_idx = word_idx

            if pixel_idx >= total_pixels:
                print(f"Warning: Binary exceeds pixel array size")
                break

            # Calculate 2D coordinates
            x = pixel_idx % image_width
            y = pixel_idx // image_width

            # Write pixel (RGBA = word bytes)
            pixels[y, x] = word_to_rgba(word)

    return pixels, entry_point


def save_pixels_as_png(pixels: np.ndarray, output_path: str):
    """Save pixel array as PNG image."""
    try:
        from PIL import Image
        img = Image.fromarray(pixels, 'RGBA')
        img.save(output_path)
        print(f"Saved RGBA pixel array to {output_path}")
    except ImportError:
        print("PIL/Pillow not installed. Saving as numpy array instead.")
        np.save(output_path.replace('.png', '.npy'), pixels)
        print(f"Saved RGBA pixel array to {output_path.replace('.png', '.npy')}")


def save_pixels_as_npy(pixels: np.ndarray, output_path: str):
    """Save pixel array as numpy .npy file."""
    np.save(output_path, pixels)
    print(f"Saved RGBA pixel array to {output_path}")


def create_minimal_test_kernel(output_path: str = 'kernel_minimal.elf'):
    """Create a minimal RISC-V test kernel for verification."""

    # Hand-coded RISC-V machine code
    #   lui a0, 0x00100        ; Load upper immediate: a0 = 0x00100000
    # Hand-coded RISC-V machine code
    #   lui a0, 0x00100        ; Load upper immediate: a0 = 0x00100000
    #   addi a0, a0, 0x100    ; Add immediate: a0 = 0x00100100
    #   addi a1, x0, 42       ; a1 = 42
    #   addi a2, x0, 23       ; a2 = 23
    #   add a3, a1, a2        ; a3 = 65
    #   lui ra, 0x00000       ; ra = 0 (just for instruction coverage)
    #   ecall                 ; System call (will halt emulator)

    machine_code = bytes([
        # lui a0, 0x00100  (0x00100537)
        0x37, 0x05, 0x10, 0x00,

        # addi a0, a0, 0x100  (0x10050513)
        0x13, 0x05, 0x05, 0x10,

        # addi a1, x0, 42  (0x02a00593)
        0x93, 0x05, 0xa0, 0x02,

        # addi a2, x0, 23  (0x01700613)
        0x13, 0x06, 0x70, 0x01,

        # add a3, a1, a2  (0x00c586b3)
        0xb3, 0x86, 0xc5, 0x00,

        # lui ra, 0x00000  (0x00000097)
        0x97, 0x00, 0x00, 0x00,

        # ecall (0x00000073)
        0x73, 0x00, 0x00, 0x00,
    ])

    with open(output_path, 'wb') as f:
        f.write(machine_code)

    print(f"Created minimal test kernel: {output_path}")
    print(f"  Size: {len(machine_code)} bytes ({len(machine_code)//4} instructions)")


def main():
    parser = argparse.ArgumentParser(description='Load RISC-V ELF binary into RGBA pixels')
    parser.add_argument('elf_path', nargs='?', help='Path to RISC-V ELF binary (not required with --create-test)')
    parser.add_argument('-o', '--output', help='Output file path (.png or .npy)')
    parser.add_argument('-w', '--width', type=int, default=4096, help='Image width (default: 4096)')
    parser.add_argument('--height', type=int, default=4096, help='Image height (default: 4096)')
    parser.add_argument('--base-addr', type=int, default=0x00000000, help='Base memory address (default: 0x00000000)')
    parser.add_argument('--info', action='store_true', help='Print ELF information and exit')
    parser.add_argument('--create-test', action='store_true', help='Create minimal test kernel')

    args = parser.parse_args()

    if args.create_test:
        create_minimal_test_kernel()
        return

    if not args.elf_path:
        parser.error("elf_path is required (or use --create-test)")

    # Check if we should just print ELF info
    if args.info:
        try:
            loader = ELFLoader(args.elf_path)
            loader.print_info()
        except ValueError:
            print(f"File is not a valid ELF: {args.elf_path}")
        return

    # Convert to pixels
    print(f"Loading: {args.elf_path}")
    pixels, entry_point = load_elf_to_pixels(
        args.elf_path,
        image_width=args.width,
        image_height=args.height,
        base_addr=args.base_addr,
    )

    print(f"Entry point: 0x{entry_point:08x}")
    print(f"Pixel array shape: {pixels.shape}")
    print(f"Non-zero pixels: {np.count_nonzero(pixels)}")

    # Determine output format
    if args.output:
        if args.output.endswith('.npy'):
            save_pixels_as_npy(pixels, args.output)
        else:
            save_pixels_as_png(pixels, args.output)
    else:
        # Default: save as both PNG and NPY
        base_name = Path(args.elf_path).stem
        save_pixels_as_png(pixels, f"{base_name}_pixels.png")
        save_pixels_as_npy(pixels, f"{base_name}_pixels.npy")


if __name__ == '__main__':
    main()