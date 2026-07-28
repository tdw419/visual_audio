# runtime/core/minimal_host.py
# Minimal Python host - just launches WGSL shaders

import wgpu
import numpy as np
import time
import struct
import sys

# Define VRAM_SIZE (must match WGSL shader)
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
VRAM_SIZE = SCREEN_WIDTH * SCREEN_HEIGHT

class MinimalPixelOSHost:
    def __init__(self):
        print("🎯 MINIMAL PIXEL OS HOST - SHADER SUBSTRATE LAUNCHER")
        
        # Initialize WebGPU
        self.device = wgpu.utils.get_default_device()
        self.queue = self.device.queue
        
        # Load core substrate shaders
        self.shaders = {
            'substrate': self._load_shader('runtime/core/substrate.wgsl'),
            'x86_emulator': self._load_shader('runtime/core/x86_emulator.wgsl'),
            'inter_shader_comms': self._load_shader('runtime/core/inter_shader_comms.wgsl'),
            'rendering_pipeline': self._load_shader('runtime/core/rendering_pipeline.wgsl'),
            'network_shader': self._load_shader('runtime/services/network_shader.wgsl'),
            'network_integration': self._load_shader('runtime/core/network_integration.wgsl'),
            'filesystem_shader': self._load_shader('runtime/services/filesystem_shader.wgsl'),
        }
        
        # Create shared memory buffers
        self.shared_buffers = self._create_shared_buffers()
        
        # Create font texture and upload dummy data
        self.font_texture = self.device.create_texture(
            size=(256, 256, 1), format=wgpu.TextureFormat.r8unorm,
            usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST
        )
        dummy_font_data = np.random.randint(0, 255, size=(256, 256), dtype=np.uint8)
        self.queue.write_texture(
            {"texture": self.font_texture},
            dummy_font_data.T.flatten(), # Transpose and flatten for wgpu
            {"bytes_per_row": 256},
            self.font_texture.size,
        )

        # Create bind groups
        self.bind_groups = self._create_bind_groups()
        
        print("✅ PIXEL OS SUBSTRATE: WGSL SHADERS LOADED AND BUFFERS INITIALIZED")
    
    def _load_shader(self, path):
        """Load WGSL shader from file"""
        with open(path, 'r') as f:
            return self.device.create_shader_module(code=f.read())
            
    def _create_shared_buffers(self):
        """Create shared memory buffers for shader communication and OS state"""
        buffers = {}

        # Substrate buffers
        buffers['vram'] = self.device.create_buffer(
            size=VRAM_SIZE * 4,  # 4 bytes per pixel (u32)
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )
        buffers['process_table'] = self.device.create_buffer(
            size=256 * (4 + 4 + 16*4 + 4), # PID, State, Registers[16], Priority
            usage=wgpu.BufferUsage.STORAGE
        )
        buffers['memory_pages'] = self.device.create_buffer(
            size=65536 * (4 + 4 + 4), # PhysicalAddr, Perms, OwnerPID
            usage=wgpu.BufferUsage.STORAGE
        )
        buffers['system_time_val'] = self.device.create_buffer(
            size=8, # u64
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )
        buffers['active_processes_count'] = self.device.create_buffer(
            size=4, # u32
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )
        buffers['x86_cpu_state'] = self.device.create_buffer(
            size=4 * 1024 * 1024, # Placeholder for X86State struct (4MB)
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )

        # Inter-shader comms buffers
        buffers['shader_mailboxes'] = self.device.create_buffer(
            size=64 * (1024 * (4 * 16 + 4*3) + 4*2 + 4*2), # Simplified size estimation
            usage=wgpu.BufferUsage.STORAGE
        )
        buffers['shared_atomic_buffer'] = self.device.create_buffer(
            size=131072 * 4, # 512KB
            usage=wgpu.BufferUsage.STORAGE
        )

        # Rendering pipeline buffers
        buffers['render_queue'] = self.device.create_buffer(
            size=4096 * (4 + 16*4 + 4 + 4), # Max 4096 commands
            usage=wgpu.BufferUsage.STORAGE
        )
        buffers['final_framebuffer'] = self.device.create_buffer(
            size=VRAM_SIZE * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST
        )

        # Network shader buffers
        buffers['network_portal'] = self.device.create_buffer(
            size=2 * 1024 * 1024, # 2MB
            usage=wgpu.BufferUsage.STORAGE
        )
        buffers['shared_network_memory'] = self.device.create_buffer(
            size=1 * 1024 * 1024, # 1MB
            usage=wgpu.BufferUsage.STORAGE
        )
        buffers['network_service_descriptor'] = self.device.create_buffer(
            size=1024, # Small buffer
            usage=wgpu.BufferUsage.STORAGE
        )

        # Filesystem shader buffers
        buffers['filesystem_state'] = self.device.create_buffer(
            size=4 * 1024 * 1024 + 2 * 1024 * 1024, # FAT, Inodes, Data Blocks
            usage=wgpu.BufferUsage.STORAGE
        )
        buffers['open_files'] = self.device.create_buffer(
            size=1024 * (4*6), # 1024 handles, each 6 u32s
            usage=wgpu.BufferUsage.STORAGE
        )
        
        return buffers

    def _create_bind_groups(self):
        """Create bind groups for all shaders"""
        bind_groups = {}
        
        # Substrate kernel bind group (Group 0)
        # All shaders share the same global BindGroup 0
        global_bind_group_layout = self.device.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # vram
            {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # process_table
            {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # memory_pages
            {"binding": 3, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # system_time_val
            {"binding": 4, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # active_processes_count
            {"binding": 5, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # x86_cpu_state
            {"binding": 6, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # shader_mailboxes (from inter_shader_comms)
            {"binding": 7, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # shared_atomic_buffer (from inter_shader_comms)
            {"binding": 8, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # render_queue (from rendering_pipeline)
            {"binding": 9, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # final_framebuffer (from rendering_pipeline)
            {"binding": 10, "visibility": wgpu.ShaderStage.COMPUTE, "texture": {"view_dimension": wgpu.TextureViewDimension.e2D, "sample_type": wgpu.TextureSampleType.float}}, # font_texture (from rendering_pipeline)
            {"binding": 11, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # network_portal (from network_shader)
            {"binding": 12, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # shared_network_memory (from network_shader)
            {"binding": 13, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # network_service (from network_integration)
            {"binding": 14, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # filesystem_state (from filesystem_shader)
            {"binding": 15, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": wgpu.BufferBindingType.storage}}, # open_files (from filesystem_shader)
        ])
        
        bind_groups['global'] = self.device.create_bind_group(
            layout=global_bind_group_layout,
            entries=[
                {"binding": 0, "resource": {"buffer": self.shared_buffers['vram'], "offset": 0, "size": self.shared_buffers['vram'].size}},
                {"binding": 1, "resource": {"buffer": self.shared_buffers['process_table'], "offset": 0, "size": self.shared_buffers['process_table'].size}},
                {"binding": 2, "resource": {"buffer": self.shared_buffers['memory_pages'], "offset": 0, "size": self.shared_buffers['memory_pages'].size}},
                {"binding": 3, "resource": {"buffer": self.shared_buffers['system_time_val'], "offset": 0, "size": self.shared_buffers['system_time_val'].size}},
                {"binding": 4, "resource": {"buffer": self.shared_buffers['active_processes_count'], "offset": 0, "size": self.shared_buffers['active_processes_count'].size}},
                {"binding": 5, "resource": {"buffer": self.shared_buffers['x86_cpu_state'], "offset": 0, "size": self.shared_buffers['x86_cpu_state'].size}},
                {"binding": 6, "resource": {"buffer": self.shared_buffers['shader_mailboxes'], "offset": 0, "size": self.shared_buffers['shader_mailboxes'].size}},
                {"binding": 7, "resource": {"buffer": self.shared_buffers['shared_atomic_buffer'], "offset": 0, "size": self.shared_buffers['shared_atomic_buffer'].size}},
                {"binding": 8, "resource": {"buffer": self.shared_buffers['render_queue'], "offset": 0, "size": self.shared_buffers['render_queue'].size}},
                {"binding": 9, "resource": {"buffer": self.shared_buffers['final_framebuffer'], "offset": 0, "size": self.shared_buffers['final_framebuffer'].size}},
                {"binding": 10, "resource": self.font_texture.create_view()},
                {"binding": 11, "resource": {"buffer": self.shared_buffers['network_portal'], "offset": 0, "size": self.shared_buffers['network_portal'].size}},
                {"binding": 12, "resource": {"buffer": self.shared_buffers['shared_network_memory'], "offset": 0, "size": self.shared_buffers['shared_network_memory'].size}},
                {"binding": 13, "resource": {"buffer": self.shared_buffers['network_service_descriptor'], "offset": 0, "size": self.shared_buffers['network_service_descriptor'].size}},
                {"binding": 14, "resource": {"buffer": self.shared_buffers['filesystem_state'], "offset": 0, "size": self.shared_buffers['filesystem_state'].size}},
                {"binding": 15, "resource": {"buffer": self.shared_buffers['open_files'], "offset": 0, "size": self.shared_buffers['open_files'].size}},
            ]
        )
        return bind_groups
    
    def launch_substrate(self):
        """Launch the Pixel OS substrate shaders"""
        print("🚀 LAUNCHING PIXEL OS SUBSTRATE SHADERS...")
        
        # Dispatch all core shaders
        commands = []
        
        commands.append(self._create_dispatch_command(
            self.shaders['substrate'], self.bind_groups['global'], 
            workgroups=(256, 1, 1), entry_point="main" # Specify entry_point for all shaders
        ))
        
        commands.append(self._create_dispatch_command(
            self.shaders['x86_emulator'], self.bind_groups['global'],
            workgroups=(64, 1, 1), entry_point="main"
        ))
        
        commands.append(self._create_dispatch_command(
            self.shaders['inter_shader_comms'], self.bind_groups['global'],
            workgroups=(64, 1, 1), entry_point="main"
        ))

        commands.append(self._create_dispatch_command(
            self.shaders['rendering_pipeline'], self.bind_groups['global'],
            workgroups=(int(np.ceil(VRAM_SIZE / 256)), 1, 1), entry_point="main"
        ))

        commands.append(self._create_dispatch_command(
            self.shaders['network_shader'], self.bind_groups['global'],
            workgroups=(256, 1, 1), entry_point="main"
        ))
        
        commands.append(self._create_dispatch_command(
            self.shaders['filesystem_shader'], self.bind_groups['global'],
            workgroups=(128, 1, 1), entry_point="main"
        ))

        commands.append(self._create_dispatch_command(
            self.shaders['network_integration'], self.bind_groups['global'],
            workgroups=(64, 1, 1), entry_point="main"
        ))
        
        self.queue.submit(commands)
        print("✅ ALL SUBSTRATE SHADERS DISPATCHED")
    
    def _create_dispatch_command(self, shader, bind_group, workgroups, entry_point="main"):
        """Create compute dispatch command"""
        command_encoder = self.device.create_command_encoder()
        compute_pass = command_encoder.begin_compute_pass()
        
        compute_pass.set_pipeline(
            self.device.create_compute_pipeline(
                layout=self.device.create_pipeline_layout(bind_group_layouts=[bind_group.layout]),
                compute={"module": shader, "entry_point": entry_point}
            )
        )
        compute_pass.set_bind_group(0, bind_group)
        compute_pass.dispatch_workgroups(*workgroups)
        compute_pass.end()
        
        return command_encoder.finish()
    
    def run_frame(self):
        """Run one frame of the Pixel OS substrate"""
        self.launch_substrate()
        
        # Read back results if needed
        # (Most communication happens shader-to-shader)
        
    def load_x86_program(self, binary_data):
        """Load x86 binary into shader memory"""
        print(f"📦 LOADING X86 PROGRAM INTO SHADER MEMORY: {len(binary_data)} bytes")
        
        x86_state_size = 4 * 1024 * 1024 # Matching buffer size
        x86_state_data = bytearray(x86_state_size)
        
        # Set up initial registers (EIP to code start)
        # Using struct.pack to put u32 values into bytearray
        struct.pack_into('<10I', x86_state_data, 0, 0, 0, 0, 0, 0, 0, 0x7FFFF000, 0, 0x00400000, 0x00000202) # EIP=0x400000
        
        # Load binary code into the memory section of X86State
        code_start_offset_in_state = 0x1000 # Example offset within X86State buffer
        
        # Ensure binary_data fits within the X86State buffer's memory section
        if code_start_offset_in_state + len(binary_data) > x86_state_size:
            raise ValueError("Binary data plus offset exceeds X86State buffer size.")

        x86_state_data[code_start_offset_in_state : code_start_offset_in_state + len(binary_data)] = binary_data
        
        # Set instruction count
        # Assuming instructions are u32s, so convert byte length to u32 count
        struct.pack_into('<I', x86_state_data, 131072 * 4, len(binary_data) // 4) # instruction_count at offset
        
        # Upload to GPU
        self.queue.write_buffer(
            self.shared_buffers['x86_cpu_state'], 0, x86_state_data
        )

    def _prepare_x86_state(self, binary_data):
        """Prepare x86 state for GPU consumption (DEPRECATED - now part of load_x86_program)"""
        pass
