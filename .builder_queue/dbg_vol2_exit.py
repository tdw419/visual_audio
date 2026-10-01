#!/usr/bin/env python3
"""Verify the extracted byte r29 each iteration of the outer scan at a
coarse level: instead capture at the field-copy loop's JZ target (3589)
i.e. loop EXITS — do exits ever happen? Count arrivals at 3589 (loop
exit) vs 3561 (loop entry) over 200k steps; and log r29 value at cell
3581 (the CMP) — decode-safe cells: just log (cell, r29) whenever cell
== 3581 first 30 times."""
import sys, tempfile
from pathlib import Path
REPO = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / 'tools'))
from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.baker import libc_runtime_kernel_image
from tools.glyph_gpt.coreutils_port import coreutils2_tool_elf
from tests.test_gh23_libc_runtime import _load_posix_program

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = tmp / 'x.elf'
    elf.write_bytes(coreutils2_tool_elf('cut', 'field2', tmp))
    program = _load_posix_program(elf.read_bytes())
    out = tmp / 'x.npy'
    libc_runtime_kernel_image(build_default_atlas(), out_path=out, user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    cpu = runner.get_cpu()
    cpu.running = True
    steps = 0
    logged = 0
    exits = 0
    while cpu.running and steps < 60000:
        x, y = cpu.pc
        cell = y * 32 + (x // 4)
        if cell == 3581 and logged < 30:
            logged += 1
            print(f'step {steps} cell 3581: r29={hex(cpu.registers[29])} '
                  f'r7={hex(cpu.registers[7])} r0={cpu.registers[0]}')
        if cell == 3589:
            exits += 1
        cpu.step(runner.image)
        steps += 1
    print('reached cell 3589 (loop exit):', exits, 'times in', steps, 'steps')
