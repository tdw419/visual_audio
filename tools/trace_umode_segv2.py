#!/usr/bin/env python3
"""
Zoom in on the single instruction that redirects U-mode pc to 0x2ac3b0903e.

From .ckpt/v618_preexec.rv64ckpt: fast-forward to just before the jump, then
single-step. At the boundary dump regs, decode the faulting-jump instruction
(read via a Python Sv39 walk), and check whether the target page is mapped.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = ".ckpt/v618_preexec.rv64ckpt"
RAM_BASE = 0x80000000
CSR_SATP = 0x180
JUMP_FROM = 0x2ac3a6fffe
TARGET = 0x2ac3b0903e
RN = ["zero","ra","sp","gp","tp","t0","t1","t2","fp","s1","a0","a1","a2","a3","a4","a5",
      "a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"]


def rd_phys_u32(core, pa):
    return core.read_mem_word(pa - RAM_BASE)


def rd_phys_u64(core, pa):
    return rd_phys_u32(core, pa) | (rd_phys_u32(core, pa + 4) << 32)


def walk(core, va, verbose=False):
    satp = core.read_csr(CSR_SATP)
    mode = satp >> 60
    if mode != 8:
        return ("no-sv39", None)
    ppn = satp & ((1 << 44) - 1)
    pt = ppn << 12
    idxs = [(va >> 30) & 0x1FF, (va >> 21) & 0x1FF, (va >> 12) & 0x1FF]
    for lvl in (2, 1, 0):
        i = idxs[2 - lvl]
        pte_pa = pt + i * 8
        pte = rd_phys_u64(core, pte_pa)
        v = pte & 1
        r, w, x = (pte >> 1) & 1, (pte >> 2) & 1, (pte >> 3) & 1
        u = (pte >> 4) & 1
        nextppn = (pte >> 10) & ((1 << 44) - 1)
        if verbose:
            print(f"    L{lvl} pte@0x{pte_pa:x} = 0x{pte:016x} v={v} r={r} w={w} x={x} u={u} ppn=0x{nextppn:x}")
        if v == 0 or (r == 0 and w == 1):
            return ("invalid", {"level": lvl, "pte": pte})
        if r or x:  # leaf
            pa = (nextppn << 12) | (va & 0xFFF)
            return ("leaf", {"level": lvl, "pte": pte, "pa": pa, "perm": (r, w, x, u)})
        pt = nextppn << 12
    return ("no-leaf", None)


def decode_jump(w):
    op = w & 0x7F
    if op == 0x6F:  # JAL
        imm = (((w >> 31) & 1) << 20) | (((w >> 12) & 0xFF) << 12) | (((w >> 20) & 1) << 11) | (((w >> 21) & 0x3FF) << 1)
        if imm & (1 << 20):
            imm -= (1 << 21)
        return f"JAL x{(w>>7)&31}, pc{imm:+#x}"
    if op == 0x67:  # JALR
        rs1 = (w >> 15) & 31
        imm = (w >> 20) & 0xFFF
        if imm & 0x800:
            imm -= 0x1000
        return f"JALR x{(w>>7)&31}, x{rs1}({RN[rs1]}){imm:+#x}"
    # RVC
    c = w & 3
    lo16 = w & 0xFFFF
    if c == 2 and ((lo16 >> 13) & 7) == 4:
        rs1 = (lo16 >> 7) & 31
        bit12 = (lo16 >> 12) & 1
        rs2 = (lo16 >> 2) & 31
        if bit12 == 0 and rs2 == 0:
            return f"C.JR x{rs1}({RN[rs1]})"
        if bit12 == 1 and rs2 == 0 and rs1 != 0:
            return f"C.JALR x{rs1}({RN[rs1]})"
    if c == 1 and ((lo16 >> 13) & 7) in (1, 5):
        return "C.J/C.JAL (imm)"
    return f"(not a recognized jump; op=0x{op:x} lo16=0x{lo16:04x})"


def regs(core):
    import numpy as np
    a = np.frombuffer(core.queue.read_buffer(core.registers.buffer), dtype=np.uint32)
    return [int(a[i * 2]) | (int(a[i * 2 + 1]) << 32) for i in range(32)]


def main():
    core = load_checkpoint(CKPT)
    core.step(steps=1_600_000)
    step = 1_600_000
    while step < 1_760_000:
        st = core.get_state()
        if st["pc"] == JUMP_FROM and st["mode"] == 0:
            print(f"\n=== at JUMP_FROM 0x{JUMP_FROM:x}  step {step:,} ===")
            r = regs(core)
            for i in range(0, 32, 4):
                print("  " + "  ".join(f"{RN[i+j]:>4}=0x{r[i+j]:016x}" for j in range(4)))
            print("\n  page walk for JUMP_FROM:")
            k, d = walk(core, JUMP_FROM, verbose=True)
            print(f"  -> {k} {d}")
            if k == "leaf":
                insn_pa = d["pa"]
                w = rd_phys_u32(core, insn_pa)
                print(f"\n  insn bytes @ VA 0x{JUMP_FROM:x} (PA 0x{insn_pa:x}) = 0x{w:08x}")
                print(f"  decode: {decode_jump(w)}")
                lo16 = w & 0xFFFF
                # if C.JR/C.JALR, print target reg value
                if (lo16 & 3) == 2 and ((lo16 >> 13) & 7) == 4:
                    rs1 = (lo16 >> 7) & 31
                    print(f"  target = x{rs1}({RN[rs1]}) = 0x{r[rs1]:x}")
            print(f"\n  page walk for TARGET 0x{TARGET:x}:")
            k2, d2 = walk(core, TARGET, verbose=True)
            print(f"  -> {k2} {d2}")
            print(f"\n  page walk for TARGET & ~0xfff (0x{TARGET & ~0xfff:x}):")
            walk(core, TARGET & ~0xFFF, verbose=True)
            # dump some GOT-ish memory near where a PLT would read: gp-relative & the
            # busybox base
            break
        core.step(steps=1)
        step += 1
    else:
        print("never hit JUMP_FROM")


if __name__ == "__main__":
    main()
