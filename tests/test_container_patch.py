"""
Unit tests for `va_container.py patch` (TASK_SE015).

Verifies pixel arrays can be painted into a sub-region of an existing MKV
frame in place, without touching the rest of the frame or other frames, and
that patching an entry-owned frame is refused unless --force is passed.

Gate rule: Tool verification before marking complete.
"""

import subprocess
import sys
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
VA_CONTAINER = TOOLS_DIR / "va_container.py"
FRAME_SIZE = 450


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, str(VA_CONTAINER), *[str(a) for a in args]],
        capture_output=True, text=True,
    )
    return result


@pytest.fixture
def blank_container(tmp_path):
    container = tmp_path / "test.mkv"
    r = run_cli("init", container)
    assert r.returncode == 0, r.stderr
    return container


def make_png(tmp_path, name, size=(20, 30), color=(10, 20, 30)):
    w, h = size
    arr = np.full((h, w, 3), color, dtype=np.uint8)
    path = tmp_path / name
    Image.fromarray(arr, mode="RGB").save(path)
    return path, arr


def append_free_frame(container):
    """write-frame with no --name leaves the appended frame unowned by any entry."""
    blank = np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8)
    path = container.parent / "blank_frame.png"
    Image.fromarray(blank, mode="RGB").save(path)
    r = run_cli("write-frame", container, path)
    assert r.returncode == 0, r.stderr
    return 1  # first payload frame appended after the directory


class TestContainerPatch:
    def test_patch_free_frame_pixel_exact(self, tmp_path, blank_container):
        frame_id = append_free_frame(blank_container)
        payload_path, payload_arr = make_png(tmp_path, "patch.png", size=(20, 30), color=(200, 50, 5))

        r = run_cli("patch", blank_container, frame_id, 100, 150, payload_path)
        assert r.returncode == 0, r.stderr

        out_path = tmp_path / "readback.png"
        r = run_cli("read-frame", blank_container, frame_id, "-o", out_path)
        assert r.returncode == 0, r.stderr

        readback = np.array(Image.open(out_path).convert("RGB"))
        patched_region = readback[150:150 + 30, 100:100 + 20]
        assert np.array_equal(patched_region, payload_arr)

    def test_unpatched_pixels_untouched(self, tmp_path, blank_container):
        frame_id = append_free_frame(blank_container)
        payload_path, _ = make_png(tmp_path, "patch.png", size=(20, 30), color=(200, 50, 5))

        run_cli("patch", blank_container, frame_id, 100, 150, payload_path)

        out_path = tmp_path / "readback.png"
        run_cli("read-frame", blank_container, frame_id, "-o", out_path)
        readback = np.array(Image.open(out_path).convert("RGB"))

        assert np.array_equal(readback[0, 0], [0, 0, 0])
        assert np.array_equal(readback[FRAME_SIZE - 1, FRAME_SIZE - 1], [0, 0, 0])

    def test_patch_rejects_out_of_bounds(self, tmp_path, blank_container):
        frame_id = append_free_frame(blank_container)
        payload_path, _ = make_png(tmp_path, "patch.png", size=(20, 30))

        r = run_cli("patch", blank_container, frame_id, FRAME_SIZE - 5, 0, payload_path)
        assert r.returncode != 0
        assert "does not fit" in r.stderr

    def test_patch_rejects_directory_frame(self, tmp_path, blank_container):
        payload_path, _ = make_png(tmp_path, "patch.png", size=(5, 5))
        r = run_cli("patch", blank_container, 0, 0, 0, payload_path)
        assert r.returncode != 0
        assert "directory" in r.stderr

    def test_patch_refuses_entry_frame_without_force(self, tmp_path, blank_container):
        entry_payload = tmp_path / "entry.bin"
        entry_payload.write_bytes(b"hello world" * 100)
        r = run_cli("add", blank_container, entry_payload, "--name", "my_entry")
        assert r.returncode == 0, r.stderr

        payload_path, _ = make_png(tmp_path, "patch.png", size=(5, 5))
        r = run_cli("patch", blank_container, 1, 0, 0, payload_path)
        assert r.returncode != 0
        assert "--force" in r.stderr
        assert "my_entry" in r.stderr

    def test_patch_entry_frame_with_force_corrupts_verify(self, tmp_path, blank_container):
        entry_payload = tmp_path / "entry.bin"
        entry_payload.write_bytes(b"hello world" * 100)
        run_cli("add", blank_container, entry_payload, "--name", "my_entry")

        payload_path, _ = make_png(tmp_path, "patch.png", size=(5, 5))
        r = run_cli("patch", blank_container, 1, 0, 0, payload_path, "--force")
        assert r.returncode == 0, r.stderr
        assert "WARNING" in r.stdout

        r = run_cli("verify", blank_container)
        assert r.returncode != 0

    def test_glyph_pixels_patch_into_container(self, tmp_path, blank_container):
        """End-to-end: compile a .glyph program with glyph_to_pixels.py, patch
        the compiled pixels into a free frame, read it back byte-exact."""
        glyph_src = tmp_path / "prog.glyph"
        glyph_src.write_text("LDI r0 2\nLDI r1 3\nADD r0 r1\nPRT r0\nHALT\n")

        compiled_png = tmp_path / "prog.png"
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "glyph_to_pixels.py"), glyph_src, "-o", compiled_png],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        compiled_arr = np.array(Image.open(compiled_png).convert("RGB"))

        frame_id = append_free_frame(blank_container)
        r = run_cli("patch", blank_container, frame_id, 0, 0, compiled_png)
        assert r.returncode == 0, r.stderr

        out_path = tmp_path / "readback.png"
        run_cli("read-frame", blank_container, frame_id, "-o", out_path)
        readback = np.array(Image.open(out_path).convert("RGB"))

        h, w = compiled_arr.shape[0], compiled_arr.shape[1]
        assert np.array_equal(readback[0:h, 0:w], compiled_arr)
