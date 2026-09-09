#!/usr/bin/env python3
"""
Boot xv6-riscv kernel on GPU RISC-V Emulator (v2)

Like tools/boot_xv6_gpu.py, but loads the emulator shader from a pixel frame
instead of from tools/RISCV_CPU_MMU.wgsl. The frame is verified by SHA-256 before
use.

This is Level 1 of the emulator_v2 migration: the emulator travels as pixels
but still compiles to native GPU code — zero runtime cost.
"""

import struct
import numpy as np
from pathlib import Path
import sys
import argparse
import wgpu
import wgpu.utils

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / 'emulator_v2'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from pack_shader import unpack

# ============================================================================
# ELF64 LOADER (from boot_xv6_gpu.py)
# ============================================================================

class ELF64Loader:
    """Parse and load RISC-V ELF64 binaries."""

    EI_CLASS_64 = 2
    EI_DATA_LITTLE = 1
    ET_EXEC = 2
    EM_RISCV = 243

    def __init__(self, elf_path: str):
        self.path = elf_path
        with open(elf_path, 'rb') as f:
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
        self.ehsize = struct.unpack_from('<H', self.data, 52)[0]
        self.phentsize = struct.unpack_from('<H', self.data, 54)[0]
        self.phnum = struct.unpack_from('<H', self.data, 56)[0]

        # Verify RISC-V ELF64
        if self.ei_class != self.EI_CLASS_64:
            raise ValueError(f"Not ELF64 (EI_CLASS={self.ei_class})")
        if self.ei_data != self.EI_DATA_LITTLE:
            raise ValueError(f"Not little-endian (EI_DATA={self.ei_data})")
        if self.e_type != self.ET_EXEC:
            raise ValueError(f"Not executable (e_type={self.e_type})")
        if self.e_machine != self.EM_RISCV:
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

    def get_loadable_segments(self):
        """Return loadable program headers (PT_LOAD)."""
        PT_LOAD = 1
        return [ph for ph in self.program_headers if ph['p_type'] == PT_LOAD]

    def get_segment_data(self, segment):
        """Return raw segment data from the file."""
        return self.data[segment['p_offset']:segment['p_offset'] + segment['p_filesz']]

    def print_info(self):
        """Print ELF information."""
        print(f"ELF64 File: {self.path}")
        print(f"Entry Point: 0x{self.entry_point:016x}")
        print(f"\nLoadable Segments:")
        for seg in self.program_headers:
            flags_str = []
            if seg['p_flags'] & 1:
                flags_str.append('X')
            if seg['p_flags'] & 2:
                flags_str.append('W')
            if seg['p_flags'] & 4:
                flags_str.append('R')
            print(f"  0x{seg['p_vaddr']:016x} - 0x{seg['p_vaddr'] + seg['p_memsz']:016x} "
                  f"({seg['p_filesz']}/{seg['p_memsz']} bytes) [{''.join(flags_str)}]")


# CPU state dtype must match RISCV_CPU_MMU.wgsl struct RiscvCPU exactly
CPU_DTYPE = np.dtype([
    ('pc', np.uint32, 2),
    ('regs', np.uint32, (32, 2)),
    ('running', np.uint32),
    ('instr_count', np.uint32),
    ('output_ptr', np.uint32),
    ('priv_mode', np.uint32),   # 3 = M-mode (boot default), 1 = S, 0 = U
    ('satp', np.uint32, 2),     # Real RV64 layout: mode [63:60], PPN [43:0]
    ('mstatus', np.uint32, 2),
    ('mtvec', np.uint32, 2),
    ('mepc', np.uint32, 2),
    ('mcause', np.uint32, 2),
    ('mtval', np.uint32, 2),
    ('mscratch', np.uint32, 2),
    ('mie', np.uint32, 2),
    ('mip', np.uint32, 2),
    ('stvec', np.uint32, 2),
    ('sepc', np.uint32, 2),
    ('scause', np.uint32, 2),
    ('stval', np.uint32, 2),
    ('sscratch', np.uint32, 2),
    ('medeleg', np.uint32, 2),
    ('mideleg', np.uint32, 2),
    ('menvcfg', np.uint32, 2),  # CSR 0x30A, machine environment config
    ('virtio_status', np.uint32),
    ('vq_desc_low', np.uint32),
    ('vq_desc_high', np.uint32),
    ('vq_avail_low', np.uint32),
    ('vq_avail_high', np.uint32),
    ('vq_used_low', np.uint32),
    ('vq_used_high', np.uint32),
    ('vq_idx', np.uint32),
    ('vq_ready', np.uint32),
    ('vq_queue_num', np.uint32),
    ('vq_queue_align', np.uint32),
    ('plic_pending', np.uint32),
    ('plic_enable', np.uint32),
    ('plic_claimed', np.uint32),
    ('uart_irq_delay', np.uint32),
    ('uart_input_ptr', np.uint32),  # guest-owned, persists across dispatches
    ('uart_input_len', np.uint32),  # host-owned; shader only reads it
    ('mtime_low', np.uint32),       # CLINT mtime (low 32 bits)
    ('mtime_high', np.uint32),      # CLINT mtime (high 32 bits)
    ('mtimecmp_low', np.uint32),    # CLINT mtimecmp (low 32 bits)
    ('mtimecmp_high', np.uint32),   # CLINT mtimecmp (high 32 bits)
    ('timer_fired', np.uint32),     # Edge trigger: timer already fired for this mtimecmp
    ('timer_interrupt_count', np.uint32),  # Number of timer interrupts taken
    ('total_interrupt_count', np.uint32),  # Total interrupts taken
    ('plic_priority_irq1', np.uint32),     # Priority for IRQ 1
    ('current_instr_len', np.uint32),      # 2 (RVC) or 4 - set by fetch
    ('uefi_heap_ptr', np.uint32),          # Next free byte in the UEFI AllocatePool heap
    ('uefi_heap_end', np.uint32),          # First byte past the UEFI heap region
])

assert CPU_DTYPE.itemsize == 528, f"CPU struct layout drifted: {CPU_DTYPE.itemsize}"

def make_cpu_state(entry_point: int, priv_mode: int = 3):
    """One-hart CPU state array, booting in M-mode with MMU off by default."""
    cpu = np.zeros(1, dtype=CPU_DTYPE)
    cpu[0]['pc'] = [entry_point & 0xFFFFFFFF, (entry_point >> 32) & 0xFFFFFFFF]
    cpu[0]['running'] = 1
    cpu[0]['priv_mode'] = priv_mode
    return cpu


# ============================================================================
# GPU HARNESS SETUP
# ============================================================================

def create_gpu_hardware_v2(shader_frame_path: Path, pixel_data: np.ndarray, cpu_state: np.ndarray, max_instructions: int = 100000000):
    """Initialize GPU and load emulator shader from a pixel frame (v2 variant)."""
    device = wgpu.utils.get_default_device()
    queue = device.queue

    # Load shader from pixel frame (v2: not from .wgsl file)
    print(f"\n[2] Loading emulator shader from pixel frame: {shader_frame_path}")

    # Unpack and verify the frame (SHA-256 check happens here)
    tmp_shader = Path('/tmp/xv6_gpu_v2_shader.wgsl')
    try:
        unpack(shader_frame_path, tmp_shader)
    except SystemExit as e:
        raise RuntimeError(f"Failed to unpack shader frame: {e}")

    shader_code = tmp_shader.read_text()
    print(f"    Loaded {len(shader_code)} bytes of WGSL from frame")

    # Clean up temp file
    tmp_shader.unlink()

    # Create buffers (same as original)
    memory_buffer = device.create_buffer(
        size=pixel_data.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    output_buffer = device.create_buffer(
        size=65536,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST,
    )

    # Input buffer for UART (inject keystrokes)
    input_buffer = device.create_buffer(
        size=1024,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        mapped_at_creation=False,
    )

    # Uniform buffer for instruction limit
    max_instr_arr = np.array([max_instructions], dtype=np.uint32)
    uniform_buffer = device.create_buffer(
        size=max_instr_arr.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )

    # Upload initial data
    queue.write_buffer(memory_buffer, 0, pixel_data.tobytes())
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())
    queue.write_buffer(uniform_buffer, 0, max_instr_arr.tobytes())
    queue.write_buffer(input_buffer, 0, np.zeros(256, dtype=np.uint32).tobytes())

    # Bind group layout (from RISCV_CPU_MMU.wgsl)
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
        {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
    ])

    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': memory_buffer, 'offset': 0, 'size': pixel_data.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': 65536}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': max_instr_arr.nbytes}},
            {'binding': 4, 'resource': {'buffer': input_buffer, 'offset': 0, 'size': 1024}},
        ]
    )

    print(f"\n[5] Creating compute pipeline from pixel-sourced shader...")
    compute_shader = device.create_shader_module(code=shader_code)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': compute_shader, 'entry_point': 'main'},
    )

    print(f"    Device: {device.adapter.info['description']}")
    print(f"    Shader: {shader_frame_path} (verified SHA-256)")
    print(f"    Memory buffer: {pixel_data.nbytes // 4} words ({pixel_data.nbytes // 1024 // 1024}MB)")

    return {
        'device': device,
        'queue': queue,
        'pipeline': pipeline,
        'bind_group': bind_group,
        'cpu_buffer': cpu_buffer,
        'output_buffer': output_buffer,
        'input_buffer': input_buffer,
        'memory_buffer': memory_buffer,
    }


# ============================================================================
# MAIN BOOT SEQUENCE
# ============================================================================

def boot_xv6_on_gpu_v2(elf_path: str, shader_frame_path: Path,
                       max_instructions: int = 100000000):
    """Boot xv6 on GPU emulator with pixel-sourced shader."""

    print("=" * 70)
    print("XV6 RISC-V GPU BOOT - v2 (shader from pixels)")
    print("=" * 70)
    print(f"Shader frame: {shader_frame_path}")

    # Load ELF kernel
    print(f"\n[1] Loading ELF64 kernel...")
    loader = ELF64Loader(elf_path)
    loader.print_info()

    # Memory setup
    print("\n[2] Loading kernel segments into memory...")
    MEMORY_SIZE_MB = 18  # Kernel is at 0x80000000, fs.img at 0x81000000 (16MB offset)
    MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
    PHYS_START = 0x80000000
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint32)

    for seg in loader.get_loadable_segments():
        addr = seg['p_vaddr']
        size = seg['p_memsz']
        filesz = seg['p_filesz']
        offset = addr - PHYS_START

        data = loader.get_segment_data(seg)
        for i, byte in enumerate(data):
            pixel_idx = (offset + i) // 4
            byte_idx = (offset + i) % 4
            memory[pixel_idx, byte_idx] = byte
        print(f"  Loaded {filesz} bytes at 0x{addr:016x}")

    # Load fs.img at fixed offset
    fs_img_path = Path('/tmp/xv6-riscv/fs.img')
    if fs_img_path.exists():
        print(f"\n[2b] Loading filesystem image...")
        fs_data = fs_img_path.read_bytes()
        fs_offset = 0x81000000 - PHYS_START
        print(f"  Loaded {len(fs_data)} bytes at 0x81000000")

        start_pixel = fs_offset // 4
        start_byte = fs_offset % 4

        if start_byte == 0:
            word_count = (len(fs_data) + 3) // 4
            byte_data = np.frombuffer(fs_data, dtype=np.uint8)
            padded_len = word_count * 4
            if len(byte_data) < padded_len:
                padded = np.zeros(padded_len, dtype=np.uint8)
                padded[:len(byte_data)] = byte_data
                byte_data = padded
            pixel_data = byte_data.reshape(-1, 4)
            memory[start_pixel:start_pixel + word_count] = pixel_data
        else:
            for i, byte in enumerate(fs_data):
                pixel_idx = (fs_offset + i) // 4
                byte_idx = (fs_offset + i) % 4
                memory[pixel_idx, byte_idx] = byte

    # CPU state setup
    cpu_state = make_cpu_state(loader.entry_point, priv_mode=3)
    print(f"\n[3] CPU state initialized: PC=0x{loader.entry_point:016x}, M-mode, MMU off")

    # Setup GPU hardware with shader from pixels
    harness = create_gpu_hardware_v2(shader_frame_path, memory, cpu_state, max_instructions)

    print("\n[6] Starting execution loop...")
    print(f"    Max instructions: {max_instructions}")

    # Simple execution loop (dispatch batches)
    device = harness['device']
    queue = harness['queue']
    pipeline = harness['pipeline']
    bind_group = harness['bind_group']
    output_buffer = harness['output_buffer']
    cpu_buffer = harness['cpu_buffer']

    instr_batch = 2000000  # Match v1: 2M instructions per readback (1.5B instr = 750 dispatches)
    total_dispatches = 0
    max_dispatches = max_instructions // instr_batch

    try:
        print(f"DEBUG: Starting loop, max_dispatches={max_dispatches}, instr_batch={instr_batch}", flush=True)
        for i in range(max_dispatches):
            # Dispatch batch
            command_encoder = device.create_command_encoder()
            compute_pass = command_encoder.begin_compute_pass()
            compute_pass.set_pipeline(pipeline)
            compute_pass.set_bind_group(0, bind_group)
            compute_pass.dispatch_workgroups(1, 1, 1)
            compute_pass.end()
            queue.submit([command_encoder.finish()])

            # Check for halt
            print(f"DEBUG: Dispatch {total_dispatches}, reading CPU buffer...", flush=True)
            cpu_readback_bytes = queue.read_buffer(cpu_buffer)
            cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=CPU_DTYPE)
            print(f"DEBUG: Read complete, running={cpu_readback['running'][0]}", flush=True)

            total_dispatches += 1

            # Progress every dispatch (unbuffered)
            pc_low = cpu_readback['pc'][0][0]
            pc_high = cpu_readback['pc'][0][1]
            pc = pc_low | (pc_high << 32)
            running = cpu_readback['running'][0]
            instr_count = cpu_readback['instr_count'][0]
            print(f"    [{total_dispatches}] {total_dispatches * instr_batch:7d} instr, PC=0x{pc:016x}, running={running}", flush=True)

            if cpu_readback['running'][0] == 0:
                print(f"\n    Halted after {total_dispatches * instr_batch} instructions")
                break
    except KeyboardInterrupt:
        print(f"\n    Interrupted after {total_dispatches * instr_batch} instructions")

    # Read UART output
    output_data = queue.read_buffer(output_buffer)
    text = ''
    for b in output_data:
        if b == 0:
            break
        if 32 <= b < 127 or b in (10, 13):
            text += chr(b)

    print("\n[7] UART Output:")
    print("=" * 70)
    print(text)
    print("=" * 70)

    print(f"\n[✓] Boot completed: {total_dispatches * instr_batch} instructions")
    print(f"    Shader source: {shader_frame_path.name} (pixel-encoded, SHA-256 verified)")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Boot xv6-riscv on GPU RISC-V Emulator (v2, shader from pixels)')
    parser.add_argument('kernel', help='Path to xv6 kernel ELF')
    parser.add_argument(
        '--shader-frame',
        default='emulator_v2/emulator_frame.png',
        help='Path to emulator shader pixel frame (default: emulator_v2/emulator_frame.png)'
    )
    parser.add_argument('--max-instructions', type=int, default=10000000,
                       help='Max instructions to execute (default: 10M)')

    args = parser.parse_args()

    kernel_path = Path(args.kernel)
    shader_frame_path = Path(args.shader_frame)

    if not kernel_path.exists():
        parser.error(f"Kernel not found: {kernel_path}")
    if not shader_frame_path.exists():
        parser.error(f"Shader frame not found: {shader_frame_path}")

    try:
        boot_xv6_on_gpu_v2(str(kernel_path), shader_frame_path, max_instructions=args.max_instructions)
    except Exception as e:
        print(f"\n[✗] Boot failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())