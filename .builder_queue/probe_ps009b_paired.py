"""PS009b paired measurement probe (RULING_ps009 leg 2 — MEASURE ONLY).

Fork arithmetic per the ruling + PS009_BASELINE_RECEIPT.md ~03:10
addendum: deficit = ModeB / GEN_batched, BOTH legs in THIS process,
back to back. No stored absolute, no stored ratio reused. The
[J-DECISION] at >=5x is Jericho's; this probe only produces the paired
numbers and files the receipt.

Workload: pyshader_fde.FIB_PROGRAM, x5=8, 43 steps (42 pin steps +
halt). One rep = one full workload run: fresh state load, dispatches
until halt, one blocking readback per dispatch (same bracket
discipline as the baseline probe's get_state rule).

Legs:
  A   step(1) x43 on SPATIAL_RV32I hand-written core   (sanity floor)
  B   step(43) x1 on SPATIAL_RV32I hand-written core   (denominator)
  GEN  GPU-resident generated-body FDE loop
       (tools/pyshader_fde_gpu shader, batch=256), device/pipeline/
       buffers built ONCE, per-rep cost = state upload + dispatches
       + blocking readbacks   (the proposed architecture, steady state)
  GEN0 full run_fde_gpu per rep, as landed — module init, shader
       compile, buffer+pipeline creation inside the timed region
       (context only; NOT the fork numerator — setup amortization is
       the entire point of the architecture)

Verification in-loop: final regs checked against the hand pin on the
warm rep and every reps//5 thereafter, both directions (A/B via
get_state, GEN/GEN0 via the readback words) — a leg that does not
reproduce the pin contributes nothing (receipt discipline).
"""
import struct
import sys
import time

sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio/tools")

import numpy as np

from spatial_rv32i_cpu import SpatialRV32ICore
from pyshader_fde import FIB_PROGRAM, FIB_EXPECTED_FINAL

WORDS = np.array(FIB_PROGRAM, dtype=np.uint32).tobytes()
N_STEPS = 43
PIN = dict(FIB_EXPECTED_FINAL)
# same pin keys the baseline probe checks: x1/x2/x3/x5
PIN_KEYS = sorted(PIN)


def check_regs(regs, tag):
    bad = {k: (regs[k], v) for k, v in PIN.items() if regs[k] != v}
    if bad:
        raise SystemExit(f"[{tag}] pin MISMATCH {bad}")
    print(f"[{tag}] pin OK")


def load(core):
    core.load_program(WORDS, entry_point=0)
    core.write_register(5, 8)


def bench_host(dispatch, reps):
    core = SpatialRV32ICore()
    load(core)
    if dispatch == 1:
        for _ in range(N_STEPS):
            core.step(1)
    else:
        core.step(dispatch)
    check_regs(core.get_state()["regs"], f"warm d={dispatch}")
    t0 = time.perf_counter()
    for i in range(reps):
        load(core)
        if dispatch == 1:
            for _ in range(N_STEPS):
                core.step(1)
        else:
            core.step(dispatch)
        if (i + 1) % (reps // 5) == 0:
            check_regs(core.get_state()["regs"], f"d={dispatch} rep {i+1}")
    dt = time.perf_counter() - t0
    rate = N_STEPS * reps / dt
    print(f"MODE {dispatch}-instr/dispatch: {rate:,.0f} steps/s "
          f"({dt/reps*1e6:,.1f} us/rep incl. load+write+readback) "
          f"[{reps} reps]")
    return rate


# ---- GPU leg: session built once, per-rep = upload + dispatch loop ----

def gen_session(batch=256):
    import wgpu
    from tools.pyshader_fde_gpu import (
        _build_shader, ARRAY_WORDS, PREFIX_WORDS, PC_OFF, STOP_OFF,
        TRACEN_OFF, STOP_HALT, load_program, REG_N)

    imem = load_program(FIB_PROGRAM)
    n = ARRAY_WORDS
    prefix = [0] * REG_N + [0, 1, 0, len(imem), 0]
    prefix[5] = 8  # FIB loop counter preload — same as probe load()'s write_register(5, 8)
    payload = prefix + [w & 0xFFFFFFFF for w in imem]
    assert len(payload) == PREFIX_WORDS + len(imem)
    blob = struct.pack(f"<{len(payload)}I", *payload)

    from tools.pyshader_wgsl import _cached_device
    device = _cached_device()
    shader = device.create_shader_module(code=_build_shader(batch),
                                         label="ps009b-probe")
    gpu_buf = device.create_buffer(
        size=n * 4,
        usage=(wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
               | wgpu.BufferUsage.COPY_DST),
        label="ps009b-state")
    readback = device.create_buffer(
        size=n * 4,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
        label="ps009b-read")
    pipe = device.create_compute_pipeline(
        layout="auto",
        compute={"module": shader, "entry_point": "main"},
        label="ps009b-pipe")
    bg = device.create_bind_group(
        layout=pipe.get_bind_group_layout(0),
        entries=[{"binding": 0,
                  "resource": {"buffer": gpu_buf, "offset": 0,
                               "size": n * 4}}],
        label="ps009b-bind")
    return device, gpu_buf, readback, pipe, bg, blob, n, PC_OFF, STOP_OFF, \
        TRACEN_OFF, STOP_HALT, REG_N


def gen_one_rep(session):
    import wgpu
    (device, gpu_buf, readback, pipe, bg, blob, n, PC_OFF, STOP_OFF,
     TRACEN_OFF, STOP_HALT, REG_N) = session
    device.queue.write_buffer(gpu_buf, 0, blob)
    words = None
    while True:
        enc = device.create_command_encoder(label="ps009b-rep")
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(1, 1, 1)
        cp.end()
        enc.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, n * 4)
        device.queue.submit([enc.finish()])
        readback.map_sync(mode=wgpu.MapMode.READ)
        words = list(struct.unpack(f"<{n}I", bytes(readback.read_mapped())))
        readback.unmap()
        if words[STOP_OFF] != STOP_HALT:
            break
    return words


def bench_gen(reps):
    session = gen_session()
    (_, _, _, _, _, _, n, PC_OFF, _, TRACEN_OFF, _, REG_N) = session
    steps_warm = 0
    words = gen_one_rep(session)
    regs = {i: words[i] for i in PIN_KEYS}
    check_regs(regs, "warm GEN")
    steps_warm = words[TRACEN_OFF]
    if steps_warm != N_STEPS - 1:
        raise SystemExit(f"[warm GEN] trace_n {steps_warm} != {N_STEPS - 1}")
    t0 = time.perf_counter()
    n_exec = 0
    for i in range(reps):
        words = gen_one_rep(session)
        n_exec = words[TRACEN_OFF]
        if (i + 1) % (reps // 5) == 0:
            regs = {k: words[k] for k in PIN_KEYS}
            check_regs(regs, f"GEN rep {i+1}")
            if n_exec != N_STEPS - 1:
                raise SystemExit(f"[GEN rep {i+1}] trace_n {n_exec}")
    dt = time.perf_counter() - t0
    # GEN executes 42 instructions: the loop stops AT the imem-OOB fetch
    # (pc=7, stop=IMEM_OOB); the host core's 43rd step IS that fetch
    # (latches halted, counted). Rate each leg on its own executed count.
    rate = n_exec * reps / dt
    print(f"MODE GEN(gpu batch=256, setup amortized): {rate:,.0f} steps/s "
          f"({dt/reps*1e6:,.1f} us/rep incl. upload+dispatch+readback, "
          f"{n_exec} exec/rep vs 43 host convention) [{reps} reps]")
    return rate


def bench_gen0(reps):
    from tools.pyshader_fde_gpu import run_fde_gpu
    state = {"pc": 0, "regs": [0] * 32}
    state["regs"][5] = 8
    r = run_fde_gpu(FIB_PROGRAM, state, max_steps=64)
    check_regs({i: r["trace"][-1]["regs"][i] for i in PIN_KEYS}, "warm GEN0")
    if r["steps_executed"] != N_STEPS - 1:
        raise SystemExit(f"[warm GEN0] steps {r['steps_executed']}")
    t0 = time.perf_counter()
    for i in range(reps):
        r = run_fde_gpu(FIB_PROGRAM, state, max_steps=64)
        if (i + 1) % (reps // 5) == 0:
            check_regs(
                {k: r["trace"][-1]["regs"][k] for k in PIN_KEYS},
                f"GEN0 rep {i+1}")
            if r["steps_executed"] != N_STEPS - 1:
                raise SystemExit(f"[GEN0 rep {i+1}] steps mismatch")
    dt = time.perf_counter() - t0
    rate = (N_STEPS - 1) * reps / dt  # GEN0 also executes 42 (see GEN note)
    print(f"MODE GEN0(as-landed run_fde_gpu, setup in-loop): {rate:,.0f} "
          f"steps/s ({dt/reps*1e6:,.1f} us/rep) [{reps} reps]")
    return rate


if __name__ == "__main__":
    a = bench_host(1, 300)
    b = bench_host(N_STEPS, 300)
    g = bench_gen(300)
    g0 = bench_gen0(100)
    print()
    print(f"PAIRED deficit ModeB/GEN = {b/g:.2f}x  "
          f"(J-DECISION fires at >=5x — Jericho's call, not this probe's)")
    print(f"context: ModeB/ModeA = {b/a:.1f}x  ModeB/GEN0 = {b/g0:.1f}x")
