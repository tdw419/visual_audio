#!/usr/bin/env python3
"""DEFECT-23-ROOT step 3 gate: producer-side bake-time page-table validation.

See .builder_queue/RULING_defect23root_step3_inwindow_slots.md,
tools/geos_aspace.py (validate_page_table, stamp_page_table), and
systems/GLYPH_SELF_HOSTING_ROADMAP.md:360 (DEFECT-23-ROOT).

Falsifiable gate legs:
- L1 RED-discriminator:
    L1a: pfn-rule rejection (pfn=9 > max_frame=8 raises; max_frame=9 control passes).
    L1b: flag-mask rejection (flags=0xFF has bits outside _FLAG_MASK=0x1F raises).
- L2 producer-green: all six baker table-setup modes produce tables passing validation.
- L3 gh25-green: _two_pass_bake("swap") output passes validation on its table window.
- L4 non-vacuity (in-gate): mutant copy of ONE producer call-site with validation call
    neutered -> the corresponding producer leg goes RED.
- L5 twins/untouched: test_defect23_pt_identity.py + test_gh17_paging.py covered in gate.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.geos_aspace import (  # noqa: E402
    PAGE_TABLE_TAG,
    PageTableValidationError,
    validate_page_table,
)
from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.baker import (  # noqa: E402
    PAGE_TABLE_BASE_WORD,
    paged_kernel_image,
    syscall_abi_kernel_image,
)
from tools.glyph_gpt.gh25_hilbert_paging import _two_pass_bake  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402


# ---------------------------------------------------------------------------
# L1: RED-discriminator legs
# ---------------------------------------------------------------------------

def test_l1a_pfn_discriminator_rejects_high_pfn():
    """L1a: Seeding 0x00000907 (pfn 9, flags 0x07) into a tagged window rejects when

    pfn 9 > max_frame 8, but passes control when max_frame >= 9.
    Discriminates ONLY via the PFN ceiling/range check, because flags 0x07 is legal.
    """
    pt_base = 1536
    memory = [0] * (pt_base + 256)
    memory[pt_base - 1] = PAGE_TABLE_TAG
    k = 5
    memory[pt_base + k] = 0x00000907  # pfn = 9, flags = 0x07 (V|W|U)

    # REJECT leg: max_frame = 8 strictly rejects pfn 9
    with pytest.raises(PageTableValidationError) as exc_info:
        validate_page_table(memory, pt_base, max_frame=8)
    err = str(exc_info.value)
    assert f"slot={k}" in err or f"Slot {k}" in err or str(k) in err
    assert "9" in err

    # CONTROL leg: max_frame = 9 admits pfn 9 without error
    summary = validate_page_table(memory, pt_base, max_frame=9)
    assert summary["slots_checked"] == 256
    assert summary["violations"] == 0


def test_l1b_flag_mask_discriminator_rejects_illegal_flags():
    """L1b: Seeding 0x000001FF (pfn 1, flags 0xFF) rejects strictly via the flag-mask rule

    even though pfn 1 <= max_frame 8.
    Discriminates ONLY via bits outside _FLAG_MASK (0x1F).
    """
    pt_base = 1536
    memory = [0] * (pt_base + 256)
    memory[pt_base - 1] = PAGE_TABLE_TAG
    k = 3
    memory[pt_base + k] = 0x000001FF  # pfn = 1, flags = 0xFF (outside 0x1F)

    with pytest.raises(PageTableValidationError) as exc_info:
        validate_page_table(memory, pt_base, max_frame=8)
    err = str(exc_info.value)
    assert f"slot={k}" in err or f"Slot {k}" in err or str(k) in err
    assert "flag" in err.lower() or "mask" in err.lower() or "0xff" in err.lower()

    # CONTROL leg: legal flags 0x07 with same pfn 1 admits
    memory[pt_base + k] = 0x00000107
    summary = validate_page_table(memory, pt_base, max_frame=8)
    assert summary["violations"] == 0


# ---------------------------------------------------------------------------
# L2: Producer-green legs (all six baker table setup modes)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mode",
    ["flat64k", "unmapped_fault", "context_switch", "pixel_parity"],
)
def test_l2_baker_paged_modes_produce_valid_tables(mode: str):
    """L2 (paged modes): run real baker on each GH-17 mode and validate the table."""
    atlas = build_default_atlas()
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / f"{mode}.npy"
        paged_kernel_image(atlas, mode=mode, out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        for _ in range(50):
            if not cpu.running:
                break
            cpu.step(runner.image)

        summary = validate_page_table(cpu.memory, PAGE_TABLE_BASE_WORD, max_frame=65535)
        assert summary["slots_checked"] == 256
        assert summary["violations"] == 0
        assert summary["mapped_slots"] > 0


@pytest.mark.parametrize(
    "mode,steps",
    [("admit", 350), ("paged_dispatch", 350)],
)
def test_l2_baker_gh18_modes_produce_valid_tables(mode: str, steps: int):
    """L2 (GH-18 modes): run real baker on admit and paged_dispatch and validate the table."""
    atlas = build_default_atlas()
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / f"{mode}.npy"
        syscall_abi_kernel_image(atlas, mode=mode, timer_quantum=35, out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        for _ in range(steps):
            if not cpu.running:
                break
            cpu.step(runner.image)

        summary = validate_page_table(cpu.memory, PAGE_TABLE_BASE_WORD, max_frame=65535)
        assert summary["slots_checked"] == 256
        assert summary["violations"] == 0
        assert summary["mapped_slots"] > 0


# ---------------------------------------------------------------------------
# L3: gh25-green leg
# ---------------------------------------------------------------------------

def test_l3_gh25_swap_produces_valid_table():
    """L3: _two_pass_bake('swap') output passes validation on its real table window."""
    img = _two_pass_bake("swap", out_path=None, cols_instrs=8, min_rows=360)
    summary = validate_page_table(img, PAGE_TABLE_BASE_WORD, max_frame=65535)
    assert summary["slots_checked"] == 256
    assert summary["violations"] == 0
    assert summary["mapped_slots"] == 1


# ---------------------------------------------------------------------------
# L4: Non-vacuity (in-gate): mutant copy of producer call-site neutered goes RED
# ---------------------------------------------------------------------------

def _load_module_from(path: Path, mod_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_l4_non_vacuity_neutered_producer_goes_red(tmp_path: Path):
    """L4 non-vacuity: create a mutant copy of gh25_hilbert_paging.py in tmp_path with

    the validate_page_table call neutered. When an invalid slot is injected,
    the live producer FAILS the bake, but the mutant PASSES without raising.
    Thus the mutant makes the rejection assertion fail (goes RED).
    """
    src_path = REPO / "tools" / "glyph_gpt" / "gh25_hilbert_paging.py"
    src_text = src_path.read_text(encoding="utf-8")

    call_target = "validate_page_table(img, PAGE_TABLE_BASE_WORD"
    assert call_target in src_text, (
        "L4 pre-check: gh25_hilbert_paging.py must contain validate_page_table call"
    )

    # 1. Verification of live producer: injecting bad table word fails the bake
    # We test that injecting a bad word causes validate_page_table in _two_pass_bake to raise.
    # We inject a bad table word right before the validate_page_table call in a test script.
    inject_bad_word = (
        "_write_table_word(img, 50, 0x000009FF)\n"
        "    validate_page_table(img, PAGE_TABLE_BASE_WORD"
    )
    patched_src = src_text.replace(call_target, inject_bad_word, 1)

    bad_prod_path = tmp_path / "bad_producer.py"
    bad_prod_path.write_text(patched_src, encoding="utf-8")
    bad_mod = _load_module_from(bad_prod_path, "bad_producer")

    def _run_producer_leg(mod):
        # A discriminating producer leg: baking with an injected invalid slot must raise.
        try:
            mod._two_pass_bake("swap", out_path=None, cols_instrs=8, min_rows=360)
        except PageTableValidationError:
            return "REJECTED_OK"
        raise AssertionError("Producer accepted invalid page table without validation!")

    # Live producer with active validation passes the leg (rejects the bad slot):
    assert _run_producer_leg(bad_mod) == "REJECTED_OK"

    # 2. Now create the MUTANT: neuter the validation call
    neutered_src = patched_src.replace(
        "validate_page_table(img, PAGE_TABLE_BASE_WORD",
        "# NEUTERED: validate_page_table\n    pass # validate_page_table(img, PAGE_TABLE_BASE_WORD",
        1,
    )
    mutant_path = tmp_path / "mutant_gh25.py"
    mutant_path.write_text(neutered_src, encoding="utf-8")
    mutant_mod = _load_module_from(mutant_path, "mutant_gh25")

    # Mutant producer with neutered validation goes RED (fails the leg with AssertionError):
    with pytest.raises(AssertionError, match="Producer accepted invalid page table"):
        _run_producer_leg(mutant_mod)


# ---------------------------------------------------------------------------
# L5: Untouched twins documentation
# ---------------------------------------------------------------------------
# L5 is covered by the gate command executing:
# tests/test_defect23_pt_identity.py + tests/test_gh17_paging.py
# Both pass unchanged, guaranteeing zero regression on twin suites.
