#!/usr/bin/env python3
"""tests/test_gh2_image_kernel.py — GH-2 oracle test (RED until baker grows a
resident kernel generator).

Falsifiable gate for GH-2 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

1. baker.bake_kernel_image(atlas, out_path=...) emits ONE image whose code
   region contains a resident :__kernel tile that, in glyph code:
     - sets up ABI registers / seeds buffers for each builder contract,
     - CALLs the atlas tile,
     - verifies the result IN-IMAGE (CMP/JZ for register results, a compare
       loop for memory results),
     - counts passes and writes  0xCAFE0000 | n_passed  to KERNEL_STATUS_WORD,
     - executes a clean HALT.

2. The host does NOT run any Python contract function. Success is judged
   purely from the runner receipt:
     - receipt["halted"] is True
     - receipt["faulted"] is False
     - receipt["memory"][KERNEL_STATUS_WORD] == KERNEL_OK  (4/4 contracts)

3. The runtime path imports only GlyphRunner (runner.py) — same zero-dev-import
   property GH-1 established; GH-2 additionally forbids spatial_builder.

Today this FAILS at import: bake_kernel_image does not exist yet.
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.baker import bake_kernel_image            # noqa: E402  (RED: not implemented)

# In-image kernel ABI (fixed for GH-2)
KERNEL_STATUS_WORD = 950            # word index the kernel writes its verdict to
KERNEL_OK = 0xCAFE0004             # 0xCAFE0000 | 4 contracts passed


def _bake(tmp: Path) -> Path:
    atlas = build_default_atlas()
    out = tmp / "kernel.glyph.npy"
    bake_kernel_image(atlas, status_word=KERNEL_STATUS_WORD, out_path=out)
    return out


def test_gh2_kernel_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d))
        assert out.exists(), "bake_kernel_image must emit one image container"


def test_gh2_kernel_runs_all_contracts_in_image():
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d))
        receipt = GlyphRunner(out).run(max_instructions=20000)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        status = receipt["memory"][KERNEL_STATUS_WORD]
        assert status == KERNEL_OK, (
            f"kernel status 0x{status:08x} != 0x{KERNEL_OK:08x} "
            f"(low byte = contracts passed in-image)")


def test_gh2_host_path_zero_dev_imports():
    """The runtime path (runner.py) must import nothing dev-time, and GH-2
    additionally forbids spatial_builder (its dispatch/contracts move into
    the image)."""
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
