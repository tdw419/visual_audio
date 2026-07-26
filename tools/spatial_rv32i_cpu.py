import wgpu
import wgpu.utils
import numpy as np
from pathlib import Path

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
    def __init__(self, memory_size_bytes: int = 1024 * 1024):
        self.device = wgpu.utils.get_default_device()
        self.queue = self.device.queue
        
        self.memory = MemoryRegion(self.device, memory_size_bytes)
        self.registers = RegisterFile(self.device)
        
        # CPUState struct: [pc (u32), halted (u32)]
        self.state_buffer = self.device.create_buffer(
            size=12, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
        
        self.pipeline = None
        self.bind_group = None
        self._init_pipeline()
        
    def _init_pipeline(self):
        """Load SPATIAL_RV32I.wgsl and initialize pipeline"""
        shader_path = Path(__file__).parent / 'SPATIAL_RV32I.wgsl'
        shader_code = shader_path.read_text()
        
        shader_module = self.device.create_shader_module(code=shader_code)
        
        bind_group_layout = self.device.create_bind_group_layout(entries=[
            {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        ])
        
        self.bind_group = self.device.create_bind_group(
            layout=bind_group_layout,
            entries=[
                {'binding': 0, 'resource': {'buffer': self.memory.buffer, 'offset': 0, 'size': self.memory.buffer.size}},
                {'binding': 1, 'resource': {'buffer': self.registers.buffer, 'offset': 0, 'size': self.registers.buffer.size}},
                {'binding': 2, 'resource': {'buffer': self.state_buffer, 'offset': 0, 'size': self.state_buffer.size}},
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

    def load_program(self, binary_data: bytes, entry_point: int = 0):
        """Load binary into memory and set PC, preserving Hilbert mapping"""
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
        
        # Reset state (PC=entry_point, halted=0, steps_remaining=0)
        state_data = np.array([entry_point, 0, 0], dtype=np.uint32).tobytes()
        self.queue.write_buffer(self.state_buffer, 0, state_data)
        
    def get_state(self) -> dict:
        state_bytes = self.queue.read_buffer(self.state_buffer)
        state_arr = np.frombuffer(state_bytes, dtype=np.uint32)
        
        regs_bytes = self.queue.read_buffer(self.registers.buffer)
        regs_arr = np.frombuffer(regs_bytes, dtype=np.uint32)
        
        return {
            'pc': state_arr[0],
            'halted': state_arr[1],
            'steps_remaining': state_arr[2],
            'regs': regs_arr
        }
        
    def step(self, steps: int = 1):
        """Execute `steps` instructions in a single WGSL dispatch"""
        # First, read the current state to preserve PC and halted status
        state = self.get_state()
        
        # Write state with the requested number of steps
        state_data = np.array([state['pc'], state['halted'], steps], dtype=np.uint32).tobytes()
        self.queue.write_buffer(self.state_buffer, 0, state_data)
        
        encoder = self.device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.pipeline)
        compute_pass.set_bind_group(0, self.bind_group)
        compute_pass.dispatch_workgroups(1)
        compute_pass.end()
        self.queue.submit([encoder.finish()])

    def run_until_halt(self, max_cycles: int = 100_000, chunk_size: int = 256) -> dict:
        """
        Dispatch batched compute passes (each running up to `chunk_size`
        instructions inside the shader's inner loop) until the CPU halts or
        max_cycles is exhausted. Returns the final state; raises TimeoutError
        if the program never halts within max_cycles.
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
