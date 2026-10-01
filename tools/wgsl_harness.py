#!/usr/bin/env python3
"""
WGSL Harness Utility Functions

Extracted from verify_wgsl_glyph_isa_v2.py for reuse in glyph dispatch verification.

Provides:
- run_wgsl(): Execute WGSL shader and return CPU state
- create_bind_group(): Standard WGSL bind group creation
- create_buffers(): Standard WGSL buffer creation
"""

import numpy as np
import wgpu
import wgpu.utils
from typing import Dict, Any, Tuple, Union


def run_wgsl(
    shader_src: str,
    image: np.ndarray,
    cpu_state: np.ndarray,
    cpu_dtype: np.dtype,
    max_steps: int = 200,
) -> Dict[str, Any]:
    """
    Execute WGSL shader and return CPU state.

    Args:
        shader_src: WGSL shader source code
        image: Pixel image (height, width, 3)
        cpu_state: CPU state array (structured numpy array)
        cpu_dtype: CPU state dtype (for binding)
        max_steps: Maximum instructions to execute

    Returns:
        Dict with CPU state as structured array
    """
    # Get device and queue
    device = wgpu.utils.get_default_device()
    queue = device.queue

    # Pack image into RGBA32 (Pixel struct = 4 x u32)
    pixel_data = image.astype(np.uint32)
    n_pixels = pixel_data.shape[0] * pixel_data.shape[1]
    rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
    flat = pixel_data.reshape(n_pixels, 3)
    rgba[:, 0:3] = flat

    # Create image buffer
    image_buffer = device.create_buffer(
        size=rgba.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(image_buffer, 0, rgba.tobytes())

    # Create CPU state buffer
    cpu_buffer = device.create_buffer(
        size=cpu_state.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(cpu_buffer, 0, cpu_state.tobytes())

    # Create output buffer (for debugging)
    output_buffer_size = 64
    output_buffer = device.create_buffer(
        size=output_buffer_size * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(output_buffer, 0, np.zeros(output_buffer_size, dtype=np.uint32).tobytes())

    # Create uniforms (image dimensions, output buffer size)
    uniforms = np.array(
        [(image.shape[1], image.shape[0], output_buffer_size)],
        dtype=np.dtype([('image_width', np.uint32), ('image_height', np.uint32),
                         ('output_buffer_size', np.uint32)]),
    )
    uniform_buffer = device.create_buffer(
        size=uniforms.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(uniform_buffer, 0, uniforms.tobytes())

    # Create bind group layout
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
    ])

    # Create bind group
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {'binding': 0, 'resource': {'buffer': image_buffer, 'offset': 0, 'size': rgba.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buffer, 'offset': 0, 'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': output_buffer, 'offset': 0, 'size': output_buffer_size * 4}},
            {'binding': 3, 'resource': {'buffer': uniform_buffer, 'offset': 0, 'size': uniforms.nbytes}},
        ],
    )

    # Create shader module and pipeline
    shader_module = device.create_shader_module(code=shader_src)
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': shader_module, 'entry_point': 'main'},
    )

    # Execute shader loop (step until halted or max_steps reached)
    step_count = 0

    for _ in range(max_steps):
        encoder = device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(pipeline)
        pass_enc.set_bind_group(0, bind_group)
        pass_enc.dispatch_workgroups(1)
        pass_enc.end()
        queue.submit([encoder.finish()])

        # Read back CPU state
        readback = np.frombuffer(device.queue.read_buffer(cpu_buffer), dtype=cpu_dtype)[0]
        running = readback['running']

        if running == 0:
            break

        step_count += 1

    # Read back final CPU state
    final_state = np.frombuffer(device.queue.read_buffer(cpu_buffer), dtype=cpu_dtype)[0]

    return {
        'cpu_state': final_state,
        'steps': step_count,
        'device': device,
        'queue': queue,
    }


def lockstep_compare(
    cpu_py: Union[Any, Dict[str, Any]],
    cpu_gpu: Dict[str, Any],
    cpu_dtype: np.dtype,
    fields_to_compare: list = None,
) -> Tuple[bool, list]:
    """
    Compare Python and GPU CPU states with detailed mismatch reporting.

    Args:
        cpu_py: Python CPU state (from GlyphCPUv2)
        cpu_gpu: GPU CPU state (from WGSL execution)
        cpu_dtype: CPU state dtype (for field extraction)
        fields_to_compare: List of field names to compare (None = all)

    Returns:
        (is_match, mismatches) where mismatches is list of field descriptions
    """
    mismatches = []

    # Get GPU CPU state from result dict
    if 'cpu_state' in cpu_gpu:
        gpu_state = cpu_gpu['cpu_state']
    else:
        gpu_state = cpu_gpu

    # Determine which fields to compare
    if fields_to_compare is None:
        # Compare basic fields
        fields_to_compare = ['running', 'instr_count']

    for field in fields_to_compare:
        # Extract values
        py_val = None
        gpu_val = None

        if hasattr(cpu_py, field):
            py_val = getattr(cpu_py, field)

        if field in gpu_state.dtype.names:
            gpu_val = gpu_state[field]

        # Handle 64-bit values (vec2<u32>)
        if isinstance(py_val, int):
            py_val_64 = py_val
        elif hasattr(py_val, '__len__') and len(py_val) == 2:
            py_val_64 = py_val[0] | (py_val[1] << 32)
        else:
            py_val_64 = py_val

        # GPU values are stored as vec2<u32> for 64-bit fields
        if isinstance(gpu_val, (int, np.integer)):
            gpu_val_64 = int(gpu_val)
        elif isinstance(gpu_val, np.ndarray) and gpu_val.shape == (2,):
            gpu_val_64 = int(gpu_val[0]) | (int(gpu_val[1]) << 32)
        else:
            gpu_val_64 = gpu_val

        # Compare
        if py_val_64 != gpu_val_64:
            mismatches.append(f"{field}: py={py_val_64}, gpu={gpu_val_64}")

    return len(mismatches) == 0, mismatches


if __name__ == "__main__":
    # Self-test
    print("WGSL harness utilities - ready for import")
    print("Functions available:")
    print("  - run_wgsl()")
    print("  - lockstep_compare()")