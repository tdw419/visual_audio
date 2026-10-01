#!/usr/bin/env python3
"""tests/test_gh6_syscalls.py — GH-6 oracle test (RED until baker grows
syscalluart_kernel_image()).

Falsifiable gate for GH-6 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

1. baker.syscalluart_kernel_image(atlas, out_path=...) emits ONE image whose
   resident kernel:
     - arms the E-K2 syscall vector: writes the packed pixel PC of its
       in-image syscall handler into KSYS_PC (engine SYSCALL traps there),
     - puts a USER task in a box (BOX0) and enters it in USER mode,
     - the user task issues SYSCALL (SWI): the engine marshals
       r17/r10/r11 -> SYS_N/SYS_A0/SYS_A1, drops to SUPER, jumps KSYS_PC,
     - the kernel handler copies len bytes from the task's buffer into the
       UART output region and appends its byte count, writes SYS_A0 back,
     - SYSRET re-enters USER with the result in r10;
     - the task then writes its syscall exit status to the EXIT word and HALTs.

2. The host does NOT execute any Python syscall handler. Success is judged
   purely from the runner receipt:
     - receipt["halted"] is True, receipt["faulted"] is False
     - receipt["memory"][UART region] contains HELLO as packed bytes
     - receipt["memory"][GH6_EXIT_WORD] == GH6_EXIT_OK
     - receipt["memory"][GH6_N_UART_WORD] == len(HELLO)

3. Box-violation leg (Lever #2 still armed under the syscall kernel):
   a USER task storing OUTSIDE its box vectors to KFAULT_PC; the in-image
   fault handler records FAULTED and the run still halts cleanly with
   GH6_FAULT_WORD == GH6_FAULT_SEEN and receipt["faulted"] True.

4. Zero-dev-import property (same as GH-2/3/5): runner.py stays clean.

Today this FAILS at import: syscalluart_kernel_image does not exist yet.
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
from tools.glyph_gpt.baker import syscalluart_kernel_image       # noqa: E402  (RED: not implemented)
from tools.glyph_isa_v2 import (                                 # noqa: E402
    KFAULT_PC_ADDR, KSYS_PC_ADDR, MODE_LATCH_ADDR,
    BOX0_LO_ADDR, BOX0_HI_ADDR, BOX1_LO_ADDR, BOX1_HI_ADDR,
    SYS_N_ADDR, SYS_A0_ADDR, SYS_A1_ADDR,
)

# GH-6 image ABI (fixed word indices; below the atlas payload region)
GH6_UART_WORD = 700        # 'H','E','L','L' packed little-endian bytes
GH6_UART_WORD2 = 701       # 'O'
GH6_UART_LEN_WORD = 702    # bytes the handler wrote
GH6_EXIT_WORD = 703        # task's syscall exit status
GH6_EXIT_OK = 0xFEED0006   # 0xFEED0000 | syscall number written by the task
GH6_FAULT_WORD = 704       # fault-leg verdict
GH6_FAULT_SEEN = 0xFA171   # handler writes this on an out-of-box user store
GH6_N = 6                  # syscall number the user task issues
HELLO = b"HELLO"

KERNEL_OK = 0xCAFE0006     # 0xCAFE0000 | 6 (GH-6 succeeds where GH-2 left off)


def _bake(tmp: Path, name: str = "gh6.glyph.npy") -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    syscalluart_kernel_image(atlas, out_path=out)
    return out


def _run(tmp: Path, name: str = "gh6.glyph.npy"):
    out = _bake(tmp, name)
    # The syscall kernel stores into the isolation MMIO block (KSYS_PC,
    # KFAULT_PC, MODE_LATCH at word 8192+), so the runner must arm
    # GlyphCPUv2._iso_enabled by sizing RAM past the MMIO top word.
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=40000)
    return receipt


def _pack_bytes(bs: bytes) -> int:
    v = 0
    for i, b in enumerate(bs):
        v |= b << (8 * i)
    return v


def test_gh6_syscall_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d)).exists(), "syscalluart_kernel_image must emit one image"


def test_gh6_hello_via_syscall():
    """The whole GH-6 gate in one image run: USER box task -> SYSCALL ->
    kernel handler appends to the UART region -> SYSRET -> task exits."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _run(Path(d))
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        assert mem[GH6_UART_WORD] == _pack_bytes(HELLO[:4]), (
            f"uart word0 0x{mem[GH6_UART_WORD]:08x} != "
            f"0x{_pack_bytes(HELLO[:4]):08x} ({HELLO!r} expected)")
        assert mem[GH6_UART_WORD2] == _pack_bytes(HELLO[4:]), (
            f"uart word1 0x{mem[GH6_UART_WORD2]:08x} != 'O'")
        assert mem[GH6_UART_LEN_WORD] == len(HELLO), (
            f"uart len {mem[GH6_UART_LEN_WORD]} != {len(HELLO)}")
        assert mem[GH6_EXIT_WORD] == GH6_EXIT_OK, (
            f"exit word 0x{mem[GH6_EXIT_WORD]:08x} != 0x{GH6_EXIT_OK:08x}")


def test_gh6_box_violation_still_traps():
    """Lever #2 survives the syscall kernel: a USER store outside BOX0
    vectors to KFAULT_PC; the in-image fault handler records the fault."""
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        out = Path(d) / "gh6_fault.glyph.npy"
        syscalluart_kernel_image(atlas, fault_leg=True, out_path=out)
        receipt = GlyphRunner(out, ram_words=16384).run(max_instructions=40000)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is True, "out-of-box user store must fault"
        mem = receipt["memory"]
        assert mem[GH6_FAULT_WORD] == GH6_FAULT_SEEN, (
            f"fault word 0x{mem[GH6_FAULT_WORD]:08x} != 0x{GH6_FAULT_SEEN:08x}")
        # the violation leg must NOT have written the uart
        assert mem[GH6_UART_LEN_WORD] == 0


def test_gh6_runner_still_zero_dev_imports():
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
