"""
WGSL Compute Shader — Spatial Glyph CPU Emulator on GPU

The fetch-decode-execute loop runs entirely on the GPU.
Thousands of spatial CPUs can execute concurrently across texture planes.

Architecture:
- Storage: storage texture binding_0 (ROM)
- PC: uniform buffer per workgroup
- Registers: storage buffer (8 x uint32)
- Memory: storage buffer (1KB x uint8)
- Output: storage buffer (output log)

Each workgroup = one spatial CPU instance.
"""

# WGSL Spatial Glyph Compute Shader
WGSL_SHADER = """
struct SpatialCPU {
    pc: vec2<u32>,        // 2D program counter
    registers: array<u32, 8>,  // r0-r7
    memory: array<u32, 256>,   // 1KB (256 x u32)
    running: u32,
    output_ptr: u32,
}

struct Uniforms {
    max_instructions: u32,
    output_buffer_size: u32,
}

@group(0) @binding(0) var<storage, read> rom: texture_2d<vec4<u32>>;
@group(0) @binding(1) var<storage, read_write> cpus: array<SpatialCPU>;
@group(0) @binding(2) var<storage, read_write> output_buffer: array<u32>;
@group(0) @binding(3) var<uniform> uniforms: Uniforms;

// Opcode definitions (must match Python OpcodeMap)
const OPCODE_LDI: u32 = 0;
const OPCODE_ADD: u32 = 1;
const OPCODE_SUB: u32 = 2;
const OPCODE_MUL: u32 = 3;
const OPCODE_JMP: u32 = 4;
const OPCODE_JZ: u32 = 5;
const OPCODE_CMP: u32 = 6;
const OPCODE_MOV: u32 = 7;
const OPCODE_PRT: u32 = 8;
const OPCODE_HALT: u32 = 9;

fn rgb_to_opcode(rgb: vec3<u32>) -> u32 {
    // Convert RGB pixel to opcode
    // Uses deterministic hashing like Python version
    let hash_val = (u32(rgb.r) * 7u) + (u32(rgb.g) * 13u) + (u32(rgb.b) * 17u);

    // Match Python deterministic RGB generation
    if (rgb == vec3<u32>(236u, 80u, 80u)) { return OPCODE_LDI; }
    if (rgb == vec3<u32>(80u, 236u, 120u)) { return OPCODE_ADD; }
    if (rgb == vec3<u32>(151u, 244u, 80u)) { return OPCODE_SUB; }
    if (rgb == vec3<u32>(80u, 190u, 80u)) { return OPCODE_MUL; }
    if (rgb == vec3<u32>(220u, 20u, 60u)) { return OPCODE_JMP; }
    if (rgb == vec3<u32>(242u, 230u, 222u)) { return OPCODE_JZ; }
    if (rgb == vec3<u32>(80u, 131u, 175u)) { return OPCODE_CMP; }
    if (rgb == vec3<u32>(178u, 34u, 34u)) { return OPCODE_MOV; }
    if (rgb == vec3<u32>(247u, 83u, 80u)) { return OPCODE_PRT; }
    if (rgb == vec3<u32>(255u, 0u, 0u)) { return OPCODE_HALT; }

    return 1000u; // Unknown opcode
}

fn fetch_operand(cpu_id: u32, pc: ptr<function, vec2<u32>>) -> vec2<u32> {
    // Fetch operand from current PC and advance
    let x = (*pc).x;
    let y = (*pc).y;

    let pixel = textureLoad(rom, vec2<i32>(i32(x), i32(y)), 0);
    let r = pixel.r;
    let g = pixel.g;
    let b = pixel.b;

    // Advance PC
    (*pc).x = x + 1u;

    // Check for immediate value (r=0, g=0, b>0)
    if (r == 0u && g == 0u && b > 0u) {
        // b is offset by 1 during encoding
        return vec2<u32>(0u, b - 1u); // type=0 (imm), value=b-1
    }

    // Check for coordinate (r=0, g>0, b>0)
    if (r == 0u && g > 0u && b > 0u) {
        // Offset by 1 during encoding
        return vec2<u32>(1u, (g - 1u) | ((b - 1u) << 16u)); // type=1 (coord), packed coords
    }

    // Check for register (grayscale: r≈g≈b)
    if (abs(i32(r) - i32(g)) < 10 && abs(i32(g) - i32(b)) < 10 && r > 40u) {
        let reg_num = (r - 50u) / 25u;
        if (reg_num <= 7u) {
            return vec2<u32>(2u, reg_num); // type=2 (reg), value=reg_num
        }
    }

    return vec2<u32>(3u, 0u); // type=3 (unknown)
}

fn unpack_coord(packed: u32) -> vec2<u32> {
    let x = packed & 0xFFFFu;
    let y = (packed >> 16u) & 0xFFFFu;
    return vec2<u32>(x, y);
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let cpu_id = global_id.x;

    if (cpu_id >= arrayLength(&cpus)) {
        return;
    }

    var cpu = cpus[cpu_id];

    if (cpu.running == 0u) {
        return;
    }

    // Fetch opcode
    let pixel = textureLoad(rom, vec2<i32>(i32(cpu.pc.x), i32(cpu.pc.y)), 0);
    let opcode = rgb_to_opcode(pixel.rgb);

    // Advance PC past opcode
    cpu.pc.x = cpu.pc.x + 1u;

    // Decode and execute
    if (opcode == OPCODE_LDI) {
        // LDI r, imm
        let op1 = fetch_operand(cpu_id, &cpu.pc);
        let op2 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 2u) { // register
            cpu.registers[op1.y] = op2.y;
        }

    } else if (opcode == OPCODE_ADD) {
        // ADD r1, r2
        let op1 = fetch_operand(cpu_id, &cpu.pc);
        let op2 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 2u && op2.x == 2u) { // both registers
            cpu.registers[op1.y] = cpu.registers[op1.y] + cpu.registers[op2.y];
        }

    } else if (opcode == OPCODE_SUB) {
        // SUB r1, r2
        let op1 = fetch_operand(cpu_id, &cpu.pc);
        let op2 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 2u && op2.x == 2u) {
            cpu.registers[op1.y] = cpu.registers[op1.y] - cpu.registers[op2.y];
        }

    } else if (opcode == OPCODE_MUL) {
        // MUL r1, r2
        let op1 = fetch_operand(cpu_id, &cpu.pc);
        let op2 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 2u && op2.x == 2u) {
            cpu.registers[op1.y] = cpu.registers[op1.y] * cpu.registers[op2.y];
        }

    } else if (opcode == OPCODE_CMP) {
        // CMP r1, r2 → set r0 = 1 if equal else 0
        let op1 = fetch_operand(cpu_id, &cpu.pc);
        let op2 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 2u && op2.x == 2u) {
            if (cpu.registers[op1.y] == cpu.registers[op2.y]) {
                cpu.registers[0] = 1u;
            } else {
                cpu.registers[0] = 0u;
            }
        }

    } else if (opcode == OPCODE_MOV) {
        // MOV r1, r2
        let op1 = fetch_operand(cpu_id, &cpu.pc);
        let op2 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 2u && op2.x == 2u) {
            cpu.registers[op1.y] = cpu.registers[op2.y];
        }

    } else if (opcode == OPCODE_PRT) {
        // PRT r → write to output buffer
        let op1 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 2u) {
            let output_idx = atomicMin(&cpu.output_ptr, uniforms.output_buffer_size - 1u);
            if (output_idx < uniforms.output_buffer_size) {
                output_buffer[output_idx] = cpu.registers[op1.y];
            }
            cpu.output_ptr = cpu.output_ptr + 1u;
        }

    } else if (opcode == OPCODE_JMP) {
        // JMP x, y
        let op1 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 1u) { // coordinate
            let coord = unpack_coord(op1.y);
            cpu.pc = coord;
        }

    } else if (opcode == OPCODE_JZ) {
        // JZ x, y → jump if r0 == 0
        let op1 = fetch_operand(cpu_id, &cpu.pc);

        if (op1.x == 1u && cpu.registers[0] == 0u) {
            let coord = unpack_coord(op1.y);
            cpu.pc = coord;
        }

    } else if (opcode == OPCODE_HALT) {
        cpu.running = 0u;
    }

    // Write back CPU state
    cpus[cpu_id] = cpu;
}
"""


class WGSLSpatialEngine:
    """
    WGSL-based spatial glyph execution engine.

    Runs thousands of spatial CPUs concurrently on GPU.
    """

    def __init__(self):
        self.device = None
        self.shader_module = None
        self.compute_pipeline = None
        self.bind_group = None

    async def initialize(self):
        """Initialize WebGPU device and pipeline."""
        try:
            import wgpu
            self.device = wgpu.utils.get_default_device()

            # Create compute pipeline
            self.shader_module = self.device.create_shader_module(
                code=WGSL_SHADER
            )

            self.compute_pipeline = self.device.create_compute_pipeline(
                layout=self.device.create_pipeline_layout(
                    bind_group_layouts=[]
                ),
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
            return False

    def load_program_image(self, image_path: str):
        """Load pixel-encoded program image as GPU texture."""
        from PIL import Image
        import numpy as np

        img = Image.open(image_path)
        rgba = np.array(img)

        # Convert to RGBA32 if needed
        if rgba.shape[2] == 3:
            # Add alpha channel
            rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, dtype=rgba.dtype)])

        # Create texture
        texture = self.device.create_texture(
            size=(rgba.shape[1], rgba.shape[0], 1),
            usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.COPY_DST,
            format=wgpu.TextureFormat.RGBA8UINT,
        )

        # Upload texture data
        self.device.queue.write_texture(
            {
                "offset": 0,
                "bytes_per_row": rgba.shape[1] * 4,
                "rows_per_image": rgba.shape[0],
            },
            rgba.tobytes(),
            {
                "buffer": texture,
                "origin": (0, 0, 0),
                "size": (rgba.shape[1], rgba.shape[0], 1),
            },
        )

        return texture

    def create_cpu_instances(self, num_cpus: int = 1000):
        """Create buffer for multiple CPU instances."""
        import struct

        # Each CPU: pc(2x4) + registers(8x4) + memory(256x4) + running(4) + output_ptr(4)
        # = 8 + 32 + 1024 + 4 + 4 = 1072 bytes per CPU
        cpu_size = 1072

        # Initialize CPUs
        cpu_data = bytearray(num_cpus * cpu_size)

        for i in range(num_cpus):
            offset = i * cpu_size

            # PC starts at (0, 0)
            struct.pack_into('II', cpu_data, offset, 0, 0)

            # running = 1
            struct.pack_into('I', cpu_data, offset + 1068, 1)

            # output_ptr = 0
            struct.pack_into('I', cpu_data, offset + 1072, 0)

        buffer = self.device.create_buffer(
            size=len(cpu_data),
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
        )
        self.device.queue.write_buffer(buffer, 0, cpu_data)

        return buffer

    def create_output_buffer(self, size: int = 1024):
        """Create output buffer for PRT operations."""
        buffer = self.device.create_buffer(
            size=size * 4,  # u32 per output
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
        )
        return buffer

    def run(self, texture, cpus_buffer, output_buffer, num_cpus: int = 1000, dispatches: int = 100):
        """Run spatial CPUs on GPU."""

        # Create bind group
        self.bind_group = self.device.create_bind_group(
            layout=self.compute_pipeline.get_bind_group_layout(0),
            entries=[
                {
                    "binding": 0,
                    "resource": texture.create_view(),
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
                        "buffer": self.device.create_buffer(
                            size=8,  # max_instructions(4) + output_buffer_size(4)
                            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
                        ),
                        "offset": 0,
                        "size": 8,
                    },
                },
            ],
        )

        # Encode commands
        command_encoder = self.device.create_command_encoder()

        # Set uniforms
        uniform_data = struct.pack('II', dispatches, output_buffer.size // 4)
        uniform_buffer = self.device.create_buffer(
            size=8,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(uniform_buffer, 0, uniform_data)

        # Run compute shader multiple times (simulating instruction loop)
        for _ in range(dispatches):
            compute_pass = command_encoder.begin_compute_pass()
            compute_pass.set_pipeline(self.compute_pipeline)
            compute_pass.set_bind_group(0, self.bind_group)
            compute_pass.dispatch_workgroups(num_cpus)
            compute_pass.end()

        # Submit commands
        self.device.queue.submit([command_encoder.finish()])

        print(f"✓ Executed {num_cpus} spatial CPUs for {dispatches} dispatches")

    def read_output(self, output_buffer):
        """Read output buffer from GPU."""
        import struct

        staging_buffer = self.device.create_buffer(
            size=output_buffer.size,
            usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST,
        )

        command_encoder = self.device.create_command_encoder()
        command_encoder.copy_buffer_to_buffer(
            output_buffer, 0, staging_buffer, 0, output_buffer.size
        )

        self.device.queue.submit([command_encoder.finish()])

        # Read back
        output_data = staging_buffer.read_map()
        values = struct.unpack(f'{output_buffer.size // 4}I', output_data)

        return values


async def demo():
    """Demonstrate WGSL spatial glyph execution."""

    print("=" * 60)
    print("WGSL SPATIAL GLYPH ENGINE DEMO")
    print("=" * 60)

    engine = WGSLSpatialEngine()

    # Initialize WebGPU
    if not await engine.initialize():
        print("Demo aborted")
        return

    # Load program image
    print("\nLoading program image...")
    texture = engine.load_program_image("demo_glyph_simple.png")
    print("✓ Program loaded as GPU texture")

    # Create CPU instances
    num_cpus = 100
    cpus_buffer = engine.create_cpu_instances(num_cpus)
    print(f"✓ Created {num_cpus} spatial CPU instances")

    # Create output buffer
    output_buffer = engine.create_output_buffer(1024)
    print("✓ Created output buffer")

    # Run
    print("\nExecuting on GPU...")
    engine.run(texture, cpus_buffer, output_buffer, num_cpus, dispatches=50)

    # Read output
    print("\nReading output...")
    output = engine.read_output(output_buffer)
    non_zero_output = [v for v in output if v > 0]

    print(f"Output values: {non_zero_output}")

    print("\n" + "=" * 60)
    print("GPU EXECUTION COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    import asyncio
    asyncio.run(demo())