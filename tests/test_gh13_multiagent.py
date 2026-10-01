#!/usr/bin/env python3
"""tests/test_gh13_multiagent.py — GH-13 oracle test (RED until baker grows
multiagent_kernel_image()).

Falsifiable gate for GH-13 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

    Multi-agent workspaces (agent = user task in its own box): generalize
    BOX0..BOXn to N per-agent arenas; each agent task runs in USER mode
    confined to its box; mailbox words for agent->agent and agent->kernel
    messages; kernel round-robins agents; a task CANNOT write outside its
    box (existing trap = isolation proof). Host-side builder agents attach
    one runner per agent box, each driven by a separate AI session.

1. baker.multiagent_kernel_image(atlas, out_path=...) emits ONE image whose
   resident kernel programs THREE boxes:
     BOX0 = agent A arena [700..717), BOX1 = agent B [718..735),
     BOX2 = agent C [736..753)   (BOX2 = the engine's third permitted range)
   and round-robins A -> B -> C via MODE_LATCH/KJMP (the one-shot latch
   consumer), each agent re-entering the kernel through the KJMP
   privilege boundary.

2. Pipeline leg (the roadmap scenario):
     - A (writer): stores pattern 0xA5A5A5A5 in its OWN scratch (BOX0),
       SYSCALL 6 -> kernel copies scratch -> A's uart (710) AND the
       agent->agent mailbox word (754).
     - B (reader/verifier): SYSCALL 7 -> kernel copies the mailbox into
       B's read-out (720); B NEVER touches A's arena -- it reads ONLY via
       the mailbox syscall, then verifies the pattern in its own box and
       writes 'V' (0x56) at its verdict word (724), 'E' on mismatch.
     - C (coordinator): SYSCALL 8 -> kernel packs A's payload (uart 710)
       and B's verdict (724) into C's read-out (746/747) via KSYS.
     Receipt proves: A uart == 0xA5A5A5A5, B read-out == 0xA5A5A5A5,
     B verdict == 'V', C read-out == (0xA5A5A5A5, 'V'), all three exit
     words 0xFEED0006/7/8, zero box violations (faulted False, badsys 0),
     final status 0xCAFE0008.

3. Interleaving proof: receipt["step_trace"] (pc,mode) must show exactly
   SIX USER phases (A-pre, A-post, B-pre, B-post, C-pre, C-post) in
   strictly increasing PC order -- kernel round-robin, no re-runs.

4. Isolation leg (fault_leg=True): agent A's out-of-box store (word 900)
   vectors to KFAULT_PC; the in-image handler records 0xFA171 at word 759;
   agents B and C are never scheduled (uarts + exits untouched).

5. Concurrent-runner leg: THREE GlyphRunner instances on the SAME baked
   image run concurrently (ThreadPoolExecutor); all three receipts are
   byte-identical and green -- the host-harness "one runner per agent"
   property.

6. Launcher invariants re-asserted: runner.py <= 200 lines, zero dev
   imports.

Today this FAILS at import: multiagent_kernel_image does not exist yet.
"""
from __future__ import annotations

import ast
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import multiagent_kernel_image        # noqa: E402  (RED: not implemented)

# GH-13 image ABI (fixed word indices; same region scheme as GH-7/GH-8).
GH13_TURN_WORD = 705         # kernel round-robin marker (SUPER-only writes)
GH13_EXIT_A, GH13_EXIT_B, GH13_EXIT_C = 703, 723, 739
GH13_UART_A_WORD = 710       # agent A output (kernel-written)
GH13_UART_A_LEN = 712
GH13_READOUT_B = 720         # agent B read-out (kernel copies mailbox here)
GH13_VERDICT_B = 724         # B's in-box verify verdict: 'V' or 'E'
GH13_UART_C_WORD0 = 746      # agent C read-out: A's payload
GH13_UART_C_WORD1 = 747      # agent C read-out: B's verdict
GH13_MAILBOX_WORD = 754      # agent->agent mailbox (kernel-mediated)
GH13_BADSYS_WORD = 758       # unknown-syscall marker ('E' = 69)
GH13_FAULT_WORD = 759        # fault-leg verdict (0xFA171)
GH13_BOX0_LO_BYTE = 4 * 700  # agent A arena [700..717)
GH13_BOX0_HI_BYTE = 4 * 717
GH13_BOX1_LO_BYTE = 4 * 718  # agent B arena [718..735)
GH13_BOX1_HI_BYTE = 4 * 735
GH13_BOX2_LO_BYTE = 4 * 736  # agent C arena [736..753)
GH13_BOX2_HI_BYTE = 4 * 753
GH13_N_A, GH13_N_B, GH13_N_C = 6, 7, 8
GH13_EXIT_OK_A = 0xFEED0000 | GH13_N_A
GH13_EXIT_OK_B = 0xFEED0000 | GH13_N_B
GH13_EXIT_OK_C = 0xFEED0000 | GH13_N_C
GH13_FAULT_SEEN = 0xFA171
GH13_PATTERN = 0xA5A5A5A5
VERIFIED = ord('V')
KERNEL_OK = 0xCAFE0008       # 0xCAFE0000 | 8 (after agent C)


def _bake(tmp: Path, name: str = "gh13.glyph.npy", fault_leg: bool = False) -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    multiagent_kernel_image(atlas, fault_leg=fault_leg, out_path=out)
    return out


def _run(tmp: Path, fault_leg: bool = False):
    out = _bake(tmp, fault_leg=fault_leg)
    # The kernel stores into the isolation MMIO block (KSYS_PC, KFAULT_PC,
    # BOX0/1/2, MODE_LATCH at word 8192+), so the runner must arm
    # GlyphCPUv2._iso_enabled by sizing RAM past the MMIO top word.
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=80000, trace=True)
    return receipt


def test_gh13_multiagent_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d)).exists(), "multiagent_kernel_image must emit one image"


def test_gh13_three_agents_pipeline():
    """A writes -> B reads (mailbox only) + verifies -> C coordinates.
    The whole GH-13 gate in one image run."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d))
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt  # zero box violations
        mem = receipt["memory"]
        # A's payload landed in A's uart AND the agent->agent mailbox
        assert mem[GH13_UART_A_WORD] == GH13_PATTERN, (
            f"uart A 0x{mem[GH13_UART_A_WORD]:08x} != 0x{GH13_PATTERN:08x}")
        assert mem[GH13_UART_A_LEN] == 4
        assert mem[GH13_MAILBOX_WORD] == GH13_PATTERN
        # B read ONLY via the mailbox syscall: read-out carries the pattern
        assert mem[GH13_READOUT_B] == GH13_PATTERN, (
            f"B read-out 0x{mem[GH13_READOUT_B]:08x} != 0x{GH13_PATTERN:08x}")
        # B verified the pattern in its own box
        assert mem[GH13_VERDICT_B] == VERIFIED, (
            f"B verdict {mem[GH13_VERDICT_B]!r} != 'V'")
        # C received both statuses via KSYS: A's payload + B's verdict
        assert mem[GH13_UART_C_WORD0] == GH13_PATTERN
        assert mem[GH13_UART_C_WORD1] == VERIFIED
        # unknown-syscall marker untouched
        assert mem[GH13_BADSYS_WORD] == 0
        # all three agents completed: exit words 0xFEED0006/7/8
        assert mem[GH13_EXIT_A] == GH13_EXIT_OK_A, (
            f"agent A exit 0x{mem[GH13_EXIT_A]:08x}")
        assert mem[GH13_EXIT_B] == GH13_EXIT_OK_B, (
            f"agent B exit 0x{mem[GH13_EXIT_B]:08x}")
        assert mem[GH13_EXIT_C] == GH13_EXIT_OK_C, (
            f"agent C exit 0x{mem[GH13_EXIT_C]:08x}")
        # final status: 0xCAFE0000 | 8 (after ALL THREE agents ran)
        assert receipt["status_word_value"] == KERNEL_OK, receipt


def test_gh13_interleaving_order():
    """Step-trace proof of 3-agent round-robin: exactly SIX USER phases
    (A-pre, A-post, B-pre, B-post, C-pre, C-post), strictly ordered; no
    agent ever runs again after its successor starts."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d))
        trace = receipt.get("step_trace") or []
        assert trace, "runner receipt must carry a step_trace"
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
        assert len(user_phases) == 6, (
            f"expected exactly 6 USER phases (A,B,C x pre/post), got "
            f"{len(user_phases)}: {user_phases}")
        assert all(p2[0] > p1[1] for p1, p2 in zip(user_phases, user_phases[1:])), (
            f"phases must be strictly ordered (round-robin A->B->C): {user_phases}")


def test_gh13_fault_leg_isolates():
    """Agent A's out-of-box store vectors to KFAULT_PC; the handler records
    0xFA171; agents B and C are never scheduled (uarts + exits untouched)."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d), fault_leg=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is True, "out-of-box agent store must fault"
        mem = receipt["memory"]
        assert mem[GH13_FAULT_WORD] == GH13_FAULT_SEEN, (
            f"fault word 0x{mem[GH13_FAULT_WORD]:08x} != 0x{GH13_FAULT_SEEN:08x}")
        # B and C never ran: their regions untouched
        assert mem[GH13_READOUT_B] == 0
        assert mem[GH13_VERDICT_B] == 0
        assert mem[GH13_EXIT_B] == 0
        assert mem[GH13_UART_C_WORD0] == 0
        assert mem[GH13_EXIT_C] == 0


def test_gh13_three_runners_concurrent_same_image():
    """Host-harness property: 3 GlyphRunner instances attached to the SAME
    baked image run concurrently; all receipts byte-identical and green."""
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d))

        def one_run(_: int):
            r = GlyphRunner(out, ram_words=16384).run(max_instructions=80000)
            return r["memory"], r["status_word_value"], r["halted"], r["faulted"]

        with ThreadPoolExecutor(max_workers=3) as ex:
            results = list(ex.map(one_run, range(3)))
        assert len(results) == 3
        first = results[0]
        assert first[2] is True and first[3] is False, "run 0 must halt clean"
        assert first[1] == KERNEL_OK
        for i, (mem, status, halted, faulted) in enumerate(results[1:], start=1):
            assert halted and not faulted, f"run {i} not clean"
            assert status == KERNEL_OK, f"run {i} status 0x{status:08x}"
            assert mem == first[0], f"run {i} memory diverges from run 0"


def test_gh13_runner_invariants_hold():
    """Launcher invariants re-asserted after the GH-13 addition (baker-only
    change, but the gate keeps them honest)."""
    lines = (_REPO / "tools" / "glyph_gpt" / "runner.py").read_text().splitlines()
    assert len(lines) <= 200, f"runner.py exceeds 200 lines: {len(lines)}"
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
