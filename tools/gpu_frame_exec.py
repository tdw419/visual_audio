#!/usr/bin/env python3
"""
gpu_frame_exec.py — One-frame GPU decode->execute->encode round trip (TASK_SE016).

Closes the loop TASK_SE015 opened: a .glyph program is compiled to pixels
(glyph_to_pixels.py), patched into an MKV frame (va_container.py patch), then
this tool decodes that frame region straight out of the container, runs it on
the GPU via the existing WGSL fetch-decode-execute engine (TASK_SE009,
wgsl_glyph_full_execute.py), and writes the resulting output back into the
container as a small result frame -- one full cycle with the CPU only
orchestrating, no Python-side instruction emulation deciding the outcome.

Scope note: this proves a single round trip, not ongoing GPU-resident
execution. Streaming/residency across many frames is separate, future work
(not part of TASK_SE016).

Usage:
    python3 tools/gpu_frame_exec.py <container.mkv> <frame_id> <x> <y> <w> <h> \\
        [--result-frame N] [--max-instructions 100]
"""

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import va_container
from mkv_glyph_emulator import OpcodeMap, GlyphCPU
from wgsl_glyph_full_execute import WGSLGlyphEngine


def encode_result_pixels(output_values, registers) -> np.ndarray:
    """Pack GPU execution output into a tiny 1-row RGB image: one pixel per
    output value (R = low byte, G = mid byte, B = high byte), so the result
    is itself a patchable pixel payload -- same substrate as the program."""
    n = max(len(output_values), 1)
    img = np.zeros((1, n, 3), dtype=np.uint8)
    for i, v in enumerate(output_values):
        v = int(v) & 0xFFFFFF
        img[0, i] = [(v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF]
    return img


async def run_frame_roundtrip(container_path: str, frame_id: int,
                               x: int, y: int, w: int, h: int,
                               result_frame_id: int = None,
                               max_instructions: int = 100) -> dict:
    """Decode a patched glyph program from a container frame region, execute
    it on the GPU, verify against the Python GlyphCPU, and write the result
    back into the container.

    Returns a dict with gpu state, python output, match status, and where
    the result was written.
    """
    path = Path(container_path)
    directory, frames = va_container.load_container(path)
    if frame_id >= len(frames):
        raise ValueError(f"frame {frame_id} does not exist (container has {len(frames)} frames)")

    region = frames[frame_id][y:y + h, x:x + w]
    if region.shape[0] != h or region.shape[1] != w:
        raise ValueError(f"region ({x},{y}) {w}x{h} does not fit in frame {frame_id}")

    # Reuse the tested load_program_image() path (it loads from a file).
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        Image.fromarray(region.astype(np.uint8), mode="RGB").save(tf.name)
        program_image_path = tf.name

    opcode_map = OpcodeMap()

    engine = WGSLGlyphEngine()
    if not await engine.initialize():
        raise RuntimeError("WebGPU device initialization failed")
    if not engine.compile_shader():
        raise RuntimeError("WGSL shader compilation failed")

    rom_buffer, img_width, img_height = engine.load_program_image(program_image_path)
    cpu_state_buffer = engine.create_cpu_state_buffer()
    output_buffer = engine.create_output_buffer(size=1000)
    dims_buffer = engine.create_image_dims_buffer(img_width, img_height, max_instructions=max_instructions)

    engine.run_compute(rom_buffer, img_width, img_height, cpu_state_buffer,
                        output_buffer, dims_buffer, max_instructions=max_instructions)

    gpu_state = await engine.read_cpu_state(cpu_state_buffer)
    gpu_output = []
    if gpu_state["output_count"] > 0:
        gpu_output = list(await engine.read_output(output_buffer, gpu_state["output_count"]))

    # Independent verification: the same region, executed by the Python
    # emulator, must agree with the GPU. This is the receipt for SE016.
    cpu = GlyphCPU(opcode_map)
    cpu.run(region, max_instructions=max_instructions)

    match = gpu_output == cpu.output and gpu_state["registers"] == cpu.registers

    # Write the result back into the container -- the "encode" half of the
    # round trip. Defaults to the next free frame if not specified.
    if result_frame_id is None:
        result_frame_id = len(frames)  # append
    result_pixels = encode_result_pixels(gpu_output, gpu_state["registers"])

    payload_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    Image.fromarray(result_pixels, mode="RGB").save(payload_path)

    if result_frame_id >= len(frames):
        # Append a fresh blank frame first, then patch the result into it.
        blank = np.zeros((va_container.FRAME_SIZE, va_container.FRAME_SIZE, 3), dtype=np.uint8)
        blank_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        Image.fromarray(blank, mode="RGB").save(blank_path)
        directory, frames = va_container.load_container(path)
        payload_frames = frames[1:]
        payload_frames.append(blank)
        va_container.save_container(directory, payload_frames, path)
        directory, frames = va_container.load_container(path)
        result_frame_id = len(frames) - 1

    directory, frames = va_container.load_container(path)
    frames[result_frame_id] = frames[result_frame_id].copy()
    rh, rw = result_pixels.shape[0], result_pixels.shape[1]
    frames[result_frame_id][0:rh, 0:rw] = result_pixels
    va_container.save_container(directory, frames[1:], path)

    return {
        "gpu_state": gpu_state,
        "gpu_output": gpu_output,
        "python_output": cpu.output,
        "python_registers": cpu.registers,
        "match": match,
        "result_frame_id": result_frame_id,
    }


def main():
    parser = argparse.ArgumentParser(description="One-frame GPU decode->execute->encode round trip")
    parser.add_argument("container")
    parser.add_argument("frame", type=int)
    parser.add_argument("x", type=int)
    parser.add_argument("y", type=int)
    parser.add_argument("w", type=int)
    parser.add_argument("h", type=int)
    parser.add_argument("--result-frame", type=int, default=None)
    parser.add_argument("--max-instructions", type=int, default=100)
    args = parser.parse_args()

    result = asyncio.run(run_frame_roundtrip(
        args.container, args.frame, args.x, args.y, args.w, args.h,
        result_frame_id=args.result_frame, max_instructions=args.max_instructions,
    ))

    print(f"GPU output:    {result['gpu_output']}")
    print(f"Python output: {result['python_output']}")
    print(f"Match: {'✓' if result['match'] else '✗ MISMATCH'}")
    print(f"Result written to frame {result['result_frame_id']}")

    if not result["match"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
