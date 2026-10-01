#!/usr/bin/env python3
"""tests/test_gh7_processes.py — GH-7 oracle test (RED until baker grows
multiproc_kernel_image()).

Falsifiable gate for GH-7 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

1. baker.multiproc_kernel_image(atlas, out_path=...) emits ONE image whose
   resident kernel:
     - arms vectors: KSYS_PC -> in-image syscall dispatcher, KFAULT_PC ->
       fault handler (loader-seeded packed pixel PCs, two-pass bake),
     - programs BOTH boxes: BOX0 = task A arena, BOX1 = task B arena,
     - enters task A (MODE_LATCH = 1, KJMP -- the only latch consumer),
     - when task A KJMP-exits to the kernel, the kernel re-arms the latch
       and KJMPs into task B (round-robin switch via MODE_LATCH/JMPR-KJMP),
     - after task B exits, the kernel writes the final status and HALTs.

2. Each task issues its own SYSCALL (A: 6, B: 7); the SUPER handler writes
   the task's payload into that task's own UART region (A: words 710..712,
   B: words 720..722) and SYSRETs. Success is judged purely from the
   runner receipt:
     - receipt["halted"] is True, receipt["faulted"] is False
     - memory[710] == 'A'|'A'<<8|'A'<<16|'A'<<24, memory[712] == 4
     - memory[720] == 'B'|'B'<<8|'B'<<16|'B'<<24, memory[722] == 4
     - both exit words show 0xFEED0000 | syscall number (703: A, 723: B)

3. Interleaving proof: receipt["step_trace"] (pc,mode) tuples must show
   task A -> kernel (SUPER) -> task B -> kernel; task A must never run
   again after task B starts (round-robin, not re-run).

4. Isolation leg: a task-A out-of-box store (fault_leg=True) vectors to
   KFAULT_PC; the in-image handler records 0xFA171 at word 731; task B's
   UART region stays untouched (the faulted task never switched on).

5. Zero-dev-import property (same as GH-2/3/5/6): runner.py stays clean.

Today this FAILS at import: multiproc_kernel_image does not exist yet.
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

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import multiproc_kernel_image         # noqa: E402  (RED: not implemented)

# GH-7 image ABI (fixed word indices; below the atlas payload region, same
# region scheme as GH-6).
GH7_TURN_WORD = 705         # kernel-owned round-robin turn marker
GH7_UART_A_WORD = 710       # task A 'A','A','A','A' packed little-endian
GH7_UART_A_WORD2 = 711
GH7_UART_A_LEN = 712
GH7_TASK_A_BUF = 713        # task A scratch (in BOX0)
GH7_EXIT_A = 703            # task A exit status word (in BOX0)
GH7_UART_B_WORD = 720       # task B 'B','B','B','B' packed little-endian
GH7_UART_B_WORD2 = 721
GH7_UART_B_LEN = 722
GH7_EXIT_B = 723            # task B exit status word (in BOX1)
GH7_TASK_B_BUF = 727        # task B scratch (in BOX1)
GH7_BADSYS_WORD = 730       # unknown-syscall marker ('E' = 69)
GH7_FAULT_WORD = 731        # fault-leg verdict (0xFA171 = violation seen)
GH7_BOX0_LO_BYTE = 4 * 700  # BOX0 = task A arena [700..717)
GH7_BOX0_HI_BYTE = 4 * 717
GH7_BOX1_LO_BYTE = 4 * 718  # BOX1 = task B arena [718..735)
GH7_BOX1_HI_BYTE = 4 * 735
GH7_N_A = 6                 # task A's syscall number
GH7_N_B = 7                 # task B's syscall number
GH7_EXIT_OK_A = 0xFEED0000 | GH7_N_A
GH7_EXIT_OK_B = 0xFEED0000 | GH7_N_B
GH7_FAULT_SEEN = 0xFA171
KERNEL_OK = 0xCAFE0007      # 0xCAFE0000 | 7 (final status after task B)
PACK_A = 0x41414141         # 'A' * 4 packed little-endian
PACK_B = 0x42424242         # 'B' * 4 packed little-endian


def _bake(tmp: Path, name: str = "gh7.glyph.npy", fault_leg: bool = False) -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    multiproc_kernel_image(atlas, fault_leg=fault_leg, out_path=out)
    return out


def _run(tmp: Path, fault_leg: bool = False):
    out = _bake(tmp, fault_leg=fault_leg)
    # The scheduler kernel stores into the isolation MMIO block (KSYS_PC,
    # KFAULT_PC, BOX0/BOX1, MODE_LATCH at word 8192+), so the runner must
    # arm GlyphCPUv2._iso_enabled by sizing RAM past the MMIO top word.
    # trace=True records the (instruction, mode) step trace used for the
    # round-robin interleaving proof.
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=60000, trace=True)
    return receipt


def _pack_bytes(bs: bytes) -> int:
    v = 0
    for i, b in enumerate(bs):
        v |= b << (8 * i)
    return v


def test_gh7_multiproc_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d)).exists(), "multiproc_kernel_image must emit one image"


def test_gh7_two_tasks_round_robin():
    """The whole GH-7 gate in one image run: kernel enters task A (USER,
    BOX0), A syscalls, kernel services and switches to task B (USER, BOX1),
    B syscalls, kernel services and halts. Both tasks' outputs are present
    in their OWN buffers; exit words prove both ran to completion."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d))
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # task A's syscall landed in A's uart region
        assert mem[GH7_UART_A_WORD] == PACK_A, (
            f"uart A word0 0x{mem[GH7_UART_A_WORD]:08x} != 0x{PACK_A:08x}")
        assert mem[GH7_UART_A_LEN] == 4, f"uart A len {mem[GH7_UART_A_LEN]} != 4"
        # task B's syscall landed in B's uart region
        assert mem[GH7_UART_B_WORD] == PACK_B, (
            f"uart B word0 0x{mem[GH7_UART_B_WORD]:08x} != 0x{PACK_B:08x}")
        assert mem[GH7_UART_B_LEN] == 4, f"uart B len {mem[GH7_UART_B_LEN]} != 4"
        # no cross-contamination: A's handler never wrote B's region (and vice versa)
        assert mem[GH7_UART_A_WORD2] == 0 and mem[GH7_UART_B_WORD2] == 0
        # unknown-syscall marker untouched
        assert mem[GH7_BADSYS_WORD] == 0
        # both tasks completed their syscall + exit writes
        assert mem[GH7_EXIT_A] == GH7_EXIT_OK_A, (
            f"task A exit 0x{mem[GH7_EXIT_A]:08x} != 0x{GH7_EXIT_OK_A:08x}")
        assert mem[GH7_EXIT_B] == GH7_EXIT_OK_B, (
            f"task B exit 0x{mem[GH7_EXIT_B]:08x} != 0x{GH7_EXIT_OK_B:08x}")
        # the turn marker was seeded by the kernel
        assert mem[GH7_TURN_WORD] == 0, "turn word must be kernel-seeded to 0"
        # final status: 0xCAFE0000 | 7 (after BOTH tasks ran)
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_gh7_interleaving_order():
    """Step-trace proof of switching: task A -> kernel(SUPER) -> task B ->
    kernel, and A never runs again after B starts (round-robin order)."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d))
        trace = receipt.get("step_trace") or []
        assert trace, "runner receipt must carry a step_trace"
        # Each task appears as TWO USER phases (pre-SYSCALL and post-SYSRET,
        # split by the SUPER-mode handler interlude): A1, A2, B1, B2.
        user_phases = []
        cur = None
        for pc, mode in trace:
            if mode == "USER":
                if cur is None:
                    cur = [pc, pc]
                else:
                    cur[1] = pc
            else:
                if cur is not None:
                    user_phases.append(tuple(cur))
                    cur = None
        if cur is not None:
            user_phases.append(tuple(cur))
        assert len(user_phases) == 4, (
            f"expected exactly 4 USER phases (A-pre, A-post, B-pre, B-post), "
            f"got {len(user_phases)}: {user_phases}")
        # Round-robin order: B never starts before A's last USER step, and
        # B's phases (higher PCs: later program region) never interleave
        # back into A's region.
        assert user_phases[1][1] < user_phases[2][0], (
            "task B must start only after task A's last USER step")
        assert all(p2 > p1 for p1, p2 in zip(user_phases, user_phases[1:])), (
            f"phases must be strictly ordered (round-robin): {user_phases}")


def test_gh7_fault_leg_isolates():
    """A task-A out-of-box store vectors to KFAULT_PC; the in-image handler
    records 0xFA171; task B's region stays untouched; run halts via kernel."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d), fault_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is True, "out-of-box user store must fault"
        mem = receipt["memory"]
        assert mem[GH7_FAULT_WORD] == GH7_FAULT_SEEN, (
            f"fault word 0x{mem[GH7_FAULT_WORD]:08x} != 0x{GH7_FAULT_SEEN:08x}")
        # the faulted A leg never switched on: B's uart untouched
        assert mem[GH7_UART_B_WORD] == 0
        assert mem[GH7_UART_B_LEN] == 0
        assert mem[GH7_EXIT_B] == 0


def test_gh7_runner_still_zero_dev_imports():
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
