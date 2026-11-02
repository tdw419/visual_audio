#!/usr/bin/env python3
"""Measure the static basic-block length distribution of the real Alpine boot image.

Answers the receipt's open question with a zero-risk ceiling: in OpenSBI + the Alpine
kernel, how long are straight-line runs between control-flow instructions? If blocks
average 2-3 instructions, basic-block threading in the real emulator saves little
(fetch+interrupt+lookup overhead is paid almost every instruction anyway). If blocks
average 5+, threading removes most of that per-instruction overhead.

A block ends at ANY instruction that can redirect execution: branches (taken or not —
the fall-through is a new block), JAL/JALR, ECALL/EBREAK/MRET/SRET/WFI, and SFENCE.VMA
(semantically a pipeline drain; cheap to also treat as a block end).

Uses the same per-slot independent decode as decode_image(): every halfword slot is
decoded as a potential instruction start, and we walk forward from valid starts, so
embedded data regions can never misalign the walk of real code after them.
"""
import sys
import struct
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rv64i_decode import decode_instruction, expand_rvc, OP_INVALID

# Control-flow opcodes from rv64i_decode.py
BRANCH_OPS = set(range(9, 15))       # BEQ..BGEU
OP_JAL, OP_JALR = 71, 72
OP_ECALL, OP_EBREAK, OP_MRET, OP_SRET, OP_WFI, OP_SFENCE_VMA = range(74, 80)

CTL_OPS = set(BRANCH_OPS) | {OP_JAL, OP_JALR, OP_ECALL, OP_EBREAK, OP_MRET, OP_SRET, OP_WFI, OP_SFENCE_VMA}

OPENSBI_BIN = '/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin'
ALPINE_LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'


def load_alpine_parts():
    data = Path(ALPINE_LNX).read_bytes()
    assert data[0:4] == b'LNX\x00', 'not an LNX container'
    kernel_offset, kernel_size, initrd_size = struct.unpack('<III', data[4:16])
    kernel = data[kernel_offset:kernel_offset + kernel_size]
    return kernel


def walk_block_lengths(code: bytes):
    """Walk the code image linearly, decoding each instruction start.

    Returns (blocks, lengths, first_ctl_op_counts) where lengths is a Counter of
    block lengths (number of non-control-flow instructions before a control-flow op)
    and blocks is the total number of blocks found.
    """
    n = len(code)
    lengths = Counter()
    blocks = 0
    ctl_counts = Counter()
    i = 0
    while i + 1 < n:
        half0 = code[i] | (code[i + 1] << 8)
        if (half0 & 0x3) == 0x3:
            if i + 3 >= n:
                break
            half1 = code[i + 2] | (code[i + 3] << 8)
            instr = (half1 << 16) | half0
            length = 4
        else:
            instr = expand_rvc(half0)
            if instr == 0:
                # Not a valid RVC instruction start — skip 2 bytes and continue
                # (data region). Do not count as a block end.
                i += 2
                continue
            length = 2

        decoded = decode_instruction(instr)
        if decoded is None:
            # Unrecognized encoding — skip; likely data or a reserved encoding.
            i += length
            continue
        op, rd, rs1, rs2, imm, aux = decoded

        # Walk forward: count consecutive non-control-flow instructions.
        blk = 0
        while decoded is not None and op not in CTL_OPS:
            blk += 1
            i += length
            if i + 1 >= n:
                break
            half0 = code[i] | (code[i + 1] << 8)
            if (half0 & 0x3) == 0x3:
                if i + 3 >= n:
                    break
                half1 = code[i + 2] | (code[i + 3] << 8)
                instr = (half1 << 16) | half0
                length = 4
            else:
                instr = expand_rvc(half0)
                if instr == 0:
                    break
                length = 2
            decoded = decode_instruction(instr)
            if decoded is not None:
                op, rd, rs1, rs2, imm, aux = decoded

        # Block ends here (either a CTL op, invalid, or end of image).
        if decoded is not None and op in CTL_OPS:
            ctl_counts[op] += 1
            i += length  # consume the control-flow op; next block starts after it
        lengths[blk] += 1
        blocks += 1
    return blocks, lengths, ctl_counts


def summarize(name, blocks, lengths, ctl_counts):
    total_insts = sum(l * c for l, c in lengths.items())
    if blocks == 0:
        print(f'{name}: no blocks found')
        return
    avg = total_insts / blocks
    median_l = 1
    acc = 0
    for l in sorted(lengths):
        acc += lengths[l]
        if acc >= blocks // 2:
            median_l = l
            break
    pct_1 = 100.0 * lengths[1] / blocks
    pct_le4 = 100.0 * sum(lengths[l] for l in lengths if l <= 4) / blocks
    pct_ge8 = 100.0 * sum(lengths[l] for l in lengths if l >= 8) / blocks
    print(f'{name}: {blocks} blocks, {total_insts} instructions, avg block={avg:.2f}, '
          f'median={median_l}, len1={pct_1:.1f}%, len<=4={pct_le4:.1f}%, len>=8={pct_ge8:.1f}%')
    print(f'  control-flow breakdown: {dict(ctl_counts)}')
    top = lengths.most_common(10)
    print(f'  top lengths: {sorted(top, key=lambda x: -x[1])}')


def main():
    print(f'OpenSBI: {OPENSBI_BIN}')
    opensbi = Path(OPENSBI_BIN).read_bytes()
    blocks, lengths, ctl = walk_block_lengths(opensbi)
    summarize('OpenSBI fw_jump', blocks, lengths, ctl)

    print(f'\nAlpine kernel: {ALPINE_LNX}')
    kernel = load_alpine_parts()
    print(f'  kernel image: {len(kernel)} bytes')
    # The RISC-V kernel Image starts with a 64-byte header; code begins at offset 0x40
    # (the effective start is the same as load address; header magic at 0x0).
    blocks, lengths, ctl = walk_block_lengths(kernel[0x40:])
    summarize('Alpine kernel', blocks, lengths, ctl)


if __name__ == '__main__':
    main()
