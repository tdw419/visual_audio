#!/usr/bin/env python3
"""
Pin the instruction that corrupts a kernel pointer (ffffffff81c6b7a0 ->
ffffffff01c6b7a0, bit 31 of the low word cleared) during setup_per_cpu_areas
on a fresh batch=50000 boot.

From .ckpt/fresh_pre_percpu_50k.rv64ckpt (saved at 'Ticket spinlock: enabled'):
fast-forward to just before the store page fault at 0xffffffff01c6b7a0, then
single-step a ring of (step, pc, mode, scause, regs). Dump the window where a
register transitions from ...81c6b7a0 to ...01c6b7a0, or the faulting store.
"""
from __future__ import annotations
import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = ".ckpt/fresh_pre_percpu_50k.rv64ckpt"
CSR_SEPC, CSR_SCAUSE, CSR_STVAL = 0x141, 0x142, 0x143
BAD = 0xffffffff01c6b7a0
GOOD = 0xffffffff81c6b7a0
RN = ["zero","ra","sp","gp","tp","t0","t1","t2","fp","s1","a0","a1","a2","a3","a4","a5",
      "a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"]


def regs(c):
    import numpy as np
    a = np.frombuffer(c.queue.read_buffer(c.registers.buffer), dtype=np.uint32)
    return [int(a[i * 2]) | (int(a[i * 2 + 1]) << 32) for i in range(32)]


def rd_phys_u32(c, pa):
    return c.read_mem_word(pa - 0x80000000)


def find_oops_step(core, cap=40_000_000, batch=50_000):
    uart = ""
    step = 0
    while step < cap:
        core.step(steps=batch)
        step += batch
        b = core.read_uart_output()
        if b:
            uart += b.decode("latin-1", "replace")
        if "Unable to handle kernel paging request" in uart or "Oops" in uart:
            return step, uart
    return None, uart


def main():
    print(f"[1] locating Oops from {CKPT} ...")
    core = load_checkpoint(CKPT)
    S, uart = find_oops_step(core)
    if S is None:
        print("Oops not seen in cap"); return
    print(f"[1] Oops-ish by step {S:,}")

    core = load_checkpoint(CKPT)
    ff = max(0, S - 400_000)
    print(f"[2] reload, fast-forward {ff:,} ...")
    core.step(steps=ff)
    step = ff

    ring = collections.deque(maxlen=600)
    prev = regs(core)
    hit = False
    while step < S + 100_000:
        core.step(steps=1)
        step += 1
        r = regs(core)
        sc = core.read_csr(CSR_SCAUSE)
        st = core.get_state()
        pc = st["pc"]
        ring.append((step, pc, int(st["mode"]), sc, list(r)))

        # transition detection: any GPR going *_81c6b7a0 -> *_01c6b7a0
        for i in range(32):
            if prev[i] != r[i] and (r[i] & 0xffffffffffffffff) == BAD:
                print(f"\n>>> reg {RN[i]} became 0x{r[i]:016x} at step {step:,} "
                      f"(was 0x{prev[i]:016x})  pc=0x{pc:x}")
                dump(core, ring, i)
                hit = True
                break
        if hit:
            break
        # or the faulting store itself
        if (sc & 0xff) == 0xf and core.read_csr(CSR_STVAL) == BAD:
            print(f"\n>>> STORE PAGE FAULT stval=0x{BAD:x} at step {step:,} "
                  f"sepc=0x{core.read_csr(CSR_SEPC):x}")
            dump(core, ring, None)
            hit = True
            break
        prev = r

    if not hit:
        print("no transition/fault caught; dumping tail")
        dump(core, ring, None)


def dump(core, ring, regidx):
    print("\n  --- last 40 single-steps (step pc mode scause  [key regs]) ---")
    for (s, pc, m, sc, rr) in list(ring)[-40:]:
        extra = ""
        if regidx is not None:
            extra = f"  {RN[regidx]}=0x{rr[regidx]:016x}"
        print(f"  {s:>12} pc=0x{pc:016x} m{m} sc=0x{sc:x}{extra}")
    s, pc, m, sc, rr = ring[-1]
    print("\n  regs at last step:")
    for i in range(0, 32, 4):
        print("   " + "  ".join(f"{RN[i+j]:>4}=0x{rr[i+j]:016x}" for j in range(4)))
    try:
        w = rd_phys_u32(core, pc & 0xffffffff if pc < 0x100000000 else 0x80000000)
    except Exception:
        pass


if __name__ == "__main__":
    main()
