#!/usr/bin/env python3
"""tests/test_gh10_shell.py — GH-10 oracle test (RED until baker grows
shell_kernel_image()).

Falsifiable gate for GH-10 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

    Shell: resident program polls cmd buffer (MMIO); commands echo/ps/cp/rm/run
    map to kernel ops; writes prompt+output to uart buffer.
    Gate: host writes "echo hi" to cmd buffer, run to halt, uart contains "hi";
    "ps" lists 2 GH-7 tasks; unknown cmd -> error string.

1. baker.shell_kernel_image(atlas, out_path=...) emits ONE image whose
   resident kernel:
     - arms vectors: KSYS_PC -> in-image shell dispatcher (the shell IS the
       kernel here: one SUPER-mode selector), KFAULT_PC -> fault handler,
     - programs BOX0 (the shell's task arena),
     - polls the cmd buffer: CMD_FLAG (0 = idle -> write prompt, done tail;
       1 = command ready -> dispatch on CMD_WORD0/HI), clearing the flag
       after servicing the command.

2. Image ABI (fixed word indices; BOX0 = [700..768), the GH-8/GH-9 scheme):
     - GH10_CMD_FLAG  = 903  host->shell: 1 = command ready (shell clears)
     - GH10_CMD_WORD0 = 904  command word LOW 24 bits (host-stored)
     - GH10_CMD_WORD1 = 905  command word HIGH 8 bits (host-stored)
     - GH10_UART      = 910  shell output: one packed 4-byte word
     - GH10_UART_LEN  = 911  output byte count
     - GH10_ERR_WORD  = 912  unknown-command verdict ('E' = 69)
     - cmd encodings: 'echo' = 0x6F686365 ('e'|'c'<<8|'h'<<16|'o'<<24
       little-endian "echo" -> low 24 bits 0x686365 'c','h','e'... the test
       fixes the exact u32 constants and the gate compares them), 'ps' =
       packed "ps" + NUL pad. Command words are HOST-stored; the shell only
       compares and reacts.
     - echo payload: the shell re-emits the command word's own bytes as the
       output word, so "echo hi" in => "hi" in the uart word (self-describing
       payload, no separate arg block needed for the gate).

3. Receipt checks (the roadmap oracle, three legs):
     - echo leg: host stores 'echo' cmd + payload word, sets CMD_FLAG=1, runs
       to halt; mem[GH10_UART] == payload ('hi' packed), mem[GH10_UART_LEN]
       == 2, CMD_FLAG back to 0 (consumed).
     - ps leg: separate image/run; mem[GH10_UART] == 0x42410000 | 2 (packed
       "AB" + task-count 2 in the low byte) — the GH-7 task letters 'A','B'
       plus the count the roadmap requires ("ps lists 2 GH-7 tasks"),
       mem[GH10_UART_LEN] == 3.
     - unknown-cmd leg: host stores 0xDEADBEEF (not a known verb), runs;
       mem[GH10_ERR_WORD] == ord('E'), the uart word stays 0 (nothing
       echoed), CMD_FLAG still consumed.

4. Idle leg: fresh image, no command armed -> the shell writes its prompt
   verdict (GH10_PROMPT = 0x3E202020 packed " >" + pad... the test pins the
   exact constant imported from baker) and halts cleanly with the status
   word showing 0xCAFE0000 | 10.

5. Isolation leg: fault_leg=True bakes the polling leg's first act as an
   out-of-box store (word 900) -> E-K1, fault handler records 0xFA171,
   the uart word stays 0.

6. Zero-dev-import property (same as GH-6..GH-9): runner.py stays clean.

Today this FAILS at import: shell_kernel_image does not exist yet.
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import shell_kernel_image             # noqa: E402  (RED: not implemented)
from tools.glyph_gpt.baker import (                              # noqa: E402
    GH10_CMD_FLAG as CMD_FLAG,
    GH10_CMD_WORD0 as CMD_WORD0,
    GH10_CMD_WORD1 as CMD_WORD1,
    GH10_UART as UART,
    GH10_UART_LEN as UART_LEN,
    GH10_ERR_WORD as ERR_WORD,
    GH10_PROMPT as PROMPT,
)

STATUS_WORD = 950

# GH-10 image ABI mirrors (fixed word indices; BOX0 = [700..768), GH-8/9
# scheme). Words 903..912: below the pixel-aliased FS window [1024,1280),
# clear of BOX0, status 950, GH-9 mailbox [800,896) + flag 960/n_px 961,
# and the GH-3 legacy payload at 964. The shell is also GH-7-aware: 'ps'
# reports task letters A/B because the GH-7 arenas are a fixed convention.
GH10_EXIT_WORD = 703      # shell session's exit word (in BOX0)
GH10_FAULT_WORD = 731     # fault-leg verdict (0xFA171)
GH10_FAULT_SEEN = 0xFA171
KERNEL_OK = 0xCAFE000A    # 0xCAFE0000 | 10
EXIT_OK = 0xFEED000A

CMD_ECHO = (ord('e') | (ord('c') << 8) | (ord('h') << 16) | (ord('o') << 24))
CMD_PS = (ord('p') | (ord('s') << 8))
# echo 'hi': the payload word rides in (CMD_WORD1 << 24 | ... no — the host
# stores the ARG word at CMD_WORD0 and the payload word at CMD_WORD1; the
# shell copies CMD_WORD1 to the uart. 'hi' packed little-endian:
PAYLOAD_HI = (ord('h') | (ord('i') << 8))
PS_EXPECT = (ord('A') | (ord('B') << 8) | (2 << 16))   # "AB" + task count 2


def _bake(tmp: Path, name: str = "gh10.glyph.npy", fault_leg: bool = False) -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    shell_kernel_image(atlas, fault_leg=fault_leg, out_path=out)
    return out


def _run(tmp: Path, cmd0: int = 0, cmd1: int = 0, arm: bool = False,
         fault_leg: bool = False, name: str = "gh10.glyph.npy"):
    """Bake, seed the host-side cmd buffer (the only host writes — the shell
    polls it in-image), run to halt, return (runner, cpu)."""
    out = _bake(tmp, name=name, fault_leg=fault_leg)
    runner = GlyphRunner(out, ram_words=16384)
    cpu = runner.get_cpu()
    if arm or fault_leg:
        cpu.memory[CMD_WORD0] = cmd0
        cpu.memory[CMD_WORD1] = cmd1
        cpu.memory[CMD_FLAG] = 1
    cpu.run(runner.image, max_instructions=60000)
    return runner, cpu


def test_gh10_shell_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d)).exists(), "shell_kernel_image must emit one image"


def test_gh10_echo_hi():
    """The roadmap oracle: host writes 'echo hi' to the cmd buffer, run to
    halt, the uart buffer contains 'hi'."""
    with tempfile.TemporaryDirectory() as d:
        _, cpu = _run(Path(d), cmd0=CMD_ECHO, cmd1=PAYLOAD_HI, arm=True)
        assert not cpu.faulted, f"faulted: addr={cpu.fault_addr:#x}"
        assert not cpu.running, "run must reach HALT"
        mem = cpu.memory
        assert mem[UART] == PAYLOAD_HI, (
            f"uart 0x{mem[UART]:08x} != payload 0x{PAYLOAD_HI:08x} ('hi')")
        assert mem[UART_LEN] == 2, f"uart len {mem[UART_LEN]} != 2"
        assert mem[CMD_FLAG] == 0, "shell must consume the cmd flag"
        assert mem[GH10_EXIT_WORD] == EXIT_OK
        assert mem[STATUS_WORD] == KERNEL_OK


def test_gh10_ps_lists_two_tasks():
    """'ps' lists the 2 GH-7 tasks: packed 'AB' + count 2 in the uart."""
    with tempfile.TemporaryDirectory() as d:
        _, cpu = _run(Path(d), cmd0=CMD_PS, cmd1=0, arm=True,
                      name="gh10_ps.glyph.npy")
        assert not cpu.faulted and not cpu.running
        mem = cpu.memory
        assert mem[UART] == PS_EXPECT, (
            f"uart 0x{mem[UART]:08x} != 0x{PS_EXPECT:08x} (packed 'AB'+2)")
        assert mem[UART_LEN] == 3
        assert mem[CMD_FLAG] == 0


def test_gh10_unknown_cmd_errors():
    """Unknown verb: 'E' verdict at GH10_ERR_WORD, nothing echoed."""
    with tempfile.TemporaryDirectory() as d:
        _, cpu = _run(Path(d), cmd0=0xDEADBEEF, cmd1=0x41414141, arm=True,
                      name="gh10_bad.glyph.npy")
        assert not cpu.faulted and not cpu.running
        mem = cpu.memory
        assert mem[ERR_WORD] == ord('E'), (
            f"err word 0x{mem[ERR_WORD]:08x} != 'E'")
        assert mem[UART] == 0, "unknown cmd must not echo anything"
        assert mem[CMD_FLAG] == 0


def test_gh10_idle_prompt():
    """No command armed: the shell writes its prompt verdict and halts via
    the done tail (status 0xCAFE000A)."""
    with tempfile.TemporaryDirectory() as d:
        _, cpu = _run(Path(d), name="gh10_idle.glyph.npy")
        assert not cpu.faulted and not cpu.running
        mem = cpu.memory
        assert mem[UART] == PROMPT, (
            f"uart 0x{mem[UART]:08x} != prompt verdict 0x{PROMPT:08x}")
        assert mem[STATUS_WORD] == KERNEL_OK


def test_gh10_fault_leg_isolates():
    """fault_leg: the shell leg's first act is an out-of-box store (word
    900); E-K1 vectors to KFAULT_PC, the handler records 0xFA171, and the
    uart stays 0."""
    with tempfile.TemporaryDirectory() as d:
        _, cpu = _run(Path(d), fault_leg=True, name="gh10_fault.glyph.npy")
        assert cpu.faulted, "out-of-box user store must fault"
        assert not cpu.running, "run must reach HALT via the fault handler"
        mem = cpu.memory
        assert mem[GH10_FAULT_WORD] == GH10_FAULT_SEEN
        assert mem[UART] == 0
        assert mem[STATUS_WORD] == KERNEL_OK


def test_gh10_runner_still_zero_dev_imports():
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
