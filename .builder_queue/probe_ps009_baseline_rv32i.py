"""PS009 [J-DECISION] baseline probe: identical FIB workload on the
hand-written SPATIAL_RV32I.wgsl, via its GPU-batched step() API.

Workload = pyshader_fde.FIB_PROGRAM (7 words, x5=8, pin final
x1=34/x2=55/x3=55/x5=0). One timed rep = one full workload run:
load_program + write_register(x5=8) + dispatches + one blocking
readback (RV64I_STATUS.md:75 discipline: bracket with a blocking
get_state, not per-step reads).

Mode A: 43 x step(1)  (1 instr per dispatch — PS007 host-loop analogue)
Mode B: 1 x step(43)  (whole program per dispatch — shader-internal
batching, the architecture PS009 proposes for the generated table)

43 = 42 pin steps + the illegal fetch that sets halted (shader halts
in-place; extra dispatches no-op). Verification runs in-loop per rep.
"""
import sys, time
sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio/tools")

import numpy as np
from spatial_rv32i_cpu import SpatialRV32ICore
from pyshader_fde import FIB_PROGRAM, FIB_EXPECTED_FINAL

WORDS = np.array(FIB_PROGRAM, dtype=np.uint32).tobytes()
N_STEPS = 43

def load(core):
    core.load_program(WORDS, entry_point=0)
    core.write_register(5, 8)

def check_pin(core, tag):
    st = core.get_state()
    bad = {k: (st["regs"][k], v) for k, v in FIB_EXPECTED_FINAL.items() if st["regs"][k] != v}
    if bad:
        raise SystemExit(f"[{tag}] pin MISMATCH {bad} pc={st['pc']} halted={st['halted']}")
    print(f"[{tag}] pin OK (pc={st['pc']}, halted={st['halted']})")

def one_rep(core, dispatch):
    """One full workload: fresh load, then either 43 x step(1) (Mode A)
    or a single step(43) (Mode B)."""
    load(core)
    if dispatch == 1:
        for _ in range(N_STEPS):
            core.step(1)
    else:
        core.step(dispatch)

def bench(dispatch, reps):
    core = SpatialRV32ICore()
    one_rep(core, dispatch)
    check_pin(core, f"warm d={dispatch}")
    t0 = time.perf_counter()
    for i in range(reps):
        one_rep(core, dispatch)
        if (i + 1) % (reps // 5) == 0:
            check_pin(core, f"d={dispatch} rep {i+1}")
    dt = time.perf_counter() - t0
    rate = N_STEPS * reps / dt
    print(f"MODE {dispatch}-instr/dispatch: {rate:,.0f} steps/s  "
          f"({dt/reps*1e6:,.1f} us/rep incl. load+write+readback) [{reps} reps]")
    return rate

a = bench(1, 500)
b = bench(N_STEPS, 500)
print(f"shader-internal batching gain on this workload: {b/a:.1f}x")
print("PS009 receipt must reuse THIS script's rep definition (one_rep) for an apples-to-apples ratio.")
