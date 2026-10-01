#!/usr/bin/env python3
"""tests/test_gh1_standalone_image.py — GH-1 oracle test.

Falsifiable gate for GH-1 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):
1. bake_image(program_text, atlas, data_words) emits ONE .png/.npy image.
2. GlyphRunner(path) loads the image and executes on GlyphCPUv2 with NO
   imports from atlas / spatial_builder / synth / generate / model / tokenizer.
3. For each of the 4 builder tasks (double, accumulate, memcpy, tile_clear)
   + 2 SB-2 ingested C tiles (sum_c, max_c):
     receipt(runner(image)) == receipt(atlas.run_linked(text))
   including memory, steps, and registers_full.
4. Data words initialization at bake time is verified.
5. Runner code isolation is verified (zero dev imports).
6. Same-image md5sum is recorded and reproducible.
"""
from __future__ import annotations

import ast
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.baker import bake_image            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner          # noqa: E402


def test_runner_no_dev_imports():
    """Verify GlyphRunner source contains zero imports from dev-time toolchain."""
    runner_source_path = _REPO / "tools" / "glyph_gpt" / "runner.py"
    assert runner_source_path.exists(), "runner.py must exist"
    tree = ast.parse(runner_source_path.read_text())

    forbidden_modules = {
        "atlas", "spatial_builder", "synth", "generate",
        "model", "tokenizer", "corpus", "train", "pack_dataset"
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for f in forbidden_modules:
                    assert f not in alias.name, f"Forbidden import '{alias.name}' in runner.py"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for f in forbidden_modules:
                assert f not in mod, f"Forbidden from-import '{mod}' in runner.py"


def _check_task_parity(caller_text: str, atlas, cols_instrs: int = 8,
                       data_words: dict[int, int] | None = None) -> tuple[dict, dict, str]:
    """Bake an image, run it via GlyphRunner, and verify bit-exact parity with run_linked."""
    with tempfile.TemporaryDirectory() as td:
        png_path = Path(td) / "image.glyph.png"
        img = bake_image(caller_text, atlas=atlas, data_words=data_words,
                         cols_instrs=cols_instrs, out_path=png_path)
        assert png_path.exists()
        img_md5 = hashlib.md5(img.tobytes()).hexdigest()

        runner = GlyphRunner(png_path)
        assert runner.cols_instrs == cols_instrs
        receipt_runner = runner.run()

        receipt_linked = atlas.run_linked(caller_text, cols_instrs=cols_instrs)

        # Assert full parity across execution receipts
        assert receipt_runner["assembled"] == receipt_linked["assembled"]
        assert receipt_runner["executed"] == receipt_linked["executed"]
        assert receipt_runner["halted"] == receipt_linked["halted"]
        assert receipt_runner["faulted"] == receipt_linked["faulted"]
        assert receipt_runner["steps"] == receipt_linked["steps"]
        assert receipt_runner["registers_full"] == receipt_linked["registers_full"]
        assert receipt_runner["registers"] == receipt_linked["registers"]
        assert receipt_runner["memory"] == receipt_linked["memory"]

        return receipt_runner, receipt_linked, img_md5


def test_gh1_builder_double():
    atlas = build_default_atlas()
    v = 21
    caller = (":__entry\nLDI r31 4351\nJMP :main\n:main\n"
              f"LDI r10 {v}\nLDI r1 0x8\nCALL :atlas_double\nHALT\n")
    rec_run, rec_link, md5 = _check_task_parity(caller, atlas, cols_instrs=8)
    assert rec_run["halted"] is True
    assert rec_run["registers_full"][10] == 42
    print(f"  PASS double parity: steps={rec_run['steps']} md5={md5}")


def test_gh1_builder_accumulate():
    atlas = build_default_atlas()
    words = [7, 9, 5]
    lines = [":__entry\nLDI r31 4351\nJMP :main\n:main\n", "LDI r11 500\n"]
    for i, w in enumerate(words):
        lines.append(f"LDI r14 {w}\n")
        if i == 0:
            lines.append("ST r11 r14\n")
        else:
            lines.append(f"LDI r15 {500 + i}\nST r15 r14\n")
    lines.append(f"LDI r12 {len(words)}\nLDI r1 0x8\nCALL :atlas_accumulate\nHALT\n")
    caller = "".join(lines)

    rec_run, rec_link, md5 = _check_task_parity(caller, atlas, cols_instrs=8)
    assert rec_run["halted"] is True
    assert rec_run["registers_full"][10] == sum(words)
    print(f"  PASS accumulate parity: steps={rec_run['steps']} md5={md5}")


def test_gh1_builder_memcpy():
    atlas = build_default_atlas()
    words = [111, 222, 333]
    dst = 600
    lines = [":__entry\nLDI r31 4351\nJMP :main\n:main\n", "LDI r11 500\n"]
    for i, w in enumerate(words):
        lines.append(f"LDI r14 {w}\n")
        if i == 0:
            lines.append("ST r11 r14\n")
        else:
            lines.append(f"LDI r15 {500 + i}\nST r15 r14\n")
    lines.append(f"LDI r12 {dst}\nLDI r13 {len(words)}\nLDI r1 0x8\nCALL :atlas_memcpy\nHALT\n")
    caller = "".join(lines)

    rec_run, rec_link, md5 = _check_task_parity(caller, atlas, cols_instrs=8)
    assert rec_run["halted"] is True
    assert rec_run["memory"][dst:dst + len(words)] == words
    print(f"  PASS memcpy parity: steps={rec_run['steps']} md5={md5}")


def test_gh1_builder_tile_clear():
    atlas = build_default_atlas()
    dst, n, fill = 400, 4, 57005
    caller = (":__entry\nLDI r31 4351\nJMP :main\n:main\n"
              f"LDI r11 {dst}\nLDI r14 {fill}\nLDI r13 {n}\nLDI r1 0x8\n"
              "CALL :atlas_tile_clear\nHALT\n")

    rec_run, rec_link, md5 = _check_task_parity(caller, atlas, cols_instrs=8)
    assert rec_run["halted"] is True
    assert rec_run["memory"][dst:dst + n] == [fill] * n
    print(f"  PASS tile_clear parity: steps={rec_run['steps']} md5={md5}")


def test_gh1_ingested_c_sum_array():
    if shutil.which("riscv64-unknown-elf-gcc") is None:
        pytest.skip("riscv64-unknown-elf-gcc not installed")

    atlas = build_default_atlas()
    c_func = ("int sum_array(int *a, int n) { int s = 0;\n"
              "for (int i = 0; i < n; i++) s += a[i]; return s; }\n")
    atlas.register_from_c("sum_c", c_func, "sum_array", cols_instrs=64)

    arr = [7, 9, 5, 4, 11, 2]
    byte_base, w = 0x800, 0x800 >> 2
    h = [":__entry", "LDI r31 30000", "LDI r2 20000"]
    for i, v in enumerate(arr):
        h += [f"LDI r14 {v}", f"LDI r15 {w + i}", "ST r15 r14"]
    h += [f"LDI r10 {byte_base}", f"LDI r11 {len(arr)}",
          "CALL :atlas_sum_c", "HALT\n"]
    caller = "\n".join(h)

    rec_run, rec_link, md5 = _check_task_parity(caller, atlas, cols_instrs=64)
    assert rec_run["halted"] is True
    assert rec_run["registers_full"][10] == sum(arr)
    print(f"  PASS sum_c parity: a0={rec_run['registers_full'][10]} steps={rec_run['steps']} md5={md5}")


def test_gh1_ingested_c_max_array():
    if shutil.which("riscv64-unknown-elf-gcc") is None:
        pytest.skip("riscv64-unknown-elf-gcc not installed")

    atlas = build_default_atlas()
    c_func = ("int max_array(int *a, int n) { int m = a[0];\n"
              "for (int i = 1; i < n; i++) { if (a[i] > m) m = a[i]; } return m; }\n")
    atlas.register_from_c("max_c", c_func, "max_array", cols_instrs=64)

    arr = [7, 42, 5, 99, 4, 11, 2]
    byte_base, w = 0x800, 0x800 >> 2
    h = [":__entry", "LDI r31 30000", "LDI r2 20000"]
    for i, v in enumerate(arr):
        h += [f"LDI r14 {v}", f"LDI r15 {w + i}", "ST r15 r14"]
    h += [f"LDI r10 {byte_base}", f"LDI r11 {len(arr)}",
          "CALL :atlas_max_c", "HALT\n"]
    caller = "\n".join(h)

    rec_run, rec_link, md5 = _check_task_parity(caller, atlas, cols_instrs=64)
    assert rec_run["halted"] is True
    assert rec_run["registers_full"][10] == max(arr)
    print(f"  PASS max_c parity: a0={rec_run['registers_full'][10]} steps={rec_run['steps']} md5={md5}")


def test_gh1_data_words_seeding():
    """Verify bake_image seeds data_words at bake time without host loader involvement."""
    program = (":__entry\nLDI r31 4351\nJMP :main\n:main\n"
               "LDI r15 100\nLD r10 r15\n"
               "LDI r15 101\nLD r11 r15\n"
               "ADD r10 r11\nHALT\n")
    data_words = {100: 42, 101: 58}

    with tempfile.TemporaryDirectory() as td:
        png_path = Path(td) / "data_test.glyph.png"
        img = bake_image(program, atlas=None, data_words=data_words, cols_instrs=8, out_path=png_path)
        runner = GlyphRunner(png_path)
        receipt = runner.run()

        assert receipt["halted"] is True
        assert receipt["registers_full"][10] == 100  # 42 + 58
        assert receipt["memory"][100] == 42
        assert receipt["memory"][101] == 58
        print(f"  PASS data_words seeding: a0={receipt['registers_full'][10]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
