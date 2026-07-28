#!/usr/bin/env python3
"""
Hybrid Kernel Loader - Supports Both ELF64 and PE32+ Kernels

This is a unified loader that automatically detects the kernel format
and loads it appropriately for the GPU emulator.

Usage:
    python3 tools/hybrid_kernel_loader.py <kernel_path>
"""
import struct
from pathlib import Path
from typing import Optional, Tuple, List


# ELF64 Constants
ELF_MAGIC = b'\x7fELF'
EI_CLASS_64 = 2
EI_DATA_LITTLE = 1
ET_EXEC = 2
EM_RISCV = 243
PT_LOAD = 1

# PE32+ Constants
MZ_SIGNATURE = 0x5A4D
PE_SIGNATURE = 0x4550
IMAGE_FILE_MACHINE_RISCV64 = 0x5064
IMAGE_SCN_MEM_EXECUTE = 0x20000000
IMAGE_SCN_MEM_READ = 0x40000000
IMAGE_SCN_MEM_WRITE = 0x80000000


class ELF64Loader:
    """Load RISC-V ELF64 binaries."""

    def __init__(self, path: str):
        self.path = Path(path)
        with open(self.path, 'rb') as f:
            self.data = f.read()
        self._parse()

    def _parse(self):
        # ELF header
        self.ei_class = self.data[4]
        self.ei_data = self.data[5]
        self.e_type = struct.unpack_from('<H', self.data, 16)[0]
        self.e_machine = struct.unpack_from('<H', self.data, 18)[0]
        self.e_entry = struct.unpack_from('<Q', self.data, 24)[0]
        self.phoff = struct.unpack_from('<Q', self.data, 32)[0]
        self.phentsize = struct.unpack_from('<H', self.data, 54)[0]
        self.phnum = struct.unpack_from('<H', self.data, 56)[0]

        # Validate
        if self.ei_class != EI_CLASS_64:
            raise ValueError(f"Not ELF64 (EI_CLASS={self.ei_class})")
        if self.ei_data != EI_DATA_LITTLE:
            raise ValueError(f"Not little-endian (EI_DATA={self.ei_data})")
        if self.e_type != ET_EXEC:
            raise ValueError(f"Not executable (e_type={self.e_type})")
        if self.e_machine != EM_RISCV:
            raise ValueError(f"Not RISC-V (e_machine={self.e_machine})")

        # Program headers
        self.program_headers = []
        for i in range(self.phnum):
            offset = self.phoff + i * self.phentsize
            ph = {
                'p_type': struct.unpack_from('<I', self.data, offset)[0],
                'p_offset': struct.unpack_from('<Q', self.data, offset + 8)[0],
                'p_vaddr': struct.unpack_from('<Q', self.data, offset + 16)[0],
                'p_paddr': struct.unpack_from('<Q', self.data, offset + 24)[0],
                'p_filesz': struct.unpack_from('<Q', self.data, offset + 32)[0],
                'p_memsz': struct.unpack_from('<Q', self.data, offset + 40)[0],
                'p_flags': struct.unpack_from('<I', self.data, offset + 48)[0],
            }
            self.program_headers.append(ph)

        self.entry_point = self.e_entry
        self.format = "ELF64"

    def get_loadable_segments(self):
        """Return loadable program headers (PT_LOAD)."""
        return [ph for ph in self.program_headers if ph['p_type'] == PT_LOAD]

    def get_segment_data(self, segment):
        """Return raw segment data from the file."""
        return self.data[segment['p_offset']:segment['p_offset'] + segment['p_filesz']]


class PE32Loader:
    """Load UEFI PE32+ executables (Linux kernels)."""

    def __init__(self, path: str):
        self.path = Path(path)
        with open(self.path, 'rb') as f:
            self.data = f.read()
        self._parse()

    def _parse(self):
        # DOS header (MZ header)
        if len(self.data) < 64:
            raise ValueError("File too small to be PE32+")

        mz_signature = struct.unpack_from('<H', self.data, 0)[0]
        if mz_signature != MZ_SIGNATURE:
            raise ValueError(f"Not a PE file (MZ signature: 0x{mz_signature:04x})")

        # PE header offset is at 0x3C
        pe_offset = struct.unpack_from('<I', self.data, 0x3C)[0]

        # PE signature
        pe_signature = struct.unpack_from('<I', self.data, pe_offset)[0]
        if pe_signature != PE_SIGNATURE:
            raise ValueError(f"Not a PE file (PE signature: 0x{pe_signature:08x})")

        # COFF header
        machine = struct.unpack_from('<H', self.data, pe_offset + 4)[0]
        num_sections = struct.unpack_from('<H', self.data, pe_offset + 6)[0]

        # Optional header (PE32+)
        magic = struct.unpack_from('<H', self.data, pe_offset + 24)[0]
        if magic != 0x20b:  # PE32+ (64-bit)
            raise ValueError(f"Not PE32+ (64-bit), magic: 0x{magic:04x}")

        # PE32+ specific fields
        entry_point_rva = struct.unpack_from('<I', self.data, pe_offset + 24 + 16)[0]
        image_base = struct.unpack_from('<Q', self.data, pe_offset + 24 + 24)[0]
        
        # In our emulator, kernel base is 0x80200000
        self.entry_point = 0x80200000 + entry_point_rva

        # Section headers
        opt_header_size = struct.unpack_from('<H', self.data, pe_offset + 20)[0]
        section_offset = pe_offset + 24 + opt_header_size

        self.sections = []
        for i in range(num_sections):
            section_name = self.data[section_offset + i*40:section_offset + i*40 + 8].rstrip(b'\x00').decode('ascii', errors='replace')
            virtual_size = struct.unpack_from('<I', self.data, section_offset + i*40 + 8)[0]
            virtual_address = struct.unpack_from('<I', self.data, section_offset + i*40 + 12)[0]
            size_of_raw_data = struct.unpack_from('<I', self.data, section_offset + i*40 + 16)[0]
            pointer_to_raw_data = struct.unpack_from('<I', self.data, section_offset + i*40 + 20)[0]
            characteristics = struct.unpack_from('<I', self.data, section_offset + i*40 + 36)[0]

            self.sections.append({
                'name': section_name,
                'virtual_size': virtual_size,
                'virtual_address': virtual_address,
                'size_of_raw_data': size_of_raw_data,
                'pointer_to_raw_data': pointer_to_raw_data,
                'characteristics': characteristics,
            })

        self.image_base = image_base
        self.num_sections = num_sections
        self.format = "PE32+"

    def get_loadable_segments(self):
        """Return loadable sections (similar to ELF PT_LOAD)."""
        # All sections with non-zero raw data are loadable
        return [s for s in self.sections if s['size_of_raw_data'] > 0]

    def get_segment_data(self, segment):
        """Return raw section data from the file."""
        start = segment['pointer_to_raw_data']
        end = start + segment['size_of_raw_data']
        return self.data[start:end]


class HybridKernelLoader:
    """Auto-detects and loads both ELF64 and PE32+ kernels."""

    @staticmethod
    def detect_format(path: str) -> str:
        """Detect kernel format (ELF64 or PE32+)."""
        with open(path, 'rb') as f:
            header = f.read(256)

        # Check for ELF64 magic
        if header[:4] == ELF_MAGIC:
            ei_class = header[4]
            if ei_class == EI_CLASS_64:
                return "ELF64"

        # Check for PE32+ magic (MZ header)
        if len(header) >= 64:
            mz_signature = struct.unpack_from('<H', header, 0)[0]
            if mz_signature == MZ_SIGNATURE:
                # Some non-standard PE files have PE at offset 0x40 instead of 0x3C
                # Try both offsets
                for pe_offset in [struct.unpack_from('<I', header, 0x3C)[0], 0x40]:
                    if pe_offset > 0 and pe_offset < len(header) - 4:
                        pe_signature = struct.unpack_from('<I', header, pe_offset)[0]
                        if pe_signature == PE_SIGNATURE:
                            # Check if it's PE32+ (64-bit)
                            if pe_offset + 24 + 2 < len(header):
                                magic = struct.unpack_from('<H', header, pe_offset + 24)[0]
                                if magic == 0x20b:
                                    return "PE32+"

        raise ValueError(f"Unknown kernel format for {path}")

    @staticmethod
    def load(path: str) -> Tuple[object, str]:
        """Load kernel, return loader and format."""
        fmt = HybridKernelLoader.detect_format(path)

        if fmt == "ELF64":
            loader = ELF64Loader(path)
        elif fmt == "PE32+":
            loader = PE32Loader(path)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        return loader, fmt


def print_kernel_info(loader, fmt: str):
    """Print kernel information."""
    print(f"\n{'='*70}")
    print(f"Kernel Format: {fmt}")
    print(f"{'='*70}")

    if fmt == "ELF64":
        print(f"Entry Point: 0x{loader.entry_point:016x}")
        print(f"\nLoadable Segments:")
        print(f"{'VA':<16} {'Size':<12} {'Flags'}")
        print(f"{'-'*50}")

        for seg in loader.get_loadable_segments():
            flags = []
            if seg['p_flags'] & 1: flags.append('X')
            if seg['p_flags'] & 2: flags.append('W')
            if seg['p_flags'] & 4: flags.append('R')
            print(f"0x{seg['p_vaddr']:016x}  {seg['p_memsz']:<12} {''.join(flags)}")

    elif fmt == "PE32+":
        print(f"Entry Point: 0x{loader.entry_point:016x}")
        print(f"Image Base: 0x{loader.image_base:016x}")
        print(f"\nLoadable Sections:")
        print(f"{'Name':<10} {'VA':<12} {'Size':<12} {'Flags'}")
        print(f"{'-'*70}")

        for sec in loader.get_loadable_segments():
            flags = []
            if sec['characteristics'] & IMAGE_SCN_MEM_EXECUTE: flags.append('X')
            if sec['characteristics'] & IMAGE_SCN_MEM_READ: flags.append('R')
            if sec['characteristics'] & IMAGE_SCN_MEM_WRITE: flags.append('W')
            print(f"{sec['name']:<10} "
                  f"0x{sec['virtual_address']:08x}  "
                  f"{sec['virtual_size']:<12} "
                  f"{''.join(flags)}")


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 hybrid_kernel_loader.py <kernel_path>")
        print("\nExamples:")
        print("  python3 hybrid_kernel_loader.py boot_images/xv6.img")
        print("  python3 hybrid_kernel_loader.py boot_images/alpine_Image")
        print("  python3 hybrid_kernel_loader.py boot_images/hello.img")
        sys.exit(1)

    path = sys.argv[1]

    if not Path(path).exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)

    try:
        loader, fmt = HybridKernelLoader.load(path)
        print_kernel_info(loader, fmt)

        # Show total size to load
        total_size = 0
        for segment in loader.get_loadable_segments():
            if fmt == "ELF64":
                total_size += segment['p_memsz']
            else:
                total_size += segment['size_of_raw_data']

        print(f"\n{'='*70}")
        print(f"Total size to load into GPU memory: {total_size:,} bytes ({total_size // 1024 // 1024} MB)")
        print(f"Entry point: 0x{loader.entry_point:016x}")
        print(f"{'='*70}")

        print(f"\n✓ Hybrid loader working!")
        print(f"  Format: {fmt}")
        print(f"  Entry point: 0x{loader.entry_point:016x}")
        print(f"  Total memory: {total_size // 1024 // 1024} MB")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()