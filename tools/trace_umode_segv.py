#!/usr/bin/env python3
"""
Pin the U-mode SIGSEGV that follows the (now working) execve.

Phase 1: from .ckpt/v618_preexec.rv64ckpt, run in coarse batches until the guest
         prints "unhandled signal 11"; record the step count S.
Phase 2: reload, fast-forward to S-WINDOW, then single-step recording a ring of
         (step, mode, pc, ra, sp, scause, sepc). Dump the ring when U-mode pc
         first lands in the fatal page, plus the last transition into it.
"""
from __future__ import annotations
import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = ".ckpt/v618_preexec.rv64ckpt"
CSR_SEPC, CSR_SCAUSE, CSR_STVAL = 0x141, 0x142, 0x143
FATAL_PAGE = 0x2ac3b09000
WINDOW = 120_000
RING = 400


def regs(core):
    import numpy as np
    a = np.frombuffer(core.queue.read_buffer(core.registers.buffer), dtype=np.uint32)
    return [int(a[i * 2]) | (int(a[i * 2 + 1]) << 32) for i in range(32)]


def phase1():
    core = load_checkpoint(CKPT)
    step = 0
    batch = 20_000
    uart = ""
    while step < 8_000_000:
        core.step(steps=batch)
        step += batch
        b = core.read_uart_output()
        if b:
            uart += b.decode("latin-1")
        if "unhandled signal 11" in uart:
            print(f"[phase1] 'unhandled signal 11' by step ~{step:,}")
            return step
    print("[phase1] never saw signal 11")
    return None


def phase2(S):
    core = load_checkpoint(CKPT)
    ff = max(0, S - WINDOW)
    print(f"[phase2] fast-forward {ff:,} steps ...")
    core.step(steps=ff)
    step = ff
    ring = collections.deque(maxlen=RING)
    prev_pc = None
    entered_at = None
    while step < S + 40_000:
        core.step(steps=1)
        step += 1
        st = core.get_state()
        pc = st["pc"]
        mode = int(st["mode"])
        sc = core.read_csr(CSR_SCAUSE)
        se = core.read_csr(CSR_SEPC)
        r = None
        ring.append((step, mode, pc, sc, se))
        in_fatal = (pc & ~0xfff) == FATAL_PAGE
        if in_fatal and entered_at is None:
            entered_at = step
            r = regs(core)
            print(f"\n>>> U/S pc entered fatal page at step {step:,}: pc=0x{pc:x} mode={mode}")
            print(f"    prev_pc=0x{prev_pc:x}")
            RN = ["zero","ra","sp","gp","tp","t0","t1","t2","fp","s1","a0","a1","a2","a3","a4","a5",
                  "a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"]
            for i in range(0, 32, 4):
                print("    " + "  ".join(f"{RN[i+j]:>4}=0x{r[i+j]:016x}" for j in range(4)))
            print("\n    --- last %d records (step mode pc scause sepc) ---" % len(ring))
            for (s2, m2, p2, c2, e2) in list(ring)[-60:]:
                print(f"    {s2:>10} m{m2} pc=0x{p2:016x} sc=0x{c2:x} sepc=0x{e2:x}")
            break
        prev_pc = pc
    if entered_at is None:
        print("[phase2] never entered fatal page in window")


if __name__ == "__main__":
    S = phase1()
    if S:
        phase2(S)
