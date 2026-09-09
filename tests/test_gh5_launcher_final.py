#!/usr/bin/env python3
"""tests/test_gh5_launcher_final.py — GH-5 oracle test.

Falsifiable gate for GH-5 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):
1. Line count invariant: runner.py MUST be <= 200 lines of code.
2. Zero dev imports: runner.py MUST NOT import any dev-time toolchain modules
   (atlas, spatial_builder, synth, generate, model, tokenizer, corpus, train, pack_dataset, baker).
3. Complete runtime driver capability:
   - GlyphRunner drives GH-2 kernel-in-image to 0xCAFE0004.
   - GlyphRunner drives GH-3 self-extension and offline execution to 0xCAFE0003.
   - GlyphRunner drives GH-4 WGSL GPU compute parity.
4. Unified launcher info & CLI interface supporting CPU and WGSL backends.
"""
from __future__ import annotations

import ast
import subprocess
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
from tools.glyph_gpt.baker import (                                    # noqa: E402
    bake_image,
    bake_kernel_image,
    bake_self_extending_kernel_image,
)
from tools.glyph_gpt.runner import GlyphRunner                         # noqa: E402
from tools.rv64i_to_glyph import assemble_glyph_to_pixels              # noqa: E402


def test_gh5_line_count_le_200():
    """Gate 1: runner.py must be <= 200 lines."""
    runner_path = _REPO / "tools" / "glyph_gpt" / "runner.py"
    lines = runner_path.read_text().splitlines()
    n_lines = len(lines)
    print(f"runner.py line count: {n_lines}")
    assert n_lines <= 200, f"runner.py exceeds 200 lines: {n_lines} lines"


def test_gh5_zero_dev_imports():
    """Gate 2: runner.py must contain zero imports from dev-time toolchain."""
    runner_path = _REPO / "tools" / "glyph_gpt" / "runner.py"
    tree = ast.parse(runner_path.read_text())
    forbidden = {
        "atlas", "spatial_builder", "synth", "generate",
        "model", "tokenizer", "corpus", "train", "pack_dataset", "baker",
    }
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            for f in forbidden:
                assert f not in n, f"runner.py must not import '{n}'"


def test_gh5_launcher_info():
    """Gate 3 (RED): GlyphRunner must provide launcher_info metadata."""
    assert hasattr(GlyphRunner, "launcher_info"), "GlyphRunner must implement launcher_info()"
    info = GlyphRunner.launcher_info()
    assert info["max_lines"] == 200
    assert info["lines"] <= 200
    assert "cpu" in info["backends"]
    assert "wgsl" in info["backends"]


def test_gh5_drives_gh2_kernel():
    """Gate 4: GlyphRunner drives GH-2 kernel-in-image to clean completion."""
    atlas = build_default_atlas()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "kernel.glyph.npy"
        bake_kernel_image(atlas, status_word=950, out_path=out)
        runner = GlyphRunner(out)
        receipt = runner.run(max_instructions=20000)
        assert receipt["halted"] is True
        assert receipt["faulted"] is False
        assert receipt["memory"][950] == 0xCAFE0004


def test_gh5_drives_gh3_extension():
    """Gate 5: GlyphRunner drives GH-3 self-extension and offline execution."""
    atlas = build_default_atlas()
    with tempfile.TemporaryDirectory() as td:
        pre_path = Path(td) / "pre.glyph.png"
        post_path = Path(td) / "post.glyph.png"

        _, patch_info = bake_self_extending_kernel_image(
            atlas, status_word=950, cols_instrs=8, out_path=pre_path
        )

        tile_text = "ADD r14 r10\nADD r10 r10\nADD r10 r14\nRET\n"
        px, _ = assemble_glyph_to_pixels(tile_text, cols_instrs=8)
        words = [(int(r) << 16) | (int(g) << 8) | int(b) for row in px for r, g, b in row][:16]

        runner = GlyphRunner(pre_path)
        cpu = runner.get_cpu()
        cpu.memory[960] = 1
        cpu.memory[961] = len(words)
        for i, w in enumerate(words):
            cpu.memory[964 + i] = w
        cpu.run(runner.image, max_instructions=5000)
        assert cpu.memory[950] == 0xCAFE0003

        from PIL import Image
        Image.fromarray(runner.image, "RGB").save(post_path)

        offline = GlyphRunner(post_path)
        rec = offline.run()
        assert rec["halted"] is True
        assert rec["memory"][950] == 0xCAFE0003


def test_gh5_drives_gh4_wgsl():
    """Gate 6: GlyphRunner drives GH-4 WGSL GPU compute backend."""
    prog = """
    :__entry
    LDI r10 42
    LDI r11 15
    LDI r12 42
    LDI r2 2
    SHL r12 r2
    XOR r10 r11
    ADD r10 r12
    HALT
    """
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "prog.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        runner = GlyphRunner(png)
        rec = runner.run_wgsl(max_steps=100)
        assert rec["halted"] is True
        assert rec["registers_full"][10] == 205


def test_gh5_cli_execution():
    """Gate 7: runner.py runs as a CLI command supporting --backend."""
    prog = ":__entry\nLDI r10 42\nHALT\n"
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "cli_test.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png)

        # CPU run via CLI
        cmd_cpu = [sys.executable, str(_REPO / "tools" / "glyph_gpt" / "runner.py"), str(png)]
        res_cpu = subprocess.run(cmd_cpu, capture_output=True, text=True, check=True)
        assert "halted=True" in res_cpu.stdout

        # WGSL run via CLI
        cmd_wgsl = [sys.executable, str(_REPO / "tools" / "glyph_gpt" / "runner.py"), str(png), "--backend=wgsl"]
        res_wgsl = subprocess.run(cmd_wgsl, capture_output=True, text=True, check=True)
        assert "halted=True" in res_wgsl.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
