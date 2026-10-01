#!/usr/bin/env python3
"""DEFECT-23 gate — the paged_dispatch prologue must install IDENTITY PTEs.

DEFECT-23 (filed 2026-09-13, `.builder_queue/DEFECT-23_paged_flat_memory_growth.json`) measured a
`paged_dispatch` run growing the engine's `memory` from 16,384 words to **134,810,550 words
(1078 MB of a bare Python list) holding 27 nonzero words**. Root cause, named this tick by
`.builder_queue/probe_defect23_pt_slot_writer.py`: the GH-17 arming loop `:__g18_ptloop`
(`tools/glyph_gpt/baker.py`, mode `paged_dispatch`) writes its MOV as `ADD r14 r13` **without
initialising `r14`**, so it accumulates:

    r14(n) = ((r14(n-1) << 8) | 7) + n        with r14(-1) = 0x150001 (prologue leftover)

giving the eight "identity" PTEs 0x15000107, 0x0010807, 0x01080907, 0x08090a07, 0x090a0b07, ...
instead of 0x007, 0x107, ... 0x707. A later USER store then walks vpn 2/3 with pfn 67,593 / 526,602
and the engine materialises 17.3M / 117.5M words of zero RAM for it.

L1 is the falsifier. It is RED on the pre-fix tree (the PTE values differ AND `memory` grows past
the RAM bound) and GREEN with the `LDI r14 0` line in the loop. L2 is the non-vacuity guard: a
guard that simply refused all paging would break the identity map's *intent*, so L2 asserts the
eight slots are exactly the documented `(vpn << 8) | 7` — not merely "small".

What a PASS does NOT prove: it does not exercise GH-17 paging under a *non*-identity map (the
paged_dispatch image has no such map), and it does not re-derive the WGSL twin (the WGSL engine
delivers no ticks and is not on this path).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RAM_WORDS = 16384
MAX_STEPS = 400
PT_BASE_SLOTS = 8


def _bake_and_run(mode: str = "paged_dispatch", steps: int = MAX_STEPS):
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.baker import syscall_abi_kernel_image
    from tools.glyph_gpt.runner import GlyphRunner

    tmp = Path(tempfile.mkdtemp(prefix="defect23_gate_"))
    out = tmp / f"{mode}.npy"
    syscall_abi_kernel_image(build_default_atlas(), mode=mode, timer_quantum=35, out_path=out)
    runner = GlyphRunner(out, ram_words=RAM_WORDS)
    cpu = runner.get_cpu()
    cpu.running = True
    ran = 0
    while cpu.running and ran < steps:
        cpu.step(runner.image)
        ran += 1
    return cpu, ran


def _pt_base(cpu) -> int:
    from tools.glyph_isa_v2 import PAGE_TABLE_ADDR

    return cpu.memory[PAGE_TABLE_ADDR >> 2]


def test_defect23_leg1_identity_ptes_and_no_growth():
    """L1 (falsifier): the arming loop installs identity PTEs; the engine does not balloon."""
    cpu, ran = _bake_and_run("paged_dispatch")
    assert ran >= 300, f"run too short to cover the arming loop + the USER store (ran {ran})"

    base = _pt_base(cpu)
    assert base != 0, "paged_dispatch must arm PAGE_TABLE_WORD (pt_base == 0 means paging is off)"

    observed = [cpu.memory[base + p] for p in range(PT_BASE_SLOTS)]
    expected = [(p << 8) | 0x7 for p in range(PT_BASE_SLOTS)]  # (vpn << 8) | V|W|U
    assert observed == expected, (
        "the paged_dispatch prologue must install IDENTITY PTEs (vpn<<8)|7.\n"
        f"  expected {[hex(v) for v in expected]}\n"
        f"  observed {[hex(v) for v in observed]}\n"
        "On the pre-fix tree this reads [0x15000107, 0x10807, 0x1080907, 0x8090a07, ...] "
        "because the loop's MOV is an uninitialised ADD (DEFECT-23)."
    )

    grown = len(cpu.memory) - RAM_WORDS
    assert grown == 0, (
        f"a paged_dispatch run must not materialise RAM past its declared {RAM_WORDS} words; "
        f"grew by {grown} words (pre-fix: 17,304,265 then 134,810,550 words)"
    )


def test_defect23_leg2_non_vacuity_identity_is_the_documented_intent():
    """L2 (non-vacuity): the slots are exactly (vpn<<8)|7, not merely 'small' or 'zero'."""
    cpu, _ = _bake_and_run("paged_dispatch")
    base = _pt_base(cpu)
    for p in range(PT_BASE_SLOTS):
        v = cpu.memory[base + p]
        assert v == (p << 8) | 0x7, f"slot {p} must be {(p << 8) | 0x7:#x}, got {v:#x}"
        assert v >> 8 == p, f"slot {p} must map frame {p} (identity), got pfn {v >> 8}"
        assert v & 0x7 == 0x7, f"slot {p} must carry V|W|U, got flags {v & 0x7:#x}"


def test_defect23_leg3_other_modes_leave_a_wellformed_window():
    """L3 (discrimination): the two writers of this window — one well-formed, one not.

    MEASURED this tick: `admit` mode's per-slot arming (`baker.py:5155-5181`) writes its eight
    PTEs as explicit constants and produces exactly `[0x7, 0x107, 0x207, 0x307, 0x407, 0x507,
    0x50F, 0x707]` — note slot 6 = `(5 << 8) | 0xF`, the documented vpn-6 PIX remap to pfn 5.
    `paged_dispatch`'s *loop* writes the same window and, pre-fix, produced
    `0x15000107, 0x10807, ...`. So this leg pins the correct shape of the window and shows the
    defect was the loop's arithmetic, not the window's contract.
    """
    cpu, _ = _bake_and_run("baseline")
    assert _pt_base(cpu) == 0, "baseline does not arm paging, so pt_base must stay 0"
    assert [cpu.memory[i] for i in range(1536, 1544)] == [0] * 8, (
        "baseline must leave the PT window zeroed"
    )

    cpu, _ = _bake_and_run("admit")
    base = _pt_base(cpu)
    assert base == 1536, f"admit arms pt_base 1536, got {base}"
    expected = [0x7, 0x107, 0x207, 0x307, 0x407, 0x507, 0x50F, 0x707]
    observed = [cpu.memory[base + p] for p in range(PT_BASE_SLOTS)]
    assert observed == expected, (
        "admit's arming writes explicit constants and must be well-formed.\n"
        f"  expected {[hex(v) for v in expected]}\n"
        f"  observed {[hex(v) for v in observed]}"
    )
    assert len(cpu.memory) == RAM_WORDS, "admit must not materialise RAM past its bound"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
