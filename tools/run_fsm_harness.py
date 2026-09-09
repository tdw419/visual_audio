#!/usr/bin/env python3
"""Run the cpio-parser FSM harness: execute the kernel's initramfs.c state
machine (VFS stubbed) over the full reference stream on the emulator, then
compare the recorded this_header-at-every-do_reset sequence against a Python
simulation of the SAME FSM. The first divergence pinpoints the entry where the
emulator's parser mis-executes.

Usage: python3 tools/run_fsm_harness.py
"""
import gzip
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.spatial_rv64i_cpu import SpatialRV64ICore
from tools.elf_to_pixel_loader import ELFLoader

ELF = '/tmp/inflate_harness/fsm_harness.elf'
LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
MARKER_ADDR = 0x00100000
INPUT_ADDR = 0x00400000
RESULTS_ADDR = 0x00800000
MARKER_MAGIC = 0xF5F00D
MAX_STEPS = 200_000_000
POLL_EVERY = 2_000_000

# state constants (match the C enum)
S_START, S_COLLECT, S_GOTHEADER, S_SKIPIT, S_GOTNAME, S_COPYFILE, S_GOTSYMLINK, S_RESET = range(8)


def load_ref() -> bytes:
    data = Path(LNX).read_bytes()
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            return gzip.decompress(data[off:off + 5400000])
    raise SystemExit('no initrd gzip found')


def nalign(l: int) -> int:
    return ((l + 1) & ~3) + 2


def simulate(ref: bytes):
    """Python replica of the harness FSM. Returns (this_headers, final_state,
    final_byte_count, final_this_header, message)."""
    CHUNK = 32768
    state = S_START
    next_state = S_START
    victim = 0            # offset into ref of the current chunk position
    byte_count = 0
    this_header = 0
    next_header = 0
    collected = 0         # offset into ref of collected data
    remains = 0
    body_len = 0
    name_len = 0
    mode = 0
    message = None
    results = []

    def eat(n):
        nonlocal victim, this_header, byte_count
        victim += n
        this_header += n
        byte_count -= n

    def read_into(size, nxt):
        nonlocal collected, remains, state, next_state
        if byte_count >= size:
            collected = victim
            eat(size)
            state = nxt
        else:
            collected = victim
            remains = size
            next_state = nxt
            state = S_COLLECT

    def do_collect():
        nonlocal remains, state
        n = min(remains, byte_count)
        eat(n)
        remains -= n
        if remains != 0:
            return 1
        state = next_state
        return 0

    def do_header():
        nonlocal body_len, name_len, mode, next_header, state, next_state, remains
        hdr = ref[collected:collected + 6]
        if hdr != b'070701':
            if hdr == b'070707':
                message = 'incorrect cpio method used: use -H newc option'
            else:
                message = 'no cpio magic'
            return 1
        fields = [int(ref[collected + i:collected + i + 8], 16) for i in range(6, 110, 8)]
        mode = fields[1]
        body_len = fields[6]
        name_len = fields[11]
        next_header = this_header + nalign(name_len) + body_len
        next_header = (next_header + 3) & ~3
        state = S_SKIPIT
        if name_len <= 0 or name_len > 4096:
            return 0
        if (mode & 0o170000) == 0o120000:  # S_ISLNK
            if body_len > 4096:
                return 0
            remains = nalign(name_len) + body_len
            next_state = S_GOTSYMLINK
            state = S_COLLECT
            return 0
        if (mode & 0o170000) == 0o100000 or not body_len:  # S_ISREG || !body_len
            read_into(nalign(name_len), S_GOTNAME)
        return 0

    def do_skip():
        nonlocal state
        if this_header + byte_count < next_header:
            eat(byte_count)
            return 1
        else:
            eat(next_header - this_header)
            state = next_state
            return 0

    def do_name():
        nonlocal state, next_state
        state = S_SKIPIT
        next_state = S_RESET
        if ref[collected:collected + 11] == b'TRAILER!!!\x00':
            return 0
        if (mode & 0o170000) == 0o100000:
            state = S_COPYFILE
        return 0

    def do_copy():
        nonlocal body_len, state
        if byte_count >= body_len:
            eat(body_len)
            state = S_SKIPIT
            return 0
        else:
            body_len -= byte_count
            eat(byte_count)
            return 1

    def do_symlink():
        nonlocal state, next_state
        state = S_SKIPIT
        next_state = S_RESET
        return 0

    def do_reset():
        results.append(this_header)
        while byte_count and ref[victim] == 0:
            eat(1)
        if byte_count and (this_header & 3):
            message = 'broken padding'
        return 1

    def action():
        nonlocal state
        if state == S_START:
            read_into(110, S_GOTHEADER)
            return 0
        if state == S_COLLECT:
            return do_collect()
        if state == S_GOTHEADER:
            return do_header()
        if state == S_SKIPIT:
            return do_skip()
        if state == S_GOTNAME:
            return do_name()
        if state == S_COPYFILE:
            return do_copy()
        if state == S_GOTSYMLINK:
            return do_symlink()
        if state == S_RESET:
            return do_reset()
        return 1

    def write_buffer(buf, ln):
        nonlocal byte_count, victim
        byte_count = ln
        victim = buf
        while not action():
            pass
        return ln - byte_count

    def flush_buffer(bufv, ln):
        nonlocal state, message
        buf = bufv
        if message:
            return -1
        written = write_buffer(buf, ln)
        while written < ln and not message:
            c = ref[buf + written]
            if c == ord('0'):
                buf += written
                ln -= written
                state = S_START
            elif c == 0:
                buf += written
                ln -= written
                state = S_RESET
            else:
                message = 'junk within compressed archive'
            if not message:
                written = write_buffer(buf, ln)
        return ln

    off = 0
    while not message and off < len(ref):
        flush_buffer(off, min(CHUNK, len(ref) - off))
        off += CHUNK

    return results, state, byte_count, this_header, message


def main() -> int:
    ref = load_ref()
    print(f'reference stream: {len(ref):,} bytes')

    elf = ELFLoader(ELF)
    ram_base = min((s['vaddr'] for s in elf.segments if s['type'] == ELFLoader.PT_LOAD), default=0)
    print(f'ELF entry 0x{elf.entry_point:x}, ram_base 0x{ram_base:x}')

    core = SpatialRV64ICore(memory_size_bytes=64 * 1024 * 1024)
    core.load_program(b'', entry_point=elf.entry_point, ram_base=ram_base)
    for seg in elf.segments:
        if seg['type'] != ELFLoader.PT_LOAD or seg['filesz'] == 0:
            continue
        data = elf.data[seg['offset']:seg['offset'] + seg['filesz']]
        core.write_mem_bytes(seg['vaddr'] - ram_base, data)
    core.write_mem_bytes(INPUT_ADDR - ram_base, ref)
    print('harness loaded, stream written')

    t0 = time.time()
    total = 0
    while total < MAX_STEPS:
        core.step(POLL_EVERY)
        total += POLL_EVERY
        core.get_state()
        m0 = core.read_mem_word(MARKER_ADDR - ram_base)
        if m0 == MARKER_MAGIC:
            break
        if m0 != 0 and m0 & 0xBAD00000 == 0xBAD00000:
            print(f'HARNESS FAILED code 0x{m0:x} at {total:,} steps')
            return 1
    dt = time.time() - t0
    print(f'{total:,} steps in {dt:.1f}s ({total / dt:,.0f} steps/s)')

    m0 = core.read_mem_word(MARKER_ADDR - ram_base)
    if m0 != MARKER_MAGIC:
        print(f'marker not set (0x{m0:x})')
        return 1
    n = core.read_mem_word(MARKER_ADDR - ram_base + 8)
    state = core.read_mem_word(MARKER_ADDR - ram_base + 16)
    bc = core.read_mem_word(MARKER_ADDR - ram_base + 24)
    th = core.read_mem_word(MARKER_ADDR - ram_base + 32)
    msg = core.read_mem_word(MARKER_ADDR - ram_base + 40)
    tfb = core.read_mem_word(MARKER_ADDR - ram_base + 48)
    print(f'n_results={n} state={state} byte_count={bc} this_header={th} '
          f'message_ptr={msg:#x} total_file_bytes={tfb}')

    core.step(1)
    import numpy as np
    buf = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(buf, dtype=np.uint32)
    linear = spatial[core.hilbert_lut_np]
    off = RESULTS_ADDR - ram_base
    n_words = n * 2
    raw = linear[off // 4:off // 4 + n_words]
    got = [(int(raw[i]) | (int(raw[i + 1]) << 32)) for i in range(0, n_words, 2)]

    exp, exp_state, exp_bc, exp_th, exp_msg = simulate(ref)
    print(f'expected: {len(exp)} results, final state={exp_state} bc={exp_bc} '
          f'this_header={exp_th} message={exp_msg}')

    ndiff = 0
    for i in range(min(len(got), len(exp))):
        if got[i] != exp[i]:
            ndiff += 1
            if ndiff <= 15:
                print(f'  DIVERGE at boundary {i}: emu this_header={got[i]} '
                      f'exp={exp[i]} (delta {got[i] - exp[i]})')
    if len(got) != len(exp):
        print(f'  COUNT: emu {len(got)} vs exp {len(exp)}')
    print(f'{ndiff} divergent boundaries of {min(len(got), len(exp))} compared')
    if ndiff == 0 and len(got) == len(exp):
        print('FSM MATCHES — parser state machine is correct on the emulator')
        return 0
    print('FSM DIVERGES — parser mis-executes; see boundary deltas above')
    return 1


if __name__ == '__main__':
    sys.exit(main())
