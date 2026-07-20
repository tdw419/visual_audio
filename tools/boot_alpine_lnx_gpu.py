#!/usr/bin/env python3
"""
Boot Alpine Linux on GPU RISC-V Emulator from LNX format

Loads alpine-riscv64.lnx.bin kernel, constructs SV39 page tables, and boots on GPU.

LNX format:
  - 4-byte magic 'LNX\x00'
  - u32 kernel_offset
  - u32 kernel_size
  - u32 initrd_size
  - Kernel is PE/COFF for RISC-V 64-bit

Phase 13: GPU-Native Linux Boot
"""

import struct
import numpy as np
from pathlib import Path
from typing import List, Tuple
import sys


# ============================================================================
# LNX CONTAINER PARSER
# ============================================================================

def parse_lnx(lnx_path: str) -> Tuple[bytes, bytes, int]:
    """
    Parse LNX container and return (kernel_bytes, initrd_bytes, entry_rva).

    Returns:
        kernel_data: PE/COFF raw kernel
        initrd_data: initramfs bytes
        entry_rva: Entry point RVA from PE/COFF
    """
    with open(lnx_path, 'rb') as f:
        data = f.read()

    magic = data[0:4]
    if magic != b'LNX\x00':
        raise ValueError(f"Not an LNX file (magic: {magic})")

    kernel_offset = struct.unpack('<I', data[4:8])[0]
    kernel_size = struct.unpack('<I', data[8:12])[0]
    initrd_size = struct.unpack('<I', data[12:16])[0]

    print(f"LNX container:")
    print(f"  Kernel offset: 0x{kernel_offset:x}")
    print(f"  Kernel size:   {kernel_size:,} bytes ({kernel_size/1024/1024:.1f} MB)")
    print(f"  Initrd size:   {initrd_size:,} bytes ({initrd_size/1024/1024:.1f} MB)")

    kernel_data = data[kernel_offset:kernel_offset + kernel_size]
    initrd_data = data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

    # Extract raw kernel from PE/COFF
    print("\nExtracting kernel from PE/COFF...")
    result = extract_raw_kernel_from_pe(kernel_data)
    if isinstance(result, tuple):
        raw_kernel, entry_rva, image_size = result
    else:
        raw_kernel = result
        entry_rva = 0
        image_size = len(raw_kernel)

    return raw_kernel, initrd_data, entry_rva


def extract_raw_kernel_from_pe(pe_data: bytes) -> Tuple[bytes, int, int]:
    """
    Extract raw kernel binary from PE/COFF EFI stub.
    Strips PE headers and lays out sections at their virtual addresses.
    """
    if pe_data[0:2] != b'MZ':
        raise ValueError("Not a PE file")

    pe_offset = struct.unpack('<I', pe_data[0x3c:0x40])[0]
    if pe_data[pe_offset:pe_offset+4] != b'PE\x00\x00':
        raise ValueError("Invalid PE signature")

    # COFF header
    coff = pe_offset + 4
    machine = struct.unpack('<H', pe_data[coff:coff+2])[0]
    num_sections = struct.unpack('<H', pe_data[coff+2:coff+4])[0]
    opt_hdr_size = struct.unpack('<H', pe_data[coff+16:coff+18])[0]

    if machine != 0x5064:  # RISC-V 64
        raise ValueError(f"Not RISC-V 64 (machine=0x{machine:04x})")

    print(f"  PE/COFF: RISC-V 64, sections={num_sections}")

    # Optional header (PE32+)
    opt_start = coff + 20
    opt_magic = struct.unpack('<H', pe_data[opt_start:opt_start+2])[0]
    if opt_magic != 0x20b:
        raise ValueError(f"Not PE32+ (opt_magic=0x{opt_magic:04x})")

    entry_rva = struct.unpack('<I', pe_data[opt_start+16:opt_start+20])[0]
    image_base = struct.unpack('<Q', pe_data[opt_start+24:opt_start+32])[0]
    size_of_image = struct.unpack('<I', pe_data[opt_start+56:opt_start+60])[0]

    print(f"  Entry RVA: 0x{entry_rva:x}")
    print(f"  Image base: 0x{image_base:x}")
    print(f"  Size of image: {size_of_image:,} bytes ({size_of_image/1024/1024:.1f} MB)")

    # Build flat image by loading sections at their RVAs
    flat = bytearray(size_of_image)

    section_table = opt_start + opt_hdr_size
    for i in range(num_sections):
        s = section_table + i * 40
        name = pe_data[s:s+8].rstrip(b'\x00').decode('ascii', errors='replace')
        vsize = struct.unpack('<I', pe_data[s+8:s+12])[0]
        vaddr = struct.unpack('<I', pe_data[s+12:s+16])[0]
        raw_size = struct.unpack('<I', pe_data[s+16:s+20])[0]
        raw_ptr = struct.unpack('<I', pe_data[s+20:s+24])[0]

        if raw_size > 0 and raw_ptr > 0:
            section_data = pe_data[raw_ptr:raw_ptr + raw_size]
            flat[vaddr:vaddr + len(section_data)] = section_data
            print(f"  Section {name}: VA=0x{vaddr:x} size=0x{vsize:x}")

    return bytes(flat), entry_rva, size_of_image


# ============================================================================
# SV39 PAGE TABLE BUILDER
# ============================================================================

def build_sv39_page_tables(segments: List[dict], page_table_root_ppn: int, page_size: int = 4096) -> bytes:
    """
    Build SV39 3-level page tables for kernel memory.

    Maps virtual addresses from segments to physical addresses.

    Returns: page table data to be loaded at physical address root_ppn * page_size
    """
    page_tables = {}  # (level, index) -> [u32 entries]

    def get_or_create_page_table(level: int, index: int) -> int:
        key = (level, index)
        if key not in page_tables:
            page_tables[key] = [0] * 1024
        return index

    # Map all segments (VA -> PA)
    for seg in segments:
        vaddr_start = seg['vaddr']
        paddr_start = seg['paddr']
        size = seg['size']
        vaddr_end = vaddr_start + size
        paddr_end = paddr_start + size

        # Align to page boundaries
        vaddr_start_aligned = vaddr_start & ~(page_size - 1)
        vaddr_end_aligned = (vaddr_end + page_size - 1) & ~(page_size - 1)
        paddr_start_aligned = paddr_start & ~(page_size - 1)

        print(f"  Mapping VA=0x{vaddr_start_aligned:016x} -> PA=0x{paddr_start_aligned:016x} (0x{(vaddr_end_aligned - vaddr_start_aligned):x})")

        for offset in range(0, vaddr_end_aligned - vaddr_start_aligned, page_size):
            vaddr = vaddr_start_aligned + offset
            paddr = paddr_start_aligned + offset

            vpn2 = (vaddr >> 30) & 0x1FF
            vpn1 = (vaddr >> 21) & 0x1FF
            vpn0 = (vaddr >> 12) & 0x1FF

            l1_idx = get_or_create_page_table(1, vpn2)
            l2_idx = get_or_create_page_table(2, vpn1 + l1_idx * 512)
            l3_idx = get_or_create_page_table(3, vpn0 + l2_idx * 512)

            # Build leaf PTE at L3 with physical address
            ppn = paddr >> 12
            pte = (ppn << 10) | 0xCF  # R+W+X+D+A+V

            key = (3, l3_idx)
            page_tables[key][vpn0] = pte

            # Build PTEs at L1 and L2
            l2_ppn = l2_idx
            pte_l1 = (l2_ppn << 10) | 0x01
            page_tables[(1, l1_idx)][vpn2] = pte_l1

            l3_ppn = l3_idx
            pte_l2 = (l3_ppn << 10) | 0x01
            page_tables[(2, l2_idx)][vpn1] = pte_l2

    # Serialize page tables
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

def build_memory_image(lnx_path: str) -> Tuple[np.ndarray, int, int, int]:
    """
    Build complete memory image for GPU execution (128MB fixed size).

    Returns: (memory_pixels, root_page_table_ppn, entry_point, dtb_addr)
    """
    # Load and parse LNX container
    print("[1] Loading LNX kernel...")
    with open(lnx_path, 'rb') as f:
        raw_data = f.read()

    # Parse LNX header
    magic = raw_data[0:4]
    if magic != b'LNX\x00':
        raise ValueError(f"Not an LNX file (magic: {magic})")

    kernel_offset = struct.unpack('<I', raw_data[4:8])[0]
    kernel_size = struct.unpack('<I', raw_data[8:12])[0]
    initrd_size = struct.unpack('<I', raw_data[12:16])[0]

    print(f"LNX container:")
    print(f"  Kernel offset: 0x{kernel_offset:x}")
    print(f"  Kernel size:   {kernel_size:,} bytes ({kernel_size/1024/1024:.1f} MB)")

    kernel_data_pe = raw_data[kernel_offset:kernel_offset + kernel_size]

    # Extract sections from PE header BEFORE flattening
    pe_offset = struct.unpack('<I', kernel_data_pe[0x3c:0x40])[0]
    coff = pe_offset + 4
    num_sections = struct.unpack('<H', kernel_data_pe[coff+2:coff+4])[0]
    opt_hdr_size = struct.unpack('<H', kernel_data_pe[coff+16:coff+18])[0]
    section_table = pe_offset + 4 + 20 + opt_hdr_size

    sections_info = []
    for i in range(num_sections):
        s = section_table + i * 40
        name = kernel_data_pe[s:s+8].rstrip(b'\x00').decode('ascii', errors='replace')
        vsize = struct.unpack('<I', kernel_data_pe[s+8:s+12])[0]
        vaddr = struct.unpack('<I', kernel_data_pe[s+12:s+16])[0]
        raw_size = struct.unpack('<I', kernel_data_pe[s+16:s+20])[0]
        raw_ptr = struct.unpack('<I', kernel_data_pe[s+20:s+24])[0]
        sections_info.append({
            'name': name,
            'vaddr': vaddr,
            'vsize': vsize,
            'raw_size': raw_size,
            'raw_ptr': raw_ptr,
        })
        print(f"  Section {name}: VA=0x{vaddr:x} vsize=0x{vsize:x} raw_size=0x{raw_size:x}")

    # Extract raw kernel from PE/COFF
    print("\nExtracting kernel from PE/COFF...")
    result = extract_raw_kernel_from_pe(kernel_data_pe)
    if isinstance(result, tuple):
        flat_kernel, entry_rva, image_size = result
    else:
        flat_kernel = result
        entry_rva = 0
        image_size = len(flat_kernel)

    # Kernel is loaded at 0x200000
    load_addr = 0x200000
    # Entry point is the virtual address (RVA) from PE
    entry_point = entry_rva

    print(f"  Entry point: 0x{entry_point:016x} (RVA=0x{entry_rva:x})")

    memory_size = 128 * 1024 * 1024  # 128MB
    memory = bytearray(memory_size)

    # Load kernel into memory
    print("\n[2] Loading kernel into memory...")
    if load_addr + len(flat_kernel) > memory_size:
        raise ValueError(f"Kernel too large: {len(flat_kernel)} bytes > {memory_size - load_addr} bytes")
    memory[load_addr:load_addr + len(flat_kernel)] = flat_kernel
    print(f"  Loaded {len(flat_kernel)} bytes at 0x{load_addr:016x}")

    # Create segment descriptors for page tables
    segments = []
    for sec in sections_info:
        if sec['raw_size'] > 0:
            phys_addr = load_addr + sec['vaddr']
            segment = {
                'vaddr': sec['vaddr'],
                'paddr': phys_addr,
                'size': (sec['vsize'] + 4095) & ~4095,
            }
            segments.append(segment)
            print(f"  Segment: {sec['name']} VA=0x{sec['vaddr']:x} -> PA=0x{phys_addr:x}, size=0x{segment['size']:x}")

    # Map UART for SBI console output (physical address 0x10000000)
    segments.append({
        'vaddr': 0x10000000,
        'paddr': 0x10000000,
        'size': 4096,
    })
    print(f"  Segment: UART VA=0x10000000 -> PA=0x10000000, size=0x1000")

    print(f"\\nTotal segments: {len(segments)}")

    # Build page tables
    print("\n[3] Building SV39 page tables...")
    dtb_size = 0x2000
    root_page_table_addr = (memory_size - 0x100000) & ~0xFFF
    root_page_table_ppn = root_page_table_addr >> 12
    dtb_addr = memory_size - dtb_size

    pt_data = build_sv39_page_tables(segments, root_page_table_ppn)

    print(f"  Page tables size: {len(pt_data)} bytes ({len(pt_data) // 4096} pages)")
    print(f"  Root page table at: 0x{root_page_table_addr:016x} (PPN={root_page_table_ppn})")

    # Store page tables
    pt_end = root_page_table_addr + len(pt_data)
    if pt_end <= memory_size:
        memory[root_page_table_addr:pt_end] = pt_data

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

    print(f"  Memory: {memory_size // (1024*1024)}MB ({num_pixels} pixels)")

    return pixels, root_page_table_ppn, entry_point, dtb_addr


# ============================================================================
# GPU EXECUTION
# ============================================================================

def create_gpu_boot_harness(pixels: np.ndarray, root_ppn: int, entry_point: int, dtb_addr: int) -> dict:
    """Create GPU buffers and CPU state for boot."""
    import wgpu
    import wgpu.utils

    print("\n[5] Initializing GPU...")
    device = wgpu.utils.get_default_device()
    queue = device.queue
    print(f"    Device: {device.adapter.info.device}")

    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()
    print(f"    Shader: {shader_path}")

    pixel_data = pixels.reshape(-1, 4).astype(np.uint32)
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())
    print(f"    Memory buffer: {pixel_data.shape[0]} words ({pixel_data.nbytes // (1024*1024)}MB)")

    # CPU state with S-mode, MMU enabled
    from riscv_gpu_cpu import make_linux_boot_state, CPU_DTYPE
    cpu_state = make_linux_boot_state(entry_point, dtb_addr)
    satp_value = (8 << 60) | (root_ppn & 0xFFFFFFFFFFFF)
    cpu_state[0]['satp'] = [satp_value & 0xFFFFFFFF, (satp_value >> 32) & 0xFFFFFFFF]

    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    satp64 = (int(cpu_state[0]['satp'][1]) << 32) | int(cpu_state[0]['satp'][0])
    print(f"    CPU state: PC=0x{entry_point:016x}, SATP=0x{satp64:016x}, DTB=0x{dtb_addr:016x}")

    output_buffer = device.create_buffer(
        size=65536,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    max_instructions = np.array([1000000], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instructions.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, max_instructions.tobytes())
    print(f"    Max instructions: {max_instructions[0]}")

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
        'cpu_layout': CPU_DTYPE,
    }


def boot_alpine_on_gpu(lnx_path: str):
    """Main boot sequence."""
    print("=" * 70)
    print("ALPINE LINUX GPU BOOT - Phase 13")
    print("=" * 70)

    # Build memory image
    pixels, root_ppn, entry_point, dtb_addr = build_memory_image(lnx_path)

    # Load DTB into memory
    print(f"\n[2.5] Loading DTB at 0x{dtb_addr:x}...")
    dtb_path = Path(__file__).parent.parent / 'gpu_machine.dtb'
    if not dtb_path.exists():
        print(f"    Warning: DTB not found at {dtb_path}")
    else:
        dtb_data = dtb_path.read_bytes()
        for i in range(0, len(dtb_data), 4):
            word_idx = (dtb_addr // 4) + (i // 4)
            existing = (pixels[word_idx][0] | (pixels[word_idx][1] << 8) |
                       (pixels[word_idx][2] << 16) | (pixels[word_idx][3] << 24))
            word = existing
            for byte_idx in range(4):
                if i + byte_idx < len(dtb_data):
                    shift = byte_idx * 8
                    word = (word & ~(0xFF << shift)) | (dtb_data[i + byte_idx] << shift)
            pixels[word_idx][0] = word & 0xFF
            pixels[word_idx][1] = (word >> 8) & 0xFF
            pixels[word_idx][2] = (word >> 16) & 0xFF
            pixels[word_idx][3] = (word >> 24) & 0xFF
        print(f"    Loaded {len(dtb_data)} bytes of DTB data")

    # Create GPU harness
    harness = create_gpu_boot_harness(pixels, root_ppn, entry_point, dtb_addr)

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

        cpu_readback = np.frombuffer(
            device.queue.read_buffer(cpu_buffer),
            dtype=cpu_layout
        )[0]

        running = cpu_readback['running']
        pc_low = cpu_readback['pc'][0]
        pc_high = cpu_readback['pc'][1]
        pc = (pc_high << 32) | pc_low
        instr_count = cpu_readback['instr_count']

        if pc == last_pc:
            stale_count += 1
            if stale_count > 10:
                print(f"    PC stalled at 0x{pc:016x}")
                break
        else:
            stale_count = 0
            last_pc = pc

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

    output_str = ''
    for i in range(0, len(output_data), 4):
        word = struct.unpack('<I', output_data[i:i+4])[0]
        for b in word.to_bytes(4, 'little'):
            if b == 0:
                break
            if 32 <= b < 127:
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
        print("Usage: python3 boot_alpine_lnx_gpu.py <alpine-riscv64.lnx.bin>")
        print("\nExample:")
        print("  python3 boot_alpine_lnx_gpu.py /home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin")
        sys.exit(1)

    lnx_path = sys.argv[1]

    if not Path(lnx_path).exists():
        print(f"Error: File not found: {lnx_path}")
        sys.exit(1)

    boot_alpine_on_gpu(lnx_path)