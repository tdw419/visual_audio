#!/usr/bin/env python3
"""
Fresh boot of the Alpine 6.18 materials on the GPU RV64 core, with:
  - configurable step batch (jitter/GPU-dispatch behaviour depends on it)
  - checkpoint-on-UART-marker and/or checkpoint-at-step
  - stop on panic / Oops / a stop-marker / max-steps
  - prints where it ended (pc, last UART, step count)

Reuses boot_alpine_v618_gpu.load() so the DTB / memory layout stay identical.

  python3 tools/fresh_boot_ckpt.py --batch 50000 \
      --ckpt-at-uart "Ticket spinlock: enabled" --out .ckpt/fresh_pre_percpu.rv64ckpt \
      --max-steps 400000000
"""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path

_R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_R / "tools")); sys.path.insert(0, str(_R))

import boot_alpine_v618_gpu as B
from spatial_rv64i_cpu import SpatialRV64ICore
from rv64i_checkpoint import save_checkpoint, load_checkpoint

STOP_MARKERS = ("Kernel panic", "Oops", "Unable to handle kernel paging request",
                "Attempted to kill", "unhandled signal")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=50000)
    ap.add_argument("--max-steps", type=int, default=600_000_000)
    ap.add_argument("--offload", action="store_true")
    ap.add_argument("--disk", default="/tmp/alpine_rootfs/alpine_disk.img")
    ap.add_argument("--initrd", default=None)
    ap.add_argument("--ckpt-at-uart", default=None,
                    help="save a checkpoint the first time this string appears in UART")
    ap.add_argument("--ckpt-at-step", type=int, default=None)
    ap.add_argument("--out", default=None, help="checkpoint path")
    ap.add_argument("--resume-from", default=None,
                    help="resume this checkpoint instead of a fresh boot")
    ap.add_argument("--fast-path", action="store_true",
                    help="resume with the pre-decoded fast path ENABLED "
                         "(shader flag patched before pipeline creation)")
    ap.add_argument("--stop-at-uart", default=None,
                    help="stop cleanly the first time this string appears")
    ap.add_argument("--continue-after-ckpt", action="store_true",
                    help="keep running after the checkpoint is taken (default: stop)")
    a = ap.parse_args()

    if a.resume_from:
        if a.fast_path:
            from fastpath_core import load_checkpoint_fast
            core = load_checkpoint_fast(a.resume_from)
            print(f"resumed {a.resume_from} [FAST PATH ENABLED]")
        else:
            core = load_checkpoint(a.resume_from)
            print(f"resumed {a.resume_from}")
    else:
        B._INITRD_OVERRIDE = a.initrd
        bootargs = ("earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0"
                    + (" root=/dev/vda rootwait" if a.offload else ""))
        core = SpatialRV64ICore(B.RAM_SIZE)
        B.load(core, bootargs)
        core.write_register(10, 0)
        core.write_register(11, B.FW_JUMP_FDT_ADDR)
        print(f"fresh boot, batch={a.batch}, bootargs={bootargs!r}")

    if a.offload and not a.resume_from:
        # offload needs its own run loop; not used for the debug path yet
        from qemu_gpu_offload import run_with_offload
        r = run_with_offload(core, a.disk, ram_base=B.RAM_BASE,
                             slice_steps=a.batch, max_steps=a.max_steps)
        print(r["final_state"]); return

    uart = ""
    steps = 0
    ckpt_done = False
    t0 = time.time()
    last_print = time.time()
    while steps < a.max_steps:
        core.step(steps=a.batch)
        steps += a.batch
        b = core.read_uart_output()
        if b:
            t = b.decode("latin-1", "replace")
            uart += t
            sys.stdout.write(t); sys.stdout.flush()

        if (not ckpt_done and a.out and
                ((a.ckpt_at_uart and a.ckpt_at_uart in uart) or
                 (a.ckpt_at_step and steps >= a.ckpt_at_step))):
            print(f"\n[ckpt] saving at step {steps:,} (uart {len(uart)}B)")
            save_checkpoint(core, a.out)
            ckpt_done = True
            if not a.continue_after_ckpt:
                print("[ckpt] stopping (no --continue-after-ckpt)")
                break

        if a.stop_at_uart and a.stop_at_uart in uart:
            print(f"\n[stop-marker '{a.stop_at_uart}' @ {steps:,}]")
            break
        if any(m in uart for m in STOP_MARKERS):
            hit = next(m for m in STOP_MARKERS if m in uart)
            print(f"\n[STOP MARKER '{hit}' @ {steps:,} steps, {time.time()-t0:.0f}s]")
            break
        if time.time() - last_print > 60:
            st = core.get_state()
            print(f"\n[hb {steps:,} steps pc=0x{st['pc']:x} {time.time()-t0:.0f}s]")
            last_print = time.time()

    st = core.get_state()
    print(f"\n=== end: steps={steps:,} pc=0x{st['pc']:x} halted={st['halted']} "
          f"uart={len(uart)}B {time.time()-t0:.0f}s ===")
    print(f"bb: total={st.get('bb_total_insts',0):,} threaded={st.get('bb_threaded_insts',0):,} "
          f"fallback={st.get('bb_fallback_insts',0):,} ctl={st.get('bb_ctl_insts',0):,}")
    print("uart tail:", repr(uart[-300:]))


if __name__ == "__main__":
    main()
