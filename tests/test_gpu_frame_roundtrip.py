"""
Unit tests for gpu_frame_exec.py (TASK_SE016): one-frame GPU
decode->execute->encode round trip.

Scope: this proves a single full cycle (container frame -> GPU execution ->
result written back into the container), verified against the Python
GlyphCPU emulator on the same program. It does NOT prove ongoing GPU-resident
execution across many frames/streaming -- that remains separate future work.

Gate rule: Tool verification before marking complete.
"""

import asyncio
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from gpu_frame_exec import run_frame_roundtrip  # noqa: E402
import va_container  # noqa: E402

FRAME_SIZE = va_container.FRAME_SIZE


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(TOOLS_DIR / "va_container.py"), *[str(a) for a in args]],
        capture_output=True, text=True,
    )


def build_container_with_program(tmp_path, glyph_source: str):
    """init -> compile -> append free frame -> patch program in. Returns
    (container_path, program_frame_id, program_width, program_height)."""
    container = tmp_path / "test.mkv"
    r = run_cli("init", container)
    assert r.returncode == 0, r.stderr

    glyph_path = tmp_path / "prog.glyph"
    glyph_path.write_text(glyph_source)

    compiled_png = tmp_path / "prog.png"
    r = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "glyph_to_pixels.py"), glyph_path, "-o", compiled_png],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    compiled = np.array(Image.open(compiled_png).convert("RGB"))
    h, w = compiled.shape[0], compiled.shape[1]

    blank = np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8)
    blank_path = tmp_path / "blank.png"
    Image.fromarray(blank, mode="RGB").save(blank_path)
    r = run_cli("write-frame", container, blank_path)
    assert r.returncode == 0, r.stderr
    frame_id = 1

    r = run_cli("patch", container, frame_id, 0, 0, compiled_png)
    assert r.returncode == 0, r.stderr

    return container, frame_id, w, h


class TestGPUFrameRoundtrip:
    def test_arithmetic_program_matches_python_emulator(self, tmp_path):
        container, frame_id, w, h = build_container_with_program(
            tmp_path, "LDI r0 2\nLDI r1 3\nADD r0 r1\nPRT r0\nHALT\n"
        )

        result = asyncio.run(run_frame_roundtrip(str(container), frame_id, 0, 0, w, h))

        assert result["match"], f"GPU vs Python mismatch: {result}"
        assert result["gpu_output"] == [5]
        assert result["python_output"] == [5]
        assert result["gpu_state"]["registers"][0] == 5
        assert result["python_registers"][0] == 5

    def test_result_written_back_into_container(self, tmp_path):
        container, frame_id, w, h = build_container_with_program(
            tmp_path, "LDI r0 2\nLDI r1 3\nADD r0 r1\nPRT r0\nHALT\n"
        )

        result = asyncio.run(run_frame_roundtrip(str(container), frame_id, 0, 0, w, h))
        result_frame_id = result["result_frame_id"]

        out_path = tmp_path / "result_readback.png"
        r = run_cli("read-frame", container, result_frame_id, "-o", out_path)
        assert r.returncode == 0, r.stderr

        readback = np.array(Image.open(out_path).convert("RGB"))
        decoded = int(readback[0, 0, 0]) * 65536 + int(readback[0, 0, 1]) * 256 + int(readback[0, 0, 2])
        assert decoded == 5

    def test_explicit_result_frame_target(self, tmp_path):
        container, frame_id, w, h = build_container_with_program(
            tmp_path, "LDI r0 7\nPRT r0\nHALT\n"
        )

        blank = np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8)
        blank_path = tmp_path / "blank2.png"
        Image.fromarray(blank, mode="RGB").save(blank_path)
        r = run_cli("write-frame", container, blank_path)
        assert r.returncode == 0, r.stderr
        target_frame = 2

        result = asyncio.run(run_frame_roundtrip(
            str(container), frame_id, 0, 0, w, h, result_frame_id=target_frame
        ))

        assert result["result_frame_id"] == target_frame
        assert result["gpu_output"] == [7]

    def test_cli_matches_library_call(self, tmp_path):
        container, frame_id, w, h = build_container_with_program(
            tmp_path, "LDI r0 4\nPRT r0\nHALT\n"
        )

        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "gpu_frame_exec.py"),
             str(container), str(frame_id), "0", "0", str(w), str(h)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert "Match: ✓" in r.stdout
        assert "GPU output:    [4]" in r.stdout
