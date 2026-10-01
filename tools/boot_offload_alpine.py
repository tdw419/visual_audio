#!/usr/bin/env python3
"""
tools/boot_offload_alpine.py
============================
Route B Phase 3 driver: boot Alpine RISC-V on the GPU RV64 core with the
virtio-blk device serviced on the *host* (VirtioBlkHost), not walked inside
the shader.

Shares the OpenSBI/kernel/DTB loader with tools/boot_alpine_gpu_fixed.py
(correct DTB placement at OpenSBI's FW_JUMP_FDT_ADDR, LUT-scatter image load)
so the boot is bit-identical to the standalone path up to the point virtio
diverges. Difference:
  - the Alpine disk image stays a host file; VirtioBlkHost reads/writes it on
    each QueueNotify yield instead of it living in GPU RAM
  - state.vq_ready is set to 2, so mmio_write() on QueueNotify yields
    (state.halted = 2) back to run_with_offload()

Needs a real GPU adapter.

Usage:
  python3 tools/boot_offload_alpine.py [--disk PATH] [--max-steps N] [--slice N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "tools"))
sys.path.insert(0, str(_REPO))

from qemu_gpu_offload import run_with_offload            # noqa: E402
import boot_alpine_gpu_fixed as bagf                     # noqa: E402

RAM_SIZE = bagf.RAM_SIZE
RAM_BASE = bagf.RAM_BASE
DEFAULT_DISK = "/tmp/alpine_rootfs/alpine_disk.img"


def main() -> int:
    ap = argparse.ArgumentParser(description="Route B offload Alpine boot")
    ap.add_argument("--disk", default=DEFAULT_DISK,
                    help=f"host disk image for VirtioBlkHost (default {DEFAULT_DISK})")
    ap.add_argument("--max-steps", type=int, default=1_500_000_000)
    ap.add_argument("--slice", type=int, default=5_000_000,
                    help="instructions per GPU dispatch between yield checks")
    ap.add_argument("--allow-missing-disk", action="store_true",
                    help="proceed even if --disk is absent (block reads -> zeros)")
    args = ap.parse_args()

    disk = Path(args.disk)
    if not disk.exists() and not args.allow_missing_disk:
        print(f"ERROR: disk image not found: {disk}\n"
              f"       pass --allow-missing-disk to boot anyway", file=sys.stderr)
        return 2

    print("=" * 70)
    print("ALPINE BOOT — Route B (host-serviced virtio-blk)")
    print(f"  RAM {RAM_SIZE // (1024*1024)}MB @ {hex(RAM_BASE)}   "
          f"disk {disk} ({'present' if disk.exists() else 'MISSING'})   "
          f"budget {args.max_steps:,}")
    print("=" * 70)

    core = bagf.SpatialRV64ICore(RAM_SIZE)
    bagf.load(core, bagf.FW_JUMP_FDT_ADDR,
              bootargs="earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0 root=/dev/vda rootwait")
    core.write_register(10, 0)
    core.write_register(11, bagf.FW_JUMP_FDT_ADDR)

    result = run_with_offload(
        core,
        str(disk) if disk.exists() else None,
        ram_base=RAM_BASE,
        slice_steps=args.slice,
        max_steps=args.max_steps,
    )

    fs = result.get("final_state", {})
    print("\n" + "=" * 70)
    print(f"  halted {fs.get('halted')}   pc {hex(fs.get('pc', 0))}   "
          f"steps {result.get('total_steps'):,}   virtio offloads {result.get('offloads')}")
    print("=" * 70)
    return 0 if fs.get("halted") == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
