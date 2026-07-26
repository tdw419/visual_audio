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
            size=8,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
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
        
    def load_program(self, binary_data: bytes, entry_point: int = 0):
        """Load binary into memory and set PC"""
        self.memory.write_data(self.queue, binary_data)
        
        # Reset state (PC=entry_point, halted=0)
        state_data = np.array([entry_point, 0], dtype=np.uint32).tobytes()
        self.queue.write_buffer(self.state_buffer, 0, state_data)
        
    def get_state(self) -> dict:
        state_bytes = self.queue.read_buffer(self.state_buffer)
        state_arr = np.frombuffer(state_bytes, dtype=np.uint32)
        
        regs_bytes = self.queue.read_buffer(self.registers.buffer)
        regs_arr = np.frombuffer(regs_bytes, dtype=np.uint32)
        
        return {
            'pc': state_arr[0],
            'halted': state_arr[1],
            'regs': regs_arr
        }
        
    def step(self):
        """Dispatch a single compute pass"""
        encoder = self.device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.pipeline)
        compute_pass.set_bind_group(0, self.bind_group)
        compute_pass.dispatch_workgroups(1)
        compute_pass.end()
        self.queue.submit([encoder.finish()])

if __name__ == "__main__":
    print("Testing SpatialRV32ICore initialization...")
    core = SpatialRV32ICore(1024)
    print("✓ Pipeline initialized successfully")
