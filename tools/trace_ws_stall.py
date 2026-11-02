#!/usr/bin/env python3
"""
Characterise the post-workingset stall from .ckpt/fresh_workingset_fpd.rv64ckpt
(current shader; both my resume tests confirmed it stalls silent, pc cycling
0x80054/0x80057/0x80086/0x8033b/0x8089d).

Fast-forward until pc is repeatedly in that band, then single-step a few
thousand instructions recording:
  - the set of distinct pcs (the loop body)
  - traps taken (scause/sepc) — a timer-IRQ-driven spin looks like
    loop-body ... trap to 0x8089d ... sret ... loop-body
  - the full register file at the start, so we can see what it's polling
"""
from __future__ import annotations
import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = sys.argv[1] if len(sys.argv) > 1 else ".ckpt/fresh_workingset_fpd.rv64ckpt"
CSR_SEPC, CSR_SCAUSE, CSR_STVAL, CSR_SATP = 0x141, 0x142, 0x143, 0x180
RN = ["zero","ra","sp","gp","tp","t0","t1","t2","fp","s1","a0","a1","a2","a3","a4","a5",
      "a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"]


def regs(c):
    import numpy as np
    a = np.frombuffer(c.queue.read_buffer(c.registers.buffer), dtype=np.uint32)
    return [int(a[i * 2]) | (int(a[i * 2 + 1]) << 32) for i in range(32)]


def main():
    core = load_checkpoint(CKPT)
    print(f"resumed {CKPT}")
    # fast-forward: run in 5M chunks until UART goes quiet for 3 chunks AND pc in band
    band = lambda pc: (pc & 0xfffff000) in (
        0xffffffff80054000, 0xffffffff80057000, 0xffffffff80058000,
        0xffffffff80059000, 0xffffffff80086000, 0xffffffff8033b000,
        0xffffffff8089d000)
    step = 0
    quiet = 0
    while step < 400_000_000:
        core.step(steps=5_000_000)
        step += 5_000_000
        b = core.read_uart_output()
        if b:
            quiet = 0
            sys.stdout.write(b.decode("latin-1", "replace")); sys.stdout.flush()
        else:
            quiet += 1
        pc = core.get_state()["pc"]
        if quiet >= 4 and band(pc):
            print(f"\n[quiet+in-band at step {step:,}, pc=0x{pc:x}]")
            break
    else:
        print("never settled into the stall band"); return

    r0 = regs(core)
    print("\n=== register file at stall ===")
    for i in range(0, 32, 4):
        print("  " + "  ".join(f"{RN[i+j]:>4}=0x{r0[i+j]:016x}" for j in range(4)))
    print(f"  satp=0x{core.read_csr(CSR_SATP):x} scause=0x{core.read_csr(CSR_SCAUSE):x} "
          f"sepc=0x{core.read_csr(CSR_SEPC):x} stval=0x{core.read_csr(CSR_STVAL):x}")

    print("\n=== single-stepping 8000 instrs ===")
    pcs = collections.Counter()
    traps = collections.Counter()
    seq = []
    last_scause = core.read_csr(CSR_SCAUSE)
    for k in range(8000):
        core.step(steps=1)
        st = core.get_state()
        pc = st["pc"]
        pcs[pc] += 1
        if len(seq) < 200:
            seq.append((pc, int(st["mode"])))
        sc = core.read_csr(CSR_SCAUSE)
        if sc != last_scause:
            traps[(sc, core.read_csr(CSR_SEPC))] += 1
            last_scause = sc

    print(f"\ndistinct pcs: {len(pcs)}   top 25:")
    for pc, n in pcs.most_common(25):
        print(f"  0x{pc:016x}  x{n}  mode-mix")
    print(f"\ntraps seen in the window: {dict(traps)}")
    print(f"\nfirst 120 (pc mode):")
    for pc, m in seq[:120]:
        print(f"  0x{pc:016x} m{m}")


if __name__ == "__main__":
    main()
