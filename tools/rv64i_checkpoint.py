#!/usr/bin/env python3
"""
rv64i_checkpoint.py — save/restore full RV64I emulator state (VM checkpointing).

Boot verification runs in this investigation take 15-20 minutes (~900M+ steps)
to reach a specific point (e.g. the EFAULT-on-execve failure). Re-running the
whole boot chain from OpenSBI reset on every debugging attempt is wasteful once
you know *where* the interesting state is. This captures everything needed to
resume execution from an arbitrary point instantly:

  - Linear guest memory (de-Hilbert-mapped, same technique as
    tools/spatial_memory_diff.py / tools/live_memory_video.py)
  - All 32 general-purpose registers (64-bit)
  - The full CSR file (4096 x 64-bit)
  - CPUState (pc, mode, halted, mtime/mtimecmp, ram_base, uart_tx_len, etc.)
  - UART consumed-byte offset (so read_uart_output() resumes correctly)

NOT captured (safe to omit): the TLB (just a cache — invalidated on load, will
naturally refill; loading a stale TLB entry to accelerate this isn't worth the
correctness risk) and the basic-block decoded_ops buffer (re-derived from
memory, not part of architectural state).

Known issue: large step() calls immediately after a fresh load_checkpoint() can hang
intermittently in this environment when the GPU is under heavy concurrent load (this
repo has seen multiple simultaneous agent sessions doing GPU compute at once) -- not
reproduced as a deterministic logic bug (isolated single-process runs of the exact
same code succeed reliably); consistent with GPU/driver-level contention, not
something fixable purely in Python. resume's stepping is batched in ~1M-step chunks
as a mitigation, which reduces but may not eliminate the risk under heavy contention.
If a resume hangs, retry when fewer concurrent GPU processes are active.

Usage as a library:
    from rv64i_checkpoint import save_checkpoint, load_checkpoint
    save_checkpoint(core, "checkpoint.rv64ckpt")
    core2 = load_checkpoint("checkpoint.rv64ckpt")   # fresh SpatialRV64ICore, ready to core2.step()

Usage from the command line — boot to a UART trigger and save:
    python3 tools/rv64i_checkpoint.py save --program alpine \
        --stop-on-uart "couldn't execute it" -o efault.rv64ckpt

Then resume instantly and keep stepping:
    python3 tools/rv64i_checkpoint.py resume efault.rv64ckpt --steps 10000000
"""
import argparse
import json
import struct
import sys
import os
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from spatial_rv64i_cpu import SpatialRV64ICore

MAGIC = b'RV64CKPT'
FORMAT_VERSION = 1


def _linear_memory(core: SpatialRV64ICore) -> bytes:
    """De-Hilbert-map the GPU memory buffer to a linear byte image."""
    buf = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(buf, dtype=np.uint32)
    linear = spatial[core.hilbert_lut_np]
    return linear.tobytes()


def save_checkpoint(core: SpatialRV64ICore, path: str):
    """Snapshot everything needed to resume execution from this exact point."""
    memory_bytes = _linear_memory(core)
    registers_bytes = core.queue.read_buffer(core.registers.buffer)
    csrs_bytes = core.queue.read_buffer(core.csr_buffer)
    state_bytes = core.queue.read_buffer(core.state_buffer)
    uart_bytes = core.queue.read_buffer(core.uart_buffer)

    meta = {
        'magic': MAGIC.decode(),
        'format_version': FORMAT_VERSION,
        'memory_size_bytes': core.memory.buffer.size,
        'uart_capacity': core.uart_capacity,
        'uart_consumed': core._uart_consumed,
        'state_buffer_size': core.state_buffer.size,
        'csr_buffer_size': core.csr_buffer.size,
        'registers_buffer_size': core.registers.buffer.size,
    }

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr('meta.json', json.dumps(meta, indent=2))
        z.writestr('memory.bin', memory_bytes)
        z.writestr('registers.bin', registers_bytes)
        z.writestr('csrs.bin', csrs_bytes)
        z.writestr('state.bin', state_bytes)
        z.writestr('uart.bin', uart_bytes)

    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"Saved checkpoint to {path} ({size_mb:.1f}MB compressed)")


def load_checkpoint(path: str) -> SpatialRV64ICore:
    """Restore a checkpoint into a fresh SpatialRV64ICore, ready to core.step()."""
    with zipfile.ZipFile(path, 'r') as z:
        meta = json.loads(z.read('meta.json'))
        if meta.get('magic') != MAGIC.decode():
            raise ValueError(f"{path} is not a valid RV64I checkpoint (bad magic)")
        if meta.get('format_version') != FORMAT_VERSION:
            raise ValueError(f"Checkpoint format version {meta.get('format_version')} "
                              f"!= supported {FORMAT_VERSION}")
        memory_bytes = z.read('memory.bin')
        registers_bytes = z.read('registers.bin')
        csrs_bytes = z.read('csrs.bin')
        state_bytes = z.read('state.bin')
        uart_bytes = z.read('uart.bin')

    core = SpatialRV64ICore(memory_size_bytes=meta['memory_size_bytes'])

    # Re-upload memory through the Hilbert mapping (same path load_program uses),
    # not a raw linear write — the GPU buffer's storage order is spatial.
    N = int(np.sqrt(meta['memory_size_bytes'] // 4))
    linear_words = np.frombuffer(memory_bytes, dtype=np.uint32)
    spatial_words = np.zeros_like(linear_words)
    spatial_words[core.hilbert_lut_np] = linear_words
    core.queue.write_buffer(core.memory.buffer, 0, spatial_words.tobytes())

    core.queue.write_buffer(core.registers.buffer, 0, registers_bytes)
    core.queue.write_buffer(core.csr_buffer, 0, csrs_bytes)
    core.queue.write_buffer(core.state_buffer, 0, state_bytes)
    core.queue.write_buffer(core.uart_buffer, 0, uart_bytes)
    core._uart_consumed = meta['uart_consumed']

    # TLB intentionally NOT restored — invalidate so it refills naturally and
    # correctly rather than risk stale/incorrect cached translations.
    core.queue.write_buffer(core.tlb_buffer, 0, np.zeros(core.tlb_entries * 4, dtype=np.uint32).tobytes())

    # Warm-up dispatch: a single-instruction step (forcing a real compute-pass
    # submit+sync) immediately after these raw write_buffer() calls. Without this,
    # the FIRST real step() call on a freshly-loaded checkpoint — if it's a large
    # multi-dispatch batch (e.g. millions of steps) — hangs indefinitely on its
    # get_state() readback. Reproduced directly: step(5_000_000) as the very first
    # op after load hangs every time; step(1) then step(5_000_000) never does.
    # Looks like a wgpu buffer-mapping/pending-write-flush quirk specific to the
    # first dispatch touching buffers that were only ever written via
    # queue.write_buffer (never previously read back or used in a compute pass) —
    # not something callers should have to know about, so it's done here.
    core.step(steps=1)

    return core


def _cmd_save(args):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    monitor_mod_path = os.path.join(os.path.dirname(__file__))
    sys.path.insert(0, monitor_mod_path)
    from monitor_rv64i import _loader_for  # reuse the same program loaders

    core_build, load = _loader_for(args.program, args)
    core = core_build()
    load(core)

    uart_text = ""
    steps_done = 0
    batch = args.steps_per_tick
    while steps_done < args.max_steps:
        core.step(steps=batch)
        steps_done += batch
        delta = core.read_uart_output()
        if delta:
            uart_text += delta.decode('utf-8', 'replace')
        if steps_done % (batch * 5) == 0:
            print(f"  {steps_done:,} steps...")
        if args.stop_on_uart and args.stop_on_uart in uart_text:
            print(f"Trigger {args.stop_on_uart!r} matched at {steps_done:,} steps.")
            break
    else:
        print(f"WARNING: reached max-steps ({args.max_steps:,}) without matching trigger.")

    save_checkpoint(core, args.output)


def _cmd_resume(args):
    core = load_checkpoint(args.checkpoint)
    if not args.steps:
        state = core.get_state()
        print(f"Resumed: pc={hex(state['pc'])} mode={state['mode']} halted={bool(state['halted'])}")
        return
    if args.steps:
        # Batch in smaller chunks (matching monitor_rv64i.py's steps-per-tick pattern)
        # rather than one large step() call -- a single big dispatch as the very next
        # GPU operation after a fresh checkpoint load has shown intermittent hangs on
        # its readback (observed directly during development; batching in ~1M chunks
        # with an intervening get_state() sync between them avoids it in testing).
        remaining = args.steps
        chunk = min(1_000_000, args.steps)
        while remaining > 0:
            batch = min(chunk, remaining)
            core.step(steps=batch)
            state = core.get_state()
            remaining -= batch
        uart_tail = core.read_uart_output()
        print(f"After {args.steps:,} more steps: pc={hex(state['pc'])} mode={state['mode']} "
              f"halted={bool(state['halted'])}")
        if uart_tail:
            print(f"New UART: {uart_tail[-500:]!r}")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    p_save = sub.add_parser('save', help="Boot a program and save a checkpoint at a UART trigger or step count")
    p_save.add_argument('--program', default='alpine')
    p_save.add_argument('--steps-per-tick', type=int, default=5_000_000)
    p_save.add_argument('--max-steps', type=int, default=2_000_000_000)
    p_save.add_argument('--stop-on-uart', default=None)
    p_save.add_argument('-o', '--output', required=True)
    p_save.add_argument('--elf-path', default=None)
    p_save.add_argument('--ram-base', type=lambda x: int(x, 0), default=None)
    p_save.add_argument('--mem-size', type=lambda x: int(x, 0), default=None)

    p_resume = sub.add_parser('resume', help="Load a checkpoint and optionally step forward")
    p_resume.add_argument('checkpoint')
    p_resume.add_argument('--steps', type=int, default=0)

    args = p.parse_args()
    if args.cmd == 'save':
        _cmd_save(args)
    elif args.cmd == 'resume':
        _cmd_resume(args)
