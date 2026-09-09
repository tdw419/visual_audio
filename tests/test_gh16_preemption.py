#!/usr/bin/env python3
"""tests/test_gh16_preemption.py — GH-16 Preemptive Scheduling oracle test.

Falsifiable gate for GH-16 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):
1. Preemptive scheduling: timer MMIO word counts down per N steps; engine
   raises tick -> kernel tick-handler saves context to box stack, advances
   round-robin.
2. Starvation proof: spinning USER task in BOX0 (infinite loop, never yields)
   cannot starve BOX1 (BOX1 completes while BOX0 spins).
3. Context save/restore: register-exact preservation across tick preemption.
4. Privilege isolation: USER task cannot disable the timer or tick handler
   (MODE_LATCH gate: tick MMIO only writeable in SUPER; USER store traps to
   KFAULT_PC).
5. Zero-dev-import property: runner.py stays clean (<= 200 lines, 0 dev imports).
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
from tools.glyph_gpt.baker import preemptive_kernel_image      # noqa: E402 (RED: not implemented yet)

# GH-16 image ABI constants
GH16_UART_A_WORD = 710
GH16_UART_A_LEN  = 712
GH16_EXIT_A      = 703
GH16_UART_B_WORD = 720
GH16_UART_B_LEN  = 722
GH16_EXIT_B      = 723
GH16_FAULT_WORD  = 731
GH16_TURN_WORD   = 705
GH16_TICKS_COUNT = 732         # kernel writes number of ticks serviced here
GH16_VERIFY_WORD = 704
GH16_VERIFY_OK   = 0xFEEDCAFE

GH16_BOX0_LO_BYTE = 4 * 700
GH16_BOX0_HI_BYTE = 4 * 717
GH16_BOX1_LO_BYTE = 4 * 718
GH16_BOX1_HI_BYTE = 4 * 735

GH16_N_B = 7
GH16_EXIT_OK_B = 0xFEED0000 | GH16_N_B
GH16_FAULT_SEEN = 0xFA171
KERNEL_OK = 0xCAFE0016
PACK_B = 0x42424242            # 'B' * 4 little-endian


def _bake(
    tmp: Path,
    name: str = "gh16.glyph.npy",
    fault_leg: bool = False,
    timer_quantum: int = 20,
    context_save_leg: bool = False,
) -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    preemptive_kernel_image(
        atlas,
        fault_leg=fault_leg,
        timer_quantum=timer_quantum,
        context_save_leg=context_save_leg,
        out_path=out,
    )
    return out


def _run(
    tmp: Path,
    fault_leg: bool = False,
    timer_quantum: int = 20,
    context_save_leg: bool = False,
):
    out = _bake(
        tmp,
        fault_leg=fault_leg,
        timer_quantum=timer_quantum,
        context_save_leg=context_save_leg,
    )
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=60000, trace=True)
    return receipt


def test_gh16_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d))
        assert out.exists(), "preemptive_kernel_image must emit an image file"


def test_gh16_spinning_task_a_cannot_starve_task_b():
    """Starvation broken: Task A in BOX0 enters an infinite loop:
        :__spin
        ADD r1 r2
        JMP :__spin
    Task A NEVER calls SYSCALL, NEVER executes KJMP, NEVER yields.
    Without preemption, Task B would never run.
    Under GH-16, the timer downcounter decrements, fires tick, kernel preempts
    Task A into SUPER, saves context, and switches to Task B in BOX1.
    Task B writes its output and completes."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d), timer_quantum=20)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]

        # Task B ran and produced its signature
        assert mem[GH16_UART_B_WORD] == PACK_B, (
            f"task B UART word 0x{mem[GH16_UART_B_WORD]:08x} != 0x{PACK_B:08x}")
        assert mem[GH16_UART_B_LEN] == 4, f"task B UART len {mem[GH16_UART_B_LEN]} != 4"
        assert mem[GH16_EXIT_B] == GH16_EXIT_OK_B, (
            f"task B exit 0x{mem[GH16_EXIT_B]:08x} != 0x{GH16_EXIT_OK_B:08x}")

        # Ticks were serviced
        assert mem[GH16_TICKS_COUNT] >= 1, (
            f"expected >= 1 tick serviced, got {mem[GH16_TICKS_COUNT]}")

        # Overall kernel completion status
        assert receipt["status_word_value"] == KERNEL_OK, receipt

        # Step trace verification: prove preemption occurred
        trace = receipt.get("step_trace") or []
        assert trace, "runner receipt must carry step_trace"

        # Check mode transitions: must see USER (Task A) -> SUPER (Tick handler) -> USER (Task B)
        modes = [mode for _, mode in trace]
        assert "USER" in modes and "SUPER" in modes

        # Find first USER phase (Task A)
        first_user = modes.index("USER")
        # Find SUPER phase following first USER phase (Tick preemption)
        first_super_after_user = modes.index("SUPER", first_user)
        # Find subsequent USER phase (Task B)
        second_user = modes.index("USER", first_super_after_user)
        assert second_user > first_super_after_user > first_user, (
            "Step trace must prove transition: Task A (USER) -> Tick (SUPER) -> Task B (USER)")


def test_gh16_context_save_restore_exact():
    """Context save/restore: register-exact preservation across tick preemption.
    Task A sets r1=0x11223344, r2=0x55667788 and spins in wait-loop.
    Tick preempts Task A into SUPER, kernel saves context to stack words (700, 701, 708).
    Task B executes in BOX1 and aggressively clobbers r1=0xDEADBEEF, r2=0xBAADF00D.
    Task B yields to resume Task A.
    Kernel restores r1/r2 from save words, resumes Task A in USER mode.
    Task A verifies r1 and r2 match original values and writes GH16_VERIFY_OK (0xFEEDCAFE)
    to word 704."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d), context_save_leg=True, timer_quantum=35)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]

        # Task B completed and produced signature
        assert mem[GH16_UART_B_WORD] == PACK_B
        assert mem[GH16_UART_B_LEN] == 4
        assert mem[GH16_EXIT_B] == GH16_EXIT_OK_B

        # Task A resumed with preserved r1/r2 and wrote VERIFY_OK
        assert mem[GH16_VERIFY_WORD] == GH16_VERIFY_OK, (
            f"verify word 0x{mem[GH16_VERIFY_WORD]:08x} != 0x{GH16_VERIFY_OK:08x}")
        assert mem[GH16_EXIT_A] == 0xFEED0000, (
            f"task A exit 0x{mem[GH16_EXIT_A]:08x} != 0xFEED0000")

        # Ticks were serviced
        assert mem[GH16_TICKS_COUNT] >= 1

        # Kernel status word
        assert receipt["status_word_value"] == KERNEL_OK


def test_gh16_user_cannot_disable_tick():
    """Privilege isolation: Task A in USER mode attempts to overwrite the timer
    countdown or tick PC MMIO word. Because 0x8000+ is outside BOX0, the store
    must trigger an E-K1 isolation fault to KFAULT_PC."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d), fault_leg=True, timer_quantum=20)
        mem = receipt["memory"]
        assert mem[GH16_FAULT_WORD] == GH16_FAULT_SEEN, (
            f"fault word 0x{mem[GH16_FAULT_WORD]:08x} != 0x{GH16_FAULT_SEEN:08x}")


def test_gh16_runner_line_budget_and_clean_imports():
    """GH-5 / GH-11 invariant preserved: runner.py <= 200 lines, 0 dev imports."""
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
