#!/usr/bin/env python3
"""tests/test_gh3_self_extension.py — GH-3 oracle test.

Falsifiable gate for GH-3 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):
1. In-image tile loader:
   - Kernel image contains a reserved patch window in its code region.
   - Host places raw tile pixels into MMIO mailbox in memory (MAILBOX_DATA).
   - Kernel copies tile pixels from mailbox into its own code region using
     PARALLEL_ST, patches its dispatch, and executes the new routine.
2. Offline re-execution test (The Thesis Test):
   - The patched image is saved to disk.
   - A fresh GlyphRunner loads that image with ZERO host mailbox writes
     (MAILBOX_FLAG = 0).
   - The fresh runner executes cleanly to HALT, successfully running the
     patched capability directly from the resident pixels.
3. Invariant check:
   - Pre-patch and post-patch images differ ONLY inside the reserved patch window.
"""
from __future__ import annotations

import ast
import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas                  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                         # noqa: E402
from tools.glyph_gpt.baker import bake_self_extending_kernel_image     # noqa: E402 (RED: not yet implemented)
from tools.rv64i_to_glyph import assemble_glyph_to_pixels              # noqa: E402

STATUS_WORD = 950
MAILBOX_FLAG = 960       # 1 = patch from mailbox, 0 = run resident
MAILBOX_N_PX = 961       # number of pixels to copy
MAILBOX_DATA = 964       # pixel words start here

EXT_OK = 0xCAFE0003      # Status indicating extended capability passed


def _assemble_tile_to_pixel_words(tile_text: str, cols_instrs: int = 8) -> list[int]:
    """Assemble a snippet of glyph instructions into a flat list of 24-bit pixel words."""
    pixels, _ = assemble_glyph_to_pixels(tile_text, cols_instrs=cols_instrs)
    h, w, _ = pixels.shape
    words = []
    # Collect all non-zero/valid pixels
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[y, x]
            words.append((int(r) << 16) | (int(g) << 8) | int(b))
    return words


def test_gh3_self_extension_and_offline_parity():
    atlas = build_default_atlas()
    with tempfile.TemporaryDirectory() as td:
        pre_path = Path(td) / "pre_kernel.glyph.png"
        post_path = Path(td) / "post_kernel.glyph.png"

        # 1. Bake initial kernel image with patch window
        pre_img, patch_info = bake_self_extending_kernel_image(
            atlas, status_word=STATUS_WORD, cols_instrs=8, out_path=pre_path
        )
        assert pre_path.exists()
        assert "patch_pixel_addr" in patch_info
        assert "patch_pixel_count" in patch_info

        # 2. Define new capability: triple a0 (r10 = r10 * 3) -> r10 = 7 * 3 = 21
        # In glyph assembly: ADD r10 to itself, add original, RET
        new_tile_text = (
            "ADD r14 r10\n"   # r14 = 7
            "ADD r10 r10\n"   # r10 = 14
            "ADD r10 r14\n"   # r10 = 21
            "RET\n"
        )
        # Assemble just this tile
        tile_px_words = _assemble_tile_to_pixel_words(new_tile_text, cols_instrs=8)
        # 4 instructions = 16 pixels
        tile_px_count = 4 * 4
        tile_words = tile_px_words[:tile_px_count]
        assert len(tile_words) <= patch_info["patch_pixel_count"]

        # 3. Arm runner with mailbox data
        runner = GlyphRunner(pre_path)
        # Seed test input (e.g. r10 = 7 for extension test)
        # Mailbox setup in memory
        def _seed_mailbox(cpu):
            cpu.memory[MAILBOX_FLAG] = 1
            cpu.memory[MAILBOX_N_PX] = len(tile_words)
            for i, w in enumerate(tile_words):
                cpu.memory[MAILBOX_DATA + i] = w

        # Run with mailbox armed
        cpu = runner.get_cpu()
        _seed_mailbox(cpu)
        steps = cpu.run(runner.image, max_instructions=5000)

        # Verify extension ran and passed contract
        assert not cpu.faulted
        assert not cpu.running
        assert cpu.memory[STATUS_WORD] == EXT_OK, f"status was 0x{cpu.memory[STATUS_WORD]:08x}"

        # 4. Save the patched image to disk
        from PIL import Image
        Image.fromarray(runner.image, "RGB").save(post_path)
        assert post_path.exists()

        # 5. Offline re-execution test (The Thesis Test)
        # Clean fresh runner loads post_path with NO host mailbox writes!
        offline_runner = GlyphRunner(post_path)
        receipt = offline_runner.run()

        assert receipt["halted"] is True
        assert receipt["faulted"] is False
        assert receipt["memory"][STATUS_WORD] == EXT_OK, (
            f"Offline re-run failed: status 0x{receipt['memory'][STATUS_WORD]:08x} != 0x{EXT_OK:08x}"
        )
        print(f"  PASS GH-3 offline execution verified! status=0x{EXT_OK:08x}")

        # 6. Invariant check: pre- and post-patch images differ ONLY inside patch window
        post_img = offline_runner.image
        diff_mask = np.any(pre_img != post_img, axis=-1)
        diff_coords = np.argwhere(diff_mask)

        patch_start = patch_info["patch_pixel_addr"]
        patch_len = patch_info["patch_pixel_count"]
        cols_px = runner.cols_instrs * 4

        for y, x in diff_coords:
            linear_px = y * cols_px + x
            assert patch_start <= linear_px < patch_start + patch_len, (
                f"Pixel modification at ({x}, {y}) [linear {linear_px}] outside patch window "
                f"[{patch_start}, {patch_start + patch_len})"
            )
        print(f"  PASS GH-3 patch isolation verified: {len(diff_coords)} pixels changed, all in window")


def test_gh3_runner_remains_isolated():
    """Verify runner.py still imports zero dev-time modules."""
    src = (_REPO / "tools" / "glyph_gpt" / "runner.py").read_text()
    tree = ast.parse(src)
    forbidden = {"atlas", "spatial_builder", "synth", "generate",
                 "model", "tokenizer", "corpus", "train", "pack_dataset",
                 "baker"}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            for f in forbidden:
                assert f not in n, f"runner.py must not import '{n}'"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
