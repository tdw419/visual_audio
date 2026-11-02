#!/usr/bin/env python3
"""
tlb_membench.py — synthetic RV64I memory-path benchmark harness.

Isolates the TLB / Sv39-walk / Hilbert-memory cost cleanly, without hunting
through the Alpine boot trace (see RV64I_STATUS.md "Next Steps"). Loads a
tlb_bench_*.elf (built by tests/bare_metal/tlb_membench/build.sh), pre-populates
an Sv39 identity map (4MB superpages) covering RAM, then runs N steps and
reports the sync-bracketed steps/s (timing bracketed by the blocking get_state()
read — NOT the meaningless async submit rate) plus the shader's TLB hit/miss
counters and the guest's UART banner.

Variant matrix (compile-time, see build.sh):
    ACCESS=ALU    register-only arithmetic loop      -> execute-path baseline
    ACCESS=LOAD   one 64-bit load per page, acc +=  -> TLB-hit / walk cost
    ACCESS=STORE  one 64-bit store per page          -> write path cost
    W=<pages>     working set; 256-entry direct-mapped TLB thrash cliff is at
                  W>=512 (index = vpn & 255 collides every 256th page).

Usage:
    python3 tools/tlb_membench.py tests/bare_metal/tlb_membench/tlb_bench_ld_w128.elf \
        [--steps 10000000] [--threading on|off]
"""
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from spatial_rv64i_cpu import SpatialRV64ICore
from elf_to_pixel_loader import ELFLoader

RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
ROOT_PT = 0x80400000
L1_PT = 0x80401000
CSR_SATP = 0x180


def build_identity_tables(core):
    """Sv39 identity map over RAM: root[2] -> L1; L1[k]=4MB superpage (k<16)."""
    root = np.zeros(512, dtype=np.uint64)
    root[2] = ((L1_PT >> 12) << 10) | 1  # pointer PTE: V=1, R=W=X=0 (not a leaf)
    l1 = np.zeros(512, dtype=np.uint64)
    for k in range(16):
        ppn = (RAM_BASE >> 12) + (k << 10)  # 4MB-aligned PPN
        l1[k] = (ppn << 10) | 1 | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 6) | (1 << 7)
    core.write_mem_bytes(ROOT_PT - RAM_BASE, root.tobytes())
    core.write_mem_bytes(L1_PT - RAM_BASE, l1.tobytes())


def load_elf(core, path):
    elf = ELFLoader(path)
    core.load_program(b'', entry_point=elf.entry_point, ram_base=RAM_BASE)
    for seg in elf.segments:
        if seg['type'] != ELFLoader.PT_LOAD or seg['filesz'] == 0:
            continue
        if seg['vaddr'] < RAM_BASE:
            continue  # ELF header/comment segments below RAM — not guest code
        data = elf.data[seg['offset']:seg['offset'] + seg['filesz']]
        core.write_mem_bytes(seg['vaddr'] - RAM_BASE, data)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('elf', help='tlb_bench_*.elf to run')
    p.add_argument('--steps', type=int, default=10_000_000)
    p.add_argument('--threading', choices=['on', 'off'], default='on')
    p.add_argument('--verify-tlb', action='store_true',
                   help='print expected TLB hit rate based on W')
    args = p.parse_args()

    w_hint = None
    for tok in os.path.basename(args.elf).split('_'):
        if tok.startswith('w') and tok[1:].isdigit():
            w_hint = int(tok[1:])

    core = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)
    load_elf(core, args.elf)
    build_identity_tables(core)
    core.set_bb_threading(args.threading == 'on')

    # Run to the guest's mret into S-mode (a few hundred steps) so we can
    # confirm it got there, then measure the loop with sync-bracketed timing.
    core.step(steps=200_000)
    banner = core.read_uart_output().decode('utf-8', 'replace')
    st = core.get_state()
    print(f'guest banner: {banner.strip()!r}')
    print(f'after entry: pc={hex(st["pc"])} mode={st["mode"]} (1=S) '
          f'halted={st["halted"]} tlb_hits={st["tlb_hits"]} tlb_misses={st["tlb_misses"]}')

    t0 = time.time()
    core.step(steps=args.steps)
    st = core.get_state()
    t1 = time.time()
    rate = args.steps / (t1 - t0)

    uart_tail = core.read_uart_output().decode('utf-8', 'replace')
    hits = int(st['tlb_hits'])
    misses = int(st['tlb_misses'])
    total = hits + misses
    hit_pct = 100.0 * hits / total if total else 0.0

    print(f'\n=== {os.path.basename(args.elf)} ({args.steps:,} steps, threading={args.threading}) ===')
    print(f'  steps/s:  {rate:,.0f}  (sync-bracketed)')
    print(f'  mode:     {st["mode"]} (1=S)  pc: {hex(st["pc"])}  halted: {st["halted"]}')
    print(f'  tlb:      {hits:,} hits / {misses:,} misses ({hit_pct:.1f}% hit)')
    if total:
        print(f'  lookups/inst: {total / args.steps:.3f}')
    if w_hint:
        expect = '~100% (working set fits)' if w_hint <= 256 else '~0% (thrash: index = vpn & 255)'
        print(f'  W={w_hint}: expected hit rate {expect}')
    if uart_tail.strip():
        print(f'  uart tail: {uart_tail[-120:]!r}')


if __name__ == '__main__':
    main()
