#!/usr/bin/env python3
"""
Boot xv6-riscv kernel on GPU RISC-V Emulator

Loads the xv6 kernel (compiled without C extension), boots in M-mode
with SBI-style UART console output.

Phase 13: GPU-Native OS Boot
"""

import struct
import json
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
import sys
import argparse
import wgpu
import wgpu.utils
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state
from hybrid_kernel_loader import HybridKernelLoader


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

        sloader.entry_point = self.e_entry

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
        print(f"Entry Point: 0x{sloader.entry_point:016x}")
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


# ============================================================================
# GPU HARNESS SETUP
# ============================================================================

def create_gpu_hardware(pixel_data: np.ndarray, cpu_state: np.ndarray, max_instructions: int = 100000000):
    """Initialize GPU, buffers, and compute pipeline."""
    device = wgpu.utils.get_default_device()
    queue = device.queue

    # Load shader
    shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
    shader_code = shader_path.read_text()

    # Create buffers
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
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
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

    # Bind group layout
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
        'input_buffer': input_buffer,
    }


# ============================================================================
# MAIN BOOT SEQUENCE
# ============================================================================

def inject_command(queue, harness, cpu_layout, text):
    """Write `text` into the UART input buffer and tell the shader how much
    is available, resetting the guest read position to 0.

    sh.c's getcmd() blocks in consoleread() until it sees a newline, so a
    command with none appended just sits there echoed but never executed.
    Only safe to call once the guest has fully drained any previous input
    (e.g. right after a fresh "$ " prompt appears).
    """
    text_nl = text if text.endswith('\n') else text + '\n'
    cmd_bytes = text_nl.encode('utf-8')[:255]  # input buffer is 256 words
    cmd_array = np.zeros(256, dtype=np.uint32)
    for i, b in enumerate(cmd_bytes):
        cmd_array[i] = b
    queue.write_buffer(harness['input_buffer'], 0, cmd_array.tobytes())
    ptr_offset = cpu_layout.fields['uart_input_ptr'][1]
    len_offset = cpu_layout.fields['uart_input_len'][1]
    queue.write_buffer(harness['cpu_buffer'], ptr_offset, np.array([0], dtype=np.uint32).tobytes())
    queue.write_buffer(harness['cpu_buffer'], len_offset, np.array([len(cmd_bytes)], dtype=np.uint32).tobytes())


AUTONOMOUS_SYSTEM_PROMPT = """You are driving an interactive shell inside \
xv6 (a minimal Unix-like teaching OS) running on an experimental GPU-native \
RISC-V emulator, through its real console. Your goal is to exercise and \
stress-test the OS: try built-in programs (ls, cat, echo, mkdir, rm, ln, \
wc, grep, kill, usertests), pipes, redirection, and process creation. \
Prefer commands you have not tried yet in this session.

Reply with EXACTLY ONE shell command to run next and nothing else - no \
explanation, no markdown formatting, no quotes around it, no leading $. \
Base it on the shell output shown below."""


def get_next_autonomous_command(recent_output, model):
    """Ask Ollama for the next shell command to try, given recent output.
    Returns a single sanitized command line, or None if Ollama's reply
    doesn't look usable."""
    from ollama_prompt import prompt_ollama
    reply = prompt_ollama(
        f"Recent shell output:\n{recent_output}\n\nNext command:",
        model=model,
        system_prompt=AUTONOMOUS_SYSTEM_PROMPT,
    )
    for line in reply.splitlines():
        line = line.strip().strip('`').strip()
        if line.startswith('$'):
            line = line[1:].strip()
        if line:
            return line[:200]
    return None


def boot_xv6_on_gpu(elf_path: str, command: str = None, autonomous: bool = False,
                    autonomous_turns: int = 20, autonomous_model: str = 'qwen2.5-coder:14b',
                    trace_file: Optional[str] = None, trace_max: int = 2000,
                    init_state: Optional[str] = None, stall_threshold: int = 100):
    """Main boot sequence.

    Args:
        elf_path: Path to xv6 kernel ELF
        command: Optional single command to inject after shell prompt
        autonomous: If True, drive the shell with Ollama-generated commands
            instead of a single fixed `command`, for up to autonomous_turns
        autonomous_turns: Cap on how many Ollama-driven commands to run
        autonomous_model: Ollama model tag to use for autonomous mode
        trace_file: If set, capture per-instruction CPU state trace to this
            JSONL file (uses max_instructions=1 for instruction-level
            granularity)
        trace_max: Max instructions to capture when tracing (default: 2000)
    """
    print("=" * 70)
    print("XV6 RISC-V GPU BOOT - Phase 13")
    print("=" * 70)
    if autonomous:
        print(f"Autonomous mode: up to {autonomous_turns} Ollama-driven commands "
              f"(model={autonomous_model})")
    elif command:
        print(f"Command to inject: {repr(command)}")
    print("=" * 70)

    # [1] Load ELF kernel
    print(f"\n[1] Loading ELF64 kernel...")
    loader, fmt = HybridKernelLoader.load(elf_path)
    
    # Check if we should inject the EFI tables
    is_pe32 = fmt == "PE32+"
    print("\n[2] Loading kernel segments into memory...")
    MEMORY_SIZE_MB = 128
    MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024  # 128MB
    PHYS_START = 0x80000000  # xv6 physical memory base

    # Create memory array (4 bytes per pixel, RGBA layout)
    # Each pixel is 4 bytes [R, G, B, A] = 4 uint32 values
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint32)

    # fmt is already returned from HybridKernelLoader.load()
    for seg in loader.get_loadable_segments():
        if fmt == "ELF64":
            addr = seg['p_vaddr']
            size = seg['p_memsz']
            filesz = seg['p_filesz']
            offset = addr - PHYS_START
        else:
            addr = seg['virtual_address'] + PHYS_START + 0x00200000
            size = seg['virtual_size']
            filesz = seg['size_of_raw_data']
            offset = addr - PHYS_START

        data = loader.get_segment_data(seg)
        start_pixel = offset // 4
        start_byte = offset % 4
        
        # We need to construct the uint32 value manually
        for i, byte in enumerate(data):
            pixel_idx = (offset + i) // 4
            byte_idx = (offset + i) % 4
            memory[pixel_idx, byte_idx] = byte
        print(f"  Loaded {filesz} bytes at 0x{addr:016x}")
        if size > filesz:
            bss_start = offset + filesz
            bss_size = size - filesz
            bss_addr = addr + filesz
            print(f"    BSS: 0x{bss_addr:016x} - 0x{addr + size:016x}")

    # [2b] Load fs.img
    fs_img_path = Path('/tmp/xv6-riscv/fs.img')
    if fs_img_path.exists():
        print(f"  Loaded {fs_img_path.stat().st_size} bytes of fs.img at 0x81000000")
        fs_data = fs_img_path.read_bytes()
        fs_offset = 0x81000000 - PHYS_START
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

    # [3] Memory is already in RGBA pixel layout (2D array)
    # No conversion needed
    print("\n[3] Memory in RGBA pixel layout...")
    print(f"  Memory: {MEMORY_SIZE_MB}MB ({pixel_count} pixels)")
    print(f"  Physical range: 0x{PHYS_START:016x} - 0x{PHYS_START + MEMORY_SIZE:016x}")

    if is_pe32:
        print("  Injecting EFI System Table...")
        efi_offset = 0
        efi_pixel = efi_offset // 4
        
        def write_word(px, value):
            memory[px, 0] = value & 0xFF
            memory[px, 1] = (value >> 8) & 0xFF
            memory[px, 2] = (value >> 16) & 0xFF
            memory[px, 3] = (value >> 24) & 0xFF

        # Header (24 bytes)
        write_word(efi_pixel, 0x20494249) # 'IBI '
        write_word(efi_pixel + 1, 0x54535953) # 'SYST'
        write_word(efi_pixel + 2, 0x00020032) # UEFI 2.50
        write_word(efi_pixel + 3, 112)        # Header Size
        write_word(efi_pixel + 4, 0)          # CRC32
        write_word(efi_pixel + 5, 0)          # Reserved
        # Fill rest of table with 0s
        for i in range(6, 112 // 4):
            write_word(efi_pixel + i, 0)
            
        # ConIn (8) -> 0x80000500
        write_word(efi_pixel + (48 // 4), 0x80000500) # offset 48
        write_word(efi_pixel + (48 // 4) + 1, 0)

        # ConOut (8) -> 0x80000400
        write_word(efi_pixel + (64 // 4), 0x80000400) # offset 64
        write_word(efi_pixel + (64 // 4) + 1, 0)
        
        # StdErr (8) -> 0x80000400
        write_word(efi_pixel + (80 // 4), 0x80000400) # offset 80
        write_word(efi_pixel + (80 // 4) + 1, 0)
        
        # RuntimeServices (8) -> 0x80000100
        write_word(efi_pixel + (88 // 4), 0x80000100) # offset 88
        write_word(efi_pixel + (88 // 4) + 1, 0)
        
        # BootServices (8) -> 0x80000200
        write_word(efi_pixel + (96 // 4), 0x80000200) # offset 96
        write_word(efi_pixel + (96 // 4) + 1, 0)
        
        # Fill RuntimeServices (0x100), ConOut (0x400), and ConIn (0x500)
        # with function pointers pointing to the unhandled trampoline at 0x80000300.
        # Bounded to each struct's actual span so this doesn't smash the
        # neighboring struct (RuntimeServices ends at BootServices' 0x200,
        # ConOut/ConIn each end at the 0x80-byte Mode struct that follows).
        # A flat 1024-byte fill previously blew through all three, corrupting
        # BootServices/ConOut/Mode with stray trampoline pointers.
        region_sizes = {0x100: 0x100, 0x400: 0x80, 0x500: 0x80}
        for offset, size in region_sizes.items():
            px_start = offset // 4
            for i in range(0, size // 8):
                # Write pointer (0x80000300) to offset i * 8
                write_word(px_start + i * 2, 0x80000300)
                write_word(px_start + i * 2 + 1, 0)

        # Generate 45 trampolines for BootServices at 0x80001000
        for i in range(45):
            # Address of trampoline i
            t_addr = 0x80001000 + i * 16
            
            # Write trampoline instructions
            #   addi a7, zero, 1000 + i
            #   ecall
            #   ret (jalr zero, 0(ra))
            px = (0x1000 + i * 16) // 4
            imm = 1000 + i
            addi_instr = (imm << 20) | (17 << 7) | 0x13
            write_word(px, addi_instr)
            write_word(px + 1, 0x00000073) # ecall
            write_word(px + 2, 0x00008067) # jalr zero, 0(ra)
            write_word(px + 3, 0)
            
            # Update BootServices table at offset i (i*8 bytes after header)
            # BootServices table starts at 0x80000200. Header is 24 bytes (0x18).
            # So function i is at offset 0x218 + i * 8
            bs_func_offset = 0x218 + i * 8
            write_word(bs_func_offset // 4, t_addr)
            write_word((bs_func_offset // 4) + 1, 0)
            
        # Generate trampoline for ConOut->OutputString (Syscall 2000) at 0x80001F00
        t_addr_out = 0x80001F00
        px_out = 0x1F00 // 4
        imm_out = 2000
        addi_instr_out = (imm_out << 20) | (17 << 7) | 0x13
        write_word(px_out, addi_instr_out)
        write_word(px_out + 1, 0x00000073) # ecall
        write_word(px_out + 2, 0x00008067) # jalr zero, 0(ra)
        write_word(px_out + 3, 0)
        
        # ConOut->OutputString is offset 8 in SIMPLE_TEXT_OUTPUT_PROTOCOL
        write_word((0x400 // 4) + (8 // 4), t_addr_out)
        write_word((0x400 // 4) + (8 // 4) + 1, 0)
                
        # ConOut->Mode -> 0x80000480
        # In SIMPLE_TEXT_OUTPUT_PROTOCOL, Mode is at offset 72
        write_word((0x400 // 4) + (72 // 4), 0x80000480)
        write_word((0x400 // 4) + (72 // 4) + 1, 0)
        
        # SIMPLE_TEXT_OUTPUT_MODE struct at 0x80000480
        m_px = 0x480 // 4
        write_word(m_px, 1)      # MaxMode = 1
        write_word(m_px + 1, 0)  # Mode = 0
        write_word(m_px + 2, 0)  # Attribute = 0
        write_word(m_px + 3, 0)  # CursorColumn = 0
        write_word(m_px + 4, 0)  # CursorRow = 0
        write_word(m_px + 5, 1)  # CursorVisible = 1
        
        print(f"DEBUG memory[208] = {memory[208]}")
        print(f"DEBUG memory[209] = {memory[209]}")
        
        # Search memory for 0x800006b7
        for i in range(len(memory)):
            val = int(memory[i, 0]) | (int(memory[i, 1]) << 8) | (int(memory[i, 2]) << 16) | (int(memory[i, 3]) << 24)
            if val == 0x800006b7 or val == 0x70068693:
                print(f"FOUND {hex(val)} at index {i} (addr {hex(0x80000000 + i*4)})")
                
        # Override AllocatePool pointer (offset 64 in BootServices)
        bs_px = 0x200 // 4
        write_word(bs_px + (64 // 4), 0x80000310)

        # Trampoline 1 at 0x80000300: Unhandled EFI (returns EFI_UNSUPPORTED)
        t_offset = 0x00000300
        t_pixel = t_offset // 4
        write_word(t_pixel, 0x157e557d)
        write_word(t_pixel + 1, 0x8082050d)
        
        # Trampoline 2 at 0x80000310: AllocatePool(PoolType a0, Size a1, Buffer** a2)
        # Previous version ecalled without moving Size into a0 or saving
        # Buffer** anywhere, and used FID=5 (WGSL only handles FID=1/2) - it
        # always fell through to SBI_ERR_NOT_SUPPORTED and never wrote back
        # an address, which is why the kernel synthesized its own
        # EFI_OUT_OF_RESOURCES. Rewritten to match handle_uefi_call's real
        # contract (FID=UEFI_ALLOCATE_POOL=1, size in a0) and to store the
        # allocated address into *Buffer before returning.
        #   mv   a3, a2                  ; save Buffer**
        #   mv   a0, a1                  ; a0 = Size
        #   lui  a7, 0x55454 ; addi a7,a7,0x649   ; a7 = SBI_EXT_UEFI
        #   addi a6, zero, 1             ; a6 = FID (UEFI_ALLOCATE_POOL)
        #   ecall                        ; a0=status, a1=address
        #   sd   a1, 0(a3)               ; *Buffer = address
        #   ret
        t2_offset = 0x00000310
        t2_pixel = t2_offset // 4
        write_word(t2_pixel, 0x00060693)
        write_word(t2_pixel + 1, 0x00058513)
        write_word(t2_pixel + 2, 0x554548b7)
        write_word(t2_pixel + 3, 0x64988893)
        write_word(t2_pixel + 4, 0x00100813)
        write_word(t2_pixel + 5, 0x00000073)
        write_word(t2_pixel + 6, 0x00b6b023)
        write_word(t2_pixel + 7, 0x00008067)

        # Trampoline 3 at 0x80000340: HandleProtocol
        # Handle(a0), Protocol GUID*(a1), Interface**(a2) -> EFI_STATUS a0
        # Pure RISC-V, no ecall: writes a fixed zeroed scratch pointer
        # (0x80000700) into *Interface and returns EFI_SUCCESS (0). The
        # caller (usually looking up LOADED_IMAGE_PROTOCOL) gets a non-null
        # interface whose fields all read as zero, which is enough to get
        # past the "protocol missing" abort path.
        #
        # Remove old HandleProtocol trampoline that collided with LocateProtocol in the EFI table

    # [4] Initialize GPU hardware
    print("\n[4] Initializing GPU...")
    ep = loader.entry_point
    cpu_state = make_cpu_state(ep, priv_mode=3)  # M-mode boot
    
    if is_pe32:
        # a0 = ImageHandle, a1 = SystemTable
        cpu_state[0]['regs'][10] = [0x80000000, 0]
        cpu_state[0]['regs'][11] = [0x80000000, 0]
        # Set stack pointer (sp/x2) to top of physical memory
        cpu_state[0]['regs'][2] = [0x87F00000, 0]
        # UEFI AllocatePool heap: below the stack, above kernel + fs.img
        UEFI_HEAP_BASE = 0x86000000
        UEFI_HEAP_SIZE = 8 * 1024 * 1024  # 8MB
        cpu_state[0]['uefi_heap_ptr'] = UEFI_HEAP_BASE
        cpu_state[0]['uefi_heap_end'] = UEFI_HEAP_BASE + UEFI_HEAP_SIZE
        print(f"    UEFI heap: 0x{UEFI_HEAP_BASE:08x} - 0x{UEFI_HEAP_BASE + UEFI_HEAP_SIZE:08x}")
    if init_state:
        from riscv_gpu_cpu import apply_init_state
        cpu_state = apply_init_state(cpu_state, init_state)
        print(f"    Applied initial state from {init_state}")
    # This is a PER-DISPATCH budget (the WGSL loop bound is exactly
    # max_instructions), not a lifetime total - a single dispatch runs to
    # completion before the host ever gets a chance to read UART output or
    # inject input, so it must be small enough that dispatches return
    # control frequently. At ~10 MIPS this is roughly 0.2s/dispatch.
    # When tracing, use max_instructions=1 for instruction-level granularity.
    if trace_file:
        max_instructions = 1
        print(f"    *** TRACE MODE: max_instructions=1, max_trace={trace_max}")
    else:
        max_instructions = 2_000_000

    harness = create_gpu_hardware(memory, cpu_state, max_instructions)
    device = harness['device']
    queue = harness['queue']

    print(f"    Device: {device.adapter.info['description']}")
    print(f"    Shader: tools/RISCV_CPU_MMU.wgsl")
    print(f"    Memory buffer: {pixel_count} words ({MEMORY_SIZE_MB // 2}MB)")
    print(f"    Initial gp (x3): 0x0x80001000")
    print(f"    CPU state: PC=0x{loader.entry_point:016x}, M-mode, MMU off")
    print(f"    Max instructions: {max_instructions}")

    # [6] Boot loop - infinite dispatch for autonomous execution
    print("\n[6] Booting xv6 on GPU...")
    if trace_file:
        print(f"    (1 instruction/dispatch, per-instruction trace mode)")
    else:
        print(f"    ({max_instructions // 1000000}M instructions/dispatch, infinite)")
    print(f"    Use Ctrl+C to stop gracefully")

    cpu_layout = cpu_state.dtype
    last_pc = 0
    stale_count = 0
    command_injected = False  # single-command mode: only ever inject once
    last_output_ptr = 0
    command_scan_start = 0
    pc_history = []
    iterations_since_injection = 0
    iteration = 0
    autonomous_turns_used = 0
    trace_out = None

    # Initialize trace output file if requested
    if trace_file:
        trace_out = open(trace_file, 'w')
        print(f"    Tracing per-instruction CPU state to {trace_file}")
        print(f"    Max trace instructions: {trace_max}")

    # Initialize CPU state variables for final readback
    cpu_readback = np.zeros(1, dtype=cpu_layout)
    pc = loader.entry_point
    running = 1
    instr_count = 0

    # Periodic UART dump: read & print the output buffer every N iterations
    # during the command grace period so we can monitor usertests progress.
    uart_dump_interval = 100       # every 100 iterations (~200M instructions)
    last_uart_dump_iter = 0

    try:
        while True:
            encoder = device.create_command_encoder()
            pass_enc = encoder.begin_compute_pass()
            pass_enc.set_pipeline(harness['pipeline'])
            pass_enc.set_bind_group(0, harness['bind_group'])
            pass_enc.dispatch_workgroups(1)
            pass_enc.end()
            queue.submit([encoder.finish()])
            
            if iteration == 0:
                print("DEBUG: Submitted first dispatch")

            # Read CPU state to check progress
            if iteration == 0:
                print("DEBUG: Calling read_buffer on cpu_buffer")
            cpu_readback_bytes = queue.read_buffer(harness['cpu_buffer'])
            if iteration == 0:
                print("DEBUG: Read cpu_buffer complete")
            cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=cpu_layout)
            pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
            running = int(cpu_readback['running'][0])
            instr_count = int(cpu_readback['instr_count'][0])
            timer_irq_count = int(cpu_readback['timer_interrupt_count'][0])
            total_irq_count = int(cpu_readback['total_interrupt_count'][0])

            # Write trace entry if tracing
            if trace_out is not None:
                regs = cpu_readback['regs'][0]
                regs_dict = {}
                for i in range(32):
                    regs_dict[f'x{i}'] = int((int(regs[i][1]) << 32) | int(regs[i][0]))
                regs_dict['pc'] = int(pc)
                regs_dict['mstatus'] = int((int(cpu_readback[0]['mstatus'][1]) << 32) | int(cpu_readback[0]['mstatus'][0]))
                regs_dict['mepc'] = int((int(cpu_readback[0]['mepc'][1]) << 32) | int(cpu_readback[0]['mepc'][0]))
                regs_dict['mcause'] = int((int(cpu_readback[0]['mcause'][1]) << 32) | int(cpu_readback[0]['mcause'][0]))
                trace_out.write(json.dumps({'pc': pc, 'instr_count': int(instr_count), 'regs': regs_dict}, 
                                      default=lambda o: int(o) if hasattr(o, 'dtype') else str(o)) + '\n')

            # Progress indicator (less frequent to not spam)
            if iteration % 1 == 0 or running == 0:
                ra = (int(cpu_readback['regs'][0][1][1]) << 32) | int(cpu_readback['regs'][0][1][0]); print(f"    Iter {iteration:5d}: PC=0x{pc:016x}, RA=0x{ra:016x}, instr={instr_count}, timer_irq={timer_irq_count}, total_irq={total_irq_count}")

            # Stall detection: track both interrupt flow and PC cycling
            pc_history.append(pc)
            if len(pc_history) > 2000:
                pc_history.pop(0)

            # Interrupt stall detection: if total_irq hasn't changed in 100 iterations,
            # capture diagnostic state - this is NOT a guest hang, it's an emulator bug
            if not hasattr(boot_xv6_on_gpu, 'last_total_irq'):
                boot_xv6_on_gpu.last_total_irq = total_irq_count
                boot_xv6_on_gpu.irq_stall_counter = 0

            if total_irq_count == boot_xv6_on_gpu.last_total_irq:
                boot_xv6_on_gpu.irq_stall_counter += 1
                # If we're not actually stalling, let it run
                if True:
                    pass
                elif boot_xv6_on_gpu.irq_stall_counter >= stall_threshold:
                    print(f"\n[!] INTERRUPT STALL DETECTED - interrupts frozen at {total_irq_count}")
                    print(f"    Last {len(set(pc_history[-20:]))} unique PCs in last 20 dispatches:")
                    for i, p in enumerate(pc_history[-20:]):
                        print(f"      [{i}] 0x{p:016x}")
                    # Read full CPU state for diagnosis
                    cpu_data = np.frombuffer(
                        dtype=cpu_layout
                    )
                    regs = cpu_data['regs'][0]
                    mstatus_val = int((int(cpu_data[0]['mstatus'][1]) << 32) | int(cpu_data[0]['mstatus'][0]))
                    mie_val = int((int(cpu_data[0]['mie'][1]) << 32) | int(cpu_data[0]['mie'][0]))
                    mip_val = int((int(cpu_data[0]['mip'][1]) << 32) | int(cpu_data[0]['mip'][0]))
                    plic_pending = int(cpu_data[0]['plic_pending'])
                    plic_enable = int(cpu_data[0]['plic_enable'])
                    print(f"    Current MSTATUS: 0x{mstatus_val:08x}")
                    print(f"    Current MIE: 0x{mie_val:08x}")
                    print(f"    Current MIP: 0x{mip_val:08x}")
                    print(f"    PLIC pending: 0x{plic_pending:08x}")
                    print(f"    PLIC enable:  0x{plic_enable:08x}")
                    print(f"    RA: 0x{int(regs[1][1]):08x}_{int(regs[1][0]):08x}")
                    print(f"    SP: 0x{int(regs[2][1]):08x}_{int(regs[2][0]):08x}")
                    print(f"    A0: 0x{int(regs[10][1]):08x}_{int(regs[10][0]):08x}")
                    print(f"    A1: 0x{int(regs[11][1]):08x}_{int(regs[11][0]):08x}")
                    break
            else:
                boot_xv6_on_gpu.last_total_irq = total_irq_count
                boot_xv6_on_gpu.irq_stall_counter = 0

            # PC cycling detection (ONLY after boot is established, iteration > 50)
            # 1000-sample window with < 5 unique addresses = genuine deadlock
            if iteration > 50 and len(pc_history) >= 1000:
                if len(set(pc_history[-1000:])) < 5:
                    print(f"\n[!] CPU PC stall detected (iter {iteration}) - cycling through {len(set(pc_history[-1000:]))} addresses:")
                    for i, p in enumerate(pc_history[-15:]):
                        print(f"    [{i}] 0x{p:016x}")
                    break

            # Periodic UART dump during command execution phase (after injection).
            # Read the output buffer every uart_dump_interval iterations and print
            # any new content so we can monitor long-running commands like usertests.
            if command_injected and running == 1 and iteration - last_uart_dump_iter >= uart_dump_interval:
                output_data = np.frombuffer(
                    device.queue.read_buffer(harness['output_buffer']),
                    dtype=np.uint8
                )
                output_str = ''
                for i in range(0, 16384, 4):
                    word = struct.unpack_from('<I', output_data[i:i+4])[0]
                    for b in word.to_bytes(4, 'little'):
                        if b == 0:
                            break
                        if 32 <= b < 127 or b == ord('\n') or b == ord('\r'):
                            output_str += chr(b)
                if len(output_str) > len(getattr(boot_xv6_on_gpu, 'last_out', '')):
                    new_portion = output_str[len(getattr(boot_xv6_on_gpu, 'last_out', '')):]
                    # Only print if there's substantial new content (avoid tiny dribbles)
                    if len(new_portion) > 10:
                        print(f"\n[UART @iter {iteration} ~{instr_count}B inst +{timer_irq_count}t {total_irq_count}irq]\n{new_portion}")
                    boot_xv6_on_gpu.last_out = output_str
                last_uart_dump_iter = iteration

            # Inject a command once a fresh "$ " prompt appears. Single-command
            # mode injects exactly once; autonomous mode re-arms after every
            # prompt and keeps going (up to autonomous_turns).
            ready_to_inject = (
                (command and not command_injected) or
                (autonomous and autonomous_turns_used < autonomous_turns)
            )
            if ready_to_inject and running == 1:
                if iteration == 0:
                    print("DEBUG: Calling read_buffer on output_buffer")
                output_data = np.frombuffer(
                    device.queue.read_buffer(harness['output_buffer']),
                    dtype=np.uint8
                )
                if iteration == 0:
                    print("DEBUG: Read output_buffer complete")
                output_str = ''
                for i in range(0, 16384, 4):
                    word = struct.unpack_from('<I', output_data[i:i+4])[0]
                    for b in word.to_bytes(4, 'little'):
                        if b == 0:
                            break
                        if 32 <= b < 127 or b == ord('\n') or b == ord('\r'):
                            output_str += chr(b)
                # Set last_out from the pre-injection read so periodic dumps
                # can track progress from here.
                boot_xv6_on_gpu.last_out = output_str
                if '$ ' in output_str[command_scan_start:]:
                    if autonomous:
                        recent = output_str[max(0, command_scan_start - 500):]
                        next_command = get_next_autonomous_command(recent, autonomous_model)
                        if not next_command:
                            print("\n[!] Ollama returned nothing usable, stopping autonomous mode.")
                            break
                        print(f"\n[Ollama #{autonomous_turns_used + 1}/{autonomous_turns}] "
                              f"{repr(next_command)}")
                        inject_command(queue, harness, cpu_layout, next_command)
                        autonomous_turns_used += 1
                        if autonomous_turns_used >= autonomous_turns:
                            # Last turn injected - give it a grace period to
                            # finish (matches the single-command path's own
                            # "up to 200 dispatches" allowance) then stop,
                            # rather than dispatching forever with nothing
                            # left that will ever get injected again.
                            iterations_since_injection = -200
                    else:
                        print(f"\n[!] Shell prompt detected, injecting command: {repr(command)}")
                        inject_command(queue, harness, cpu_layout, command)
                        command_injected = True
                        iterations_since_injection = -5000
                    print(f"[!] Command injected, resuming...")
                    # Update scan position to avoid re-detecting the same prompt
                    command_scan_start = len(output_str)

            if iterations_since_injection < 0:
                iterations_since_injection += 1
                if iterations_since_injection == 0:
                    print(f"\n[!] Final command had 200 dispatches to run, stopping.")
                    break

            if running == 0:
                print(f"\n[*] Guest CPU halted, stopping dispatch loop.")
                break

            # Trace mode cap
            if trace_out is not None and iteration >= trace_max:
                print(f"\n[*] Reached trace max ({trace_max} instructions), stopping.")
                break

            iteration += 1

    except KeyboardInterrupt:
        print(f"\n\n[!] Interrupted by user after {iteration} dispatches")
    except Exception as e:
        print(f"\n\n[!] Exception in dispatch loop: {e}")
        raise
    finally:
        if trace_out is not None:
            trace_out.close()
            print(f"  Trace closed ({iteration} entries written)")

    # Read output (UART console)
    print("\n[7] Reading UART console output...")
    output_data = np.frombuffer(
        device.queue.read_buffer(harness['output_buffer']),
        dtype=np.uint8
    )

    output_str = ''
    for i in range(4096, min(len(output_data), 4096 + 16384), 4):
        word = struct.unpack('<I', output_data[i:i+4])[0]
        for b in word.to_bytes(4, 'little'):
            if b == 0:
                break
            if 32 <= b < 127 or b == ord('\n') or b == ord('\r'):
                output_str += chr(b)

    print("\n" + "=" * 70)
    print("UART CONSOLE OUTPUT")
    print("=" * 70)
    print(output_str)

    # Print final CPU state
    print("=" * 70)
    regs = cpu_readback['regs'][0]
    print(f"ra: 0x{regs[1][1]:08x}_{regs[1][0]:08x} "
          f"a0: 0x{regs[10][1]:08x}_{regs[10][0]:08x} "
          f"a1: 0x{regs[11][1]:08x}_{regs[11][0]:08x} "
          f"a2: 0x{regs[12][1]:08x}_{regs[12][0]:08x}")
    print(f"Final PC: 0x{pc:016x}")
    print(f"Instructions executed: {instr_count}")
    print(f"CPU running: {running}")
    print("=" * 70)
    
    # Read output buffer for diagnostics
    output_read = device.queue.read_buffer(harness['output_buffer']).cast("I")
    diag_instr = output_read[0]
    diag_code = output_read[1]
    if diag_code == 0xBEEF:
        print(f"Diagnostic: ILLEGAL INSTRUCTION (0x{diag_instr:08x})")
    elif diag_code == 0xCAFE:
        print(f"Diagnostic: UNHANDLED M-TRAP")
    elif diag_code == 0xFACE:
        print(f"Diagnostic: UNHANDLED S-TRAP")
    else:
        print(f"Diagnostic Code: 0x{diag_code:08x}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Boot xv6-riscv on GPU RISC-V Emulator')
    parser.add_argument('kernel', help='Path to xv6 kernel ELF')
    parser.add_argument('--command', '-c', help='Single command to inject after shell prompt')
    parser.add_argument('--autonomous', action='store_true',
                        help='Drive the shell with Ollama-generated commands instead of --command')
    parser.add_argument('--autonomous-turns', type=int, default=20,
                        help='Max Ollama-driven commands to run (default: 20)')
    parser.add_argument('--autonomous-model', default='qwen2.5-coder:14b',
                        help='Ollama model tag for autonomous mode (default: qwen2.5-coder:14b)')
    parser.add_argument('--trace', metavar='FILE',
                        help='Capture per-instruction CPU state trace to FILE (JSONL format)')
    parser.add_argument('--trace-max', type=int, default=2000,
                        help='Max instructions to capture when tracing (default: 2000)')
    parser.add_argument('--init-state', metavar='JSON',
                        help='Load initial CPU state from QEMU-extracted JSON')
    parser.add_argument('--stall-threshold', type=int, default=100,
                        help='Dispatches with no IRQ-count change before treating '
                             'as a stall (default: 100; small payloads whose first '
                             'legitimate interrupt takes longer need this raised)')
    args = parser.parse_args()

    if args.autonomous and args.command:
        parser.error('--autonomous and --command are mutually exclusive')

    boot_xv6_on_gpu(args.kernel, args.command, args.autonomous,
                    args.autonomous_turns, args.autonomous_model,
                    args.trace, args.trace_max, args.init_state,
                    args.stall_threshold)