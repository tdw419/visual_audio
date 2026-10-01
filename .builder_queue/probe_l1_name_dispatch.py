#!/usr/bin/env python3
"""L1 WIP probe: name-dispatch + 'time' skeleton (NOT landed; measures the
ISA surface L1 needs: 2-byte name match, digit PRT, SUB/MUL/DIV-free epoch
print via repeated subtraction)."""
import sys, tempfile
from pathlib import Path
sys.path[:0] = [".", "tools", "experiments"]

import time as _time
from glyph_interactive_shell import build_dispatch_shell, repl, run_turn
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2, INPUT_DATA_ADDR, INPUT_LEN_ADDR

d = Path(tempfile.mkdtemp())
image = build_dispatch_shell(str(d / "w.dat"), str(d / "a.wav"))

# Probe 1: does the name-dispatch grammar survive byte2==' '?
out = repl(lines=["e hi", "zz top", "w abc"], image=image, fs_pix_enabled=True)
print("grammar legs:", out)

# Probe 2: epoch math cost on this engine (host clock, per-turn stamp).
cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8, fs_pix_enabled=True)
cpu.memory = [0] * 16384
line = "e " + "y" * 30
data = line.encode()
cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
cpu.memory[(INPUT_DATA_ADDR >> 2) - 8] = 0  # cursor
for i, b in enumerate(data):
    cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
cpu.pc = (0, 0)
cpu.registers = [0] * 32
cpu.output = []
cpu.running = True
n = cpu.run(image, max_instructions=4096)
print("30-char echo steps:", n)

# Probe 3: epoch value size — can it be an immediate?
epoch = int(_time.time())
print("epoch:", epoch, "fits u32 imm:", epoch < 2**32)
