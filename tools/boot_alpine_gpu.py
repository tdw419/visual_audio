#!/usr/bin/env python3
"""
Boot Alpine Linux on GPU RISC-V Emulator

Loads vmlinuz-riscv64 kernel, constructs SV39 page tables, and boots on GPU.

Phase 13: GPU-Native Linux Boot
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
    EI_CLASS_32 = 1
    EI_DATA_LITTLE = 1
    ET_EXEC = 2
    EM_RISCV = 243

    def __init__(self, elf_path: str):
        self.path = Path(elf_path)
        self.data: bytes = b''
        self.entry_point: int = 0
        self.program_headers: List[dict] = []
        self.sections: List[dict] = []
        self._parse()

    def _parse(self):
        """Parse ELF64 header and program headers."""
        with open(self.path, 'rb') as f:
            self.data = f.read()

        # Validate ELF magic
        if self.data[:4] != b'\x7fELF':
            raise ValueError(f"Invalid ELF file: {self.path}")

        # Parse ELF64 header
        ei_class = self.data[4]
        ei_data = self.data[5]
        e_type = struct.unpack('<H', self.data[16:18])[0]
        e_machine = struct.unpack('<H', self.data[18:20])[0]
        e_entry = struct.unpack('<Q', self.data[24:32])[0]
        e_phoff = struct.unpack('<Q', self.data[32:40])[0]
        e_phentsize = struct.unpack('<H', self.data[54:56])[0]
        e_phnum = struct.unpack('<H', self.data[56:58])[0]
        e_shoff = struct.unpack('<Q', self.data[40:48])[0]
        e_shentsize = struct.unpack('<H', self.data[58:60])[0]
        e_shnum = struct.unpack('<H', self.data[60:62])[0]

        # Validate ELF64 RISC-V
        if ei_class != self.EI_CLASS_64:
            raise ValueError(f"Only ELF64 supported (got class {ei_class})")
        if ei_data != self.EI_DATA_LITTLE:
            raise ValueError(f"Only little-endian ELF supported")
        if e_machine != self.EM_RISCV:
            raise ValueError(f"Only RISC-V ELF supported (got machine {e_machine})")

        self.entry_point = e_entry

        # Parse program headers (loadable segments)
        for i in range(e_phnum):
            ph_offset = e_phoff + i * e_phentsize
            p_type = struct.unpack('<I', self.data[ph_offset:ph_offset+4])[0]
            p_flags = struct.unpack('<I', self.data[ph_offset+4:ph_offset+8])[0]
            p_offset = struct.unpack('<Q', self.data[ph_offset+8:ph_offset+16])[0]
            p_vaddr = struct.unpack('<Q', self.data[ph_offset+16:ph_offset+24])[0]
            p_paddr = struct.unpack('<Q', self.data[ph_offset+24:ph_offset+32])[0]
            p_filesz = struct.unpack('<Q', self.data[ph_offset+32:ph_offset+40])[0]
            p_memsz = struct.unpack('<Q', self.data[ph_offset+40:ph_offset+48])[0]

            if p_type == 1:  # PT_LOAD
                self.program_headers.append({
                    'offset': p_offset,
                    'vaddr': p_vaddr,
                    'paddr': p_paddr,
                    'filesz': p_filesz,
                    'memsz': p_memsz,
                    'flags': p_flags,
                })

    def get_segment_data(self, segment: dict) -> bytes:
        """Extract raw segment data from ELF."""
        return self.data[segment['offset']:segment['offset'] + segment['filesz']]

    def print_info(self):
        """Print ELF information."""
        print(f"ELF64 File: {self.path}")
        print(f"Entry Point: 0x{self.entry_point:016x}")
        print(f"\nLoadable Segments:")
        for seg in self.program_headers:
            flags_str = []
            if seg['flags'] & 0x1: flags_str.append('X')
            if seg['flags'] & 0x2: flags_str.append('W')
            if seg['flags'] & 0x4: flags_str.append('R')
            flags_str = ''.join(flags_str) or '---'
            print(f"  0x{seg['vaddr']:016x} - 0x{seg['vaddr'] + seg['memsz']:016x} "
                  f"({seg['filesz']:6d}/{seg['memsz']:6d} bytes) [{flags_str}]")


# ============================================================================
# SV39 PAGE TABLE BUILDER
# ============================================================================

def build_sv39_page_tables(segments: List[dict], page_table_root_ppn: int, page_size: int = 4096) -> bytes:
    """
    Build SV39 3-level page tables for kernel memory.

    Returns: page table data to be loaded at physical address root_ppn * page_size
    """
    page_tables = {}  # (level, index) -> [u32 entries]

    def get_or_create_page_table(level: int, index: int) -> int:
        """Get or create a page table at given level and return its PPN."""
        key = (level, index)
        if key not in page_tables:
            # Allocate new page table (4096 bytes = 1024 u32 entries)
            page_tables[key] = [0] * 1024
        return index  # Simplified: PPN = index

    # Identity map all loadable segments
    for seg in segments:
        vaddr_start = seg['vaddr']
        vaddr_end = vaddr_start + seg['memsz']

        # Align to page boundaries
        vaddr_start_aligned = vaddr_start & ~(page_size - 1)
        vaddr_end_aligned = (vaddr_end + page_size - 1) & ~(page_size - 1)

        print(f"  Mapping 0x{vaddr_start_aligned:016x} - 0x{vaddr_end_aligned:016x}")

        # Walk page addresses
        for vaddr in range(vaddr_start_aligned, vaddr_end_aligned, page_size):
            # Extract VPNs (SV39: 9 bits per level)
            vpn2 = (vaddr >> 30) & 0x1FF  # bits [38:30]
            vpn1 = (vaddr >> 21) & 0x1FF  # bits [29:21]
            vpn0 = (vaddr >> 12) & 0x1FF  # bits [20:12]

            # Get or create page tables at each level
            l1_idx = get_or_create_page_table(1, vpn2)
            l2_idx = get_or_create_page_table(2, vpn1 + l1_idx * 512)
            l3_idx = get_or_create_page_table(3, vpn0 + l2_idx * 512)

            # Build leaf PTE at L3
            # PTE format: [PPN, 2b reserved, D, A, G, U, X, W, R, V]
            ppn = vaddr >> 12  # Identity mapping: PPN = VPN
            pte = (ppn << 10) | 0xCF  # D=1, A=1, X=1, W=1, R=1, V=1 (0xCF = 0b11001111)

            key = (3, l3_idx)
            page_tables[key][vpn0] = pte

            # Build PTEs at L1 and L2 (point to next level)
            # L1 -> L2
            l2_ppn = l2_idx
            pte_l1 = (l2_ppn << 10) | 0x01  # V=1 (not a leaf)
            page_tables[(1, l1_idx)][vpn2] = pte_l1

            # L2 -> L3
            l3_ppn = l3_idx
            pte_l2 = (l3_ppn << 10) | 0x01  # V=1 (not a leaf)
            page_tables[(2, l2_idx)][vpn1] = pte_l2

    # Serialize page tables to bytes
    # Simplified: allocate contiguous pages for all page tables
    num_page_tables = len(page_tables)
    total_size = num_page_tables * page_size
    pt_data = bytearray(total_size)

    pt_offset = 0
    for (level, idx), entries in sorted(page_tables.items()):
        for i, entry in enumerate(entries):
            offset = pt_offset + i * 4
            pt_data[offset:offset+4] = entry.to_bytes(4, 'little')
        pt_offset += page_size

    return bytes(pt_data)


# ============================================================================
# MEMORY IMAGE BUILDER
# ============================================================================

def build_memory_image(elf_path: str) -> Tuple[np.ndarray, int, int]:
    """
    Build complete memory image for GPU execution (1GB fixed size).

    Returns: (memory_pixels, root_page_table_ppn, entry_point)
    """
    # Load ELF
    print("[1] Loading ELF64 kernel...")
    elf = ELF64Loader(elf_path)
    elf.print_info()

    # Memory layout (physical addresses):
    # 0x00000000 - 0xFFFFFFFF: Full 4GB space mapped
    # Use 1GB memory (practical for GPU)

    memory_size = 1024 * 1024 * 1024  # 1GB
    memory = bytearray(memory_size)

    # Load ELF segments
    print("\n[2] Loading kernel segments into memory...")
    for seg in elf.program_headers:
        data = elf.get_segment_data(seg)
        if data:
            # Verify segment fits in memory
            if seg['vaddr'] + len(data) > memory_size:
                print(f"Warning: Segment at 0x{seg['vaddr']:016x} exceeds memory")
            else:
                # Store segment data (identity mapping for now)
                memory[seg['vaddr']:seg['vaddr'] + len(data)] = data
                # Zero-fill BSS
                if seg['memsz'] > seg['filesz']:
                    bss_start = seg['vaddr'] + seg['filesz']
                    bss_end = seg['vaddr'] + seg['memsz']
                    if bss_end <= memory_size:
                        memory[bss_start:bss_end] = b'\x00' * (bss_end - bss_start)

    # Build page tables
    print("\n[3] Building SV39 page tables...")
    root_page_table_addr = 0x10000000
    root_page_table_ppn = root_page_table_addr >> 12

    pt_data = build_sv39_page_tables(elf.program_headers, root_page_table_ppn)

    print(f"  Page tables size: {len(pt_data)} bytes ({len(pt_data) // 4096} pages)")
    print(f"  Root page table at: 0x{root_page_table_addr:016x} (PPN={root_page_table_ppn})")

    # Store page tables in memory
    pt_end = root_page_table_addr + len(pt_data)
    if pt_end <= memory_size:
        memory[root_page_table_addr:pt_end] = pt_data
    else:
        raise ValueError("Page tables exceed memory size")

    # Convert to RGBA pixels (1 pixel = 4 bytes = 1 word)
    print(f"\n[4] Converting to RGBA pixels...")
    num_pixels = memory_size // 4
    pixels = np.zeros((num_pixels, 4), dtype=np.uint8)

    for i in range(num_pixels):
        word = struct.unpack('<I', memory[i*4:i*4+4])[0]
        pixels[i] = [
            word & 0xFF,           # R
            (word >> 8) & 0xFF,    # G
            (word >> 16) & 0xFF,   # B
            (word >> 24) & 0xFF,   # A
        ]

    print(f"  Memory: {memory_size_mb}MB ({num_pixels} pixels)")
    print(f"  Entry point: 0x{elf.entry_point:016x}")
    print(f"  SATP: 0x{8 << 22 | root_page_table_ppn:08x} (SV39, root PPN={root_page_table_ppn})")

    return pixels, root_page_table_ppn, elf.entry_point


def create_gpu_boot_harness(pixels: np.ndarray, root_ppn: int, entry_point: int) -> dict:
    """Create GPU buffers and CPU state for boot."""
    import wgpu
    import wgpu.utils

    # Initialize GPU
    print("\n[5] Initializing GPU...")
    device = wgpu.utils.get_default_device()
    queue = device.queue
    print(f"    Device: {device.adapter.info.device}")

    # Load shader
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    print(f"    Shader: {shader_path}")

    # Create memory buffer
    pixel_data = pixels.reshape(-1, 4).astype(np.uint32)
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())
    print(f"    Memory buffer: {pixel_data.shape[0]} words ({pixel_data.nbytes // (1024*1024)}MB)")

    # Create CPU state with MMU enabled (shared layout, real RV64 satp format)
    from riscv_gpu_cpu import make_cpu_state, make_satp
    cpu_state = make_cpu_state(entry_point, satp=make_satp(root_ppn))

    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    satp64 = (int(cpu_state[0]['satp'][1]) << 32) | int(cpu_state[0]['satp'][0])
    print(f"    CPU state: PC=0x{entry_point:016x}, SATP=0x{satp64:016x}")

    # Output buffer
    output_buffer = device.create_buffer(
        size=65536,  # 16KB for kernel output
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    # Max instructions uniform
    max_instructions = np.array([1000000], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions.tobytes())
    print(f"    Max instructions: {max_instructions[0]}")

    # Create bind group
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])

    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': pixel_data.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': 65536}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': max_instructions.nbytes}},
        ]
    )

    # Create compute pipeline
    print("\n[6] Creating compute pipeline...")
    compute_shader = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': compute_shader, 'entry_point': 'main'},
    )

    return {
        'device': device,
        'queue': queue,
        'pipeline': pipeline,
        'bind_group': bind_group,
        'cpu_buffer': cpu_buffer,
        'output_buffer': output_buffer,
        'cpu_layout': cpu_layout,
    }


def boot_alpine_on_gpu(elf_path: str):
    """Main boot sequence."""
    print("=" * 70)
    print("ALPINE LINUX GPU BOOT - Phase 13")
    print("=" * 70)

    # Build memory image
    pixels, root_ppn, entry_point = build_memory_image(elf_path)

    # Create GPU harness
    harness = create_gpu_boot_harness(pixels, root_ppn, entry_point)

    # Execute
    print("\n[7] Booting Alpine Linux on GPU...")
    print("    (This will execute up to 1M instructions)")
    print()

    device = harness['device']
    queue = harness['queue']
    pipeline = harness['pipeline']
    bind_group = harness['bind_group']
    cpu_buffer = harness['cpu_buffer']
    output_buffer = harness['output_buffer']
    cpu_layout = harness['cpu_layout']

    # Dispatch iterations
    last_pc = 0
    stale_count = 0

    for iteration in range(5000):
        encoder = device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(pipeline)
        pass_enc.set_bind_group(0, bind_group)
        pass_enc.dispatch_workgroups(1)
        pass_enc.end()
        queue.submit([encoder.finish()])

        # Read CPU state
        cpu_readback = np.frombuffer(
            device.queue.read_buffer(cpu_buffer),
            dtype=cpu_layout
        )[0]

        running = cpu_readback['running']
        pc_low = cpu_readback['pc'][0]
        pc_high = cpu_readback['pc'][1]
        pc = (pc_high << 32) | pc_low
        instr_count = cpu_readback['instr_count']

        # Check for PC stall
        if pc == last_pc:
            stale_count += 1
            if stale_count > 10:
                print(f"    PC stalled at 0x{pc:016x}")
                break
        else:
            stale_count = 0
            last_pc = pc

        # Progress indicator
        if iteration % 100 == 0 or running == 0:
            print(f"    Iter {iteration:5d}: PC=0x{pc:016x}, running={running}, instr={instr_count}")

        if running == 0:
            print(f"\n    Halted after {instr_count} instructions")
            break

    # Read output
    print("\n[8] Reading kernel output...")
    output_data = np.frombuffer(
        device.queue.read_buffer(output_buffer),
        dtype=np.uint8
    )

    # Find null-terminated strings in output
    output_str = ''
    for i in range(0, len(output_data), 4):
        word = struct.unpack('<I', output_data[i:i+4])[0]
        for b in word.to_bytes(4, 'little'):
            if b == 0:
                break
            if 32 <= b < 127:  # Printable ASCII
                output_str += chr(b)

    print("\n" + "=" * 70)
    print("KERNEL OUTPUT")
    print("=" * 70)
    if output_str:
        print(output_str)
    else:
        print("(No output captured)")

    print("=" * 70)
    print(f"Final PC: 0x{pc:016x}")
    print(f"Instructions executed: {instr_count}")
    print(f"CPU running: {running}")
    print("=" * 70)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 boot_alpine_gpu.py <vmlinuz-riscv64>")
        print("\nExample:")
        print("  python3 boot_alpine_gpu.py /home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin")
        sys.exit(1)

    elf_path = sys.argv[1]

    if not Path(elf_path).exists():
        print(f"Error: File not found: {elf_path}")
        sys.exit(1)

    boot_alpine_on_gpu(elf_path)