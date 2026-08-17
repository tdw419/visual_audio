"""
WGSL Compute Shader — Spatial Glyph CPU Emulator on GPU

The fetch-decode-execute loop runs entirely on the GPU.
Thousands of spatial CPUs can execute concurrently across texture planes.

Architecture:
- Storage: storage buffer binding_0 (ROM as RGBA32 pixels)
- PC: storage buffer with cpu_id indexing
- Registers: storage buffer (8 x uint32 per CPU)
- Memory: storage buffer (1KB x uint8 per CPU)
- Output: storage buffer (output log)

Each workgroup = one spatial CPU instance.
"""

import struct
import asyncio
from pathlib import Path
import numpy as np

# WGSL Spatial Glyph Compute Shader
WGSL_SHADER = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

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
    image_width: u32,
    image_height: u32,
}

@group(0) @binding(0) var<storage, read> rom: array<Pixel>;
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
const OPCODE_PARALLEL_LD: u32 = 10;
const OPCODE_PARALLEL_ST: u32 = 11;
const OPCODE_PARALLEL_ADD: u32 = 12;
const OPCODE_PARALLEL_SUB: u32 = 13;
const OPCODE_PARALLEL_REDUCE_SUM: u32 = 14;

// Simple opcode lookup by color (simpler than vector comparison)
fn get_opcode_from_color(r: u32, g: u32, b: u32) -> u32 {
    // Original scalar opcodes
    if (r == 236u && g == 80u && b == 80u) { return OPCODE_LDI; }
    if (r == 80u && g == 236u && b == 120u) { return OPCODE_ADD; }
    if (r == 151u && g == 244u && b == 80u) { return OPCODE_SUB; }
    if (r == 80u && g == 190u && b == 80u) { return OPCODE_MUL; }
    if (r == 220u && g == 20u && b == 60u) { return OPCODE_JMP; }
    if (r == 242u && g == 230u && b == 222u) { return OPCODE_JZ; }
    if (r == 80u && g == 131u && b == 175u) { return OPCODE_CMP; }
    if (r == 178u && g == 34u && b == 34u) { return OPCODE_MOV; }
    if (r == 247u && g == 83u && b == 80u) { return OPCODE_PRT; }
    if (r == 255u && g == 0u && b == 0u) { return OPCODE_HALT; }
    
    // GPU-native parallel opcodes (matching FIXED_COLORS in glyph_isa_v2.py)
    if (r == 147u && g == 51u && b == 234u) { return OPCODE_PARALLEL_LD; }          // Purple
    if (r == 255u && g == 20u && b == 147u) { return OPCODE_PARALLEL_ST; }         // Deep Pink
    if (r == 0u && g == 255u && b == 127u) { return OPCODE_PARALLEL_ADD; }        // Spring Green
    if (r == 255u && g == 140u && b == 0u) { return OPCODE_PARALLEL_SUB; }        // Dark Orange
    if (r == 0u && g == 191u && b == 255u) { return OPCODE_PARALLEL_REDUCE_SUM; } // Deep Sky Blue

    return 1000u; // Unknown opcode
}

fn load_pixel(x: u32, y: u32) -> vec3<u32> {
    let index = y * uniforms.image_width + x;
    let pixel = rom[index];
    return vec3<u32>(pixel.r, pixel.g, pixel.b);
}

fn fetch_operand(cpu_id: u32) -> vec2<u32> {
    // Fetch operand from current CPU's PC and advance PC
    let x = cpus[cpu_id].pc.x;
    let y = cpus[cpu_id].pc.y;

    let pixel = load_pixel(x, y);
    let r = pixel.r;
    let g = pixel.g;
    let b = pixel.b;

    // Advance PC (mutate storage buffer directly)
    cpus[cpu_id].pc.x = x + 1u;

    // Check for immediate value (r=0, g=0, b>0)
    if (r == 0u && g == 0u && b > 0u) {
        return vec2<u32>(0u, b - 1u); // type=0 (imm), value=b-1
    }

    // Check for coordinate (r=0, g>0, b>0)
    if (r == 0u && g > 0u && b > 0u) {
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

var<workgroup> shared_opcode: u32;
var<workgroup> shared_op1: vec2<u32>;
var<workgroup> shared_op2: vec2<u32>;
var<workgroup> shared_op3: vec2<u32>;
var<workgroup> shared_op4: vec2<u32>;
var<workgroup> reduction_scratch: array<u32, 256>;

@compute @workgroup_size(256)
fn main(
    @builtin(workgroup_id) workgroup_id: vec3<u32>,
    @builtin(local_invocation_id) local_id: vec3<u32>
) {
    let cpu_id = workgroup_id.x;
    let thread_id = local_id.x;

    if (cpu_id >= arrayLength(&cpus)) {
        return;
    }

    if (cpus[cpu_id].running == 0u) {
        return;
    }

    // Decode phase: Only thread 0 reads the instruction and decodes it
    if (thread_id == 0u) {
        let pixel = load_pixel(cpus[cpu_id].pc.x, cpus[cpu_id].pc.y);
        shared_opcode = get_opcode_from_color(pixel.r, pixel.g, pixel.b);
        cpus[cpu_id].pc.x = cpus[cpu_id].pc.x + 1u; // Advance PC past opcode

        // Pre-fetch operands based on opcode arity
        if (shared_opcode == OPCODE_LDI || shared_opcode == OPCODE_ADD || shared_opcode == OPCODE_SUB || shared_opcode == OPCODE_MUL || shared_opcode == OPCODE_CMP || shared_opcode == OPCODE_MOV) {
            shared_op1 = fetch_operand(cpu_id);
            shared_op2 = fetch_operand(cpu_id);
        } else if (shared_opcode == OPCODE_PARALLEL_LD || shared_opcode == OPCODE_PARALLEL_ST || shared_opcode == OPCODE_PARALLEL_REDUCE_SUM) {
            shared_op1 = fetch_operand(cpu_id);
            shared_op2 = fetch_operand(cpu_id);
            shared_op3 = fetch_operand(cpu_id);
        } else if (shared_opcode == OPCODE_PARALLEL_ADD || shared_opcode == OPCODE_PARALLEL_SUB) {
            shared_op1 = fetch_operand(cpu_id);
            shared_op2 = fetch_operand(cpu_id);
            shared_op3 = fetch_operand(cpu_id);
            shared_op4 = fetch_operand(cpu_id);
        } else if (shared_opcode == OPCODE_JMP || shared_opcode == OPCODE_JZ || shared_opcode == OPCODE_PRT) {
            shared_op1 = fetch_operand(cpu_id);
        }
    }

    // Synchronize all 256 threads so they see the decoded opcode and operands
    workgroupBarrier();

    let opcode = shared_opcode;

    // Execute phase
    if (opcode == OPCODE_LDI) {
        if (thread_id == 0u && shared_op1.x == 2u) {
            cpus[cpu_id].registers[shared_op1.y] = shared_op2.y;
        }
    } else if (opcode == OPCODE_ADD) {
        if (thread_id == 0u && shared_op1.x == 2u && shared_op2.x == 2u) {
            cpus[cpu_id].registers[shared_op1.y] = cpus[cpu_id].registers[shared_op1.y] + cpus[cpu_id].registers[shared_op2.y];
        }
    } else if (opcode == OPCODE_SUB) {
        if (thread_id == 0u && shared_op1.x == 2u && shared_op2.x == 2u) {
            cpus[cpu_id].registers[shared_op1.y] = cpus[cpu_id].registers[shared_op1.y] - cpus[cpu_id].registers[shared_op2.y];
        }
    } else if (opcode == OPCODE_MUL) {
        if (thread_id == 0u && shared_op1.x == 2u && shared_op2.x == 2u) {
            cpus[cpu_id].registers[shared_op1.y] = cpus[cpu_id].registers[shared_op1.y] * cpus[cpu_id].registers[shared_op2.y];
        }
    } else if (opcode == OPCODE_CMP) {
        if (thread_id == 0u && shared_op1.x == 2u && shared_op2.x == 2u) {
            if (cpus[cpu_id].registers[shared_op1.y] == cpus[cpu_id].registers[shared_op2.y]) {
                cpus[cpu_id].registers[0] = 1u;
            } else {
                cpus[cpu_id].registers[0] = 0u;
            }
        }
    } else if (opcode == OPCODE_MOV) {
        if (thread_id == 0u && shared_op1.x == 2u && shared_op2.x == 2u) {
            cpus[cpu_id].registers[shared_op1.y] = cpus[cpu_id].registers[shared_op2.y];
        }
    } else if (opcode == OPCODE_PRT) {
        if (thread_id == 0u && shared_op1.x == 2u) {
            let output_idx = cpus[cpu_id].output_ptr;
            if (output_idx < uniforms.output_buffer_size) {
                output_buffer[cpu_id * uniforms.output_buffer_size + output_idx] = cpus[cpu_id].registers[shared_op1.y];
            }
            cpus[cpu_id].output_ptr = cpus[cpu_id].output_ptr + 1u;
        }
    } else if (opcode == OPCODE_JMP) {
        if (thread_id == 0u && shared_op1.x == 1u) {
            cpus[cpu_id].pc = unpack_coord(shared_op1.y);
        }
    } else if (opcode == OPCODE_JZ) {
        if (thread_id == 0u && shared_op1.x == 1u && cpus[cpu_id].registers[0] == 0u) {
            cpus[cpu_id].pc = unpack_coord(shared_op1.y);
        }
    } else if (opcode == OPCODE_PARALLEL_LD) {
        if (shared_op1.x == 2u && shared_op3.y > 0u) {
            let base_addr = shared_op2.y;
            let count = shared_op3.y;
            // All 256 threads participate in loading
            for (var i = thread_id; i < count; i = i + 256u) {
                let mem_addr = base_addr + i;
                let mem_idx = mem_addr % 256u;
                cpus[cpu_id].registers[i + shared_op1.y] = cpus[cpu_id].memory[mem_idx];
            }
        }
    } else if (opcode == OPCODE_PARALLEL_ST) {
        if (shared_op2.x == 2u && shared_op3.y > 0u) {
            let base_addr = shared_op1.y;
            let rs_base = shared_op2.y;
            let count = shared_op3.y;
            // All 256 threads participate in storing
            for (var i = thread_id; i < count; i = i + 256u) {
                let mem_addr = base_addr + i;
                let mem_idx = mem_addr % 256u;
                cpus[cpu_id].memory[mem_idx] = cpus[cpu_id].registers[i + rs_base];
            }
        }
    } else if (opcode == OPCODE_PARALLEL_ADD) {
        if (shared_op1.x == 2u && shared_op2.x == 2u && shared_op3.x == 2u && shared_op4.y > 0u) {
            let count = shared_op4.y;
            // All 256 threads participate in addition
            for (var i = thread_id; i < count; i = i + 256u) {
                cpus[cpu_id].registers[i + shared_op1.y] = cpus[cpu_id].registers[i + shared_op2.y] + cpus[cpu_id].registers[i + shared_op3.y];
            }
        }
    } else if (opcode == OPCODE_PARALLEL_SUB) {
        if (shared_op1.x == 2u && shared_op2.x == 2u && shared_op3.x == 2u && shared_op4.y > 0u) {
            let count = shared_op4.y;
            // All 256 threads participate in subtraction
            for (var i = thread_id; i < count; i = i + 256u) {
                cpus[cpu_id].registers[i + shared_op1.y] = cpus[cpu_id].registers[i + shared_op2.y] - cpus[cpu_id].registers[i + shared_op3.y];
            }
        }
    } else if (opcode == OPCODE_PARALLEL_REDUCE_SUM) {
        if (shared_op1.x == 2u && shared_op3.y > 0u) {
            let base_addr = shared_op2.y;
            let count = shared_op3.y;
            
            // Phase 1: Local reduction per thread
            var local_sum: u32 = 0u;
            for (var i = thread_id; i < count; i = i + 256u) {
                let mem_addr = base_addr + i;
                let mem_idx = mem_addr % 256u;
                local_sum = local_sum + cpus[cpu_id].memory[mem_idx];
            }
            reduction_scratch[thread_id] = local_sum;
            
            // Wait for all threads to finish local sum
            workgroupBarrier();
            
            // Phase 2: Final sum by thread 0
            if (thread_id == 0u) {
                var final_sum: u32 = 0u;
                // Sum up to min(count, 256u) because threads beyond count have local_sum = 0
                let active_threads = select(256u, count, count < 256u);
                for (var i = 0u; i < active_threads; i = i + 1u) {
                    final_sum = final_sum + reduction_scratch[i];
                }
                cpus[cpu_id].registers[shared_op1.y] = final_sum;
            }
        }
    } else if (opcode == OPCODE_HALT) {
        if (thread_id == 0u) {
            cpus[cpu_id].running = 0u;
        }
    }
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
        self.wgpu = None

    async def initialize(self):
        """Initialize WebGPU device and pipeline."""
        try:
            self.wgpu = __import__('wgpu')
            self.device = self.wgpu.utils.get_default_device()

            # Create shader module
            self.shader_module = self.device.create_shader_module(
                code=WGSL_SHADER
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

        # Flatten to RGBA32 array (4 x u32 per pixel)
        flat_data = rgba.reshape(-1, 4)

        # Create storage buffer
        buffer = self.device.create_buffer(
            size=len(flat_data) * 4 * 4,  # 4 channels * 4 bytes per u32
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST,
        )

        self.device.queue.write_buffer(buffer, 0, flat_data.tobytes())

        return buffer, width, height

    def create_cpu_instances(self, num_cpus: int = 1000):
        """Create buffer for multiple CPU instances."""
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
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST | self.wgpu.BufferUsage.COPY_SRC,
        )
        self.device.queue.write_buffer(buffer, 0, cpu_data)

        return buffer

    def create_output_buffer(self, size: int = 1024):
        """Create output buffer for PRT operations."""
        buffer = self.device.create_buffer(
            size=size * 4,  # u32 per output
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST | self.wgpu.BufferUsage.COPY_SRC,
        )
        return buffer

    def run(self, rom_buffer, image_width, image_height, cpus_buffer, output_buffer, num_cpus: int = 1000, dispatches: int = 100):
        """Run spatial CPUs on GPU."""

        # Create uniform buffer
        uniform_data = struct.pack('IIII', dispatches, output_buffer.size // 4 // num_cpus, image_width, image_height)
        uniform_buffer = self.device.create_buffer(
            size=16,
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
                        "size": 16,
                    },
                },
            ],
        )

        # Encode commands
        command_encoder = self.device.create_command_encoder()

        # Run compute shader multiple times (simulating instruction loop)
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
    rom_buffer, width, height = engine.load_program_image("demo_glyph_simple.png")
    print(f"✓ Program loaded as GPU buffer: {width}x{height}")

    # Create CPU instances
    num_cpus = 10  # Start small
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