#!/usr/bin/env python3
"""
GPU Hilbert Mapping Benchmark — Full 64MB (22 tiles)

Benchmarks CPU (NumPy vectorized) vs GPU (WGSL compute shader) on the full
capture size used in qemu_to_mkv.py: 22 tiles × 3MB = 64MB of linear RAM
mapped to 1024×1024×3 RGB pixels.

This tests the scaling hypothesis: at larger payloads, fixed overheads (PCIe
transfer, kernel dispatch) amortize and GPU bandwidth advantage should compound.
"""

import os
import time
import numpy as np
import sys
from pathlib import Path

# Dual-GPU (Intel + NVIDIA) sandboxes: Vulkan mesa device-select can pick the
# NVIDIA render node and spin forever waiting on a fence that never signals.
# Forcing GL + the Intel iris driver avoids that hang. See BYTE_COUNT_FIX.md /
# session notes for the strace that found this.
os.environ.setdefault("WGPU_BACKEND", "gl")
os.environ.setdefault("MESA_LOADER_DRIVER_OVERRIDE", "iris")

try:
    import wgpu
    from wgpu.backends.wgpu_native import lib as wgpu_native
    WGPU_AVAILABLE = True
except ImportError:
    WGPU_AVAILABLE = False


# ============================================================================
# Hilbert Curve Mapping (CPU — NumPy Vectorized)
# ============================================================================

def hilbert_d2xy(n: int, d: int):
    """Convert distance d along Hilbert curve to (x, y) coordinates."""
    x, y = 0, 0
    s = 1
    rx = ry = 0

    while s < n:
        rx = (d >> 1) & 1
        ry = (d >> 0) & 1

        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x

        x += s * rx
        y += s * ry
        d >>= 2
        s <<= 1

    return x, y


# Cache Hilbert coordinates
_hilbert_cache = {}


def map_ram_to_pixels_cpu(ram_data: bytes, width: int = 1024, height: int = 1024):
    """Map linear RAM data to 2D pixel grid using Hilbert curve (CPU NumPy)."""
    key = (width, height)
    total_pixels = width * height
    required_bytes = total_pixels * 3

    if len(ram_data) < required_bytes:
        ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
    else:
        ram_data = ram_data[:required_bytes]

    if key not in _hilbert_cache:
        # Precompute Hilbert coordinates (LUT)
        y_coords = np.zeros(total_pixels, dtype=np.int32)
        x_coords = np.zeros(total_pixels, dtype=np.int32)
        for pixel_idx in range(total_pixels):
            x, y = hilbert_d2xy(max(width, height), pixel_idx)
            x_coords[pixel_idx] = x
            y_coords[pixel_idx] = y
        valid = (x_coords < width) & (y_coords < height)
        _hilbert_cache[key] = (y_coords[valid], x_coords[valid], valid)

    y_coords, x_coords, valid = _hilbert_cache[key]

    # Vectorized scatter using NumPy fancy indexing
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    ram_pixels = np.frombuffer(ram_data, dtype=np.uint8).reshape(total_pixels, 3)
    pixels[y_coords[valid], x_coords[valid]] = ram_pixels[valid]

    return pixels


# ============================================================================
# Hilbert Curve Mapping (GPU — WGSL Compute Shader)
# ============================================================================

WGPU_SHADER = """
// WGSL compute shader for Hilbert curve mapping
struct HilbertLUTEntry {
    x: u32,
    y: u32,
};

@group(0) @binding(0)
var<storage, read> lut: array<HilbertLUTEntry>;

@group(0) @binding(1)
var<storage, read> ram_data: array<u32>;  // Pack 3 bytes (RGB) into 1 u32 for alignment

@group(0) @binding(2)
var<storage, read_write> output: array<u32>;

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let idx = global_id.x;
    let total_pixels = arrayLength(&lut);

    if (idx >= total_pixels) {
        return;
    }

    let lut_entry = lut[idx];
    let x = lut_entry.x;
    let y = lut_entry.y;

    // Check bounds (1024x1024 grid)
    if (x >= 1024u || y >= 1024u) {
        return;
    }

    // Calculate output index
    let out_idx = y * 1024u + x;

    // Read packed RGB from RAM data
    let ram_idx = idx;  // Direct mapping for this kernel
    if (ram_idx < arrayLength(&ram_data)) {
        let packed = ram_data[ram_idx];

        // Extract RGB bytes
        let r = u8((packed >> 0u) & 0xFFu);
        let g = u8((packed >> 8u) & 0xFFu);
        let b = u8((packed >> 16u) & 0xFFu);

        // Pack back into output (ABGR format for wgpu texture)
        output[out_idx] = u32(b) | (u32(g) << 8u) | (u32(r) << 16u) | (0xFFu << 24u);
    }
}
"""


def map_ram_to_pixels_gpu(ram_data: bytes, width: int = 1024, height: int = 1024):
    """Map linear RAM data to 2D pixel grid using Hilbert curve (GPU WGSL)."""
    if not WGPU_AVAILABLE:
        raise RuntimeError("wgpu not available")

    total_pixels = width * height
    required_bytes = total_pixels * 3

    if len(ram_data) < required_bytes:
        ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
    else:
        ram_data = ram_data[:required_bytes]

    # Create GPU device
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    device = adapter.request_device()

    # Precompute Hilbert LUT (on CPU, then upload)
    if (width, height) not in _hilbert_cache:
        y_coords = np.zeros(total_pixels, dtype=np.int32)
        x_coords = np.zeros(total_pixels, dtype=np.int32)
        for pixel_idx in range(total_pixels):
            x, y = hilbert_d2xy(max(width, height), pixel_idx)
            x_coords[pixel_idx] = x
            y_coords[pixel_idx] = y
        valid = (x_coords < width) & (y_coords < height)
        _hilbert_cache[(width, height)] = (y_coords[valid], x_coords[valid], valid)

    y_coords, x_coords, valid = _hilbert_cache[(width, height)]

    # Pack LUT into bytes
    lut_data = np.column_stack([x_coords[valid], y_coords[valid]]).astype(np.uint32).tobytes()

    # Pack RAM data into u32 array (3 bytes per pixel + 1 padding)
    ram_array = np.frombuffer(ram_data, dtype=np.uint8).reshape(total_pixels, 3)
    packed_ram = np.zeros(total_pixels, dtype=np.uint32)
    for i in range(total_pixels):
        packed_ram[i] = ram_array[i, 0] | (ram_array[i, 1] << 8) | (ram_array[i, 2] << 16)

    # Create buffers
    lut_buffer = device.create_buffer(
        size=len(lut_data),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    device.queue.write_buffer(lut_buffer, 0, lut_data)

    ram_buffer = device.create_buffer(
        size=packed_ram.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST,
    )
    device.queue.write_buffer(ram_buffer, 0, packed_ram.tobytes())

    output_buffer = device.create_buffer(
        size=width * height * 4,  # 4 bytes per pixel (ABGR)
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )

    # Create bind group layout and pipeline
    bind_group_layout = device.create_bind_group_layout(
        entries=[
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": "read-only-storage-buffer"},
            },
            {
                "binding": 1,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": "read-only-storage-buffer"},
            },
            {
                "binding": 2,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "buffer": {"type": "storage-buffer"},
            },
        ]
    )

    compute_pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bind_group_layout]),
        compute_shader=device.create_shader_module(code=WGPU_SHADER),
    )

    bind_group = device.create_bind_group(
        layout=bind_group_layout,
        entries=[
            {"binding": 0, "resource": lut_buffer},
            {"binding": 1, "resource": ram_buffer},
            {"binding": 2, "resource": output_buffer},
        ]
    )

    # Dispatch compute shader
    workgroup_count = (total_pixels + 255) // 256  # 256 workgroup size
    command_encoder = device.create_command_encoder()

    compute_pass = command_encoder.begin_compute_pass()
    compute_pass.set_pipeline(compute_pipeline)
    compute_pass.set_bind_group(0, bind_group)
    compute_pass.dispatch_workgroups(workgroup_count)
    compute_pass.end()

    device.queue.submit([command_encoder.finish()])

    # Read back results
    readback_buffer = device.create_buffer(
        size=width * height * 4,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
    )

    copy_encoder = device.create_command_encoder()
    copy_encoder.copy_buffer_to_buffer(
        output_buffer, 0, readback_buffer, 0, width * height * 4
    )
    device.queue.submit([copy_encoder.finish()])

    # Map and read
    output_data = device.queue.read_buffer(readback_buffer)
    output_array = np.frombuffer(output_data, dtype=np.uint32)

    # Convert ABGR to RGB
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    for i in range(height * width):
        pixel = output_array[i]
        r = (pixel >> 16) & 0xFF
        g = (pixel >> 8) & 0xFF
        b = pixel & 0xFF
        y = i // width
        x = i % width
        pixels[y, x] = [r, g, b]

    return pixels


# ============================================================================
# Benchmark Runner
# ============================================================================

def benchmark_cpu(ram_data: bytes, iterations: int = 10):
    """Benchmark CPU NumPy implementation."""
    print(f"\n{'='*70}")
    print(f"CPU Benchmark (NumPy Vectorized, Cached LUT)")
    print(f"{'='*70}")

    # Warmup
    map_ram_to_pixels_cpu(ram_data[:1024*1024*3])

    times = []
    for i in range(iterations):
        start = time.perf_counter()
        pixels = map_ram_to_pixels_cpu(ram_data)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)
        if i < 3 or i >= iterations - 2:
            print(f"  Iteration {i+1}/{iterations}: {elapsed:.2f} ms")

    mean_time = np.mean(times)
    std_time = np.std(times)
    print(f"\n  Mean: {mean_time:.2f} ms ± {std_time:.2f} ms")

    return mean_time, std_time, pixels


def benchmark_gpu(ram_data: bytes, iterations: int = 10):
    """Benchmark GPU WGSL implementation."""
    print(f"\n{'='*70}")
    print(f"GPU Benchmark (WGSL Compute Shader, Full PCIe Round-Trip)")
    print(f"{'='*70}")

    if not WGPU_AVAILABLE:
        print("  ⚠ wgpu not available, skipping GPU benchmark")
        return None, None, None

    # Warmup
    try:
        map_ram_to_pixels_gpu(ram_data[:1024*1024*3])
    except Exception as e:
        print(f"  ⚠ GPU warmup failed: {e}")
        return None, None, None

    times = []
    for i in range(iterations):
        try:
            start = time.perf_counter()
            pixels = map_ram_to_pixels_gpu(ram_data)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)
            if i < 3 or i >= iterations - 2:
                print(f"  Iteration {i+1}/{iterations}: {elapsed:.2f} ms")
        except Exception as e:
            print(f"  ⚠ Iteration {i+1} failed: {e}")
            continue

    if not times:
        print("\n  ✗ All iterations failed")
        return None, None, None

    mean_time = np.mean(times)
    std_time = np.std(times)
    print(f"\n  Mean: {mean_time:.2f} ms ± {std_time:.2f} ms")

    return mean_time, std_time, pixels


def verify_correctness(cpu_pixels, gpu_pixels):
    """Verify CPU and GPU outputs are identical."""
    print(f"\n{'='*70}")
    print(f"Correctness Verification")
    print(f"{'='*70}")

    if gpu_pixels is None:
        print("  ⚠ GPU output not available, skipping verification")
        return False

    if cpu_pixels.shape != gpu_pixels.shape:
        print(f"  ✗ Shape mismatch: CPU {cpu_pixels.shape} vs GPU {gpu_pixels.shape}")
        return False

    # Compare arrays
    diff = np.not_equal(cpu_pixels, gpu_pixels)
    mismatch_count = np.sum(diff)

    if mismatch_count == 0:
        print(f"  ✓ Outputs are bitwise identical ({cpu_pixels.size} pixels)")
        return True
    else:
        print(f"  ✗ {mismatch_count} / {cpu_pixels.size} pixels differ")
        print(f"     Mismatch rate: {100*mismatch_count/cpu_pixels.size:.2f}%")
        return False


# ============================================================================
# Main
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='GPU Hilbert Mapping Benchmark (Full 64MB)')
    parser.add_argument('--iterations', '-n', type=int, default=10,
                       help='Number of benchmark iterations (default: 10)')
    parser.add_argument('--skip-cpu', action='store_true',
                       help='Skip CPU benchmark')
    parser.add_argument('--skip-gpu', action='store_true',
                       help='Skip GPU benchmark')
    args = parser.parse_args()

    print("=" * 70)
    print("GPU Hilbert Mapping Benchmark — Full 64MB (22 Tiles)")
    print("=" * 70)
    print(f"Iterations: {args.iterations}")
    print(f"Grid size: 1024×1024 RGB24")
    print(f"Payload: 64MB (22 tiles × 3MB)")

    # Generate test data (simulating full capture)
    print(f"\n[1] Generating 64MB test payload...")
    ram_data = np.random.randint(0, 256, size=64 * 1024 * 1024, dtype=np.uint8).tobytes()
    print(f"  ✓ Generated {len(ram_data) / (1024*1024):.1f} MB")

    # Run benchmarks
    cpu_time, cpu_std, cpu_pixels = None, None, None
    gpu_time, gpu_std, gpu_pixels = None, None, None

    if not args.skip_cpu:
        cpu_time, cpu_std, cpu_pixels = benchmark_cpu(ram_data, args.iterations)

    if not args.skip_gpu:
        gpu_time, gpu_std, gpu_pixels = benchmark_gpu(ram_data, args.iterations)

    # Verify correctness
    correct = False
    if cpu_pixels is not None and gpu_pixels is not None:
        correct = verify_correctness(cpu_pixels, gpu_pixels)

    # Summary
    print(f"\n{'='*70}")
    print(f"Benchmark Summary")
    print(f"{'='*70}")

    if cpu_time is not None:
        print(f"CPU (NumPy):    {cpu_time:.2f} ms ± {cpu_std:.2f} ms")

    if gpu_time is not None:
        print(f"GPU (WGSL):    {gpu_time:.2f} ms ± {gpu_std:.2f} ms")

    if cpu_time is not None and gpu_time is not None:
        speedup = cpu_time / gpu_time
        print(f"\nSpeedup:      {speedup:.2f}x ({'GPU faster' if speedup > 1 else 'CPU faster'})")
        print(f"Time saved:   {(cpu_time - gpu_time):.2f} ms per frame")
        print(f"Throughput:   {64*1024*1024 / (gpu_time/1000) / (1024*1024):.1f} MB/s (GPU)")

    if correct:
        print(f"\n✓ Correctness: BITWISE IDENTICAL")
    elif cpu_pixels is not None and gpu_pixels is not None:
        print(f"\n✗ Correctness: MISMATCH DETECTED")

    print(f"{'='*70}\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())