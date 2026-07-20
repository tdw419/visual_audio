#!/usr/bin/env python3
"""
MINIMAL WGSL Glyph Engine - Simplified to avoid naga panic

This is a minimal test of GPU-native glyph execution that avoids:
- Pointer dereferencing
- Complex expression trees
- Nested function calls

Instead, it uses direct array indexing and linear execution.
"""

import wgpu
import struct
import numpy as np
import argparse
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.mkv_glyph_emulator import OpcodeMap, GlyphAssembler, GlyphCPU

# Minimal WGSL shader - no pointers, no complex expressions
MINIMAL_WGSL = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

// Buffer bindings
@group(0) @binding(0) var<storage, read> rom: array<Pixel>;        // Program image
@group(0) @binding(1) var<storage, read_write> output: array<u32>;  // Output buffer
@group(0) @binding(2) var<storage, read> uniforms: array<u32>;      // Image dimensions

struct Uniforms {
    image_width: u32,
    image_height: u32,
    output_offset: u32,
    padding: u32,
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let idx = global_id.x;
    let width = uniforms[0];
    let height = uniforms[1];

    // Bounds check
    if (idx >= width * height) {
        return;
    }

    // Read pixel from ROM
    let pixel = rom[idx];

    // Write RGB sum to output (simple computation)
    let rgb_sum = pixel.r + pixel.g + pixel.b;
    output[idx] = rgb_sum;
}
"""


class MinimalWGSEngine:
    """Minimal WGSL engine for testing GPU execution without panics"""

    def __init__(self):
        self.wgpu = wgpu
        self.device = None
        self.compute_pipeline = None

    async def initialize(self):
        """Initialize WebGPU device"""
        try:
            adapter = await self.wgpu.gpu.request_adapter_async(
                power_preference="high-performance"
            )
            self.device = await adapter.request_device_async()
            print("✓ WebGPU device initialized")
            return True
        except Exception as e:
            print(f"✗ WebGPU initialization failed: {e}")
            return False

    def load_program_image(self, image_path: str):
        """Load program image as GPU buffer"""
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        width, height = img.size
        pixels = np.array(img)

        # Flatten to (width*height, 4) RGBA
        buffer_data = np.zeros((width * height, 4), dtype=np.uint32)
        buffer_data[:, 0] = pixels[:, :, 0]  # R
        buffer_data[:, 1] = pixels[:, :, 1]  # G
        buffer_data[:, 2] = pixels[:, :, 2]  # B
        buffer_data[:, 3] = 255  # A

        # Create GPU buffer
        rom_buffer = self.device.create_buffer(
            size=buffer_data.nbytes,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(rom_buffer, 0, buffer_data.tobytes())

        return rom_buffer, width, height

    def create_output_buffer(self, size: int):
        """Create storage buffer for GPU output (NOT mappable)"""
        return self.device.create_buffer(
            size=size * 4,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_SRC,
        )

    def create_staging_buffer(self, size: int):
        """Create staging buffer for readback (mappable, COPY_DST only)"""
        return self.device.create_buffer(
            size=size * 4,
            usage=self.wgpu.BufferUsage.MAP_READ | self.wgpu.BufferUsage.COPY_DST,
        )

    def create_uniform_buffer(self, width: int, height: int):
        """Create uniform buffer"""
        data = np.array([width, height, 0, 0], dtype=np.uint32)
        uniform_buffer = self.device.create_buffer(
            size=16,
            usage=self.wgpu.BufferUsage.STORAGE | self.wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(uniform_buffer, 0, data.tobytes())
        return uniform_buffer

    def compile_shader(self):
        """Compile minimal WGSL shader"""
        try:
            shader_module = self.device.create_shader_module(code=MINIMAL_WGSL)
            print("✓ WGSL shader compiled successfully")

            # Create bind group layout
            bind_group_layout = self.device.create_bind_group_layout(
                entries=[
                    {
                        "binding": 0,
                        "visibility": self.wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": "read-only-storage"},
                    },
                    {
                        "binding": 1,
                        "visibility": self.wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": "storage"},
                    },
                    {
                        "binding": 2,
                        "visibility": self.wgpu.ShaderStage.COMPUTE,
                        "buffer": {"type": "read-only-storage"},
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
                compute={"module": shader_module, "entry_point": "main"},
            )
            print("✓ Compute pipeline created")
            return True
        except Exception as e:
            print(f"✗ Shader compilation failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_compute(
        self, rom_buffer, width: int, height: int, output_buffer, uniform_buffer
    ):
        """Run compute shader"""
        # Create bind group
        bind_group = self.device.create_bind_group(
            layout=self.compute_pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": 0, "resource": {"buffer": rom_buffer, "offset": 0, "size": rom_buffer.size}},
                {
                    "binding": 1,
                    "resource": {"buffer": output_buffer, "offset": 0, "size": output_buffer.size},
                },
                {
                    "binding": 2,
                    "resource": {"buffer": uniform_buffer, "offset": 0, "size": 16},
                },
            ],
        )

        # Encode commands
        command_encoder = self.device.create_command_encoder()
        compute_pass = command_encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.compute_pipeline)
        compute_pass.set_bind_group(0, bind_group)

        # Dispatch workgroups (64 threads per workgroup)
        num_pixels = width * height
        num_workgroups = (num_pixels + 63) // 64
        compute_pass.dispatch_workgroups(num_workgroups)
        compute_pass.end()

        self.device.queue.submit([command_encoder.finish()])
        print(f"✓ Executed {num_pixels} pixels in {num_workgroups} workgroups")

    async def read_output(self, output_buffer, size: int):
        """Read output buffer from GPU using staging buffer"""
        staging_buffer = self.device.create_buffer(
            size=size * 4,
            usage=self.wgpu.BufferUsage.MAP_READ | self.wgpu.BufferUsage.COPY_DST,
        )

        command_encoder = self.device.create_command_encoder()
        command_encoder.copy_buffer_to_buffer(output_buffer, 0, staging_buffer, 0, size * 4)
        self.device.queue.submit([command_encoder.finish()])

        # Map asynchronously and wait for completion
        await staging_buffer.map_async(self.wgpu.MapMode.READ)

        # Read mapped data
        output_data = staging_buffer.read_mapped()
        values = struct.unpack(f"{size}I", output_data)
        return values


async def demo():
    """Demonstrate minimal WGSL execution"""

    print("=" * 60)
    print("MINIMAL WGSL GLYPH ENGINE DEMO")
    print("=" * 60)

    engine = MinimalWGSEngine()

    # Initialize WebGPU
    if not await engine.initialize():
        print("Demo aborted")
        return

    # Compile shader
    if not engine.compile_shader():
        print("Demo aborted - shader compilation failed")
        return

    # Create test program
    print("\n[1] Creating test program image...")
    opcode_map = OpcodeMap()
    assembler = GlyphAssembler(opcode_map)
    program = [
        "LDI R0 5",
        "LDI R1 10",
        "ADD R0 R1",
        "PRT R0",
        "HALT",
    ]
    pixels = assembler.assemble_to_pixels(program)
    height, width, _ = pixels.shape
    print(f"  ✓ Program assembled: {len(program)} instructions → {width}×{height} pixels")

    # Save program image
    test_image = "/tmp/minimal_test_glyph.png"
    from PIL import Image
    img = Image.fromarray(pixels.astype(np.uint8), mode='RGB')
    img.save(test_image)
    print(f"  ✓ Saved to {test_image}")

    # Load program image
    print("\n[2] Loading program image into GPU...")
    rom_buffer, img_width, img_height = engine.load_program_image(test_image)
    print(f"  ✓ Loaded {img_width}×{img_height} pixels into GPU")

    # Create buffers
    print("\n[3] Creating GPU buffers...")
    output_buffer = engine.create_output_buffer(img_width * img_height)
    uniform_buffer = engine.create_uniform_buffer(img_width, img_height)
    print("  ✓ Output buffer and uniform buffer created")

    # Run compute shader
    print("\n[4] Running compute shader...")
    engine.run_compute(rom_buffer, img_width, img_height, output_buffer, uniform_buffer)

    # Read results
    print("\n[5] Reading results from GPU...")
    results = await engine.read_output(output_buffer, img_width * img_height)

    # Display sample results
    print("\n[6] Sample results (first 10 pixels):")
    for i in range(min(10, len(results))):
        print(f"  Pixel {i}: RGB sum = {results[i]}")

    print("\n" + "=" * 60)
    print("MINIMAL WGSL DEMO COMPLETE")
    print("=" * 60)
    print("\n✓ WGSL shader compiled and executed successfully")
    print("✓ GPU-native pixel access working")
    print("✓ Compute pipeline functional")
    print("\nNext steps:")
    print("  - Add opcode decoding logic")
    print("  - Implement CPU state in storage buffer")
    print("  - Add fetch-decode-execute loop")


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo())