"""PS010b pin probe (2026-09-20, orchestrator pre-lock verification).

Verifies, through the EXISTING PS008/PS007 machinery, the pins the
PS010b skeleton will lock:
  - LOW_PROG (all harts same length): per-hart transitions.
  - MIX_PROG_SHORT / MIX_PROG_LONG (population mix): lengths + rounds.
  - DIVERGENT_PROG (mid-run split on a per-hart register): both paths'
    transition counts and halt rounds at n=4 (2+2).
Scratch only; not part of any gate. Run: python3 .builder_queue/probe_ps010b_pins.py
"""
import sys
sys.path.insert(0, ".")
from tools.rv32i_asm import assemble
from tools.pyshader_ctl import execute_ctl, ControlHalt
from tools.pyshader_fde import execute_one, fetch, REG_N
from tools.pyshader_rvdecode import decode_ref


def words(t):
    b = assemble(t)
    return [int.from_bytes(b[i:i + 4], "little")
            for i in range(0, len(b), 4)]


LOW_PROG = """
        addi x1, x0, 2
        addi x1, x1, -1
        bne  x1, x0, -4
        ebreak
"""

MIX_SHORT = """
        addi x1, x0, 0
        ebreak
"""

MIX_LONG = """
        addi x1, x0, 8
loop:   addi x1, x1, -1
        bne  x1, x0, -4
        ebreak
"""

# Divergence mid-run on a REGISTER, not a static program mix:
# x5 preloaded per-hart; bne x5,x0 taken -> SKIP spin; not-taken -> spin.
# Spin counter is x1 counted DOWN TO ZERO with BLT (signed) — BNE on the
# wrapped u32 never reaches 0 within any sane round budget (measured).
DIVERGENT = """
        bne  x5, x0, 12       # 0: taken -> skip the spin loop (+3 insns)
        addi x1, x0, 8        # 1: spin-loop counter
spin:   addi x1, x1, -1       # 2
        blt  x0, x1, -4       # 3: back to insn 2 while 0 < x1 (signed)
        ebreak                # 4
"""

w_low, w_ms, w_ml, w_div = (words(p) for p in
                            (LOW_PROG, MIX_SHORT, MIX_LONG, DIVERGENT))
print("LOW     :", [hex(w) for w in w_low])
print("MIX_S   :", [hex(w) for w in w_ms])
print("MIX_L   :", [hex(w) for w in w_ml])
print("DIVERG  :", [hex(w) for w in w_div])


def run(imem, x5_init=0, cap=10000):
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


for name, imem, x5 in [("LOW", w_low, 0), ("MIX_S", w_ms, 0),
                       ("MIX_L", w_ml, 0), ("DIVERG taken", w_div, 4),
                       ("DIVERG not-taken", w_div, 0)]:
    steps, st = run(imem, x5)
    print(f"{name}: transitions={steps} x1={st['regs'][1]} pc={st['pc']}")
