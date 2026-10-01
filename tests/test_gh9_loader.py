#!/usr/bin/env python3
"""tests/test_gh9_loader.py — GH-9 oracle test (RED until baker grows
loader_kernel_image()).

Falsifiable gate for GH-9 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):

1. baker.loader_kernel_image(atlas, out_path=...) emits ONE image whose
   resident kernel:
     - reserves a PATCH WINDOW in its code region (GH-3 machinery: mailbox
       flag/n_px/data at words 960/961/964, PARALLEL_ST copy loop),
     - arms vectors: KSYS_PC -> in-image syscall dispatcher, KFAULT_PC ->
       fault handler (loader-seeded packed pixel PCs, two-pass bake),
     - programs BOX0 (user arena [700..768)), latches MODE_LATCH = USER,
       and instead of jumping straight to a baked task, ACTS AS LOADER:
       mailbox armed -> patch window -> launch; mailbox empty -> relaunch
       the RESIDENT window (offline exec path).

2. The HOST is the program loader + process creator: it assembles the
   injected program (argv-computing mix) into raw pixel words with the
   public assembler, arms the mailbox, and seeds the argv block
   (GH9_ARGV_WORD/ARGV_WORD+1 = argv0/argv1) in the runner's RAM before
   the first step — exactly what an OS does before exec. The kernel never
   sees the program source; the launch sequence is:
     a. patch window <- mailbox pixels (PARALLEL_ST loop),
     b. copy mailbox argv words into the argv block at 750/751
        (in BOX0, the program's arena — the kernel hands off argv),
     c. KJMP into the window at the argv pointer (r10 = 750), USER mode.

3. The injected program (host text, kernel data):
     LD argv0/argv1 from the block via r9 = r10 + 1,
     r11 = ((argv0 ^ argv1) + (argv0 << 2))  [the GH-4 mix contract],
     ST result to argv base + 4 (word 754),
     write exit word 703 = 0xFEED0009, HALT.
   Receipt checks (judged from cpu memory after the run):
     - not cpu.faulted, not cpu.running (halted)
     - mem[754] == native C reference (gcc) on the same argv, byte-exact
     - mem[703] == 0xFEED0009, mem[950] == 0xCAFE0009

4. Offline leg (loader thesis): run 1 patches the window IN THE IMAGE —
   cpu.run(runner.image) executes in place (same driver as GH-3), so the
   saved post-run PNG carries the injected program as resident pixels.
   A FRESH runner + fresh cpu on that image seeds ONLY the argv block
   (exec semantics: new argv, same text) — no mailbox, no program bytes.
   The kernel's relaunch path execs the resident window and the result
   reproduces byte-exact: the program lives in the image, argv is the
   only per-process state.

5. Isolation leg: fault_leg=True bakes a kernel whose launch leg KJMPs to
   a fault-task that stores word 900 (byte 3600, outside BOX0) — E-K1
   vectors to KFAULT_PC, the handler records 0xFA171 at word 731, and
   the clean-exit words stay zero.

6. Zero-dev-import property (same as GH-2/3/5/6/7/8): runner.py stays clean.

Today this FAILS at import: loader_kernel_image does not exist yet.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import loader_kernel_image            # noqa: E402
from tools.glyph_gpt.baker import (                              # noqa: E402
    GH9_MAILBOX_DATA as MAILBOX_DATA,
    GH9_MAILBOX_FLAG as MAILBOX_FLAG,
    GH9_MAILBOX_N_PX as MAILBOX_N_PX,
)
from tools.rv64i_to_glyph import assemble_glyph_to_pixels        # noqa: E402

STATUS_WORD = 950
# MAILBOX_FLAG/MAILBOX_N_PX/MAILBOX_DATA are imported from baker (the ABI
# owner): the payload region moved to [800,896) because words [1024,1280)
# alias image pixels under GH-8b, which corrupted any payload reaching past
# word 1024.

# GH-9 image ABI (fixed word indices; BOX0 = [700..768), GH-8 scheme).
GH9_ARGV_WORD = 750      # argv block: argv0 @750, argv1 @751 (inside BOX0)
GH9_ARGV_RESULT = 754    # injected program stores its result here
GH9_EXIT_WORD = 703      # injected program's exit word (inside BOX0)
GH9_FAULT_WORD = 731     # fault-leg verdict (0xFA171)
GH9_FAULT_SEEN = 0xFA171
KERNEL_OK = 0xCAFE0009   # 0xCAFE0000 | 9
EXIT_OK = 0xFEED0009
N_WINDOW_INSTRS = 24     # patch-window capacity (instructions)

ARGV0 = 1234
ARGV1 = 567

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


def _native_reference() -> int:
    """Byte-exact native C reference for the same argv computation."""
    with tempfile.TemporaryDirectory() as td:
        c = Path(td) / "ref.c"
        c.write_text(
            "#include <stdio.h>\n"
            "int main() {\n"
            f"    unsigned a = {ARGV0}; unsigned b = {ARGV1};\n"
            "    unsigned r = ((a ^ b) + (a << 2)) & 0xFFFFFFFFu;\n"
            "    printf(\"%u\\n\", r);\n"
            "    return 0;\n"
            "}\n"
        )
        binp = Path(td) / "ref"
        subprocess.run(["gcc", "-O1", str(c), "-o", str(binp)], check=True)
        out = subprocess.run([str(binp)], capture_output=True, text=True, check=True)
        return int(out.stdout.strip())


def _program_pixel_words() -> list[int]:
    """Loader step 1: assemble the program text into flat 24-bit pixel
    words (row-major), exactly the payload the kernel will PARALLEL_ST
    into its patch window."""
    pixels, _ = assemble_glyph_to_pixels(INJECTED_PROGRAM_TEXT, cols_instrs=8)
    h, w, _ = pixels.shape
    return [((int(pixels[y, x][0]) << 16) | (int(pixels[y, x][1]) << 8)
             | int(pixels[y, x][2])) for y in range(h) for x in range(w)]


def _bake(tmp: Path, name: str = "gh9.glyph.npy", fault_leg: bool = False) -> Path:
    atlas = build_default_atlas()
    out = tmp / name
    loader_kernel_image(atlas, fault_leg=fault_leg, out_path=out)
    return out


def _run_online(tmp: Path, fault_leg: bool = False, name: str = "gh9.glyph.npy"):
    """Bake, then drive the image IN PLACE (GH-3 driver): host seeds the
    argv block + mailbox in the runner's RAM, cpu.run mutates runner.image
    so the patch lands in the pixels we can later save."""
    out = _bake(tmp, name=name, fault_leg=fault_leg)
    runner = GlyphRunner(out, ram_words=16384)
    cpu = runner.get_cpu()
    cpu.memory[GH9_ARGV_WORD] = ARGV0          # process creator: set argv
    cpu.memory[GH9_ARGV_WORD + 1] = ARGV1
    if not fault_leg:
        words = _program_pixel_words()
        assert len(words) >= N_WINDOW_INSTRS * 4, (
            f"injected program too small: {len(words)} words")
        cpu.memory[MAILBOX_FLAG] = 1
        cpu.memory[MAILBOX_N_PX] = N_WINDOW_INSTRS * 4
        for i, w in enumerate(words[:N_WINDOW_INSTRS * 4]):
            cpu.memory[MAILBOX_DATA + i] = w
    cpu.run(runner.image, max_instructions=60000)
    return runner, cpu


def test_gh9_loader_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d)).exists(), "loader_kernel_image must emit one image"


def test_gh9_injected_program_computes_on_argv():
    """The whole GH-9 gate in one image run: host loads the program pixels
    via the mailbox, kernel patches its window, copies argv into the block
    and launches the program USER-mode at the argv pointer; the result
    word matches the native C reference byte-exact."""
    want = _native_reference()
    with tempfile.TemporaryDirectory() as d:
        runner, cpu = _run_online(Path(d))
        assert not cpu.faulted, f"faulted: addr={cpu.fault_addr:#x}"
        assert not cpu.running, "run must reach HALT"
        mem = cpu.memory
        got = mem[GH9_ARGV_RESULT]
        assert got == want, (
            f"result 0x{got:08x} != native C reference 0x{want:08x}")
        assert mem[GH9_EXIT_WORD] == EXIT_OK, (
            f"exit 0x{mem[GH9_EXIT_WORD]:08x} != 0x{EXIT_OK:08x}")
        assert mem[STATUS_WORD] == KERNEL_OK, (
            f"status 0x{mem[STATUS_WORD]:08x} != 0x{KERNEL_OK:08x}")
        assert mem[MAILBOX_FLAG] == 0, "kernel must consume the mailbox flag"


def test_gh9_offline_rerun_replays_launch():
    """Loader thesis: run 1 patched the window IN THE IMAGE; the saved
    post-run PNG carries the program as resident pixels. A fresh runner +
    fresh cpu seeds ONLY the argv block (no mailbox, no program bytes) —
    the kernel's relaunch path execs the resident window and the result
    reproduces byte-exact."""
    want = _native_reference()
    with tempfile.TemporaryDirectory() as d:
        runner, cpu = _run_online(Path(d), name="gh9_offline.glyph.npy")
        assert not cpu.faulted and not cpu.running
        post_path = Path(d) / "post_gh9.glyph.png"
        Image.fromarray(runner.image, "RGB").save(post_path)

        offline = GlyphRunner(post_path, ram_words=16384)
        cpu2 = offline.get_cpu()
        cpu2.memory[GH9_ARGV_WORD] = ARGV0        # exec: same text, new argv
        cpu2.memory[GH9_ARGV_WORD + 1] = ARGV1
        # mailbox flag stays 0: the only program text available is the one
        # resident in the image's patch window.
        cpu2.run(offline.image, max_instructions=60000)
        assert not cpu2.faulted, f"offline faulted: {cpu2.fault_addr:#x}"
        assert not cpu2.running
        mem2 = cpu2.memory
        assert mem2[GH9_ARGV_RESULT] == want, (
            f"offline result 0x{mem2[GH9_ARGV_RESULT]:08x} != 0x{want:08x}")
        assert mem2[STATUS_WORD] == KERNEL_OK


def test_gh9_fault_leg_isolates():
    """fault_leg: the launched leg's first act is an out-of-box store
    (word 900); E-K1 vectors to KFAULT_PC, the handler records 0xFA171,
    and the clean-exit words never get written."""
    with tempfile.TemporaryDirectory() as d:
        _, cpu = _run_online(Path(d), fault_leg=True)
        assert cpu.faulted, "out-of-box user store must fault"
        assert not cpu.running, "run must reach HALT via the fault handler"
        mem = cpu.memory
        assert mem[GH9_FAULT_WORD] == GH9_FAULT_SEEN
        assert mem[GH9_EXIT_WORD] == 0
        assert mem[GH9_ARGV_RESULT] == 0
        assert mem[STATUS_WORD] == KERNEL_OK


def test_gh9_runner_still_zero_dev_imports():
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
