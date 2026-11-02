#!/usr/bin/env python3
"""
Proof of Concept: PE32+ Loader for RISC-V UEFI Kernels

This is a minimal PE32+ parser to demonstrate what's needed to boot
Ubuntu/Alpine RISC-V kernels on the GPU emulator.

Usage:
    python3 tools/pe32_loader.py <path_to_pe32_kernel>
"""
import struct
from pathlib import Path

# PE32+ Constants
MZ_SIGNATURE = 0x5A4D  # "MZ"
PE_SIGNATURE = 0x4550  # "PE"
IMAGE_FILE_MACHINE_RISCV64 = 0x5064  # RISC-V 64-bit
IMAGE_SCN_MEM_EXECUTE = 0x20000000
IMAGE_SCN_MEM_READ = 0x40000000
IMAGE_SCN_MEM_WRITE = 0x80000000


class PE32Loader:
    """Minimal PE32+ loader for UEFI kernels."""

    def __init__(self, path: str):
        self.path = Path(path)
        with open(self.path, 'rb') as f:
            self.data = f.read()
        self._parse()

    def _parse(self):
        """Parse PE32+ headers."""

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

        # COFF header (at pe_offset + 4)
        machine = struct.unpack_from('<H', self.data, pe_offset + 4)[0]
        num_sections = struct.unpack_from('<H', self.data, pe_offset + 6)[0]
        timestamp = struct.unpack_from('<I', self.data, pe_offset + 8)[0]

        # Optional header (PE32+ has different layout than PE32)
        magic = struct.unpack_from('<H', self.data, pe_offset + 24)[0]

        if magic == 0x10b:  # PE32 (32-bit)
            raise ValueError("PE32 (32-bit) not supported, need PE32+ (64-bit)")
        elif magic == 0x20b:  # PE32+ (64-bit)
            pass  # Good
        else:
            raise ValueError(f"Unknown PE magic: 0x{magic:04x}")

        # PE32+ specific fields
        # Entry point is at offset 24 in optional header
        self.entry_point = struct.unpack_from('<Q', self.data, pe_offset + 24 + 16)[0]
        image_base = struct.unpack_from('<Q', self.data, pe_offset + 24 + 24)[0]
        section_alignment = struct.unpack_from('<I', self.data, pe_offset + 24 + 32)[0]
        file_alignment = struct.unpack_from('<I', self.data, pe_offset + 24 + 36)[0]

        # Section headers (after optional header)
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

        self.machine = machine
        self.image_base = image_base
        self.num_sections = num_sections

    def print_info(self):
        """Print PE32+ information."""
        print(f"\n{'='*60}")
        print(f"PE32+ File: {self.path}")
        print(f"{'='*60}")
        print(f"Machine: 0x{self.machine:04x} (RISC-V 64-bit = 0x5064)")
        print(f"Sections: {self.num_sections}")
        print(f"Image Base: 0x{self.image_base:016x}")
        print(f"Entry Point: 0x{self.entry_point:016x}")
        print(f"\nSections:")
        print(f"{'Name':<10} {'VA':<12} {'Size':<12} {'Raw':<12} {'Flags'}")
        print(f"{'-'*70}")

        for section in self.sections:
            flags = []
            if section['characteristics'] & IMAGE_SCN_MEM_EXECUTE:
                flags.append('X')
            if section['characteristics'] & IMAGE_SCN_MEM_READ:
                flags.append('R')
            if section['characteristics'] & IMAGE_SCN_MEM_WRITE:
                flags.append('W')

            print(f"{section['name']:<10} "
                  f"0x{section['virtual_address']:08x}  "
                  f"{section['virtual_size']:<12} "
                  f"{section['size_of_raw_data']:<12} "
                  f"{''.join(flags)}")

    def get_loadable_segments(self):
        """Return loadable sections (similar to ELF PT_LOAD)."""
        # All sections with non-zero raw data are loadable
        return [s for s in self.sections if s['size_of_raw_data'] > 0]

    def get_section_data(self, section):
        """Return raw section data from the file."""
        start = section['pointer_to_raw_data']
        end = start + section['size_of_raw_data']
        return self.data[start:end]


class UEFIEnvironmentBuilder:
    """
    Skeleton for UEFI runtime environment initialization.
    Responsible for mapping SystemTable, BootServices, RuntimeServices,
    and required protocols into guest memory before boot.
    """
    def __init__(self, memory_array, phys_start=0x80000000):
        self.memory = memory_array
        self.phys_start = phys_start
        self.sys_table_addr = self.phys_start
        self.boot_services_addr = self.phys_start + 0x200
        self.runtime_services_addr = self.phys_start + 0x100
        
    def write_word(self, pixel_idx: int, value: int):
        """Write a 32-bit word into the RGBA memory array (4 bytes per pixel)"""
        self.memory[pixel_idx, 0] = value & 0xFF
        self.memory[pixel_idx, 1] = (value >> 8) & 0xFF
        self.memory[pixel_idx, 2] = (value >> 16) & 0xFF
        self.memory[pixel_idx, 3] = (value >> 24) & 0xFF

    def allocate_struct(self, size: int) -> int:
        """Bump-allocate `size` bytes above the highest region reserved so far, 16-byte aligned."""
        if not hasattr(self, '_bump_ptr'):
            # First reservation starts after ConfigurationTable + VendorTable slack (0x600 + 0x40)
            self._bump_ptr = self.phys_start + 0x700
        addr = (self._bump_ptr + 0xF) & ~0xF
        self._bump_ptr = addr + size
        return addr
        
    def build_system_table(self):
        """Write EFI_SYSTEM_TABLE to memory"""
        efi_pixel = (self.sys_table_addr - self.phys_start) // 4
        
        # Header (24 bytes)
        self.write_word(efi_pixel, 0x20494249) # 'IBI '
        self.write_word(efi_pixel + 1, 0x54535953) # 'SYST'
        self.write_word(efi_pixel + 2, 0x00020032) # UEFI 2.50
        self.write_word(efi_pixel + 3, 112)        # Header Size
        self.write_word(efi_pixel + 4, 0)          # CRC32
        self.write_word(efi_pixel + 5, 0)          # Reserved
        
        # Fill rest of table with 0s
        for i in range(6, 112 // 4):
            self.write_word(efi_pixel + i, 0)
            
        # ConIn (8) -> 0x80000500
        self.write_word(efi_pixel + (48 // 4), self.phys_start + 0x500)
        self.write_word(efi_pixel + (48 // 4) + 1, 0)

        # ConOut (8) -> 0x80000400
        self.write_word(efi_pixel + (64 // 4), self.phys_start + 0x400)
        self.write_word(efi_pixel + (64 // 4) + 1, 0)
        
        # StdErr (8) -> 0x80000400
        self.write_word(efi_pixel + (80 // 4), self.phys_start + 0x400)
        self.write_word(efi_pixel + (80 // 4) + 1, 0)
        
        # RuntimeServices (8) -> offset 88
        self.write_word(efi_pixel + (88 // 4), self.runtime_services_addr)
        self.write_word(efi_pixel + (88 // 4) + 1, 0)
        
        # BootServices (8) -> offset 96
        self.write_word(efi_pixel + (96 // 4), self.boot_services_addr)
        self.write_word(efi_pixel + (96 // 4) + 1, 0)
        
        # NumberOfTableEntries (8) -> offset 104
        self.write_word(efi_pixel + (104 // 4), 1)
        self.write_word(efi_pixel + (104 // 4) + 1, 0)
        
        # ConfigurationTable (8) -> offset 112
        conf_table_addr = self.phys_start + 0x600
        self.write_word(efi_pixel + (112 // 4), conf_table_addr)
        self.write_word(efi_pixel + (112 // 4) + 1, 0)
        
        # Build Configuration Table (at 0x600)
        # Struct: VendorGuid (16 bytes), VendorTable (8 bytes)
        ct_pixel = (conf_table_addr - self.phys_start) // 4
        
        # FDT GUID: b1b621d5-f19c-41a5-830b-d9152c69aae0
        self.write_word(ct_pixel, 0xb1b621d5)
        self.write_word(ct_pixel + 1, 0x41a5f19c)
        self.write_word(ct_pixel + 2, 0x15d90b83)
        self.write_word(ct_pixel + 3, 0xe0aa692c)
        
        # VendorTable -> Address of FDT
        fdt_addr = self.phys_start + 0x100000 # Put FDT at 1MB mark
        self.write_word(ct_pixel + 4, fdt_addr)
        self.write_word(ct_pixel + 5, 0)
        
    def build_boot_services(self):
        """Map all BootServices functions to WGSL trampolines"""
        # Fill RuntimeServices (0x100), ConOut (0x400), and ConIn (0x500) 
        # with function pointers pointing to the unhandled trampoline at 0x80000300
        for offset in [0x100, 0x400, 0x500]:
            px_start = offset // 4
            for i in range(0, 1024 // 8):
                self.write_word(px_start + i * 2, self.phys_start + 0x300)
                self.write_word(px_start + i * 2 + 1, 0)

        # Generate 45 trampolines for BootServices at 0x80001000
        for i in range(45):
            t_addr = self.phys_start + 0x1000 + i * 16
            px = (0x1000 + i * 16) // 4
            imm = 1000 + i
            
            #   addi a7, zero, 1000 + i
            #   ecall
            #   ret (jalr zero, 0(ra))
            addi_instr = (imm << 20) | (17 << 7) | 0x13
            self.write_word(px, addi_instr)
            self.write_word(px + 1, 0x00000073) # ecall
            self.write_word(px + 2, 0x00008067) # jalr zero, 0(ra)
            self.write_word(px + 3, 0)
            
            # Update BootServices table at offset i (i*8 bytes after header)
            # BootServices table starts at 0x80000200. Header is 24 bytes (0x18).
            self.write_word((self.boot_services_addr - self.phys_start + 0x18 + i * 8) // 4, t_addr)
            self.write_word(((self.boot_services_addr - self.phys_start + 0x18 + i * 8) // 4) + 1, 0)
            
        # Trampoline 1 at 0x80000300: Unhandled EFI (returns EFI_UNSUPPORTED)
        t_pixel = 0x00000300 // 4
        self.write_word(t_pixel, 0x157e557d)
        self.write_word(t_pixel + 1, 0x8082050d)
        
        # Trampoline 2 at 0x80000310: AllocatePool (FID=1)
        t2_pixel = 0x00000310 // 4
        self.write_word(t2_pixel, 0x00060693)     # mv a3, a2
        self.write_word(t2_pixel + 1, 0x00058513) # mv a0, a1
        self.write_word(t2_pixel + 2, 0x554548b7) # lui a7, 0x55454
        self.write_word(t2_pixel + 3, 0x64988893) # addi a7,a7,0x649
        self.write_word(t2_pixel + 4, 0x00100813) # addi a6,zero,1
        self.write_word(t2_pixel + 5, 0x00000073) # ecall
        self.write_word(t2_pixel + 6, 0x00b6b023) # sd a1, 0(a3)
        self.write_word(t2_pixel + 7, 0x00008067) # ret
        
        # Override AllocatePool pointer (offset 64 in BootServices)
        bs_px = (self.boot_services_addr - self.phys_start) // 4
        self.write_word(bs_px + (64 // 4), self.phys_start + 0x310)
        self.write_word(bs_px + (64 // 4) + 1, 0)
        
    def initialize_kernel_data_globals(self, loader):
        """
        Pre-initialize known .data globals in the loaded kernel image.
        1. Set GP pointer targets to valid addresses.
        2. Initialize device tree pointer (required by Linux).
        3. Reserve ACPI region.
        """
        # Find .text section to locate GP initialization
        text_sec = next((s for s in loader.sections if s['name'] == '.text'), None)
        if text_sec:
            # We look for `auipc gp, imm` -> `addi gp, gp, imm`
            # In the alpine image this is around offset 0x54
            data = loader.get_section_data(text_sec)
            for i in range(0, min(len(data), 0x1000) - 4, 2):
                import struct
                instr = struct.unpack_from('<I', data, i)[0]
                if (instr & 0x7F) == 0x17 and ((instr >> 7) & 0x1F) == 3:
                    # auipc gp, imm
                    imm20 = instr & 0xFFFFF000
                    gp_base = (text_sec['virtual_address'] + i + imm20) & 0xFFFFFFFF
                    # Next instruction should be addi gp, gp, imm12
                    next_instr = struct.unpack_from('<I', data, i + 4)[0]
                    # opcode=0x13, rd=3, funct3=0, rs1=3
                    if (next_instr & 0x7F) == 0x13 and ((next_instr >> 7) & 0x1F) == 3 and ((next_instr >> 12) & 0x7) == 0 and ((next_instr >> 15) & 0x1F) == 3:
                        imm12 = next_instr >> 20
                        if imm12 & 0x800:
                            imm12 -= 4096
                        gp_target = gp_base + imm12
                        print(f"[*] Found GP initialization: GP targets 0x{self.phys_start + gp_target:08x}")
                        
                        # Apply patches to the GP target region if needed
                        # E.g., setting global pointers that were compiled as 0
                        gp_pixel = (gp_target) // 4 + (self.phys_start // 4)
                        
                        # To be safe, we can pre-populate a block around GP with sane values
                        # to avoid NULL pointer dereferences in early boot runtime
                        # self.write_word(gp_pixel, ...)
                        break


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 pe32_loader.py <pe32_kernel>")
        print("\nExample:")
        print("  python3 pe32_loader.py /tmp/ubuntu_riscv_vmlinux")
        print("  python3 pe32_loader.py boot_images/alpine_Image")
        sys.exit(1)

    path = sys.argv[1]

    if not Path(path).exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)

    try:
        loader = PE32Loader(path)
        loader.print_info()

        # Show what would be loaded
        loadable = loader.get_loadable_segments()
        print(f"\nLoadable Sections: {len(loadable)}")
        for section in loadable:
            data = loader.get_section_data(section)
            print(f"  {section['name']}: {len(data)} bytes @ 0x{section['virtual_address']:08x}")
            
        print(f"\n{'='*60}")
        print(f"Testing UEFIEnvironmentBuilder skeleton")
        print(f"{'='*60}")
        import numpy as np
        memory_array = np.zeros((1024*1024, 4), dtype=np.uint32)
        builder = UEFIEnvironmentBuilder(memory_array)
        builder.build_system_table()
        builder.build_boot_services()
        builder.initialize_kernel_data_globals(loader)

        print(f"\n{'='*60}")
        print(f"✓ PE32+ parsing successful!")
        print(f"{'='*60}")
        print(f"\nThis is a proof-of-concept PE32+ loader.")
        print(f"To use it with the GPU emulator, you would need to:")
        print(f"  1. Integrate this into tools/boot_xv6_gpu.py")
        print(f"  2. Add UEFI runtime services to tools/RISCV_CPU_MMU.wgsl")
        print(f"  3. Handle relocations (if any)")
        print(f"  4. Pass UEFI boot parameters to the kernel")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()