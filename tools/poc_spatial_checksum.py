#!/usr/bin/env python3
"""
Spatial Checksum PoC: parallel-reduction checksum on the GPU vs a sequential
CPU checksum, over data encoded the same way pixelrts_v2_converter.py does.

Proves the hybrid model: CPU stays in charge of orchestration, a
data-parallel subsystem (checksum / reduction) is offloaded to a spatial
(Hilbert-mappable) compute pass and runs in O(log N) depth instead of O(N).

Usage:
    python3 tools/poc_spatial_checksum.py [--grid-size 256] [--random]
"""
import argparse
import time

import numpy as np
import wgpu
import wgpu.utils

SHADER_PATH = "tools/spatial_checksum.wgsl"
WORKGROUP = 16  # matches @workgroup_size(16, 16) in the shader


def encode_pixelrts_bytes(data: bytes, grid_size: int) -> np.ndarray:
    """Pack raw bytes into u32s using pixelrts_v2_converter.py's id_val = byte + 16
    scheme (r<<16 | g<<8 | b), zero-padded to grid_size*grid_size. Row-major, not
    Hilbert-ordered here since the shader only needs the packed byte value per cell,
    not spatial adjacency."""
    n = grid_size * grid_size
    if len(data) > n:
        raise ValueError(f"data size {len(data)} exceeds grid capacity {n}")
    padded = np.zeros(n, dtype=np.uint8)
    padded[: len(data)] = np.frombuffer(data, dtype=np.uint8)
    id_vals = padded.astype(np.uint32) + 16
    return id_vals  # already fits in low 24 bits, matches (r<<16|g<<8|b) unpack


def cpu_checksum(data: bytes) -> int:
    return int(sum(data))


def gpu_checksum(id_vals: np.ndarray, grid_size: int) -> tuple[int, float]:
    device = wgpu.utils.get_default_device()
    queue = device.queue

    with open(SHADER_PATH) as f:
        shader_code = f.read()

    memory_texture = device.create_texture(
        size=(grid_size, grid_size, 1),
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
        dimension="2d",
        format=wgpu.TextureFormat.r32uint,
    )
    queue.write_texture(
        {"texture": memory_texture},
        id_vals.tobytes(),
        {"bytes_per_row": grid_size * 4, "rows_per_image": grid_size},
        (grid_size, grid_size, 1),
    )
    memory_view = memory_texture.create_view()

    groups_per_row = (grid_size + WORKGROUP - 1) // WORKGROUP
    num_blocks = groups_per_row * groups_per_row
    block_sums_buffer = device.create_buffer(
        size=num_blocks * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    params = np.array([grid_size], dtype=np.uint32)
    params_buffer = device.create_buffer(
        size=params.nbytes,
        usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
    )
    queue.write_buffer(params_buffer, 0, params.tobytes())

    bind_group_layout = device.create_bind_group_layout(entries=[
        {"binding": 0, "visibility": wgpu.ShaderStage.COMPUTE, "texture": {"sample_type": "uint", "view_dimension": "2d"}},
        {"binding": 1, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": "storage"}},
        {"binding": 2, "visibility": wgpu.ShaderStage.COMPUTE, "buffer": {"type": "uniform"}},
    ])
    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {"binding": 0, "resource": memory_view},
            {"binding": 1, "resource": {"buffer": block_sums_buffer, "offset": 0, "size": num_blocks * 4}},
            {"binding": 2, "resource": {"buffer": params_buffer, "offset": 0, "size": params.nbytes}},
        ],
    )

    pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bind_group_layout]),
        compute={
            "module": device.create_shader_module(code=shader_code),
            "entry_point": "parallel_checksum",
        },
    )

    t0 = time.perf_counter()
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(pipeline)
    pass_enc.set_bind_group(0, bind_group)
    pass_enc.dispatch_workgroups(groups_per_row, groups_per_row)
    pass_enc.end()
    queue.submit([encoder.finish()])

    block_sums = np.frombuffer(device.queue.read_buffer(block_sums_buffer), dtype=np.uint32)
    elapsed = time.perf_counter() - t0

    return int(block_sums.sum()), elapsed


def main():
    parser = argparse.ArgumentParser(description="Spatial checksum PoC (parallel reduction)")
    parser.add_argument("--grid-size", type=int, default=256)
    parser.add_argument("--random", action="store_true", help="use random bytes instead of all-ones")
    args = parser.parse_args()

    grid_size = args.grid_size
    n = grid_size * grid_size

    print("=== Spatial Checksum PoC ===")
    print(f"Grid: {grid_size}x{grid_size} ({n} bytes)")

    if args.random:
        rng = np.random.default_rng(0)
        data = rng.integers(0, 256, size=n, dtype=np.uint8).tobytes()
    else:
        data = bytes([1]) * n

    expected = cpu_checksum(data)

    t0 = time.perf_counter()
    cpu_result = cpu_checksum(data)
    cpu_time = time.perf_counter() - t0

    id_vals = encode_pixelrts_bytes(data, grid_size)
    gpu_result, gpu_time = gpu_checksum(id_vals, grid_size)

    print(f"\nCPU sequential sum : {cpu_result} ({cpu_time * 1e3:.3f} ms)")
    print(f"GPU parallel reduce : {gpu_result} ({gpu_time * 1e3:.3f} ms)")
    print(f"Expected            : {expected}")

    ok = gpu_result == expected == cpu_result
    print(f"\nResult: {'PASS ✅' if ok else 'FAIL ❌'}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
