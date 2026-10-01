#!/usr/bin/env python3
"""
monitor_rv64i.py — live state monitor for the RV64I GPU emulator, in the same spirit
as watch_input.sh/watch_both_events.sh (V5 desktop input debugging): run in the
foreground, tick through execution, and stream a state trace to stdout AND a JSONL
file you can `tail -f` from another terminal while the boot runs.

Usage:
    python3 tools/monitor_rv64i.py --program alpine [--steps-per-tick 200000]
        [--max-steps 500000000] [--out /tmp/rv64i_state.jsonl]

Each tick prints/logs: wall-clock timestamp, cumulative steps, steps/s for that
tick, pc, mode (M=3/S=1/U=0), halted, trap_pending, mcause/scause (only meaningful
once a trap has landed), how many new UART bytes arrived since the last tick,
the per-tick TLB hit rate (delta since the previous tick, 0% while the TLB is
untouched), and cumulative TLB hits/misses. The mode column is annotated with a
per-mode step split every 10 ticks (e.g. S98/M2 = 98% of steps since start in
S-mode), so a boot phase that bypasses the MMU entirely shows up at a glance.

Ctrl-C stops cleanly and prints a final summary (mirrors guest_state.sh's one-shot
snapshot style for a quick "where are we" check).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from spatial_rv64i_cpu import SpatialRV64ICore

CSR_MCAUSE = 0x342
CSR_SCAUSE = 0x142

MODE_NAMES = {0: 'U', 1: 'S', 3: 'M'}


def _loader_for(program: str, args) -> tuple:
    """Returns a (build_core, load) pair for the named program."""
    if program == 'alpine':
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))
        from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

        def build():
            return SpatialRV64ICore(memory_size_bytes=RAM_SIZE)

        def load(core):
            dtb_addr = load_opensbi_alpine_and_dtb(core)
            core.write_register(10, 0)
            core.write_register(11, dtb_addr)

        return build, load

    if program == 'opensbi':
        # Firmware alone, no kernel/DTB — for isolating M-mode-only boot behavior
        # (e.g. checking whether a stall is in OpenSBI itself vs. the kernel it chains to).
        opensbi_bin = args.elf_path or '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
        ram_base = args.ram_base if args.ram_base is not None else 0x80000000
        mem_size = args.mem_size or (16 * 1024 * 1024)

        def build():
            return SpatialRV64ICore(memory_size_bytes=mem_size)

        def load(core):
            with open(opensbi_bin, 'rb') as f:
                fw = f.read()
            core.load_program(fw, entry_point=ram_base, ram_base=ram_base)

        return build, load

    if program == 'elf':
        # Generic RV64 ELF loader — any bare-metal test image, not just Alpine/OpenSBI.
        if not args.elf_path:
            raise ValueError("--program elf requires --elf-path")
        sys.path.insert(0, os.path.dirname(__file__))
        from elf_to_pixel_loader import ELFLoader

        elf = ELFLoader(args.elf_path)
        ram_base = args.ram_base if args.ram_base is not None else min(
            (seg['vaddr'] for seg in elf.segments if seg['type'] == ELFLoader.PT_LOAD), default=0
        )
        mem_size = args.mem_size or (64 * 1024 * 1024)

        def build():
            return SpatialRV64ICore(memory_size_bytes=mem_size)

        def load(core):
            # Establish memory + reset PC/CSRs first (entry_point relative to nothing loaded
            # yet is fine — load_program's Hilbert scatter of an empty buffer is a cheap
            # baseline reset), then place each PT_LOAD segment at its own offset.
            core.load_program(b'', entry_point=elf.entry_point, ram_base=ram_base)
            for seg in elf.segments:
                if seg['type'] != ELFLoader.PT_LOAD or seg['filesz'] == 0:
                    continue
                data = elf.data[seg['offset']:seg['offset'] + seg['filesz']]
                core.write_mem_bytes(seg['vaddr'] - ram_base, data)

        return build, load

    raise ValueError(f"Unknown --program {program!r} (supported: alpine, opensbi, elf)")


def _dump_linear_memory(core, path: str):
    """Dump the guest memory buffer to a linear (physical) byte image.

    The GPU buffer is stored in Hilbert-curve order; the host keeps the inverse
    map (hilbert_lut_np[d] = spatial word index of linear word d), so a fancy
    index produces the linear image. Word 0 of the image = guest physical
    ram_base (0x80000000 for the alpine boot).
    """
    buf = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(buf, dtype=np.uint32)
    linear = spatial[core.hilbert_lut_np]
    linear.tofile(path)
    print(f"Dumped {linear.nbytes // (1024 * 1024)}MB linear guest memory to {path}")


def monitor(program: str, steps_per_tick: int, max_steps: int, out_path: str, args,
            stall_ticks: int = 5):
    build, load = _loader_for(program, args)
    core = build()
    load(core)
    if args.no_threading:
        core.set_bb_threading(False)
        print("Basic-block threading DISABLED (A/B control)")

    out_fh = open(out_path, 'w') if out_path else None
    total_steps = 0
    t_start = time.time()
    uart_text = ""
    mem_dumped = False

    # Stall detection: a PC that hasn't moved for `stall_ticks` consecutive ticks with
    # zero new UART output is exactly the pattern that hid the frozen-TLB bug (PC pinned
    # at 0xffffffff807fc3d8 for 20+ ticks, easy to miss by eye in a scrolling log).
    last_pc = None
    stall_count = 0
    stall_warned = False
    # TLB counters are monotonic in the shader; track deltas per tick.
    tlb_prev_hits = 0
    tlb_prev_misses = 0
    mode_steps = {}  # mode name -> cumulative steps observed in that mode
    tick_idx = 0

    print(f"Monitoring RV64I core ({program}); writing state trace to {out_path or '(stdout only)'}")
    print(f"{'steps':>12} {'steps/s':>10} {'pc':>18} {'mode':>10} {'halt':>4} {'trap':>4} {'mcause':>10} {'scause':>10} {'uart+':>6} {'tlbH%':>6} {'tlbH':>9} {'tlbM':>9}")

    try:
        while total_steps < max_steps:
            batch = min(steps_per_tick, max_steps - total_steps)
            t0 = time.time()
            core.step(steps=batch)
            # get_state() issues a blocking GPU buffer read, which is what actually
            # forces the queued dispatch to complete — timing core.step() alone measures
            # only how fast the async submit() call returns, not real GPU throughput.
            state = core.get_state()
            t1 = time.time()
            total_steps += batch

            uart_delta = core.read_uart_output()
            mcause = core.read_csr(CSR_MCAUSE)
            scause = core.read_csr(CSR_SCAUSE)

            rate = batch / (t1 - t0) if t1 > t0 else float('inf')
            mode = MODE_NAMES.get(state['mode'], str(state['mode']))
            mode_steps[mode] = mode_steps.get(mode, 0) + batch
            tick_idx += 1

            tlb_hits = int(state['tlb_hits'])
            tlb_misses = int(state['tlb_misses'])
            d_hits = tlb_hits - tlb_prev_hits
            d_misses = tlb_misses - tlb_prev_misses
            tlb_prev_hits, tlb_prev_misses = tlb_hits, tlb_misses
            d_total = d_hits + d_misses
            tlb_delta_pct = (100.0 * d_hits / d_total) if d_total else 0.0
            tlb_total = tlb_hits + tlb_misses
            tlb_cum_pct = (100.0 * tlb_hits / tlb_total) if tlb_total else 0.0

            # Per-mode step split, refreshed every 10 ticks so a phase change shows
            # up without flooding the line.
            mode_annot = mode
            if tick_idx % 10 == 0 and mode_steps:
                total_steps_seen = sum(mode_steps.values()) or 1
                parts = sorted(mode_steps.items(), key=lambda kv: -kv[1])
                mode_annot = '/'.join(f"{k}{100 * v // total_steps_seen}" for k, v in parts[:3])

            line = {
                'ts': time.time(),
                'steps': total_steps,
                'steps_per_s': round(rate),
                'pc': state['pc'],
                'mode': mode,
                'halted': bool(state['halted']),
                'trap_pending': bool(state['trap_pending']),
                'mcause': mcause,
                'scause': scause,
                'uart_new_bytes': len(uart_delta),
                'tlb_hits': tlb_hits,
                'tlb_misses': tlb_misses,
                'tlb_hit_pct': round(tlb_cum_pct, 2),
                'tlb_tick_hit_pct': round(tlb_delta_pct, 2),
            }
            print(f"{total_steps:>12} {round(rate):>10} {hex(state['pc']):>18} {mode_annot:>10} "
                  f"{int(state['halted']):>4} {int(state['trap_pending']):>4} "
                  f"{hex(mcause):>10} {hex(scause):>10} {len(uart_delta):>6} "
                  f"{tlb_delta_pct:>5.1f}% {tlb_hits:>9} {tlb_misses:>9}")

            if state['pc'] == last_pc and len(uart_delta) == 0:
                stall_count += 1
            else:
                stall_count = 0
                stall_warned = False
            last_pc = state['pc']

            if stall_count >= stall_ticks and not stall_warned:
                print(f"  !! STALL: PC has not moved and no UART output for "
                      f"{stall_count} ticks ({stall_count * batch:,} steps) — "
                      f"likely an infinite trap/refault loop, not just slow execution.")
                if out_fh:
                    out_fh.write(json.dumps({'ts': time.time(), 'stall_warning': True,
                                              'pc': state['pc'], 'ticks': stall_count}) + '\n')
                    out_fh.flush()
                stall_warned = True

            if out_fh:
                out_fh.write(json.dumps(line) + '\n')
                out_fh.flush()
            if uart_delta and out_fh:
                out_fh.write(json.dumps({'ts': time.time(), 'uart': uart_delta.decode('utf-8', 'replace')}) + '\n')
                out_fh.flush()
            if uart_delta:
                uart_text += uart_delta.decode('utf-8', 'replace')
                if args.stop_on_uart and args.stop_on_uart in uart_text and not mem_dumped:
                    print(f"  !! UART stop trigger {args.stop_on_uart!r} matched — stopping.")
                    if args.dump_mem:
                        _dump_linear_memory(core, args.dump_mem)
                        mem_dumped = True
                    break

            if state['halted']:
                print("Core halted.")
                break
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if out_fh:
            out_fh.close()
    if args.dump_mem and not mem_dumped:
        _dump_linear_memory(core, args.dump_mem)
        mem_dumped = True

    elapsed = time.time() - t_start
    final_state = core.get_state()
    print("\n=== FINAL STATE ===")
    print(f"  steps:   {total_steps} ({total_steps / elapsed:.0f} steps/s avg)")
    print(f"  pc:      {hex(final_state['pc'])}")
    print(f"  mode:    {MODE_NAMES.get(final_state['mode'], final_state['mode'])}")
    print(f"  halted:  {bool(final_state['halted'])}")
    fh = int(final_state.get('tlb_hits', 0))
    fm = int(final_state.get('tlb_misses', 0))
    ft = fh + fm
    if ft:
        print(f"  tlb:     {fh:,} hits / {fm:,} misses ({100.0 * fh / ft:.1f}% hit rate)")
    else:
        print("  tlb:     never exercised (no S-mode MMU traffic)")
    tail = core.read_uart_output()
    if tail:
        print(f"  uart tail: {tail[-300:]!r}")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--program', default='alpine', choices=['alpine', 'opensbi', 'elf'],
                    help="Which boot target to load")
    p.add_argument('--steps-per-tick', type=int, default=200_000, help="Instructions to run per monitor tick")
    p.add_argument('--max-steps', type=int, default=500_000_000, help="Stop after this many total steps")
    p.add_argument('--out', default='/tmp/rv64i_state.jsonl', help="JSONL trace path (tail -f this from another terminal)")
    p.add_argument('--stall-ticks', type=int, default=5,
                    help="Warn if PC is unchanged and no UART output arrives for this many consecutive ticks")
    p.add_argument('--no-threading', action='store_true',
                    help="Disable basic-block threading (A/B control for threading-induced mis-execution)")
    p.add_argument('--stop-on-uart', default=None,
                    help="Stop the run (and optionally dump memory) as soon as this substring appears in UART output")
    p.add_argument('--dump-mem', default=None,
                    help="Dump linear guest memory to this path on stop-trigger (or at run end)")
    p.add_argument('--elf-path', default=None,
                    help="Path to the binary to load (ELF for --program elf; firmware .bin for --program opensbi)")
    p.add_argument('--ram-base', type=lambda x: int(x, 0), default=None,
                    help="Guest physical address mapping to word 0 (default: lowest PT_LOAD vaddr for elf, 0x80000000 for opensbi)")
    p.add_argument('--mem-size', type=lambda x: int(x, 0), default=None,
                    help="Emulator RAM size in bytes, must be a perfect-square word count (default: 16MB opensbi, 64MB elf/alpine)")
    args = p.parse_args()

    monitor(args.program, args.steps_per_tick, args.max_steps, args.out, args,
            stall_ticks=args.stall_ticks)
