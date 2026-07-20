#!/usr/bin/env python3
"""
Boot xv6-riscv kernel on GPU RISC-V Emulator

Loads the xv6 kernel (compiled without C extension), boots in M-mode
with SBI-style UART console output.

Phase 13: GPU-Native OS Boot
"""

import struct
import numpy as np
from pathlib import Path
from typing import List, Tuple
import sys


# ============================================================================
# ELF64 LOADER (reused from boot_alpine_lnx_gpu.py)
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
# MEMORY IMAGE BUILDER
# ============================================================================

def build_memory_image(elf_path: str) -> Tuple[np.ndarray, int]:
    """
    Build complete memory image for GPU execution (128MB fixed size).
    xv6 boots at 0x80000000 (standard RISC-V QEMU virt machine).

    Memory layout:
    - 0x80000000: 128MB DRAM (maps to pixel 0)
    - 0x10000000: UART (maps to pixel for UART writes)

    Returns: (memory_pixels, entry_point)
    """
    # Load ELF
    print("[1] Loading ELF64 kernel...")
    elf = ELF64Loader(elf_path)
    elf.print_info()

    # xv6 uses 128MB memory starting at 0x80000000
    memory_size = 16 * 1024 * 1024
    dram_base = 0x80000000
    memory = bytearray(memory_size)

    # Load ELF segments
    print("\n[2] Loading kernel segments into memory...")
    for seg in elf.program_headers:
        data = elf.get_segment_data(seg)
        if data:
            # Convert virtual address to physical offset
            # xv6 uses identity mapping: VA = PA
            phys_offset = seg['vaddr'] - dram_base

            if phys_offset < 0:
                print(f"Warning: Segment at 0x{seg['vaddr']:016x} below DRAM base")
                continue

            if phys_offset + len(data) > memory_size:
                print(f"Warning: Segment at 0x{seg['vaddr']:016x} exceeds memory")
            else:
                memory[phys_offset:phys_offset + len(data)] = data
                print(f"  Loaded {len(data)} bytes at 0x{seg['vaddr']:016x}")
                # Zero-fill BSS
                if seg['memsz'] > seg['filesz']:
                    bss_start = phys_offset + seg['filesz']
                    bss_end = phys_offset + seg['memsz']
                    if bss_end <= memory_size:
                        memory[bss_start:bss_end] = b'\x00' * (bss_end - bss_start)
                        print(f"    BSS: 0x{seg['vaddr'] + seg['filesz']:016x} - 0x{seg['vaddr'] + seg['memsz']:016x}")

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

    print(f"  Memory: {memory_size // (1024*1024)}MB ({num_pixels} pixels)")
    print(f"  Physical range: 0x{dram_base:x} - 0x{dram_base + memory_size:x}")

    return pixels, elf.entry_point


# ============================================================================
# GPU EXECUTION
# ============================================================================

def create_gpu_boot_harness(pixels: np.ndarray, entry_point: int) -> dict:
    """Create GPU buffers and CPU state for boot."""
    import wgpu
    import wgpu.utils

    print("\n[4] Initializing GPU...")
    device = wgpu.utils.get_default_device()
    queue = device.queue
    print(f"    Device: {device.adapter.info.device}")

    # Use MMU shader (RISCV_CPU_MMU.wgsl) even though xv6 boots in M-mode
    # We can always keep MMU disabled (SATP=0)
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

    # CPU state with M-mode boot (no MMU, no SBI needed)
    from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
    cpu_state = make_cpu_state(entry_point, satp=(0, 0), priv_mode=3)  # M-mode
    
    # Initialize gp (register 3) for small data access
    # The boot stub uses: ADDI sp, gp, 0; ADDI sp, sp, -1936; LHU a0, 607(sp)
    # Setting gp=0x80001000 gives sp=0x80001000-1936=0x80000720, and sp+607=0x8000098b (valid)
    gp_value = 0x80001000
    cpu_state[0]['regs'][3] = [gp_value & 0xFFFFFFFF, (gp_value >> 32) & 0xFFFFFFFF]
    print(f"    Initial gp (x3): 0x{gp_value:#010x}")

    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    print(f"    CPU state: PC=0x{entry_point:016x}, M-mode, MMU off")

    # Output buffer for UART console
    output_buffer = device.create_buffer(
        size=65536,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    max_instructions = np.array([60000005], dtype=np.uint32)  # 2M instructions for kernel boot
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

    print("\n[5] Creating compute pipeline...")
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


def boot_xv6_on_gpu(elf_path: str):
    """Main boot sequence."""
    print("=" * 70)
    print("XV6 RISC-V GPU BOOT - Phase 13")
    print("=" * 70)

    # Build memory image
    pixels, entry_point = build_memory_image(elf_path)

    # Create GPU harness
    harness = create_gpu_boot_harness(pixels, entry_point)

    # Execute
    print("\n[6] Booting xv6 on GPU...")
    print("    (This will execute up to 2M instructions)")
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

    for iteration in range(100000):
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
        scause = cpu_readback['scause'][0] | (cpu_readback['scause'][1] << 32)
        if scause in [12, 13, 15]:
            print(f'\n[!] Page Fault Caught! scause={scause}')
            print(f'Fault VA: 0x{cpu_readback["mmu_debug_va"][1]:x}{cpu_readback["mmu_debug_va"][0]:08x}')
            print(f'Fault Level: {cpu_readback["mmu_debug_fault_level"]}')
            print(f'L1 PTE: 0x{cpu_readback["mmu_debug_l1_pte"][0]:08x}')
            print(f'L2 PTE: 0x{cpu_readback["mmu_debug_l2_pte"][0]:08x}')
            print(f'L3 PTE: 0x{cpu_readback["mmu_debug_l3_pte"][0]:08x}')
            running = 0
        pc_low = cpu_readback['pc'][0]
        pc_high = cpu_readback['pc'][1]
        pc = (pc_high << 32) | pc_low
        instr_count = cpu_readback['instr_count']

        last_pc = pc
        if pc == 0x80000ac0:
            print('Kernel panic caught!')
            running = 0

        # Progress indicator (less frequent to not spam)
        if iteration % 100 == 0 or running == 0:
            print(f"    Iter {iteration:5d}: PC=0x{pc:016x}, running={running}, instr={instr_count}")

        if running == 0:
            break
        if instr_count >= 60000005:
            print(f'\n[!] Instruction limit {60000005} reached.')
            break
            print(f"\n    Halted after {instr_count} instructions")

            def f64(name):
                lo, hi = cpu_readback[name]
                return (int(hi) << 32) | int(lo)

            mepc, mcause, mtval = f64('mepc'), f64('mcause'), f64('mtval')
            sepc, scause, stval = f64('sepc'), f64('scause'), f64('stval')
            priv = int(cpu_readback['priv_mode'])
            causes = {0: 'instr addr misaligned', 1: 'instr access fault',
                      2: 'illegal instruction', 3: 'breakpoint',
                      4: 'load addr misaligned', 5: 'load access fault',
                      6: 'store addr misaligned', 7: 'store access fault',
                      8: 'ecall from U', 9: 'ecall from S', 11: 'ecall from M',
                      12: 'instr page fault', 13: 'load page fault', 15: 'store page fault'}
            print("\n" + "=" * 70)
            print("TRAP DUMP")
            print("=" * 70)
            print(f"    priv_mode = {priv} (0=U 1=S 3=M)")
            print(f"    mepc      = 0x{mepc:016x}")
            print(f"    mcause    = 0x{mcause:016x}  ({causes.get(mcause & 0xF, 'unknown')})")
            print(f"    mtval     = 0x{mtval:016x}")
            print(f"    sepc      = 0x{sepc:016x}")
            print(f"    scause    = 0x{scause:016x}  ({causes.get(scause & 0xF, 'unknown')})")
            print(f"    stval     = 0x{stval:016x}")
            # If mtval/stval look like a 32-bit instruction word rather than
            # an address, decode its opcode/funct3/funct7 for a quick read.
            for label, val in (('mtval', mtval), ('stval', stval)):
                if 0 < val <= 0xFFFFFFFF:
                    op = val & 0x7F
                    f3 = (val >> 12) & 0x7
                    f7 = (val >> 25) & 0x7F
                    print(f"    {label} as instr: opcode=0x{op:02x} funct3=0x{f3:x} funct7=0x{f7:02x}")
            print(f"    MMU Fault Level: {cpu_readback['mmu_debug_fault_level']}")
            print(f"    MMU L1 PTE: 0x{cpu_readback['mmu_debug_l1_pte'][1]:08x}_{cpu_readback['mmu_debug_l1_pte'][0]:08x}")
            print(f"    MMU L2 PTE: 0x{cpu_readback['mmu_debug_l2_pte'][1]:08x}_{cpu_readback['mmu_debug_l2_pte'][0]:08x}")
            print(f"    MMU L3 PTE: 0x{cpu_readback['mmu_debug_l3_pte'][1]:08x}_{cpu_readback['mmu_debug_l3_pte'][0]:08x}")
            print(f"    MMU Fault VA: 0x{cpu_readback['mmu_debug_va'][1]:08x}_{cpu_readback['mmu_debug_va'][0]:08x}")
            print("=" * 70)
            break

    # Read output (UART console)
    print("\n[7] Reading UART console output...")
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
            if 32 <= b < 127 or b == ord('\n') or b == ord('\r'):
                output_str += chr(b)

    print("\n" + "=" * 70)
    print("UART CONSOLE OUTPUT")
    print("=" * 70)
    if output_str:
        print(output_str)
    else:
        print("(No output captured)")

    print("=" * 70)
    a2_val = cpu_readback["regs"][12][0] | (cpu_readback["regs"][12][1] << 32)
    a4_val = cpu_readback["regs"][14][0] | (cpu_readback["regs"][14][1] << 32)
    a5_val = cpu_readback["regs"][15][0] | (cpu_readback["regs"][15][1] << 32)
    print('ra:', hex(cpu_readback['regs'][1][0]), 'a0:', hex(cpu_readback['regs'][10][0]), 'a1:', hex(cpu_readback['regs'][11][0]), 'a2:', hex(a2_val))
    print(f"Final PC: 0x{pc:016x}")
    print(f"Instructions executed: {instr_count}")
    print(f"CPU running: {running}")
    print("=" * 70)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 boot_xv6_gpu.py <xv6-kernel.elf>")
        print("\nExample:")
        print("  python3 boot_xv6_gpu.py /tmp/xv6-riscv/kernel/kernel")
        sys.exit(1)

    elf_path = sys.argv[1]

    if not Path(elf_path).exists():
        print(f"Error: File not found: {elf_path}")
        sys.exit(1)

    boot_xv6_on_gpu(elf_path)