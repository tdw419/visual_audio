#!/usr/bin/env python3
"""
Alpine boot on the GPU RV64 core with the DTB placed where OpenSBI's fw_jump
actually hands it to the kernel (a1 = 0x82200000, per the "Domain0 Next Arg1"
banner line) instead of at end-of-RAM where the kernel never looks.

Prints UART and, on the first S/M-mode trap after the OpenSBI handoff, dumps
the trap CSRs so a stall can be diagnosed.

  python3 tools/boot_alpine_gpu_fixed.py [--max-steps N] [--dtb-addr 0xADDR]
"""
from __future__ import annotations
import argparse, struct, sys
from pathlib import Path

_R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_R / "tools")); sys.path.insert(0, str(_R))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

OPENSBI = "/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin"
KERNEL_LNX = str(_R / "boot_images/alpine_riscv64.lnx.bin")
RAM_BASE = 0x80000000
RAM_SIZE = 64 * 1024 * 1024
KERNEL_OFF = 0x200000
FW_JUMP_FDT_ADDR = 0x82200000          # what OpenSBI's fw_jump passes as a1


def load(core, dtb_addr, bootargs=None):
    sbi = Path(OPENSBI).read_bytes()
    d = Path(KERNEL_LNX).read_bytes()
    ko, ks, irs = struct.unpack("<III", d[4:16])
    kpe = d[ko:ko + ks]
    initrd = d[ko + ks: ko + ks + irs]
    e = struct.unpack("<I", kpe[0x3C:0x40])[0]
    kmem = struct.unpack("<I", kpe[e + 24 + 56: e + 24 + 60])[0]

    kern_addr = RAM_BASE + KERNEL_OFF
    initrd_addr = max(kern_addr + ((kmem + 4095) & ~4095), RAM_BASE + 0x2800000)
    if not (kern_addr + kmem <= dtb_addr < initrd_addr):
        print(f"WARN: dtb 0x{dtb_addr:x} not in the free gap "
              f"[0x{kern_addr + kmem:x}, 0x{initrd_addr:x})")

    dtb = build_device_tree(
        ram_base=RAM_BASE, ram_size=RAM_SIZE, uart_base=0x10000000,
        isa="rv64imafdc", timebase=10_000_000,
        bootargs=bootargs or "earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0 loglevel=8 virtio_mmio.debug",
        kernel_addr=kern_addr, initrd_addr=initrd_addr, initrd_size=irs,
    )
    core.load_program(sbi, entry_point=RAM_BASE, ram_base=RAM_BASE)
    core.write_mem_bytes(KERNEL_OFF, kpe)
    core.write_mem_bytes(initrd_addr - RAM_BASE, initrd)
    core.write_mem_bytes(dtb_addr - RAM_BASE, dtb)
    print(f"  kernel 0x{kern_addr:x}-0x{kern_addr + kmem:x}  initrd 0x{initrd_addr:x}"
          f"  dtb 0x{dtb_addr:x} ({len(dtb)}B)")
    return dtb_addr


def csrs(core):
    g = lambda a: core.read_csr(a)
    return (f"mstatus=0x{g(0x300):x} mcause=0x{g(0x342):x} mepc=0x{g(0x341):x} "
            f"mtval=0x{g(0x343):x} | scause=0x{g(0x142):x} sepc=0x{g(0x141):x} "
            f"stval=0x{g(0x143):x} satp=0x{g(0x180):x}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-steps", type=int, default=120_000_000)
    ap.add_argument("--dtb-addr", type=lambda x: int(x, 0), default=FW_JUMP_FDT_ADDR)
    ap.add_argument("--batch", type=int, default=1_000_000)
    a = ap.parse_args()

    core = SpatialRV64ICore(RAM_SIZE)
    load(core, a.dtb_addr)
    core.write_register(10, 0)          # a0 = hart 0
    core.write_register(11, a.dtb_addr) # a1 = FDT (same addr OpenSBI forwards)

    uart = bytearray()
    entered_kernel = False
    reported_trap = False
    steps = 0
    while steps < a.max_steps:
        core.step(steps=a.batch); steps += a.batch
        b = core.read_uart_output()
        if b:
            uart += b
            sys.stdout.write(b.decode("latin-1")); sys.stdout.flush()
        st = core.get_state()
        pc = st["pc"]
        if pc >= 0x80200000 and pc < RAM_BASE + RAM_SIZE:
            entered_kernel = True
        if entered_kernel and pc < 0x80040000 and not reported_trap:
            print(f"\n[trap] back in firmware at pc=0x{pc:x} after {steps} steps")
            print(f"[trap] {csrs(core)}")
            reported_trap = True
        if st["halted"]:
            print(f"\n[halt] halted={st['halted']} pc=0x{pc:x} steps={steps}")
            break

    st = core.get_state()
    print(f"\n=== end: pc=0x{st['pc']:x} halted={st['halted']} steps={steps} "
          f"uart={len(uart)}B ===")
    tail = bytes(uart[-600:]).decode("latin-1")
    if "Kernel panic" in tail or "Linux version" in tail:
        print("--- uart tail ---\n" + tail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
