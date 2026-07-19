"""
Working WGSL spatial glyph engine - minimal then incremental.
"""

import struct
import asyncio
import numpy as np

# MINIMAL WORKING SHADER (Test 10 equivalent)
WGSL_SHADER_MINIMAL = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

struct SpatialCPU {
    pc: vec2<u32>,
    registers: array<u32, 8>,
    memory: array<u32, 256>,
    running: u32,
    output_ptr: u32,
}

struct Uniforms {
    image_width: u32,
    output_buffer_size: u32,
}

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> cpus: array<SpatialCPU>;
@group(0) @binding(2) var<storage, read_write> output: array<u32>;
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

fn load_pixel(x: u32, y: u32) -> vec3<u32> {
    let index = y * uniforms.image_width + x;
    let pixel = rom[index];
    return vec3<u32>(pixel.r, pixel.g, pixel.b);
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var cpu = cpus[global_id.x];
    if (cpu.running == 0u) { return; }

    let pixel = load_pixel(cpu.pc.x, cpu.pc.y);
    cpu.pc.x = cpu.pc.x + 1u;

    // Opcodes
    if (pixel.r == 236u && pixel.g == 80u && pixel.b == 80u) {
        // LDI: load immediate
        // Next pixel is register, next is value
        let reg_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc.x = cpu.pc.x + 1u;
        let reg_num = (reg_pixel.r - 50u) / 25u;

        let val_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc.x = cpu.pc.x + 1u;
        let val = val_pixel.b - 1u;

        cpu.registers[reg_num] = val;

    } else if (pixel.r == 80u && pixel.g == 236u && pixel.b == 120u) {
        // ADD
        let reg1_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc.x = cpu.pc.x + 1u;
        let reg1 = (reg1_pixel.r - 50u) / 25u;

        let reg2_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc.x = cpu.pc.x + 1u;
        let reg2 = (reg2_pixel.r - 50u) / 25u;

        cpu.registers[reg1] = cpu.registers[reg1] + cpu.registers[reg2];

    } else if (pixel.r == 151u && pixel.g == 244u && pixel.b == 80u) {
        // SUB
        let reg1_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc.x = cpu.pc.x + 1u;
        let reg1 = (reg1_pixel.r - 50u) / 25u;

        let reg2_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc.x = cpu.pc.x + 1u;
        let reg2 = (reg2_pixel.r - 50u) / 25u;

        cpu.registers[reg1] = cpu.registers[reg1] - cpu.registers[reg2];

    } else if (pixel.r == 247u && pixel.g == 83u && pixel.b == 80u) {
        // PRT: print register
        let reg_pixel = load_pixel(cpu.pc.x, cpu.pc.y);
        cpu.pc.x = cpu.pc.x + 1u;
        let reg_num = (reg_pixel.r - 50u) / 25u;

        output[global_id.x * uniforms.output_buffer_size + cpu.output_ptr] = cpu.registers[reg_num];
        cpu.output_ptr = cpu.output_ptr + 1u;

    } else if (pixel.r == 255u && pixel.g == 0u && pixel.b == 0u) {
        // HALT
        cpu.running = 0u;
    }

    cpus[global_id.x] = cpu;
}
"""


class WGSLSpatialEngine:
    """
    WGSL-based spatial glyph execution engine - MINIMAL WORKING VERSION.
    """

    def __init__(self):
        self.device = None
        self.shader_module = None
        self.compute_pipeline = None
        self.wgpu = None

    async def initialize(self):
        """Initialize WebGPU device and pipeline."""
        try:
            self.wgpu = __import__('wgpu')
            self.device = self.wgpu.utils.get_default_device()

            # Create shader module
            self.shader_module = self.device.create_shader_module(
                code=WGSL_SHADER_MINIMAL
            )

            # Create bind group layout
            bind_group_layout = self.device.create_bind_group_layout(
                entries=[
                    {
                        "binding": 0,
                        "visibility": self.wgpu.ShaderStage.COMPUTE,
                        "buffer": {
                            "type": self.wgpu.BufferBindingType.read_only_storage,
                        },
                    },
                    {
                        "binding": 1,
                        "visibility": self.wgpu.ShaderStage.COMPUTE,
                        "buffer": {
                            "type": self.wgpu.BufferBindingType.storage,
                        },
                    },
                    {
                        "binding": 2,
                        "visibility": self.wgpu.ShaderStage.COMPUTE,
                        "buffer": {
                            "type": self.wgpu.BufferBindingType.storage,
                        },
                    },
                    {
                        "binding": 3,
                        "visibility": self.wgpu.ShaderStage.COMPUTE,
                        "buffer": {
                            "type": self.wgpu.BufferBindingType.uniform,
                        },
                    },
                ]
            )

            # Create pipeline layout
            pipeline_layout = self.device.create_pipeline_layout(
                bind_group_layouts=[bind_group_layout]
            )

            # Create compute pipeline
            self.compute_pipeline = self.device.create_compute_pipeline(
                layout=pipeline_layout,
                compute={
                    "module": self.shader_module,
                    "entry_point": "main",
                },
            )

            print("✓ WGSL Spatial Engine initialized")
            return True

        except ImportError:
            print("✗ wgpu not installed. Install with: pip install wgpu")
            return False
        except Exception as e:
            print(f"✗ WGSL initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_program_image(self, image_path: str):
        """Load pixel-encoded program image as GPU buffer."""
        from PIL import Image

        if not self.device:
            raise RuntimeError("Engine not initialized. Call initialize() first.")

        img = Image.open(image_path)
        rgba = np.array(img)

        # Convert to RGBA32 if needed
        if rgba.shape[2] == 3:
            rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, dtype=rgba.dtype)])

        height, width = rgba.shape[:2]

        # Flatten to RGBA32 array (4 x uint8 per pixel)
        # WGSL will read these as u32 values 0-255
        flat_data = rgba.reshape(-1, 4)

        # Create storage buffer
        buffer = self.device.create_buffer(
            size=len(flat_data) * 4,  # 4 bytes per pixel (RGBA)
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST,
        )

        self.device.queue.write_buffer(buffer, 0, flat_data.tobytes())

        return buffer, width, height

    def create_cpu_instances(self, num_cpus: int = 10):
        """Create buffer for CPU instances."""
        # Each CPU: pc(2x4) + registers(8x4) + memory(256x4) + running(4) + output_ptr(4)
        cpu_size = 1072

        # Initialize CPUs
        cpu_data = bytearray(num_cpus * cpu_size)

        for i in range(num_cpus):
            offset = i * cpu_size

            # PC starts at (0, 0) at offset 0
            struct.pack_into('II', cpu_data, offset, 0, 0)

            # running = 1 at offset 1064 (8 + 32 + 1024)
            struct.pack_into('I', cpu_data, offset + 1064, 1)

            # output_ptr = 0 at offset 1068 (8 + 32 + 1024 + 4)
            struct.pack_into('I', cpu_data, offset + 1068, 0)

        buffer = self.device.create_buffer(
            size=len(cpu_data),
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST | self.wgpu.BufferUsage.COPY_SRC,
        )
        self.device.queue.write_buffer(buffer, 0, cpu_data)

        return buffer

    def create_output_buffer(self, size: int = 1024):
        """Create output buffer."""
        buffer = self.device.create_buffer(
            size=size * 4,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST | self.wgpu.BufferUsage.COPY_SRC,
        )
        return buffer

    def run(self, rom_buffer, image_width, image_height, cpus_buffer, output_buffer, num_cpus: int = 10, dispatches: int = 20):
        """Run spatial CPUs on GPU."""

        # Create uniform buffer
        uniform_data = struct.pack('II', image_width, output_buffer.size // 4 // num_cpus)
        uniform_buffer = self.device.create_buffer(
            size=8,
            usage=self.wgpu.BufferUsage.UNIFORM | self.wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(uniform_buffer, 0, uniform_data)

        # Create bind group
        bind_group = self.device.create_bind_group(
            layout=self.compute_pipeline.get_bind_group_layout(0),
            entries=[
                {
                    "binding": 0,
                    "resource": {
                        "buffer": rom_buffer,
                        "offset": 0,
                        "size": rom_buffer.size,
                    },
                },
                {
                    "binding": 1,
                    "resource": {
                        "buffer": cpus_buffer,
                        "offset": 0,
                        "size": cpus_buffer.size,
                    },
                },
                {
                    "binding": 2,
                    "resource": {
                        "buffer": output_buffer,
                        "offset": 0,
                        "size": output_buffer.size,
                    },
                },
                {
                    "binding": 3,
                    "resource": {
                        "buffer": uniform_buffer,
                        "offset": 0,
                        "size": 8,
                    },
                },
            ],
        )

        # Encode commands
        command_encoder = self.device.create_command_encoder()

        # Run compute shader
        for _ in range(dispatches):
            compute_pass = command_encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.compute_pipeline)
            compute_pass.set_bind_group(0, bind_group)
            compute_pass.dispatch_workgroups(num_cpus)
            compute_pass.end()

        # Submit commands
        self.device.queue.submit([command_encoder.finish()])

        print(f"✓ Executed {num_cpus} spatial CPUs for {dispatches} dispatches")

    def read_output(self, output_buffer):
        """Read output buffer from GPU."""
        staging_buffer = self.device.create_buffer(
            size=output_buffer.size,
            usage=self.wgpu.BufferUsage.MAP_READ | self.wgpu.BufferUsage.COPY_DST,
        )

        command_encoder = self.device.create_command_encoder()
        command_encoder.copy_buffer_to_buffer(
            output_buffer, 0, staging_buffer, 0, output_buffer.size
        )

        self.device.queue.submit([command_encoder.finish()])

        # Map then read
        staging_buffer.map_sync(self.wgpu.MapMode.READ)
        output_data = staging_buffer.read_mapped()
        values = struct.unpack(f'{output_buffer.size // 4}I', output_data)
        staging_buffer.unmap()

        return values


async def demo():
    """Demonstrate WGSL spatial glyph execution."""

    print("=" * 60)
    print("WGSL SPATIAL GLYPH ENGINE - MINIMAL VERSION")
    print("=" * 60)

    engine = WGSLSpatialEngine()

    # Initialize WebGPU
    if not await engine.initialize():
        print("Demo aborted")
        return

    # Load program image
    print("\nLoading program image...")
    rom_buffer, width, height = engine.load_program_image("demo_glyph_simple.png")
    print(f"✓ Program loaded: {width}x{height}")

    # Create CPU instances
    num_cpus = 10
    cpus_buffer = engine.create_cpu_instances(num_cpus)
    print(f"✓ Created {num_cpus} spatial CPU instances")

    # Create output buffer
    output_buffer = engine.create_output_buffer(1024)
    print("✓ Created output buffer")

    # Run
    print("\nExecuting on GPU...")
    engine.run(rom_buffer, width, height, cpus_buffer, output_buffer, num_cpus, dispatches=20)

    # Read output
    print("\nReading output...")
    output = engine.read_output(output_buffer)
    non_zero_output = [v for v in output if v > 0]

    print(f"Output values: {non_zero_output}")

    print("\n" + "=" * 60)
    print("GPU EXECUTION COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(demo())