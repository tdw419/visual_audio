#!/usr/bin/env python3
"""
Spatial Compiler - Apply VLM-generated patches to VRAM

This is the bridge between the VLM Spatial Observer and the GPU.
It takes patch payloads (JSON from VLM), converts them to WGSL PatchOps,
and dispatches the Spatial Compiler shader to mutate VRAM natively.

Architecture:
  VLM Observer → Patch Payload (JSON) → Python Bridge → WGSL Shader → VRAM Update
"""

import argparse
import json
import struct
import numpy as np
import wgpu
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.spatial_os_kernel_3d import SpatialOS3D


# Patch operation types (matching WGSL constants)
OP_NOP = 0
OP_WRITE_PIXEL = 1
OP_COPY_BLOCK = 2
OP_FILL_RECT = 3
OP_CLEAR_REGION = 4


class SpatialCompiler:
    """Bridge between VLM patches and GPU spatial memory"""

    def __init__(self, os_kernel: SpatialOS3D):
        self.os = os_kernel
        self.device = os_kernel.device
        self.vram_width = os_kernel.vram_width
        self.vram_height = os_kernel.vram_height
        self.vram_depth = os_kernel.vram_depth

        # Load WGSL shader
        shader_path = Path(__file__).parent / "SPATIAL_COMPILER.wgsl"
        with open(shader_path, 'r') as f:
            self.wgsl_code = f.read()

        self.shader = None
        self.pipeline = None
        self._init_pipeline()

    def _init_pipeline(self):
        """Initialize the compute pipeline"""
        self.shader = self.device.create_shader_module(code=self.wgsl_code)

        # Bind group layout
        bind_group_layout = self.device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {
                        "type": wgpu.BufferBindingType.read_only_storage,
                    },
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {
                        "type": wgpu.BufferBindingType.storage,
                    },
                },
                {
                    "binding": 2,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {
                        "type": wgpu.BufferBindingType.read_only_storage,
                    },
                },
                {
                    "binding": 3,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {
                        "type": wgpu.BufferBindingType.uniform,
                    },
                },
            ]
        )

        pipeline_layout = self.device.create_pipeline_layout(
            bind_group_layouts=[bind_group_layout]
        )

        self.pipeline = self.device.create_compute_pipeline(
            layout=pipeline_layout,
            compute={
                "module": self.shader,
                "entry_point": "main",
            }
        )

    def _parse_coordinate(self, coord_str: str) -> tuple:
        """Parse coordinate string like '(16, 20)' or '(16, 20, 0)'"""
        # Remove parentheses and split
        cleaned = coord_str.strip("()")
        parts = [p.strip() for p in cleaned.split(",")]
        coords = tuple(int(p) for p in parts if p)
        
        # Ensure 3D coordinate
        if len(coords) == 2:
            coords = (coords[0], coords[1], 0)  # Default to frame 0
        elif len(coords) != 3:
            raise ValueError(f"Invalid coordinate: {coord_str}")
        
        return coords

    def vlm_patch_to_ops(self, patch_payload: dict) -> list:
        """Convert VLM patch JSON to WGSL PatchOp structures"""
        ops = []

        for patch in patch_payload.get("patches", []):
            patch_type = patch.get("type", "").upper()
            target = patch.get("target", "")
            color = patch.get("color", [236, 80, 80])  # Default LDI color

            # Handle combined types (e.g., "COMPACTION|REALLOCATION|COALESCING")
            # Pick the first matching operation
            ops_to_try = patch_type.split("|")
            processed = False

            for op_to_check in ops_to_try:
                op_to_check = op_to_check.strip()
                if processed:
                    break

                if "WRITE_PIXEL" in op_to_check:
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_WRITE_PIXEL,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "r": color[0],
                            "g": color[1],
                            "b": color[2],
                        })
                        processed = True
                    except ValueError:
                        pass

                elif "FILL_RECT" in op_to_check:
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_FILL_RECT,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "r": color[0],
                            "g": color[1],
                            "b": color[2],
                            "width": 4,
                            "height": 4,
                        })
                        processed = True
                    except ValueError:
                        pass

                elif "CLEAR_REGION" in op_to_check or "COALESCING" in op_to_check:
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_CLEAR_REGION,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "width": 4,
                            "height": 4,
                        })
                        processed = True
                    except ValueError:
                        pass

                elif "COMPACTION" in op_to_check:
                    try:
                        coords = self._parse_coordinate(target)
                        ops.append({
                            "op_type": OP_FILL_RECT,
                            "x": coords[0],
                            "y": coords[1],
                            "z": coords[2],
                            "r": 236,
                            "g": 80,
                            "b": 80,
                            "width": 4,
                            "height": 4,
                        })
                        processed = True
                    except ValueError:
                        pass

                elif "REALLOCATION" in op_to_check:
                    try:
                        if " to " in target:
                            parts = target.split(" to ")
                            src_coords = self._parse_coordinate(parts[0].replace("from ", ""))
                            dest_coords = self._parse_coordinate(parts[1])

                            ops.append({
                                "op_type": OP_COPY_BLOCK,
                                "x": dest_coords[0],
                                "y": dest_coords[1],
                                "z": dest_coords[2],
                                "width": 4,
                                "height": 4,
                                "src_x": src_coords[0],
                                "src_y": src_coords[1],
                                "src_z": src_coords[2],
                            })
                            processed = True
                    except ValueError:
                        pass

        return ops

    def apply_patch(self, patch_payload: dict, verify: bool = True) -> bool:
        """Apply a patch payload to VRAM"""
        print("=" * 60)
        print("SPATIAL COMPILER")
        print("=" * 60)

        # Convert VLM patch to operations
        print(f"\n[1] Parsing VLM patch payload...")
        ops = self.vlm_patch_to_ops(patch_payload)
        print(f"  ✓ Generated {len(ops)} operations")

        if len(ops) == 0:
            print("  WARNING: No valid operations found")
            return False

        # Create GPU buffers for patch operations
        print(f"\n[2] Allocating GPU buffers...")

        # Patch ops buffer
        patch_data = np.zeros(len(ops) * 13, dtype=np.uint32)
        for i, op in enumerate(ops):
            base = i * 13
            patch_data[base + 0] = op["op_type"]
            patch_data[base + 1] = op.get("x", 0)
            patch_data[base + 2] = op.get("y", 0)
            patch_data[base + 3] = op.get("z", 0)
            patch_data[base + 4] = op.get("r", 0)
            patch_data[base + 5] = op.get("g", 0)
            patch_data[base + 6] = op.get("b", 0)
            patch_data[base + 7] = op.get("width", 1)
            patch_data[base + 8] = op.get("height", 1)
            patch_data[base + 9] = op.get("src_x", 0)
            patch_data[base + 10] = op.get("src_y", 0)
            patch_data[base + 11] = op.get("src_z", 0)
            patch_data[base + 12] = 0

        patch_buf = self.device.create_buffer(
            size=patch_data.nbytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(patch_buf, 0, patch_data.tobytes())
        print(f"  ✓ Patch buffer: {len(patch_data)} u32s ({patch_data.nbytes} bytes)")

        # Op count buffer
        count_buf = self.device.create_buffer(
            size=4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(count_buf, 0, struct.pack("I", len(ops)))
        print(f"  ✓ Op count: {len(ops)}")

        # Uniforms buffer
        uniform_data = struct.pack("III", self.vram_width, self.vram_height, self.vram_depth)
        uniform_buf = self.device.create_buffer(
            size=12,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(uniform_buf, 0, uniform_data)
        print(f"  ✓ Uniforms: {self.vram_width}x{self.vram_height}x{self.vram_depth}")

        # Create bind group
        bind_group = self.device.create_bind_group(
            layout=self.pipeline.get_bind_group_layout(0),
            entries=[
                {"binding": 0, "resource": {"buffer": patch_buf, "offset": 0, "size": patch_data.nbytes}},
                {"binding": 1, "resource": {"buffer": self.os.vram_buf, "offset": 0, "size": self.os.vram_buf.size}},
                {"binding": 2, "resource": {"buffer": count_buf, "offset": 0, "size": 4}},
                {"binding": 3, "resource": {"buffer": uniform_buf, "offset": 0, "size": 12}},
            ]
        )

        # Dispatch compute shader
        print(f"\n[3] Dispatching compute shader...")
        workgroups = (len(ops) + 63) // 64
        command_encoder = self.device.create_command_encoder()

        compute_pass = command_encoder.begin_compute_pass()
        compute_pass.set_pipeline(self.pipeline)
        compute_pass.set_bind_group(0, bind_group, [], 0, 999999)
        compute_pass.dispatch_workgroups(workgroups)
        compute_pass.end()

        self.device.queue.submit([command_encoder.finish()])
        print(f"  ✓ Dispatched {workgroups} workgroups")

        # Verify patch application
        if verify:
            print(f"\n[4] Verifying patch application...")
            self._verify_operations(ops)
            print(f"  ✓ Verification complete")

        print(f"\n" + "=" * 60)
        print("PATCH APPLIED SUCCESSFULLY")
        print("=" * 60)
        return True

    def _verify_operations(self, ops: list):
        """Verify that operations were applied correctly"""
        data = self.os.device.queue.read_buffer(self.os.vram_buf)
        pixels = np.frombuffer(data, dtype=np.uint32).reshape(
            self.vram_depth, self.vram_height, self.vram_width, 4
        ).astype(np.uint8)

        verified = 0
        checked = 0

        for i, op in enumerate(ops):
            op_type = op["op_type"]
            x, y, z = op.get("x", 0), op.get("y", 0), op.get("z", 0)
            r, g, b = op.get("r", 0), op.get("g", 0), op.get("b", 0)
            width, height = op.get("width", 1), op.get("height", 1)

            if op_type == OP_WRITE_PIXEL:
                if x < self.vram_width and y < self.vram_height and z < self.vram_depth:
                    actual = pixels[z, y, x, :3]
                    if (actual[0], actual[1], actual[2]) == (r, g, b):
                        verified += 1
                    else:
                        print(f"  WARNING: Op {i} mismatch at ({x}, {y}, {z})")
                    checked += 1

            elif op_type == OP_FILL_RECT or op_type == OP_CLEAR_REGION:
                all_match = True
                rect_checked = 0
                for dy in range(height):
                    for dx in range(width):
                        px, py = x + dx, y + dy
                        if px < self.vram_width and py < self.vram_height and z < self.vram_depth:
                            actual = pixels[z, py, px, :3]
                            expected = (r, g, b) if op_type == OP_FILL_RECT else (0, 0, 0)
                            if (actual[0], actual[1], actual[2]) != expected:
                                all_match = False
                            rect_checked += 1

                if rect_checked > 0 and all_match:
                    verified += 1
                checked += rect_checked

        print(f"  Verified {verified}/{len(ops)} operations ({checked} pixels checked)")

    def create_test_patch(self) -> dict:
        """Create a test patch for verification"""
        return {
            "version": "1.0",
            "source": "Test Script",
            "patches": [
                {
                    "type": "WRITE_PIXEL",
                    "target": "(5, 5)",
                    "rationale": "Test pixel write",
                    "color": [236, 80, 80],
                },
                {
                    "type": "FILL_RECT",
                    "target": "(10, 10)",
                    "rationale": "Test fill rect",
                    "color": [80, 236, 120],
                },
                {
                    "type": "CLEAR_REGION",
                    "target": "(20, 20)",
                    "rationale": "Test clear region",
                },
            ]
        }


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Compiler - Apply VLM patches to VRAM"
    )
    parser.add_argument(
        "--patch-file",
        type=str,
        help="JSON file containing VLM patch payload",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run with test patch",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip verification step",
    )

    args = parser.parse_args()

    # Initialize Spatial OS kernel
    print("\nBooting Spatial OS 3D Kernel...")
    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    # Initialize Spatial Compiler
    print("\nInitializing Spatial Compiler...")
    compiler = SpatialCompiler(os_kernel)

    # Load patch
    if args.test:
        print("\nUsing test patch...")
        patch = compiler.create_test_patch()
    elif args.patch_file:
        print(f"\nLoading patch from {args.patch_file}...")
        with open(args.patch_file, 'r') as f:
            patch = json.load(f)
    else:
        print("\nERROR: Specify --patch-file or --test")
        sys.exit(1)

    # Apply patch
    success = compiler.apply_patch(patch, verify=not args.no_verify)

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()