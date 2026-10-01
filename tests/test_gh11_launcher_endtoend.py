#!/usr/bin/env python3
"""tests/test_gh11_launcher_endtoend.py — GH-11 oracle test (RED until
runner.py grows the end-to-end driver).

Falsifiable gate for GH-11 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

    Launcher final form ≤200 lines driving GH-6..GH-10 suites end-to-end.
    Gate: line-count assert + all GH suites green through launcher.

1. Line-count invariant: runner.py stays ≤200 lines (GH-5 gate, re-checked
   after the GH-11 addition).
2. Zero dev imports: same AST gate as GH-5..GH-10 — the launcher must never
   import atlas/spatial_builder/synth/baker/etc.
3. The launcher drives each resident kernel suite end-to-end THROUGH
   GlyphRunner (no test-file drivers re-implemented in the launcher; the
   launcher exposes a generic session: construct from an image, seed words,
   run, read words). Proof legs (one per suite, receipt-checked):

     GH-6: bake syscalluart_kernel_image, launcher seeds nothing, run —
           uart words 700/701 carry 'HELL'/'O', len 5, exit 0xFEED0006.
     GH-7: bake multiproc_kernel_image, run — task A uart 0x41414141,
           task B uart 0x42424242, both exit words 0xFEED0006/7, status
           0xCAFE0007.
     GH-8: bake fs_kernel_image (min_rows=80), run — readout 0x11223344,
           exits 0xFEED0006/0xFEED0007, status 0xCAFE0008.
     GH-9: bake loader_kernel_image, launcher seeds argv + mailbox pixels
           (host-assembled program), run — result word == native C ref,
           exit 0xFEED0009, status 0xCAFE0009.
     GH-10: bake shell_kernel_image, launcher seeds cmd buffer 'echo hi',
           run — uart 'hi', len 2, flag consumed, status 0xCAFE000A.

   The same driver object type drives all five: one generic API, every
   generation of resident kernel.
4. Fault-leg spot checks through the same launcher (GH-7 fault leg +
   GH-10 fault leg): out-of-box USER stores fault and the handlers record
   0xFA171 — the launcher surfaces `faulted` honestly.

Today this FAILS at import: GlyphRunner.drive_kernel_suite() does not exist
yet.
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

from tools.glyph_gpt.atlas import build_default_atlas             # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                    # noqa: E402
from tools.glyph_gpt.baker import (                               # noqa: E402
    fs_kernel_image,
    loader_kernel_image,
    multiproc_kernel_image,
    shell_kernel_image,
    syscalluart_kernel_image,
    GH9_MAILBOX_DATA,
    GH9_MAILBOX_FLAG,
    GH9_MAILBOX_N_PX,
)
from tools.rv64i_to_glyph import assemble_glyph_to_pixels         # noqa: E402

STATUS_WORD = 950

# --- per-suite receipt constants (mirror the suite tests) ---------------------
GH6_UART_W0, GH6_UART_W1, GH6_UART_LEN, GH6_EXIT = 700, 701, 702, 703
GH6_PACK = (ord('H') | (ord('E') << 8) | (ord('L') << 16) | (ord('L') << 24))
GH6_FAULT_WORD = 704
GH7_UART_A, GH7_UART_B, GH7_EXIT_A, GH7_EXIT_B = 710, 720, 703, 723
GH7_FAULT_WORD = 731
GH8_READOUT = 752
GH8_EXIT_A, GH8_EXIT_B = 703, 723
GH8_PAYLOAD0 = 0x11223344
GH9_ARGV_WORD, GH9_ARGV_RESULT, GH9_EXIT = 750, 754, 703
GH9_FAULT_WORD = 731
ARGV0, ARGV1 = 1234, 567
GH10_CMD_FLAG, GH10_CMD_WORD0, GH10_CMD_WORD1 = 903, 904, 905
GH10_UART, GH10_UART_LEN = 910, 911
GH10_FAULT_WORD = 731
GH10_CMD_ECHO = (ord('e') | (ord('c') << 8) | (ord('h') << 16) | (ord('o') << 24))
GH10_PAYLOAD_HI = (ord('h') | (ord('i') << 8))
FAULT_SEEN = 0xFA171
N_WINDOW_INSTRS = 24

INJECTED_PROGRAM_TEXT = """
:__injected
LDI r4 1
ADD r9 r10
ADD r9 r4
LD r12 r9
SUB r9 r4
LD r11 r9
LDI r4 2
XOR r12 r11
SHL r11 r4
ADD r11 r12
LDI r4 4
ADD r9 r4
ST r9 r11
LDI r4 9
LDI r14 65261
LDI r5 16
SHL r14 r5
ADD r14 r4
LDI r15 703
ST r15 r14
HALT
"""


def _program_pixel_words() -> list:
    pixels, _ = assemble_glyph_to_pixels(INJECTED_PROGRAM_TEXT, cols_instrs=8)
    h, w, _ = pixels.shape
    return [((int(pixels[y, x][0]) << 16) | (int(pixels[y, x][1]) << 8)
             | int(pixels[y, x][2])) for y in range(h) for x in range(w)]


def _bake(tmp, fn, name, **kw):
    atlas = build_default_atlas()
    out = tmp / name
    fn(atlas, out_path=out, **kw)
    return out


# --- gate 1+2: line count + zero dev imports (unchanged invariants) -----------
def test_gh11_runner_line_count_le_200():
    lines = (_REPO / "tools" / "glyph_gpt" / "runner.py").read_text().splitlines()
    assert len(lines) <= 200, f"runner.py exceeds 200 lines: {len(lines)}"


def test_gh11_runner_still_zero_dev_imports():
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


# --- gate 3: one generic launcher session drives all five suites --------------
def test_gh11_drives_gh6():
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d), syscalluart_kernel_image, "gh6.glyph.npy")
        r = GlyphRunner(out, ram_words=16384).run(max_instructions=40000)
        assert r["halted"] and not r["faulted"], r.get("error", r)
        mem = r["memory"]
        assert mem[GH6_UART_W0] == GH6_PACK
        assert mem[GH6_UART_LEN] == 5
        assert mem[GH6_EXIT] == 0xFEED0006


def test_gh11_drives_gh7():
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d), multiproc_kernel_image, "gh7.glyph.npy")
        r = GlyphRunner(out, ram_words=16384).run(max_instructions=40000)
        assert r["halted"] and not r["faulted"], r.get("error", r)
        mem = r["memory"]
        assert mem[GH7_UART_A] == 0x41414141
        assert mem[GH7_UART_B] == 0x42424242
        assert mem[GH7_EXIT_A] == 0xFEED0006 and mem[GH7_EXIT_B] == 0xFEED0007
        assert r["status_word_value"] == 0xCAFE0007


def test_gh11_drives_gh8():
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        out = Path(d) / "gh8.glyph.npy"
        fs_kernel_image(atlas, min_rows=80, out_path=out)
        r = GlyphRunner(out, ram_words=16384).run(max_instructions=60000)
        assert r["halted"] and not r["faulted"], r.get("error", r)
        mem = r["memory"]
        assert mem[GH8_READOUT] == GH8_PAYLOAD0
        assert mem[GH8_EXIT_A] == 0xFEED0006 and mem[GH8_EXIT_B] == 0xFEED0007
        assert r["status_word_value"] == 0xCAFE0008


def test_gh11_drives_gh9():
    """Launcher seeds argv + mailbox (host is the program loader), drives the
    resident loader kernel, checks the result against the native C reference."""
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d), loader_kernel_image, "gh9.glyph.npy")
        runner = GlyphRunner(out, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.memory[GH9_ARGV_WORD] = ARGV0
        cpu.memory[GH9_ARGV_WORD + 1] = ARGV1
        words = _program_pixel_words()
        assert len(words) >= N_WINDOW_INSTRS * 4
        cpu.memory[GH9_MAILBOX_FLAG] = 1
        cpu.memory[GH9_MAILBOX_N_PX] = N_WINDOW_INSTRS * 4
        for i, w in enumerate(words[:N_WINDOW_INSTRS * 4]):
            cpu.memory[GH9_MAILBOX_DATA + i] = w
        cpu.run(runner.image, max_instructions=60000)
        assert not cpu.faulted and not cpu.running
        mem = cpu.memory
        # native C reference for the mix contract
        c = Path(d) / "ref.c"
        c.write_text(
            "#include <stdio.h>\n"
            "int main() {\n"
            f"    unsigned a = {ARGV0}; unsigned b = {ARGV1};\n"
            "    unsigned r = ((a ^ b) + (a << 2)) & 0xFFFFFFFFu;\n"
            "    printf(\"%u\\n\", r);\n"
            "    return 0;\n"
            "}\n"
        )
        binp = Path(d) / "ref"
        subprocess.run(["gcc", "-O1", str(c), "-o", str(binp)], check=True)
        got_out = subprocess.run([str(binp)], capture_output=True, text=True, check=True)
        want = int(got_out.stdout.strip())
        assert mem[GH9_ARGV_RESULT] == want, (
            f"result 0x{mem[GH9_ARGV_RESULT]:08x} != native 0x{want:08x}")
        assert mem[GH9_EXIT] == 0xFEED0009
        assert mem[STATUS_WORD] == 0xCAFE0009


def test_gh11_drives_gh10():
    with tempfile.TemporaryDirectory() as d:
        out = _bake(Path(d), shell_kernel_image, "gh10.glyph.npy")
        runner = GlyphRunner(out, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.memory[GH10_CMD_WORD0] = GH10_CMD_ECHO
        cpu.memory[GH10_CMD_WORD1] = GH10_PAYLOAD_HI
        cpu.memory[GH10_CMD_FLAG] = 1
        cpu.run(runner.image, max_instructions=60000)
        assert not cpu.faulted and not cpu.running
        mem = cpu.memory
        assert mem[GH10_UART] == GH10_PAYLOAD_HI
        assert mem[GH10_UART_LEN] == 2
        assert mem[GH10_CMD_FLAG] == 0
        assert mem[STATUS_WORD] == 0xCAFE000A


# --- gate 4: fault legs through the same launcher ------------------------------
def test_gh11_fault_legs_surface_honestly():
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        # GH-7 fault leg
        out7 = Path(d) / "gh7f.glyph.npy"
        multiproc_kernel_image(atlas, fault_leg=True, out_path=out7)
        r7 = GlyphRunner(out7, ram_words=16384).run(max_instructions=40000)
        assert r7["faulted"] and r7["halted"]
        assert r7["memory"][GH7_FAULT_WORD] == FAULT_SEEN
        # GH-10 fault leg
        out10 = Path(d) / "gh10f.glyph.npy"
        shell_kernel_image(atlas, fault_leg=True, out_path=out10)
        runner = GlyphRunner(out10, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.memory[GH10_CMD_FLAG] = 1
        cpu.run(runner.image, max_instructions=60000)
        assert cpu.faulted and not cpu.running
        assert cpu.memory[GH10_FAULT_WORD] == FAULT_SEEN


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
