"""PS010 step 4 probe #2: crafted consistency pair (docstring NOTE).

A writes flag (dmem[0]) + payload (dmem[1]) in SEQUENCE inside one coarse
round; B reads BOTH in the SAME round. sync="single" (no per-round copies)
lets B observe a TORN one-new/one-old state; sync="double" only ever shows
all-old or all-new. Probe measures the actual traces before the gate pins
them. Not part of the gate.
"""
import sys

sys.path.insert(0, ".")

from tests.test_pyshader_hart import _words  # noqa: E402
from tools.pyshader_hart import run_two_hart  # noqa: E402

# A: insn0 addi x9,x0,1 (payload); insn1 sw x9,0(x0) -> dmem[0]=1;
#    insn2 addi x10,x0,7 (pin);     insn3 sw x10,4(x0) -> dmem[1]=7;
#    insn4 ebreak
PROG_A = """
        addi x9, x0, 1
        sw   x9, 0(x0)
        addi x10, x0, 7
        sw   x10, 4(x0)
        ebreak
"""
# B: insn0 lw x5,0(x0); insn1 lw x6,4(x0); insn2 ebreak
PROG_B = """
        lw   x5, 0(x0)
        lw   x6, 4(x0)
        ebreak
"""

a, b = _words(PROG_A), _words(PROG_B)
dmem0 = [0, 0, 123, 0, 0, 0, 0, 0]

for spr in (1, 2):
    s = run_two_hart(a, b, list(dmem0), sync="single", steps_per_round=spr)
    d = run_two_hart(a, b, list(dmem0), sync="double", steps_per_round=spr)
    for name, r in (("SINGLE", s), ("DOUBLE", d)):
        print(f"spr={spr} {name}:", dict(
            completed=r["completed"], rounds=r["rounds"],
            steps_a=r["steps_a"], steps_b=r["steps_b"], dmem=r["dmem"],
            x5=r["regs_b"][5], x6=r["regs_b"][6]))
