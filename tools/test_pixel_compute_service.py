#!/usr/bin/env python3
"""End-to-end test client for pixel_compute_service: sends a real
pixel-encoded SPIR-V kernel (parallel_collatz, already proven correct in
parallel_pixels_bench.rs) plus a pixel-encoded input array over the
service's Unix socket, decodes the result PNG, and checks it against a
plain CPU computation of the same Collatz step counts. Fails loudly on any
mismatch - this is a correctness check, not a smoke test.
"""
import json
import socket
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SOCKET_PATH = "/tmp/pixel_compute.sock"
SHADER_PNG = "/tmp/parallel_collatz_pixels.png"
INPUT_PNG = "/tmp/pcs_test_input.png"
OUTPUT_PNG = "/tmp/pcs_test_output.png"


def collatz_steps(x: int) -> int:
    # Must match the shader's/Rust CPU baseline's u32-wrapping arithmetic
    # exactly (3u32.wrapping_mul / .wrapping_add in Rust, plain `%`/`/` in
    # WGSL's u32 type) - a handful of starting values under 2,000,000 have
    # intermediate 3n+1 values that briefly exceed 2^32, so unbounded
    # Python-int math legitimately disagrees with both the GPU and CPU
    # u32 versions for those inputs. Caught this for real: 3/10000
    # mismatches before this fix, all explained by wraparound divergence.
    mask = 0xFFFFFFFF
    steps = 0
    while x > 1:
        x = (x // 2) if x % 2 == 0 else ((3 * x + 1) & mask)
        steps += 1
    return steps


def encode_u32_png(values: np.ndarray, path: str) -> None:
    n = len(values)
    side = int(np.ceil(np.sqrt(n)))
    rgba = np.zeros((side * side, 4), dtype=np.uint8)
    rgba[:n] = values.astype("<u4").view(np.uint8).reshape(n, 4)
    Image.fromarray(rgba.reshape(side, side, 4), "RGBA").save(path)


def decode_u32_png(path: str, n: int) -> np.ndarray:
    img = np.array(Image.open(path).convert("RGBA"))
    flat = img.reshape(-1, 4)[:n]
    return flat.view("<u4").reshape(-1)


def main() -> int:
    if not Path(SHADER_PNG).exists():
        print(f"missing {SHADER_PNG} - run parallel_pixels_bench once first to produce it", file=sys.stderr)
        return 1

    n = 10_000
    inputs = np.array([2 + (i * 2654435761) % 2_000_000 for i in range(n)], dtype=np.uint32)
    expected = np.array([collatz_steps(int(x)) for x in inputs], dtype=np.uint32)

    encode_u32_png(inputs, INPUT_PNG)
    print(f"Encoded {n} u32 inputs into {INPUT_PNG}")

    shader_len = Path(SHADER_PNG.replace(".png", ".spv")).stat().st_size \
        if Path(SHADER_PNG.replace(".png", ".spv")).exists() \
        else Path("systems/geos_pixel_v5/shaders/parallel_collatz.spv").stat().st_size

    req = {
        "action": "run_kernel",
        "shader_png": SHADER_PNG,
        "shader_len": shader_len,
        "input_png": INPUT_PNG,
        "input_len": n * 4,
        "output_png": OUTPUT_PNG,
    }

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(SOCKET_PATH)
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    resp = json.loads(buf.decode())
    print("Service response:", resp)

    if resp.get("status") != "ok":
        print("FAIL: service returned an error", file=sys.stderr)
        return 1

    result = decode_u32_png(OUTPUT_PNG, n)
    if not np.array_equal(result, expected):
        mismatches = np.sum(result != expected)
        print(f"FAIL: {mismatches}/{n} results do not match CPU computation", file=sys.stderr)
        return 1

    print(f"PASS: all {n} results match CPU Collatz computation exactly "
          f"(service reported {resp.get('elements')} elements, {resp.get('elapsed_ms'):.2f}ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
