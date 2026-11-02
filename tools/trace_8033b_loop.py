#!/usr/bin/env python3
"""
The fresh boot tight-loops at pc ~0xffffffff8033b5xx-6xx after
'Freeing initrd memory' (before Run /init). Resume the workingset checkpoint,
advance until pc is stuck in that window, then single-step and dump:
  - the exact loop body (ordered unique pcs)
  - traps taken during the window (timer IRQ etc.)
  - the register file
  - the words the loop loads from memory (candidate poll target)
"""
from __future__ import annotations
import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = sys.argv[1] if len(sys.argv) > 1 else ".ckpt/fresh_workingset_fpd.rv64ckpt"
LOOP_LO, LOOP_HI = 0xffffffff8033b000, 0xffffffff8033c000
CSR_SEPC, CSR_SCAUSE, CSR_STVAL, CSR_SATP = 0x141, 0x142, 0x143, 0x180
RN = ["zero","ra","sp","gp","tp","t0","t1","t2","fp","s1","a0","a1","a2","a3","a4","a5",
      "a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"]


def regs(c):
    import numpy as np
    a = np.frombuffer(c.queue.read_buffer(c.registers.buffer), dtype=np.uint32)
    return [int(a[i * 2]) | (int(a[i * 2 + 1]) << 32) for i in range(32)]


def walk(c, va):
    satp = c.read_csr(CSR_SATP)
    if (satp >> 60) != 8:
        return None
    pt = (satp & ((1 << 44) - 1)) << 12
    for lvl in (2, 1, 0):
        i = (va >> (12 + 9 * lvl)) & 0x1FF
        pa = pt + i * 8
        lo = c.read_mem_word(pa - 0x80000000)
        hi = c.read_mem_word(pa - 0x80000000 + 4)
        pte = lo | (hi << 32)
        if pte & 1 == 0:
            return None
        if (pte >> 1) & 7:
            ppn = (pte >> 10) & ((1 << 44) - 1)
            return (ppn << 12) | (va & 0xFFF)
        pt = ((pte >> 10) & ((1 << 44) - 1)) << 12
    return None


def main():
    c = load_checkpoint(CKPT)
    print(f"resumed {CKPT}")
    uart = ""
    step = 0
    inwin = 0
    while step < 500_000_000:
        c.step(steps=200_000)
        step += 200_000
        b = c.read_uart_output()
        if b:
            t = b.decode("latin-1", "replace")
            uart += t
            sys.stdout.write(t); sys.stdout.flush()
        pc = c.get_state()["pc"]
        if LOOP_LO <= pc < LOOP_HI:
            inwin += 1
        else:
            inwin = 0
        if inwin >= 8 and "Freeing initrd memory" in uart:
            print(f"\n[stuck in 0x8033b window at step {step:,}, pc=0x{pc:x}]")
            break
        if inwin >= 40:
            print(f"\n[stuck in 0x8033b window (no initrd msg) at step {step:,}, pc=0x{pc:x}]")
            break
    else:
        print("never got stuck in the window"); return

    r0 = regs(c)
    print("\n=== regs ===")
    for i in range(0, 32, 4):
        print("  " + "  ".join(f"{RN[i+j]:>4}=0x{r0[i+j]:016x}" for j in range(4)))
    print(f"  satp=0x{c.read_csr(CSR_SATP):x} scause=0x{c.read_csr(CSR_SCAUSE):x} "
          f"sepc=0x{c.read_csr(CSR_SEPC):x}")

    order = []
    seen = set()
    traps = collections.Counter()
    last_sc = c.read_csr(CSR_SCAUSE)
    reg_hist = collections.defaultdict(set)
    for k in range(4000):
        c.step(steps=1)
        st = c.get_state()
        pc = st["pc"]
        if pc not in seen:
            seen.add(pc); order.append(pc)
        sc = c.read_csr(CSR_SCAUSE)
        if sc != last_sc:
            traps[(sc, c.read_csr(CSR_SEPC))] += 1
            last_sc = sc
        if k % 50 == 0:
            rr = regs(c)
            for i in (5, 6, 7, 10, 11, 12, 13, 14, 15, 28, 29, 30, 31):
                reg_hist[RN[i]].add(rr[i] & 0xffffffffffffffff)

    print(f"\n=== loop body ({len(order)} distinct pcs) ===")
    for pc in sorted(order):
        mark = " <-- in 0x8033b" if LOOP_LO <= pc < LOOP_HI else ""
        print(f"  0x{pc:016x}{mark}")
    print(f"\ntraps in window: {dict(traps)}")
    print("\nregs that varied across the loop (candidate counters / poll vals):")
    for name, vals in reg_hist.items():
        if len(vals) > 1:
            print(f"  {name}: {sorted(hex(v) for v in vals)[:8]}")
        else:
            print(f"  {name}: {hex(next(iter(vals)))} (constant)")

    # try reading memory near pointers in a0..a5, s0..s2
    rr = regs(c)
    print("\n=== memory at candidate pointers ===")
    for i in (8, 9, 10, 11, 12, 13, 18, 19):
        p = rr[i] & 0xffffffffffffffff
        if 0xffffff0000000000 <= p or (0x80000000 <= p < 0x84000000):
            pa = walk(c, p) if p >= 0xffffff0000000000 else p
            if pa and 0x80000000 <= pa < 0x84000000:
                w = c.read_mem_word(pa - 0x80000000)
                print(f"  {RN[i]}=0x{p:016x} -> PA 0x{pa:x} -> [*]=0x{w:08x}")


if __name__ == "__main__":
    main()
