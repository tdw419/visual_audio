#!/usr/bin/env python3
"""tests/test_gh17_paging.py — GH-17 Spatial Paging oracle test.

Falsifiable gate for GH-17 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):
1. Memory map non-collision assertion: Page Table region (1536..1792) must not
   collide with context/stack words (700..735), mailbox window (800..896),
   status word (950), FS window (1024..1280), or BOX MMIO (8192..8256).
2. Flat 64K-word virtual space: tasks address virtual words beyond 1024 up to
   word 65535 via page table mapping.
3. Page fault on unmapped access: access to unmapped virtual page (PTE_V == 0)
   traps to KFAULT_PC, records faulting address, and sets verdict word.
4. Context switch with >1024 words resident: Task A and Task B have working
   pages above 1024 words; resident data survives context switch and preemption.
5. CPU ≡ WGSL parity on paged pixel access: spatial pixel-backed page frame
   access produces identical 32-register state on CPU and GPU compute.
6. Zero-dev-import property: runner.py stays <= 200 LOC with 0 dev imports.
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
from tools.glyph_gpt.baker import (                            # noqa: E402
    bake_image,
    paged_kernel_image,
    PAGE_TABLE_BASE_WORD,
    PAGE_WORDS,
    PTE_V,
    PTE_W,
    PTE_U,
    PTE_PIX,
)

# Architectural memory map ranges
STACK_WINDOW   = range(700, 736)
MAILBOX_WINDOW = range(800, 897)
STATUS_WINDOW  = range(950, 951)
FS_WINDOW      = range(1024, 1280)
PT_WINDOW      = range(PAGE_TABLE_BASE_WORD, PAGE_TABLE_BASE_WORD + 256)
BOX_MMIO_WINDOW = range(8192, 8256)

# GH-17 Status and ABI constants
GH17_KERNEL_OK = 0xCAFE0017
GH17_FAULT_WORD = 731
GH17_FAULT_VERDICT = 0xFA017
GH17_VERIFY_WORD = 704
GH17_VERIFY_OK = 0xFEED0017


def test_gh17_memory_map_no_collisions():
    """Assertion: Page Table region must strictly avoid colliding with any
    pre-existing architectural or MMIO windows."""
    regions = {
        "STACK_WINDOW": STACK_WINDOW,
        "MAILBOX_WINDOW": MAILBOX_WINDOW,
        "STATUS_WINDOW": STATUS_WINDOW,
        "FS_WINDOW": FS_WINDOW,
        "PAGE_TABLE": PT_WINDOW,
        "BOX_MMIO": BOX_MMIO_WINDOW,
    }
    for name1, r1 in regions.items():
        for name2, r2 in regions.items():
            if name1 != name2:
                overlap = set(r1) & set(r2)
                assert not overlap, f"Collision between {name1} and {name2}: words {overlap}"


def test_gh17_flat_64k_word_space_access():
    """Flat 64K-word virtual space: task writes and reads addresses > 1024 up to
    word 65280 (0xFF00) through the page table."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gh17_flat64k.glyph.npy"
        atlas = build_default_atlas()
        paged_kernel_image(atlas, mode="flat64k", out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=10000)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        assert receipt["status_word_value"] == GH17_KERNEL_OK, (
            f"status 0x{receipt['status_word_value']:08x} != 0x{GH17_KERNEL_OK:08x}")


def test_gh17_page_fault_on_unmapped_access():
    """Page fault: access to unmapped virtual page traps to KFAULT_PC and
    writes verdict word."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gh17_fault.glyph.npy"
        atlas = build_default_atlas()
        paged_kernel_image(atlas, mode="unmapped_fault", out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=10000)
        mem = receipt["memory"]
        assert mem[GH17_FAULT_WORD] == GH17_FAULT_VERDICT, (
            f"fault word 0x{mem[GH17_FAULT_WORD]:08x} != 0x{GH17_FAULT_VERDICT:08x}")


def test_gh17_context_switch_with_resident_pages_gt_1024():
    """Context switch with resident pages > 1024 words: Task A (page 8, word 2048)
    and Task B (page 16, word 4096) preserve their paged working data across
    preemption/round-robin switch."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gh17_ctx_switch.glyph.npy"
        atlas = build_default_atlas()
        paged_kernel_image(atlas, mode="context_switch", timer_quantum=35, out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=10000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        mem = receipt["memory"]
        assert mem[GH17_VERIFY_WORD] == GH17_VERIFY_OK, (
            f"verify word 0x{mem[GH17_VERIFY_WORD]:08x} != 0x{GH17_VERIFY_OK:08x}")


def test_gh17_cpu_wgsl_paged_pixel_parity():
    """Parity: spatial pixel-backed page frame access matches bit-exact between
    Python CPU emulator and WGSL compute shader."""
    with tempfile.TemporaryDirectory() as d:
        png_path = Path(d) / "gh17_parity.glyph.png"
        atlas = build_default_atlas()
        paged_kernel_image(atlas, mode="pixel_parity", out_path=png_path)
        runner = GlyphRunner(png_path, ram_words=16384)

        rec_cpu = runner.run(max_instructions=1000)
        assert rec_cpu["halted"] is True, rec_cpu.get("error", rec_cpu)

        rec_wgsl = runner.run_wgsl(max_steps=1000)
        assert rec_wgsl["halted"] is True, rec_wgsl.get("error", rec_wgsl)

        assert rec_cpu["registers_full"] == rec_wgsl["registers_full"], (
            f"CPU vs WGSL register mismatch:\nCPU:  {rec_cpu['registers_full']}\nWGSL: {rec_wgsl['registers_full']}"
        )


def test_gh17_runner_line_budget_and_clean_imports():
    """GH-5 / GH-11 / GH-16 invariant preserved: runner.py <= 200 lines, 0 dev imports."""
    runner_path = _REPO / "tools" / "glyph_gpt" / "runner.py"
    lines = runner_path.read_text().splitlines()
    assert len(lines) <= 200, f"runner.py exceeds 200 lines: {len(lines)}"

    tree = ast.parse(runner_path.read_text())
    forbidden = {
        "atlas", "spatial_builder", "synth", "generate",
        "model", "tokenizer", "corpus", "train", "pack_dataset", "baker",
        "pytest", "hypothesis", "scipy", "torch", "transformers",
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
