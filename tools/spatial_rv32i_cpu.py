import wgpu
import wgpu.utils
import numpy as np
from pathlib import Path
from typing import Optional

class MemoryRegion:
    """
    GPU-resident, Hilbert-ordered memory region for spatial computation.
    """
    def __init__(self, device: wgpu.GPUDevice, size_bytes: int):
        self.size_bytes = size_bytes
        # Ensure size is aligned to 4 bytes for u32 array
        aligned_size = (size_bytes + 3) & ~3
        self.buffer = device.create_buffer(
            size=aligned_size,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        
    def write_data(self, queue: wgpu.GPUQueue, data: bytes, offset: int = 0):
        queue.write_buffer(self.buffer, offset, data)
        
    def read_data(self, queue: wgpu.GPUQueue, size: int, offset: int = 0) -> bytes:
        return queue.read_buffer(self.buffer, buffer_offset=offset, size=size)

class RegisterFile:
    """
    32 x 32-bit GPU memory representing RV32I registers.
    """
    def __init__(self, device: wgpu.GPUDevice):
        self.buffer = device.create_buffer(
            size=32 * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

class SpatialRV32ICore:
    """
    GPU-native RV32I core without CPU-side instruction emulation.
    """
    def __init__(self, memory_size_bytes: int = 1024 * 1024, trace_file: Optional[str] = None):
        self.device = wgpu.utils.get_default_device()
        self.queue = self.device.queue

        self.memory = MemoryRegion(self.device, memory_size_bytes)
        self.registers = RegisterFile(self.device)

        # CPUState struct: [pc, halted, steps_remaining, mode, trap_pending,
        #                    reservation_valid, reservation_addr, uart_tx_len,
        #                    mtime, mtimecmp, ram_base, uart_rx_data_pending, uart_rx_byte]
        self.state_buffer = self.device.create_buffer(
            size=52, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # Flat CSR file, addressed directly by the 12-bit CSR index (array<u32, 4096>)
        self.csr_buffer = self.device.create_buffer(
            size=4096 * 4, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # UART TX ring buffer: one byte per u32 slot (array<u32, 4096>)
        self.uart_capacity = 4096
        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        self._uart_consumed = 0

        self.pipeline = None
        self.bind_group = None
        self._init_pipeline()

        # Optional trace file for diff_qemu_gpu_traces.py
        self.trace_file = trace_file
        self.trace_fd = None
        if trace_file:
            self.trace_fd = open(trace_file, 'w')

    def __del__(self):
        if self.trace_fd:
            self.trace_fd.close()

    def _trace_state(self, pc, regs):
        if not self.trace_fd:
            return

        import json
        entry = {
            'pc': int(pc),
            'regs': {f'x{i}': int(regs[i]) for i in range(32)},
        }
        self.trace_fd.write(json.dumps(entry) + '\n')
        self.trace_fd.flush()  # Ensure immediate write for debugging
        
    def _init_pipeline(self):
        """Load SPATIAL_RV32I.wgsl and initialize pipeline"""
        shader_path = Path(__file__).parent / 'SPATIAL_RV32I.wgsl'
        shader_code = shader_path.read_text()
        
        shader_module = self.device.create_shader_module(code=shader_code)
        
        bind_group_layout = self.device.create_bind_group_layout(entries=[
            {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        ])

        self.bind_group = self.device.create_bind_group(
            layout=bind_group_layout,
            entries=[
                {'binding': 0, 'resource': {'buffer': self.memory.buffer, 'offset': 0, 'size': self.memory.buffer.size}},
                {'binding': 1, 'resource': {'buffer': self.registers.buffer, 'offset': 0, 'size': self.registers.buffer.size}},
                {'binding': 2, 'resource': {'buffer': self.state_buffer, 'offset': 0, 'size': self.state_buffer.size}},
                {'binding': 3, 'resource': {'buffer': self.csr_buffer, 'offset': 0, 'size': self.csr_buffer.size}},
                {'binding': 4, 'resource': {'buffer': self.uart_buffer, 'offset': 0, 'size': self.uart_buffer.size}},
            ]
        )
        
        pipeline_layout = self.device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
        self.pipeline = self.device.create_compute_pipeline(
            layout=pipeline_layout,
            compute={'module': shader_module, 'entry_point': 'main'},
        )
        
    def _d2xy(self, n: int, d: int):
        t = d
        x = 0
        y = 0
        s = 1
        while s < n:
            rx = (t // 2) & 1
            ry = (t ^ rx) & 1
            if ry == 0:
                if rx == 1:
                    x = s - 1 - x
                    y = s - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            t //= 4
            s *= 2
        return x, y
        
    def load_asm(self, source: str, entry_point: int = 0):
        """Assemble RV32I source and load it, preserving Hilbert mapping."""
        from rv32i_asm import assemble
        self.load_program(assemble(source), entry_point)

    def load_program(self, binary_data: bytes, entry_point: int = 0, ram_base: int = 0):
        """Load binary into memory and set PC, preserving Hilbert mapping.

        `ram_base` is the guest physical address that maps to word 0 of our memory buffer
        (word 0 of the Hilbert-mapped array corresponds to guest address ram_base). Bare-metal
        test programs use the default of 0; a real kernel image (e.g. one linked to run at
        0x80000000) should pass that as ram_base, with entry_point given as an absolute guest
        address >= ram_base.
        """
        # Convert to u32 array
        # Pad with 0 to make it multiple of 4
        padded_data = binary_data + b'\x00' * ((4 - len(binary_data) % 4) % 4)
        linear_arr = np.frombuffer(padded_data, dtype=np.uint32)

        # Create full VRAM array
        mem_len = self.memory.buffer.size // 4
        spatial_arr = np.zeros(mem_len, dtype=np.uint32)

        # N = sqrt(mem_len)
        N = int(np.sqrt(mem_len))
        if N * N != mem_len:
            raise ValueError("Memory length must be a perfect square for Hilbert mapping")

        for i, val in enumerate(linear_arr):
            x, y = self._d2xy(N, i)
            idx = y * N + x
            spatial_arr[idx] = val

        self.memory.write_data(self.queue, spatial_arr.tobytes())

        # Reset state (PC=entry_point, halted=0, steps_remaining=0, mode=Machine,
        # trap_pending=0, reservation_valid=0, reservation_addr=0, uart_tx_len=0,
        # mtime=0, mtimecmp=0, ram_base=ram_base, uart_rx_data_pending=0, uart_rx_byte=0)
        state_data = np.array(
            [entry_point, 0, 0, 3, 0, 0, 0, 0, 0, 0, ram_base, 0, 0], dtype=np.uint32
        ).tobytes()
        self.queue.write_buffer(self.state_buffer, 0, state_data)

        # Reset CSRs so state doesn't leak across program loads on a reused core
        self.queue.write_buffer(self.csr_buffer, 0, np.zeros(4096, dtype=np.uint32).tobytes())
        self._uart_consumed = 0

        # Trace initial state
        self._trace_state(entry_point, np.zeros(32, dtype=np.uint32))
        
    def get_state(self) -> dict:
        state_bytes = self.queue.read_buffer(self.state_buffer)
        state_arr = np.frombuffer(state_bytes, dtype=np.uint32)
        
        regs_bytes = self.queue.read_buffer(self.registers.buffer)
        regs_arr = np.frombuffer(regs_bytes, dtype=np.uint32)
        
        return {
            'pc': state_arr[0],
            'halted': state_arr[1],
            'steps_remaining': state_arr[2],
            'mode': state_arr[3],
            'trap_pending': state_arr[4],
            'reservation_valid': state_arr[5],
            'reservation_addr': state_arr[6],
            'uart_tx_len': state_arr[7],
            'mtime': state_arr[8],
            'mtimecmp': state_arr[9],
            'ram_base': state_arr[10],
            'uart_rx_data_pending': state_arr[11],
            'uart_rx_byte': state_arr[12],
            'regs': regs_arr
        }

    def read_uart_output(self) -> bytes:
        """Drain bytes written to the UART TX MMIO register since the last call."""
        state = self.get_state()
        total = int(state['uart_tx_len'])
        new_count = total - self._uart_consumed
        if new_count <= 0:
            return b''
        if new_count > self.uart_capacity:
            # Backlog overran the ring buffer since the last drain; only the most
            # recent uart_capacity bytes are still recoverable.
            new_count = self.uart_capacity
            self._uart_consumed = total - self.uart_capacity

        out = bytearray()
        for i in range(new_count):
            pos = (self._uart_consumed + i) % self.uart_capacity
            data = self.queue.read_buffer(self.uart_buffer, buffer_offset=pos * 4, size=4)
            out.append(int(np.frombuffer(data, dtype=np.uint32)[0]) & 0xFF)
        self._uart_consumed = total
        return bytes(out)

    def write_uart_input(self, data: bytes):
        """Feed bytes into the UART RX FIFO. Non-blocking: each byte overwrites the previous one."""
        for byte in data:
            # Write uart_rx_data_pending=1, uart_rx_byte=byte at offset 11 and 12
            self.queue.write_buffer(self.state_buffer, 11 * 4, np.array([1], dtype=np.uint32).tobytes())
            self.queue.write_buffer(self.state_buffer, 12 * 4, np.array([byte & 0xFF], dtype=np.uint32).tobytes())

    def write_mem_word(self, byte_addr: int, value: int):
        """Write a single word directly into (Hilbert-mapped) physical memory, e.g. to build page tables.
        byte_addr is buffer-relative (word 0 == guest ram_base), not a guest address."""
        mem_len = self.memory.buffer.size // 4
        N = int(np.sqrt(mem_len))
        x, y = self._d2xy(N, byte_addr // 4)
        idx = y * N + x
        self.queue.write_buffer(self.memory.buffer, idx * 4, np.array([value], dtype=np.uint32).tobytes())

    def write_mem_bytes(self, byte_addr: int, data: bytes):
        """Write an arbitrary byte blob into (Hilbert-mapped) physical memory, e.g. a DTB.
        byte_addr is buffer-relative; must be 4-byte aligned. Pads the tail to a whole word."""
        assert byte_addr % 4 == 0
        padded = data + b'\x00' * ((4 - len(data) % 4) % 4)
        words = np.frombuffer(padded, dtype=np.uint32)
        for i, word in enumerate(words):
            self.write_mem_word(byte_addr + i * 4, int(word))

    def write_register(self, index: int, value: int):
        """Write a GPR directly (e.g. a0/a1 boot arguments before the first step())."""
        self.queue.write_buffer(self.registers.buffer, index * 4, np.array([value], dtype=np.uint32).tobytes())

    def read_mem_word(self, byte_addr: int) -> int:
        """Read a single word directly from (Hilbert-mapped) physical memory."""
        mem_len = self.memory.buffer.size // 4
        N = int(np.sqrt(mem_len))
        x, y = self._d2xy(N, byte_addr // 4)
        idx = y * N + x
        data = self.queue.read_buffer(self.memory.buffer, buffer_offset=idx * 4, size=4)
        return int(np.frombuffer(data, dtype=np.uint32)[0])

    def read_csr(self, addr: int) -> int:
        """Read a CSR directly from the flat CSR file (bypasses csrrX instructions)."""
        csr_bytes = self.queue.read_buffer(self.csr_buffer, buffer_offset=addr * 4, size=4)
        return int(np.frombuffer(csr_bytes, dtype=np.uint32)[0])

    def write_csr(self, addr: int, value: int):
        """Write a CSR directly into the flat CSR file (e.g. to install a trap vector before running)."""
        self.queue.write_buffer(self.csr_buffer, addr * 4, np.array([value], dtype=np.uint32).tobytes())

    def step(self, steps: int = 1):
        """Execute `steps` instructions in a single WGSL dispatch"""
        # First, read the current state to preserve PC and halted status
        state = self.get_state()

        # Write state with the requested number of steps
        state_data = np.array([
            state['pc'], state['halted'], steps, state['mode'], state['trap_pending'],
            state['reservation_valid'], state['reservation_addr'], state['uart_tx_len'],
            state['mtime'], state['mtimecmp'], state['ram_base'],
        ], dtype=np.uint32).tobytes()
        self.queue.write_buffer(self.state_buffer, 0, state_data)

        encoder = self.device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.pipeline)
        compute_pass.set_bind_group(0, self.bind_group)
        compute_pass.dispatch_workgroups(1)
        compute_pass.end()
        self.queue.submit([encoder.finish()])

        # Trace the new state after execution
        new_state = self.get_state()
        self._trace_state(new_state['pc'], new_state['regs'])

    def set_mode(self, mode: int):
        """Force the privilege mode directly (test/debug helper — real code should reach a
        given mode via mret/sret/traps, not this)."""
        self.queue.write_buffer(self.state_buffer, 3 * 4, np.array([mode], dtype=np.uint32).tobytes())

    def run_until_halt(self, max_cycles: int = 100_000, chunk_size: int = 256) -> dict:
        """
        Dispatch batched compute passes (each running up to `chunk_size`
        instructions inside the shader's inner loop) until the CPU halts or
        max_cycles is exhausted. Returns the final state; raises TimeoutError
        if the program never halts within max_cycles.

        Legacy SBI ecalls (console putchar, set timer) are serviced natively inside
        the GPU shader itself (see SPATIAL_RV32I.wgsl's ecall handling) and never halt
        execution, so they need no special handling here.
        """
        cycles_run = 0
        while cycles_run < max_cycles:
            n = min(chunk_size, max_cycles - cycles_run)
            self.step(steps=n)
            cycles_run += n

            state = self.get_state()
            if state['halted']:
                return state

        raise TimeoutError(f"Program did not halt within {max_cycles} cycles")

    def run_program(self, source: str, entry_point: int = 0,
                     max_cycles: int = 100_000, chunk_size: int = 256) -> dict:
        """Assemble, load, and run RV32I source to completion. Returns final state."""
        self.load_asm(source, entry_point)
        return self.run_until_halt(max_cycles=max_cycles, chunk_size=chunk_size)

if __name__ == "__main__":
    print("Testing SpatialRV32ICore initialization...")
    core = SpatialRV32ICore(1024)
    print("✓ Pipeline initialized successfully")
