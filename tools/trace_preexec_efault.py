#!/usr/bin/env python3
"""
Automated EFAULT diagnostic from .ckpt/v618_preexec.rv64ckpt (Run /init, pre-panic).

Steps in small batches, records every S-mode trap (scause/stval/sepc), dumps the
faulting instruction word + a register snapshot, and stops when the guest prints
the EFAULT / panic string. Goal: pin the exact instruction + fault the emulator
mishandles for the PIE busybox execve.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = sys.argv[1] if len(sys.argv) > 1 else ".ckpt/v618_preexec.rv64ckpt"
CSR_SEPC, CSR_SCAUSE, CSR_STVAL, CSR_SSTATUS, CSR_SATP = 0x141, 0x142, 0x143, 0x100, 0x180
REG = ["zero","ra","sp","gp","tp","t0","t1","t2","fp","s1","a0","a1","a2","a3","a4","a5",
       "a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"]
CAUSES = {0:"insn-misalign",1:"insn-access",2:"illegal-insn",3:"breakpoint",4:"load-misalign",
          5:"load-access",6:"store-misalign",7:"store-access",8:"ecall-U",9:"ecall-S",
          12:"insn-page-fault",13:"load-page-fault",15:"store-page-fault"}


def regs(core):
    import numpy as np
    b = core.queue.read_buffer(core.registers.buffer)
    a = np.frombuffer(b, dtype=np.uint32)
    return [int(a[i * 2]) | (int(a[i * 2 + 1]) << 32) for i in range(32)]


def snap(core, tag):
    s = core.get_state()
    sepc = core.read_csr(CSR_SEPC); scause = core.read_csr(CSR_SCAUSE)
    stval = core.read_csr(CSR_STVAL); satp = core.read_csr(CSR_SATP)
    sstatus = core.read_csr(CSR_SSTATUS)
    ci = scause & 0xff
    print(f"\n--- {tag} ---")
    print(f"  pc=0x{s['pc']:016x} mode={s['mode']} trap_pending={s['trap_pending']}")
    print(f"  scause=0x{scause:x} ({CAUSES.get(ci,'?')})  stval=0x{stval:x}  sepc=0x{sepc:x}")
    print(f"  satp=0x{satp:x}  sstatus=0x{sstatus:x}  SUM={(sstatus>>18)&1} MXR={(sstatus>>19)&1}")
    rr = regs(core)
    for i in range(0, 32, 4):
        print("  " + "  ".join(f"{REG[i+j]:>4}=0x{rr[i+j]&0xffffffffffffffff:016x}" for j in range(4)))
    return (s['pc'], scause, stval, sepc)


def main():
    print(f"loading {CKPT} ...")
    core = load_checkpoint(CKPT)
    snap(core, "start")

    batch = 2000
    total = 0
    max_steps = 60_000_000
    uart = ""
    last_trap = None
    trap_log = []
    t0 = time.time()
    while total < max_steps:
        core.step(steps=batch)
        total += batch
        b = core.read_uart_output()
        if b:
            txt = b.decode("latin-1")
            uart += txt
            sys.stdout.write(txt); sys.stdout.flush()

        scause = core.read_csr(CSR_SCAUSE)
        sepc = core.read_csr(CSR_SEPC)
        key = (scause, sepc)
        if scause and key != last_trap:
            last_trap = key
            info = snap(core, f"TRAP @ step +{total:,}")
            trap_log.append(info)
            # try to show the faulting instruction word
            try:
                w = core.read_mem_word(info[3] & 0xffffffff)
                print(f"  insn@sepc = 0x{w:08x}")
            except Exception as e:
                print(f"  insn read failed: {e}")

        low = uart.lower()
        if "efault" in low or "kill the idle task" in low or "kernel panic" in low or "-14" in uart:
            print(f"\n>>> hit terminal string at +{total:,} steps ({time.time()-t0:.0f}s)")
            snap(core, "AT TERMINAL STRING")
            break
    else:
        print(f"\n=== ran {total:,} steps, no terminal string ===")

    print("\n=== distinct traps seen ===")
    for pc, sc, tv, se in trap_log:
        print(f"  scause=0x{sc:x} {CAUSES.get(sc&0xff,'?'):<16} stval=0x{tv:x} sepc=0x{se:x}")


if __name__ == "__main__":
    main()
