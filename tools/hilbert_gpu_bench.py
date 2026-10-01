#!/usr/bin/env python3
"""
hilbert_gpu_bench.py - Fair CPU-vs-GPU benchmark for Hilbert-curve RAM->pixel
scatter, the one piece of the boot-trace pipeline that is genuinely
parallel and non-branchy (a real candidate for the "GPU is faster" theory,
unlike OS kernel execution).

Both paths precompute/cache the Hilbert (x,y) LUT once and exclude it from
the timed region, so neither side wins on a strawman. Timed region:
  CPU:  NumPy fancy-indexing scatter (same code path as qemu_to_mkv.py's
        map_ram_to_pixels, which already uses a cached LUT).
  GPU:  upload RAM buffer -> dispatch compute shader -> read back result.
        PCIe transfer both ways is included, since a real pipeline pays it.
"""

import sys
import time
from pathlib import Path

import numpy as np
import wgpu
import wgpu.utils

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qemu_to_mkv import hilbert_d2xy, _hilbert_cache


def build_lut(width: int, height: int) -> np.ndarray:
    """Same LUT construction as map_ram_to_pixels, cached the same way."""
    key = (width, height)
    if key not in _hilbert_cache:
        n = max(width, height)
        total_pixels = width * height
        y_coords = np.zeros(total_pixels, dtype=np.int32)
        x_coords = np.zeros(total_pixels, dtype=np.int32)
        for pixel_idx in range(total_pixels):
            x, y = hilbert_d2xy(n, pixel_idx)
            x_coords[pixel_idx] = x
            y_coords[pixel_idx] = y
        valid = (x_coords < width) & (y_coords < height)
        _hilbert_cache[key] = (y_coords[valid], x_coords[valid], valid)
    return _hilbert_cache[key]


def cpu_scatter(ram_data: bytes, width: int, height: int, y_coords, x_coords, valid) -> np.ndarray:
    total_pixels = width * height
    required_bytes = total_pixels * 3
    if len(ram_data) < required_bytes:
        ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
    else:
        ram_data = ram_data[:required_bytes]

    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    ram_pixels = np.frombuffer(ram_data, dtype=np.uint8).reshape(total_pixels, 3)
    pixels[y_coords, x_coords] = ram_pixels[valid]
    return pixels


class GpuScatter:
    def __init__(self, width: int, height: int, y_coords, x_coords, valid):
        self.width = width
        self.height = height
        self.total_pixels = width * height

        # Pack the same LUT the CPU uses into (x<<16 | y) per pixel_idx,
        # in linear byte order (pixel_idx = 0..total_pixels-1). Invalid
        # (out-of-bounds) entries point at pixel (0,0); their source bytes
        # are zero-padding anyway since valid masks the same positions.
        full_x = np.zeros(self.total_pixels, dtype=np.uint32)
        full_y = np.zeros(self.total_pixels, dtype=np.uint32)
        n = max(width, height)
        valid_idx = np.nonzero(valid)[0]
        full_x[valid_idx] = x_coords
        full_y[valid_idx] = y_coords
        lut_packed = (full_x << 16) | full_y

        device = wgpu.utils.get_default_device()
        self.device = device
        self.queue = device.queue

        shader_path = Path(__file__).resolve().parent / "hilbert_scatter.wgsl"
        shader_code = shader_path.read_text()
        self.shader_module = device.create_shader_module(code=shader_code)

        self.lut_buffer = device.create_buffer(
            size=lut_packed.nbytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        )
        self.queue.write_buffer(self.lut_buffer, 0, lut_packed.tobytes())

        ram_bytes = self.total_pixels * 3
        ram_words = (ram_bytes + 3) // 4
        self.ram_buffer = device.create_buffer(
            size=ram_words * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
        )

        out_bytes = self.total_pixels * 4
        self.out_buffer = device.create_buffer(
            size=out_bytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST,
        )

        dims = np.array([width, height, self.total_pixels, 0], dtype=np.uint32)
        self.dims_buffer = device.create_buffer(
            size=dims.nbytes,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self.queue.write_buffer(self.dims_buffer, 0, dims.tobytes())

        bind_group_layout = device.create_bind_group_layout(entries=[
            {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
            {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
            {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
            {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
        ])
        self.bind_group = device.create_bind_group(
            layout=bind_group_layout,
            entries=[
                {'binding': 0, 'resource': {'buffer': self.ram_buffer, 'offset': 0, 'size': self.ram_buffer.size}},
                {'binding': 1, 'resource': {'buffer': self.lut_buffer, 'offset': 0, 'size': self.lut_buffer.size}},
                {'binding': 2, 'resource': {'buffer': self.out_buffer, 'offset': 0, 'size': self.out_buffer.size}},
                {'binding': 3, 'resource': {'buffer': self.dims_buffer, 'offset': 0, 'size': self.dims_buffer.size}},
            ],
        )
        pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
        self.pipeline = device.create_compute_pipeline(
            layout=pipeline_layout,
            compute={"module": self.shader_module, "entry_point": "main"},
        )

    def scatter(self, ram_data: bytes) -> np.ndarray:
        required_bytes = self.total_pixels * 3
        if len(ram_data) < required_bytes:
            ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
        else:
            ram_data = ram_data[:required_bytes]
        pad = (-len(ram_data)) % 4
        if pad:
            ram_data = ram_data + b'\x00' * pad

        self.queue.write_buffer(self.ram_buffer, 0, ram_data)

        encoder = self.device.create_command_encoder()
        pass_enc = encoder.begin_compute_pass()
        pass_enc.set_pipeline(self.pipeline)
        pass_enc.set_bind_group(0, self.bind_group)
        workgroups = (self.total_pixels + 255) // 256
        pass_enc.dispatch_workgroups(workgroups)
        pass_enc.end()
        self.queue.submit([encoder.finish()])

        raw = self.queue.read_buffer(self.out_buffer)
        packed = np.frombuffer(raw, dtype=np.uint32).reshape(self.height, self.width)
        rgb = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        rgb[:, :, 0] = packed & 0xFF
        rgb[:, :, 1] = (packed >> 8) & 0xFF
        rgb[:, :, 2] = (packed >> 16) & 0xFF
        return rgb


def main():
    tiles = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    width = height = 1024
    tile_size = width * height * 3  # 3MB tile, matches one qemu_to_mkv tile
    total_size = tile_size * tiles
    print(f"Grid: {width}x{height} x {tiles} tile(s), total RAM payload: {total_size / (1024*1024):.2f} MB")

    rng = np.random.default_rng(42)
    tile_buffers = [rng.integers(0, 256, size=tile_size, dtype=np.uint8).tobytes() for _ in range(tiles)]

    print("\nBuilding Hilbert LUT (excluded from timed region, cached like production code)...")
    t0 = time.perf_counter()
    y_coords, x_coords, valid = build_lut(width, height)
    print(f"  LUT build: {time.perf_counter() - t0:.3f}s (one-time cost)")

    print("\nWarming up GPU pipeline (buffer/pipeline creation excluded from timed region)...")
    gpu = GpuScatter(width, height, y_coords, x_coords, valid)
    gpu.scatter(tile_buffers[0])  # warm-up dispatch, not timed

    n_runs = 20

    print(f"\nCPU (NumPy vectorized scatter, cached LUT), {n_runs} runs over {tiles} tile(s) each:")
    cpu_times = []
    cpu_results = None
    for _ in range(n_runs):
        t0 = time.perf_counter()
        cpu_results = [cpu_scatter(buf, width, height, y_coords, x_coords, valid) for buf in tile_buffers]
        cpu_times.append(time.perf_counter() - t0)
    print(f"  mean={np.mean(cpu_times)*1000:.3f}ms  min={min(cpu_times)*1000:.3f}ms  max={max(cpu_times)*1000:.3f}ms")

    print(f"\nGPU (upload + dispatch + readback), {n_runs} runs over {tiles} tile(s) each:")
    gpu_times = []
    gpu_results = None
    for _ in range(n_runs):
        t0 = time.perf_counter()
        gpu_results = [gpu.scatter(buf) for buf in tile_buffers]
        gpu_times.append(time.perf_counter() - t0)
    print(f"  mean={np.mean(gpu_times)*1000:.3f}ms  min={min(gpu_times)*1000:.3f}ms  max={max(gpu_times)*1000:.3f}ms")

    match = all(np.array_equal(c, g) for c, g in zip(cpu_results, gpu_results))
    print(f"\nCorrectness: CPU and GPU outputs {'MATCH' if match else 'DIFFER'} across all {tiles} tile(s)")
    if not match:
        for i, (c, g) in enumerate(zip(cpu_results, gpu_results)):
            if not np.array_equal(c, g):
                diff = np.argwhere(c != g)
                print(f"  tile {i}: {len(diff)} differing byte positions, first few: {diff[:5].tolist()}")

    speedup = np.mean(cpu_times) / np.mean(gpu_times)
    throughput_cpu = (total_size / (1024*1024)) / (np.mean(cpu_times))
    throughput_gpu = (total_size / (1024*1024)) / (np.mean(gpu_times))
    print(f"\nThroughput: CPU={throughput_cpu:.1f} MB/s  GPU={throughput_gpu:.1f} MB/s")
    print(f"Result: GPU is {speedup:.2f}x {'faster' if speedup > 1 else 'slower'} than vectorized NumPy")
    return 0 if match else 1


if __name__ == '__main__':
    sys.exit(main())
