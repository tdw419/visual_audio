#!/usr/bin/env python3
"""Interactive Linux shell on the GPU RV64 core — type at it yourself.

Boots the h12 shell container (tools/build_gpu_shell_blob.py) to the
`gpu-rv64:~#` prompt, then drives the guest UART from your keyboard:
each command is fed byte-by-byte into the UART RX FIFO with
ECHO-ACKNOWLEDGED PACING — the guest UART RX FIFO is one byte deep, so
a byte is only sent after the kernel has echoed the previous one back.
The command's output streams to your terminal. The guest is paused
while you think: nothing executes between your commands.

Usage:
    python3 tools/build_gpu_shell_blob.py -o /tmp/h12/alpine_shell.lnx.bin
    python3 tools/gpu_shell_live.py --kernel /tmp/h12/alpine_shell.lnx.bin \
        --max-steps 3000000000            # then type: ls / etc.
    python3 tools/gpu_shell_live.py --kernel ... --script "ls /" "free"   # non-interactive
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "tools"))
sys.path.insert(0, str(_REPO))

from qemu_gpu_offload import GpuRam, VirtioBlkHost, QueueConfig  # noqa: E402
import boot_alpine_gpu_fixed as bagf                             # noqa: E402

PROMPT = b"gpu-rv64:~# "
FEED_STEPS = 100_000               # slice size while a byte is in flight
PROMPT_TIMEOUT_STEPS = 800_000_000   # per command (ls-scale is far below this)


def save_snapshot(core, path: str) -> None:
    """Dump every GPU buffer that constitutes the machine to an .npz file.

    The memory surface IS the machine state — this is literally the
    computer saved as an image of itself."""
    import numpy as np
    q = core.queue

    def rd(buf):
        return np.frombuffer(q.read_buffer(buf, 0, buf.size), dtype=np.uint8)

    np.savez_compressed(
        path,
        memory=rd(core.memory.buffer),
        registers=rd(core.registers.buffer),
        state=rd(core.state_buffer),
        csr=rd(core.csr_buffer),
        uart=rd(core.uart_buffer),
        tlb=rd(core.tlb_buffer),
    )
    print(f"[snapshot] saved machine state -> {path}", flush=True)


def restore_snapshot(core, path: str) -> None:
    """Write every buffer back and rebuild host-side shadows."""
    import numpy as np
    z = np.load(path)
    q = core.queue
    q.write_buffer(core.memory.buffer, 0, z["memory"].tobytes())
    q.write_buffer(core.registers.buffer, 0, z["registers"].tobytes())
    q.write_buffer(core.state_buffer, 0, z["state"].tobytes())
    q.write_buffer(core.csr_buffer, 0, z["csr"].tobytes())
    q.write_buffer(core.uart_buffer, 0, z["uart"].tobytes())
    q.write_buffer(core.tlb_buffer, 0, z["tlb"].tobytes())
    # Rebuild the linear shadow and force full re-decode of decoded ops.
    words = core._linear_shadow.shape[0]
    raw = q.read_buffer(core.memory.buffer, 0, words * 4)
    core._linear_shadow[:] = np.frombuffer(raw, dtype=np.uint32)
    core._mark_range_dirty(0, words * 4)
    # Sync the UART accounting so read_uart_output does not replay old bytes.
    core._uart_consumed = int(core.get_state().get("uart_tx_len", 0))
    print(f"[snapshot] restored machine state <- {path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kernel", required=True, help="shell LNX container")
    ap.add_argument("--disk", default=None)
    ap.add_argument("--max-steps", type=int, default=2_500_000_000)
    ap.add_argument("--slice", type=int, default=5_000_000)
    ap.add_argument("--script", nargs="*", default=None,
                    help="commands to run at the prompt, in order (non-interactive)")
    ap.add_argument("--snapshot", default=None,
                    help="resume a saved machine state instead of booting")
    ap.add_argument("--save-snapshot", default=None,
                    help="save machine state when the prompt is first reached")
    args = ap.parse_args()

    bagf.KERNEL_LNX = args.kernel
    disk = Path(args.disk) if args.disk else None

    print("=" * 70)
    print("GPU LINUX LIVE SHELL - boot to prompt, then type commands")
    print(f"  kernel {args.kernel}   disk {disk or 'none'}   budget {args.max_steps:,}")
    print("=" * 70)

    core = bagf.SpatialRV64ICore(bagf.RAM_SIZE)
    if args.snapshot:
        restore_snapshot(core, args.snapshot)
    else:
        bagf.load(core, bagf.FW_JUMP_FDT_ADDR,
                  bootargs="earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0 root=/dev/vda rootwait")
        core.write_register(10, 0)
        core.write_register(11, bagf.FW_JUMP_FDT_ADDR)

    ram = GpuRam(core, bagf.RAM_BASE)
    blk_host = VirtioBlkHost(str(disk) if disk else None)
    core.queue.write_buffer(core.state_buffer, 43 * 4,
                            np.array([2], dtype=np.uint32).tobytes())

    script = list(args.script) if args.script is not None else None
    queue: list[int] = []         # bytes of the current command still to send
    in_flight: int | None = None  # byte sent, awaiting kernel echo
    cmd_deadline = None
    cmd_index = 0                 # scripted commands completed
    prompt_stable = 0             # consecutive drains ending at the prompt
    saved = False                 # --save-snapshot written yet?
    # A resumed machine is already blocked at its shell read; its prompt
    # bytes were consumed before the snapshot was taken. Seed the parser
    # with the prompt so dispatch fires without waiting to re-see it.
    buf = PROMPT if args.snapshot else b""
    total_steps = 0
    t0 = time.time()
    rc = 1
    try:
        while total_steps < args.max_steps:
            state_arr = np.frombuffer(core.queue.read_buffer(core.state_buffer), dtype=np.uint32)
            halted = int(state_arr[2])
            if halted == 1:
                print("[live] core clean halt")
                rc = 0
                break
            if halted == 2:
                cfg = QueueConfig(state_arr)
                processed = blk_host.service_queue(ram, cfg)
                if processed > 0:
                    CSR_MIP = 0x344
                    core.write_csr(CSR_MIP, core.read_csr(CSR_MIP) | 0x200)
                core.queue.write_buffer(core.state_buffer, 2 * 4,
                                        np.array([0], dtype=np.uint32).tobytes())

            out = core.read_uart_output()
            if out:
                sys.stdout.write(out.decode("utf-8", errors="replace"))
                sys.stdout.flush()
                if in_flight is not None and in_flight in out:
                    in_flight = None   # kernel echoed the byte: safe to send the next
                # CRs are our own flusher's noise: normalize them out so the
                # prompt-stability check sees flush cycles as silence.
                new_buf = (buf + out).replace(b"\r", b"")[-4096:]
                if new_buf != buf:
                    buf = new_buf
                    prompt_stable = 0
                elif buf.endswith(PROMPT):
                    prompt_stable += 1
            else:
                if buf.endswith(PROMPT):
                    prompt_stable += 1

            at_prompt = len(buf) >= len(PROMPT) and buf.endswith(PROMPT)

            # dispatch a new command only once the prompt has settled
            # (two consecutive drains with no fresh output) and nothing
            # of the previous command is in flight
            if (at_prompt and prompt_stable >= 2 and in_flight is None
                    and not queue and cmd_deadline is None):
                if args.save_snapshot and not saved:
                    save_snapshot(core, args.save_snapshot)
                    saved = True
                if script is not None:
                    if cmd_index >= len(script):
                        rc = 0   # scripted run finished cleanly at the prompt
                        break
                    cmd = script[cmd_index]
                    cmd_index += 1
                    queue = list(cmd.encode()) + [10]
                    print(f"\n[live] sending: {cmd}", flush=True)
                elif sys.stdin.isatty():
                    sys.stdout.write("\n[live] type a command (guest paused): ")
                    sys.stdout.flush()
                    cmd = input()
                    queue = list(cmd.encode()) + [10]
                else:
                    rc = 0   # non-interactive, nothing to send: done
                    break

            if in_flight is None and queue:
                in_flight = queue.pop(0)
                core.write_uart_input(bytes([in_flight]))

            step = FEED_STEPS if in_flight is not None else args.slice
            core.step(step)
            total_steps += step

            if cmd_deadline is None and (queue or in_flight is not None):
                cmd_deadline = total_steps + PROMPT_TIMEOUT_STEPS
            if cmd_deadline is not None and not queue and in_flight is None \
                    and buf.endswith(PROMPT):
                cmd_deadline = None   # command completed
            elif cmd_deadline is not None and total_steps > cmd_deadline:
                print(f"\n[live] command timed out after {PROMPT_TIMEOUT_STEPS:,} steps", flush=True)
                queue, in_flight, cmd_deadline = [], None, None
    finally:
        blk_host.close()

    print("\n" + "=" * 70)
    print(f"  steps {total_steps:,}   wall {time.time()-t0:.0f}s   rc {rc}")
    print("=" * 70)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
