#!/usr/bin/env python3
"""
run_with_offload_glyph() -- the Route B co-simulation loop with the glyph
dispatch bridge wired in.

This is `tools/qemu_gpu_offload.py :: run_with_offload` with two additions:
  * a GlyphDispatchHost is constructed alongside the VirtioBlkHost, and
  * host.on_yield() is called on every servicing turn (state halted == 2),
    right after the VirtIO queue is walked.

It is kept as a copy rather than a patch to the repo tool per the project's
"don't modify tools/" rule (README Copy Policy). The loop body is ~40 lines and
mirrors the upstream one; if run_with_offload changes, re-sync here. The hook
itself is exercised in isolation by tests/test_item3_mmio_bridge.py; a real
RISC-V guest driving this on a real core is ROADMAP item 4.
"""

import sys
from pathlib import Path
from typing import Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GD_ROOT = Path(__file__).resolve().parents[2]
for p in (str(_REPO_ROOT / "tools"), str(_GD_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from qemu_gpu_offload import GpuRam, VirtioBlkHost, QueueConfig  # noqa: E402
from src.offload.glyph_dispatch_host import GlyphDispatchHost      # noqa: E402


def run_with_offload_glyph(core, disk_path: str, ram_base: int = 0x80000000,
                           slice_steps: int = 50000,
                           max_steps: int = 2_000_000_000,
                           glyph_db_path: Optional[str] = None) -> dict:
    ram = GpuRam(core, ram_base)
    blk_host = VirtioBlkHost(disk_path)
    glyph_host = GlyphDispatchHost(ram, glyph_db_path=glyph_db_path)

    offloads = 0
    total_steps = 0

    # Route QueueNotify to the host (vq_ready = 2), as run_with_offload does.
    core.queue.write_buffer(core.state_buffer, 43 * 4,
                            np.array([2], dtype=np.uint32).tobytes())

    try:
        while True:
            state_bytes = core.queue.read_buffer(core.state_buffer)
            state_arr = np.frombuffer(state_bytes, dtype=np.uint32)
            halted = int(state_arr[2])

            if halted == 1:
                print("[Offload] Core clean halt (halted=1) detected.")
                break

            if halted == 2:
                offloads += 1
                cfg = QueueConfig(state_arr)
                processed = blk_host.service_queue(ram, cfg)
                if processed > 0:
                    CSR_MIP = 0x344
                    core.write_csr(CSR_MIP, core.read_csr(CSR_MIP) | 0x200)

                # glyph dispatch bridge: same servicing turn as VirtIO.
                glyph_host.on_yield()

                core.queue.write_buffer(core.state_buffer, 2 * 4,
                                        np.array([0], dtype=np.uint32).tobytes())

            uart_out = core.read_uart_output()
            if uart_out:
                sys.stdout.write(uart_out.decode("utf-8", errors="replace"))
                sys.stdout.flush()

            core.step(slice_steps)
            total_steps += slice_steps
            if total_steps > max_steps:
                print(f"[Offload] step budget reached ({max_steps})")
                break
    finally:
        blk_host.close()

    return {
        "final_state": core.get_state(),
        "total_steps": total_steps,
        "offloads": offloads,
        "glyph": glyph_host.stats(),
    }
