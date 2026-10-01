"""Probe: measure transitions for the PS010c grid pins.

Reuses the PS010b probe discipline (probe_ps010b_pins.py: assemble(),
execute_one for ALU, execute_ctl for branches + EBREAK halt).
Scratch only; not part of any gate.
"""
import sys

sys.path.insert(0, ".")

from tools.rv32i_asm import assemble
from tools.pyshader_ctl import ControlHalt, execute_ctl
from tools.pyshader_fde import REG_N, execute_one, fetch
from tools.pyshader_rvdecode import decode_ref


def words(t):
    b = assemble(t)
    return [int.from_bytes(b[i:i + 4], "little")
            for i in range(0, len(b), 4)]


LOW_SRC = """
        addi x1, x0, 2
        addi x1, x1, -1
        bne  x1, x0, -4
        ebreak
"""

DIV_SRC = """
        bne  x5, x0, 12       # taken -> skip the spin loop (+3 insns)
        addi x1, x0, 8
spin:   addi x1, x1, -1
        blt  x0, x1, -4       # signed: counts x1 down to 0
        ebreak
"""


def run(imem, x5_init=0, cap=100000):
    st = {"pc": 0, "regs": [0] * REG_N}
    st["regs"][5] = x5_init
    steps = 0
    while True:
        d = decode_ref(fetch(st["pc"], imem))
        if d["fmt"] in ("R", "I") and d["opcode"] in (0x33, 0x13):
            st = execute_one(st, imem)
        else:
            try:
                st = execute_ctl(st, d, [0] * 8)
            except ControlHalt:
                return steps, st
            steps += 1
        if steps > cap:
            raise RuntimeError(f"no halt within {cap} steps — spin bug")


for name, imem, x5 in [("LOW", words(LOW_SRC), 0),
                       ("DIV taken", words(DIV_SRC), 4),
                       ("DIV not-taken", words(DIV_SRC), 0)]:
    steps, st = run(imem, x5)
    print(f"{name}: transitions={steps} x1={st['regs'][1]} "
          f"x5={st['regs'][5]} pc={st['pc']}")
