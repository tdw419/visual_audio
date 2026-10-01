#!/usr/bin/env python3
"""
Boot the *working* Alpine RISC-V materials on the GPU RV64 core:
  boot_images/alpine_Image   - kernel 6.18.35 (raw RISC-V Image / PE), NOT the
                               broken alpine_riscv64.lnx.bin
  boot_images/alpine_initrd  - real 16MB cpio initramfs (has /init + version-
                               matched virtio_mmio.ko / virtio_blk.ko)

DTB at OpenSBI's FW_JUMP_FDT_ADDR (0x82200000); disk@ reserved node omitted
(it collides with this larger kernel and Route B doesn't use the in-RAM disk).

  python3 tools/boot_alpine_v618_gpu.py [--offload] [--disk PATH] [--max-steps N]

--offload : serve /dev/vda from a host file via VirtioBlkHost (vq_ready=2).
            Without it, plain boot -> initramfs (rescue shell if no root).
"""
from __future__ import annotations
import argparse, struct, sys
from pathlib import Path

_R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_R / "tools")); sys.path.insert(0, str(_R))

from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

OPENSBI = "/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin"
KERNEL = str(_R / "boot_images/alpine_Image")
INITRD = str(_R / "boot_images/alpine_initrd")
_INITRD_OVERRIDE = None
RAM_BASE = 0x80000000
RAM_SIZE = 64 * 1024 * 1024
KERNEL_OFF = 0x200000
FW_JUMP_FDT_ADDR = 0x82200000
INITRD_ADDR = 0x82400000


def load(core, bootargs):
    sbi = Path(OPENSBI).read_bytes()
    kimg = Path(KERNEL).read_bytes()
    initrd = Path(_INITRD_OVERRIDE or INITRD).read_bytes()
    image_size = struct.unpack("<Q", kimg[16:24])[0]  # RISC-V Image header
    kern_end = RAM_BASE + KERNEL_OFF + image_size
    if not (kern_end <= FW_JUMP_FDT_ADDR and FW_JUMP_FDT_ADDR < INITRD_ADDR
            and INITRD_ADDR + len(initrd) < RAM_BASE + RAM_SIZE):
        print(f"WARN layout: kernel ends 0x{kern_end:x}, dtb 0x{FW_JUMP_FDT_ADDR:x}, "
              f"initrd 0x{INITRD_ADDR:x}+0x{len(initrd):x}")

    dtb = build_device_tree(
        ram_base=RAM_BASE, ram_size=RAM_SIZE, uart_base=0x10000000,
        isa="rv64imafdc", timebase=10_000_000, bootargs=bootargs,
        kernel_addr=RAM_BASE + KERNEL_OFF,
        initrd_addr=INITRD_ADDR, initrd_size=len(initrd),
        disk_reserved=False,
    )
    core.load_program(sbi, entry_point=RAM_BASE, ram_base=RAM_BASE)
    core.write_mem_bytes(KERNEL_OFF, kimg)
    core.write_mem_bytes(INITRD_ADDR - RAM_BASE, initrd)
    core.write_mem_bytes(FW_JUMP_FDT_ADDR - RAM_BASE, dtb)
    print(f"  kernel 0x{RAM_BASE+KERNEL_OFF:x}-0x{kern_end:x}  dtb 0x{FW_JUMP_FDT_ADDR:x} "
          f"({len(dtb)}B)  initrd 0x{INITRD_ADDR:x}+{len(initrd)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offload", action="store_true")
    ap.add_argument("--initrd", default=None)
    ap.add_argument("--disk", default="/tmp/alpine_rootfs/alpine_disk.img")
    ap.add_argument("--max-steps", type=int, default=3_000_000_000)
    ap.add_argument("--batch", type=int, default=5_000_000)
    a = ap.parse_args()

    bootargs = ("earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0"
                + (" root=/dev/vda rootwait" if a.offload else ""))
    global _INITRD_OVERRIDE
    _INITRD_OVERRIDE = a.initrd
    core = SpatialRV64ICore(RAM_SIZE)
    load(core, bootargs)
    core.write_register(10, 0)
    core.write_register(11, FW_JUMP_FDT_ADDR)

    if a.offload:
        from qemu_gpu_offload import run_with_offload
        r = run_with_offload(core, a.disk, ram_base=RAM_BASE,
                             slice_steps=a.batch, max_steps=a.max_steps)
        fs = r["final_state"]
        print(f"\n=== halted {fs['halted']} pc 0x{fs['pc']:x} steps {r['total_steps']:,} "
              f"offloads {r['offloads']} ===")
        return 0 if fs["halted"] == 1 else 1

    u = bytearray(); steps = 0
    while steps < a.max_steps:
        core.step(steps=a.batch); steps += a.batch
        b = core.read_uart_output()
        if b:
            u += b; sys.stdout.write(b.decode("latin-1")); sys.stdout.flush()
        st = core.get_state()
        if st["halted"]:
            print(f"\n[halt] {st['halted']} pc=0x{st['pc']:x}"); break
    print(f"\n=== pc=0x{core.get_state()['pc']:x} steps={steps} uart={len(u)}B ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
