#!/usr/bin/env python3
"""
Pin the qspinlock-slowpath deadlock at pc 0xffffffff808a4aa2 that a fresh boot
hits right after 'percpu:'.  The lock is console_sem.lock (~VA 0xffffffff81c6b7a0
from the earlier Oops).  We translate that VA to a PA, then single-step across
the setup_per_cpu_areas / percpu-printk window logging every change to the lock
word plus the instruction that made it.

  python3 tools/trace_qspin_deadlock.py [ckpt] [lock_va_hex]
"""
from __future__ import annotations
import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = sys.argv[1] if len(sys.argv) > 1 else ".ckpt/fresh_pre_percpu_jit.rv64ckpt"
LOCK_VA = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0xffffffff81c6b7a0
DEADLOCK_PC = 0xffffffff808a4aa2
RAM_BASE = 0x80000000
CSR_SATP, CSR_SEPC, CSR_SCAUSE, CSR_STVAL = 0x180, 0x141, 0x142, 0x143
RN = ["zero","ra","sp","gp","tp","t0","t1","t2","fp","s1","a0","a1","a2","a3","a4","a5",
      "a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"]


def rd_phys_u32(c, pa): return c.read_mem_word(pa - RAM_BASE)
def rd_phys_u64(c, pa): return rd_phys_u32(c, pa) | (rd_phys_u32(c, pa + 4) << 32)


def walk(c, va):
    satp = c.read_csr(CSR_SATP)
    if (satp >> 60) != 8:
        return None
    pt = (satp & ((1 << 44) - 1)) << 12
    idxs = [(va >> 30) & 0x1FF, (va >> 21) & 0x1FF, (va >> 12) & 0x1FF]
    for lvl in (2, 1, 0):
        pte = rd_phys_u64(c, pt + idxs[2 - lvl] * 8)
        if (pte & 1) == 0:
            return None
        r, w, x = (pte >> 1) & 1, (pte >> 2) & 1, (pte >> 3) & 1
        ppn = (pte >> 10) & ((1 << 44) - 1)
        if r or x:
            return (ppn << 12) | (va & 0xFFF)
        pt = ppn << 12
    return None


def regs(c):
    import numpy as np
    a = np.frombuffer(c.queue.read_buffer(c.registers.buffer), dtype=np.uint32)
    return [int(a[i * 2]) | (int(a[i * 2 + 1]) << 32) for i in range(32)]


def main():
    print(f"[1] {CKPT}  lock_va=0x{LOCK_VA:x}")
    core = load_checkpoint(CKPT)

    # advance to the percpu printk
    uart = ""
    step = 0
    while step < 30_000_000:
        core.step(steps=100_000)
        step += 100_000
        b = core.read_uart_output()
        if b:
            uart += b.decode("latin-1", "replace")
        if "percpu: Embedded" in uart:
            break
    print(f"[1] 'percpu: Embedded' by step {step:,}")

    core = load_checkpoint(CKPT)
    ff = max(0, step - 500_000)
    print(f"[2] reload, fast-forward {ff:,}")
    core.step(steps=ff)
    cur = ff

    lock_pa = walk(core, LOCK_VA)
    print(f"[2] lock PA = {hex(lock_pa) if lock_pa else None}")
    # also watch the whole cache line
    ring = collections.deque(maxlen=80)
    last_lock = None
    changes = []
    saw_deadlock_pc = 0
    while cur < step + 3_000_000:
        core.step(steps=1)
        cur += 1
        st = core.get_state()
        pc = st["pc"]
        # re-walk occasionally in case satp changed
        if lock_pa is None or (cur % 20000 == 0):
            npa = walk(core, LOCK_VA)
            if npa:
                lock_pa = npa
        lv = rd_phys_u32(core, lock_pa) if lock_pa else None
        ring.append((cur, pc, int(st["mode"]), lv))
        if lv != last_lock:
            r = regs(core)
            sc = core.read_csr(CSR_SCAUSE); se = core.read_csr(CSR_SEPC)
            print(f"\n[lock {last_lock} -> {lv}] step {cur:,} pc=0x{pc:x} mode={st['mode']} "
                  f"scause=0x{sc:x} sepc=0x{se:x}")
            for i in range(0, 32, 4):
                print("   " + "  ".join(f"{RN[i+j]:>4}=0x{r[i+j]:016x}" for j in range(4)))
            print("   recent pcs:", " ".join(f"0x{p:x}" for (_, p, _, _) in list(ring)[-12:]))
            changes.append((cur, pc, last_lock, lv))
            last_lock = lv
        if pc == DEADLOCK_PC:
            saw_deadlock_pc += 1
            if saw_deadlock_pc == 1:
                print(f"\n[reached deadlock pc 0x{DEADLOCK_PC:x} at step {cur:,}, lock={lv}]")
            if saw_deadlock_pc > 200000:
                print(f"[spinning at deadlock pc; lock stuck at {lv}] stopping")
                break

    print("\n=== lock-word change history (step pc old new) ===")
    for (s, pc, o, n) in changes:
        print(f"  {s:>12} pc=0x{pc:016x}  0x{o if o is not None else 0:08x} -> 0x{n if n is not None else 0:08x}")


if __name__ == "__main__":
    main()
