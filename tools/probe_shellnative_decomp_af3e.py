"""Decompose the shell-native grep turn: gcc legs vs engine (run) leg.

Repeat measurement, 5 trials, fresh process each. Companion to
RESEARCH_shellnative_turn_budget.md. Builder af3e62239ce2 2026-09-25.
"""
import sys, time, tempfile
sys.path.insert(0, '.')
sys.path.insert(0, 'tools')
from pathlib import Path

from experiments.glyph_l1_shell import GlyphL1Shell
from tools.glyph_gpt.coreutils_port import _TOOL_SOURCES, _VOL2_TOOL_SOURCES, _c_literal
from tests.test_gh23_libc_runtime import _load_posix_program, LIBC_C, SHIM_S
from tools.glyph_gpt.baker import libc_runtime_kernel_image
from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner
import subprocess

data = "hello world record2 payload"
pat = "record2"

for trial in range(5):
    # leg A: gcc compile x2 + link (the subprocess legs)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "tool.c"
        body = _VOL2_TOOL_SOURCES.get("grep") or _TOOL_SOURCES.get("grep")
        src.write_text(f'static const char *grep_data = "{_c_literal(data)}";\n'
                       f'static const char *grep_pattern = "{_c_literal(pat)}";\n'
                       '#define GREP_DATA grep_data\n#define GREP_PAT grep_pattern\n'
                       + body)
        libc = tmp / "gh23_libc.c"
        libc.write_text(LIBC_C)
        shim = tmp / "shim.S"
        shim.write_text(SHIM_S)
        gcc = "riscv64-unknown-elf-gcc"
        t0 = time.perf_counter()
        objs = []
        for i, cf in enumerate((src, libc)):
            obj = tmp / f"t{i}.o"
            subprocess.run([gcc, "-march=rv32i", "-mabi=ilp32", "-O1",
                            "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                            "-ffixed-x31", "-nostdlib", "-fno-builtin",
                            "-ffreestanding", "-w", "-c", str(cf), "-o", str(obj)],
                           capture_output=True, timeout=60, check=True)
            objs.append(obj)
        elf = tmp / "tool.elf"
        subprocess.run([gcc, "-march=rv32i", "-mabi=ilp32",
                        "-ffixed-x28", "-ffixed-x29", "-ffixed-x30", "-ffixed-x31",
                        "-nostdlib", "-Wl,-Ttext=0x0", "-Wl,-N", "-Wl,--entry=_start",
                        "-w", *map(str, objs), str(shim), "-o", str(elf)],
                       capture_output=True, timeout=60, check=True)
        t_gcc = (time.perf_counter() - t0) * 1000

        # leg B: load + bake + engine run at the 300k budget
        t0 = time.perf_counter()
        program = _load_posix_program(elf.read_bytes())
        image = tmp / "sn.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=image,
                                  user_program=program)
        t_bake = (time.perf_counter() - t0) * 1000
        runner = GlyphRunner(image, ram_words=16384)
        t0 = time.perf_counter()
        receipt = runner.run(max_instructions=300000, trace=True)
        t_run = (time.perf_counter() - t0) * 1000
        steps = receipt.get("steps", -1)
    print(f"trial{trial}: gcc={t_gcc:.0f}ms bake={t_bake:.0f}ms "
          f"engine_run={t_run:.0f}ms steps={steps} halted={receipt.get('halted')}")
