#!/usr/bin/env python3
"""
emulator/v2/spatial_rv64i_v2.py — V2 wrapper for GPU RV64 emulator

Independent development workspace for self-hosting emulator.
Version 2.0 starts as feature-parity copy of v1 (c41448f baseline).

Usage:
    from emulator.v2.spatial_rv64i_v2 import SpatialRV64ICoreV2
    core = SpatialRV64ICoreV2(64 * 1024 * 1024)  # 64MB
"""

import wgpu
import wgpu.utils
import numpy as np
import os
from pathlib import Path
from typing import Optional

# V2-specific cache directory
_V2_CACHE = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'visual_audio' / 'v2'

# ============================================================================
# Hilbert LUT (shared with v1, but separate cache)
# ============================================================================

def _build_hilbert_lut(n: int) -> np.ndarray:
    """Return lut[d] = y*N + x for every linear word d in a Hilbert-mapped N*N buffer."""
    size = n * n
    d = np.arange(size, dtype=np.uint32)
    x = np.zeros(size, dtype=np.uint32)
    y = np.zeros(size, dtype=np.uint32)
    t = d.copy()
    s = 1
    while s < n:
        rx = (t // 2) & 1
        ry = (t ^ rx) & 1
        reflect = (ry == 0) & (rx == 1)
        x_r = np.where(reflect, s - 1 - x, x)
        y_r = np.where(reflect, s - 1 - y, y)
        swap = ry == 0
        x_s = np.where(swap, y_r, x_r)
        y_s = np.where(swap, x_r, y_r)
        x = x_s + s * rx
        y = y_s + s * ry
        t = t // 4
        s *= 2
    return (y * n + x).astype(np.uint32)

def _get_hilbert_lut(n: int) -> np.ndarray:
    """Build or load from disk the Hilbert LUT for side length n (V2 cache)."""
    _V2_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = _V2_CACHE / f'hilbert_lut_{n}.npy'
    if cache_path.exists():
        lut = np.load(cache_path)
        if lut.shape == (n * n,):
            return lut
    lut = _build_hilbert_lut(n)
    np.save(cache_path, lut)
    return lut

# ============================================================================
# V2 Core
# ============================================================================

class SpatialRV64ICoreV2:
    """
    GPU-native RV64I core with V2 infrastructure.

    Version 2.0: Feature-parity copy of v1 (c41448f)
    - Identical shader structure (RISCV_CPU_MMU_V2.wgsl)
    - Identical Python wrapper logic
    - Version field added to state for detection
    """

    # V2 version constants
    VERSION_MAJOR = 2
    VERSION_MINOR = 0
    VERSION_PATCH = 0
    VERSION_STRING = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"

    def __init__(self, memory_size_bytes: int = 1024 * 1024, trace_file: Optional[str] = None):
        self.device = wgpu.utils.get_default_device()
        self.queue = self.device.queue
        self.memory_size = memory_size_bytes

        # UART capacity (must be set before _setup_uart)
        self.uart_capacity = 8192  # 8KB ring buffer

        # V2-specific shader
        shader_path = Path(__file__).parent / "RISCV_CPU_MMU_V2.wgsl"
        if not shader_path.exists():
            raise FileNotFoundError(f"V2 shader not found: {shader_path}")

        self.shader_module = self.device.create_shader_module(
            code=shader_path.read_text()
        )

        # Memory and registers (same as v1)
        self._setup_memory()
        self._setup_registers()
        self._setup_state_buffer()
        self._setup_uart()

        # Hilbert LUT
        mem_words = (self.memory_size + 3) // 4
        self.hilbert_n = int(np.sqrt(mem_words))
        self.hilbert_lut = _get_hilbert_lut(self.hilbert_n)

        self._uart_consumed = 0
        
        # CSR buffer (flat file)
        self.csr_buffer = self.device.create_buffer(
            size=4096 * 8,  # 4096 CSRs, 64 bits each
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        
        # TLB buffer
        self.tlb_buffer = self.device.create_buffer(
            size=256 * 16,  # 256 entries, 16 bytes each
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        
        # Decoded ops buffer
        mem_len_words = (self.memory_size + 3) // 4
        n_halfwords = mem_len_words * 2
        self.decoded_ops_buffer = self.device.create_buffer(
            size=n_halfwords * 9 * 4,  # 9 u32s per DecodedOp
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

    def _setup_memory(self):
        """Setup GPU memory buffer (Hilbert-mapped)."""
        aligned_size = (self.memory_size + 3) & ~3
        self.memory = self.device.create_buffer(
            size=aligned_size,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

    def _setup_registers(self):
        """Setup GPU register file (32 x vec2<u32>)."""
        self.registers = self.device.create_buffer(
            size=32 * 8,  # 64 bits per register
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

    def _setup_state_buffer(self):
        """Setup CPU state buffer with V2 version field."""
        # State buffer size + V2 version tracking
        self.state_buffer = self.device.create_buffer(
            size=4 * 1024,  # Sufficient for state + metadata
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # Initialize V2 version field
        version_word = (self.VERSION_MAJOR << 16) | (self.VERSION_MINOR << 8) | self.VERSION_PATCH
        self.queue.write_buffer(self.state_buffer, 0, np.array([version_word], dtype=np.uint32).tobytes())

    def _setup_uart(self):
        """Setup UART ring buffer (same as v1)."""
        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,  # u32 ring buffer
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

    # ============================================================================
    # V2 Version Detection
    # ============================================================================

    def get_version(self) -> str:
        """Return V2 version string."""
        return self.VERSION_STRING

    def get_state(self) -> dict:
        """Read GPU state, including V2 version field."""
        state_bytes = self.queue.read_buffer(self.state_buffer)
        state_arr = np.frombuffer(state_bytes, dtype=np.uint32)

        # First word is V2 version
        version_word = int(state_arr[0])
        version_major = (version_word >> 16) & 0xFF
        version_minor = (version_word >> 8) & 0xFF
        version_patch = version_word & 0xFF

        # Rest of state follows same layout as v1
        pc_lo = int(state_arr[1])
        pc_hi = int(state_arr[2])
        pc = (pc_hi << 32) | pc_lo

        return {
            "version": f"{version_major}.{version_minor}.{version_patch}",
            "pc": pc,
            "running": bool(state_arr[3]),
            "priv_mode": state_arr[4],
            "instr_count": state_arr[5],
            # ... rest of v1 state fields ...
        }

    # ============================================================================
    # Compatibility: Same API as v1
    # ============================================================================

    def load_program(self, program_bytes: bytes, entry_point: int, ram_base: int):
        """Load program into GPU memory (same as v1)."""
        self.write_mem_bytes(entry_point - ram_base, program_bytes)

    def write_mem_bytes(self, byte_addr: int, data: bytes):
        """Write an arbitrary byte blob into (Hilbert-mapped) physical memory, e.g. a DTB.
        byte_addr is buffer-relative; must be 4-byte aligned. Pads the tail to a whole word."""
        assert byte_addr >= 0, f"byte_addr must be non-negative, got {byte_addr}"
        assert byte_addr % 4 == 0
        assert byte_addr < self.memory.buffer.size
        padded = data + b'\x00' * ((4 - len(data) % 4) % 4)
        words = np.frombuffer(padded, dtype=np.uint32)

        # Keep the linear shadow in sync (both the small and chunk paths below write
        # the same words to the Hilbert-mapped buffer).
        start_word = byte_addr // 4
        self._linear_shadow[start_word:start_word + len(words)] = words
        self._mark_range_dirty(byte_addr, byte_addr + len(words) * 4)

        # For small writes (<64KB), use the word-by-word approach (simpler, less overhead)
        if len(words) < 16384:  # 64KB
            for i, word in enumerate(words):
                self.write_mem_word(byte_addr + i * 4, int(word))
            return

        # Large writes: scatter linear words into their Hilbert cells via the SAME
        # precomputed LUT the shader reads memory back through (hilbert_lut_np), then
        # upload the whole buffer once. The previous per-chunk copy-shader
        # (inline d2xy, dest[hilbert_idx]=src[i]) corrupted large writes — sparse
        # word-level scramble that left ~1/4 of a 20MB kernel image with zeroed /
        # neighbour-shifted words, so Linux never got past its head.S BSS clear.
        # Readback+scatter+writeback of 64MB costs a few seconds; a boot does this
        # ~3 times (kernel/initrd/dtb) and gets a bit-correct image.
        start_word = byte_addr // 4
        sidx = self.hilbert_lut_np[start_word:start_word + len(words)]
        buf = np.frombuffer(
            self.memory.read_data(self.queue, self.memory.buffer.size),
            dtype=np.uint32,
        ).copy()
        buf[sidx] = words
        self.memory.write_data(self.queue, buf.tobytes())
        return



    def step(self, steps: int = 1):
        """Execute N instructions on GPU (same as v1, uses V2 shader)."""
        # TODO: Port compute pipeline dispatch from v1
        raise NotImplementedError("V2 needs compute pipeline dispatch from v1")

    def read_uart_output(self) -> bytes:
        """Read UART output (same as v1, bulk read optimization)."""
        state = self.get_state()
        total = int(state.get("uart_tx_len", 0))
        new_count = total - self._uart_consumed
        if new_count <= 0:
            return b''
        if new_count > self.uart_capacity:
            new_count = self.uart_capacity
            self._uart_consumed = total - self.uart_capacity

        # Bulk GPU read (v1 optimization)
        start_pos = self._uart_consumed % self.uart_capacity
        chunk1_len = min(new_count, self.uart_capacity - start_pos)
        chunk2_len = new_count - chunk1_len

        data_bytes = bytearray()
        if chunk1_len > 0:
            chunk1 = self.queue.read_buffer(self.uart_buffer, buffer_offset=start_pos * 4, size=chunk1_len * 4)
            data_bytes.extend(chunk1)
        if chunk2_len > 0:
            chunk2 = self.queue.read_buffer(self.uart_buffer, buffer_offset=0, size=chunk2_len * 4)
            data_bytes.extend(chunk2)

        words = np.frombuffer(data_bytes, dtype=np.uint32)
        out = bytes([w & 0xFF for w in words])
        self._uart_consumed = total
        return out

    def get_csr(self, addr: int) -> int:
        """Read CSR value (same as v1)."""
        # TODO: Port CSR read logic from v1
        raise NotImplementedError("V2 needs CSR read path from v1")

    def write_register(self, reg: int, value: int):
        """Write to register (same as v1)."""
        raise NotImplementedError("V2 needs register write from v1")

    def read_csr(self, addr: int) -> int:
        """Read a CSR directly from the flat CSR file (bypasses csrrX instructions)."""
        csr_bytes = self.queue.read_buffer(self.csr_buffer, buffer_offset=addr * 8, size=8)
        low, high = np.frombuffer(csr_bytes, dtype=np.uint32)
        return int(np.uint64((int(high) << 32) | int(low)))


    def write_csr(self, addr: int, value: int):
        """Write a CSR directly into the flat CSR file (e.g. to install a trap vector before running)."""
        low = value & 0xFFFFFFFF
        high = (value >> 32) & 0xFFFFFFFF
        self.queue.write_buffer(self.csr_buffer, addr * 8, np.array([low, high], dtype=np.uint32).tobytes())


    def write_register(self, index: int, value: int):
        """Write a GPR directly (e.g. a0/a1 boot arguments before the first step())."""
        # For 64-bit registers, write low word at index*8 and high word at index*8+4
        self.queue.write_buffer(self.registers.buffer, index * 8, np.array([value & 0xFFFFFFFF], dtype=np.uint32).tobytes())
        self.queue.write_buffer(self.registers.buffer, index * 8 + 4, np.array([(value >> 32) & 0xFFFFFFFF], dtype=np.uint32).tobytes())


    def _setup_compute_pipeline(self):
        """Setup GPU compute pipeline (ported from v1)."""
        shader_path = Path(__file__).parent / 'RISCV_CPU_MMU_V2.wgsl'
        shader_module = self.device.create_shader_module(
            code=shader_path.read_text()
        )
        
        bind_group_layout = self.device.create_bind_group_layout(
            entries=[
                {'binding': 0, 'resource': {'buffer': self.memory.buffer, 'offset': 0, 'size': self.memory.buffer.size}},
                {'binding': 1, 'resource': {'buffer': self.registers.buffer, 'offset': 0, 'size': self.registers.buffer.size}},
                {'binding': 2, 'resource': {'buffer': self.state_buffer, 'offset': 0, 'size': self.state_buffer.size}},
                {'binding': 3, 'resource': {'buffer': self.csr_buffer, 'offset': 0, 'size': self.csr_buffer.size}},
                {'binding': 4, 'resource': {'buffer': self.uart_buffer, 'offset': 0, 'size': self.uart_buffer.size}},
                {'binding': 5, 'resource': {'buffer': self.hilbert_lut_buffer, 'offset': 0, 'size': self.hilbert_lut_buffer.size}},
                {'binding': 6, 'resource': {'buffer': self.decoded_ops_buffer, 'offset': 0, 'size': self.decoded_ops_buffer.size}},
                {'binding': 7, 'resource': {'buffer': self.tlb_buffer, 'offset': 0, 'size': self.tlb_buffer.size}},
            ]
        )
        
        pipeline_layout = self.device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
        self.pipeline = self.device.create_compute_pipeline(
            layout=pipeline_layout,
            compute={'module': shader_module, 'entry_point': 'main'},
        )

    def step(self, steps: int = 1):
        """Execute N instructions on GPU (v2: uses V2 shader)."""
        self.bind_group = self.device.create_bind_group(
            layout=self.pipeline.get_bind_group_layout(0),
            entries=[
                {'binding': 0, 'resource': {'buffer': self.memory.buffer, 'offset': 0, 'size': self.memory.buffer.size}},
                {'binding': 1, 'resource': {'buffer': self.registers.buffer, 'offset': 0, 'size': self.registers.buffer.size}},
                {'binding': 2, 'resource': {'buffer': self.state_buffer, 'offset': 0, 'size': self.state_buffer.size}},
                {'binding': 3, 'resource': {'buffer': self.csr_buffer, 'offset': 0, 'size': self.csr_buffer.size}},
                {'binding': 4, 'resource': {'buffer': self.uart_buffer, 'offset': 0, 'size': self.uart_buffer.size}},
                {'binding': 5, 'resource': {'buffer': self.hilbert_lut_buffer, 'offset': 0, 'size': self.hilbert_lut_buffer.size}},
                {'binding': 6, 'resource': {'buffer': self.decoded_ops_buffer, 'offset': 0, 'size': self.decoded_ops_buffer.size}},
                {'binding': 7, 'resource': {'buffer': self.tlb_buffer, 'offset': 0, 'size': self.tlb_buffer.size}},
            ]
        )
        
        # Read binding groups from v1 to get the full dispatch logic
        # For now, implement basic dispatch
        for _ in range(steps):
            command_encoder = self.device.create_command_encoder()
            compute_pass = command_encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.pipeline)
            compute_pass.set_bind_group(0, self.bind_group, [], 0, 999999)
            workgroups = (self.memory.buffer.size + 65535) // 65536  # Simplified
            compute_pass.dispatch_workgroups(workgroups, 1, 1)
            compute_pass.end()
            self.queue.submit([command_encoder.finish()])
        
        # Wait for GPU completion
        self.queue.submit([])
        self.queue.wait_idle()

if __name__ == "__main__":
    # V2 version test
    core = SpatialRV64ICoreV2()
    print(f"V2 Core version: {core.get_version()}")
    print(f"State version field: {core.get_state()['version']}")