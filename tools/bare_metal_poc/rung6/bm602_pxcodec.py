#!/usr/bin/env python3
"""BM602 (Rung 6): the PXC2-E medium -- PXC1's payload plus three parity planes.

Same payload, same interleave, same destinations: rung-9's codec is IMPORTED
and called, not copied, so "the ECC medium carries the bytes the proven medium
carries" is true by construction rather than by two files agreeing. What changes
is the medium: four data planes become seven, because Hamming(7,4) over BYTE
symbols treats one codeword as the four planes at one in-plane offset:

    payload byte i -> medium byte PX_BASE_LBA*512 + (i%4)*PLANE + i//4
    => the symbols of codeword x are (PB0[x], PB1[x], PB2[x], PB3[x])
    => p1 = d0^d1^d3, p2 = d0^d2^d3, p4 = d1^d2^d3, stored at planes 4/5/6

Linear over GF(2), so a single-byte fault makes its syndrome EQUAL the fault
value -- that is why the corrector needs no GF(256) multiply and no table, and
why "locate by the nonzero pattern of (s1,s2,s4), fix by XOR with any covering
syndrome" is the whole algorithm.

Parity is derived and never CRC'd: the guest's CRC32 gate keeps running over
the 13,631,488 DECODED, CORRECTED payload bytes exactly as in BM903. The
corrector has no uncorrectable verdict at all -- the (s1,s2,s4) nonzero pattern
always names some symbol -- so a two-symbol codeword is confidently mis-fixed
and the gate is what refuses it. That is leg G of BM601_ECC_SCOPING.md, and
selftest() below pins it as an expectation rather than a discovery. The class
below leg G is quieter: three equal faults leave all three syndromes ZERO, so
the corrector reports an undamaged codeword and prints ECC=0 on damaged bytes.
Both are the gate's job, which is why the corrector sits between the read and
the CRC and never in front of it.

  usage: python3 bm602_pxcodec.py     # payload + planes + layout .inc, no boots
"""
import hashlib
import json
import operator
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
sys.path.insert(0, str(RUNG9))
import bm903_pxcodec as pxc1                                # noqa: E402

SECTOR = pxc1.SECTOR
BASE_LBA = 1 + 16                                # stage1 + 16 sectors of band
DATA_PLANES, PARITY_PLANES = pxc1.PLANES, 3
PLANES = DATA_PLANES + PARITY_PLANES
CONTAINER = 'PXC2-E'
TAG = 0x32435850       # the four bytes 'P','X','C','2', low to high: dd'd into the MBR
TAG_OFF = 0x180          # MBR reserved band: past this stage1's code, clear of the 0x1BE DPT
SUB_NAMES = ['kernel setup+header', 'kernel pm payload', 'initrd']


def xor(a, b):
    return bytes(map(operator.xor, a, b))


def split(payload):
    """The four data planes: pxc1.encode's own arithmetic, payload[p::4]."""
    return [bytes(payload[p::DATA_PLANES]) for p in range(DATA_PLANES)]


def parity(d):
    """(p1, p2, p4) as whole planes, from the scoping note's three formulas."""
    d0, d1, d2, d3 = d
    return [xor(xor(d0, d1), d3), xor(xor(d0, d2), d3), xor(xor(d1, d2), d3)]


def encode(stage1, stage2, payload, base_lba=BASE_LBA):
    d = split(payload)
    planes = d + parity(d)
    plane = len(planes[0])
    med = bytearray((base_lba + PLANES * (plane // SECTOR)) * SECTOR)
    med[0:len(stage1)] = stage1
    med[SECTOR:SECTOR + len(stage2)] = stage2
    for p, blob in enumerate(planes):
        start = base_lba * SECTOR + p * plane
        med[start:start + len(blob)] = blob
    return bytes(med)


def read_planes(med, base_lba=BASE_LBA):
    """All seven planes, in plane order."""
    plane = (len(med) // SECTOR - base_lba) // PLANES * SECTOR
    return [bytes(med[base_lba * SECTOR + p * plane:
                     base_lba * SECTOR + (p + 1) * plane]) for p in range(PLANES)]


def join(d):
    out = bytearray(len(d[0]) * DATA_PLANES)
    for p, blob in enumerate(d):
        out[p::DATA_PLANES] = blob
    return bytes(out)


def locate(s1, s2, s4):
    """Which symbol the (non)zero pattern names: 0-3 = a data symbol,
    4/5/6 = a parity plane, None = the codeword reads clean."""
    pattern = (s1 != 0) + 2 * (s2 != 0) + 4 * (s4 != 0)
    return {3: 0, 5: 1, 6: 2, 7: 3, 1: 4, 2: 5, 4: 6}.get(pattern)


def correct(d, pp):
    """Host mirror of the loader's pass 1, case for case. Returns
    (corrected data planes, data symbols fixed, parity-only faults)."""
    d = [bytearray(b) for b in d]
    p1, p2, p4 = pp
    fixed = par = 0
    for x in range(len(d[0])):
        s1 = p1[x] ^ d[0][x] ^ d[1][x] ^ d[3][x]
        s2 = p2[x] ^ d[0][x] ^ d[2][x] ^ d[3][x]
        s4 = p4[x] ^ d[1][x] ^ d[2][x] ^ d[3][x]
        sym = locate(s1, s2, s4)
        if sym is None:
            continue
        if sym < DATA_PLANES:
            d[sym][x] ^= s1 if sym != 2 else s2
            fixed += 1
        else:
            par += 1
    return [bytes(b) for b in d], fixed, par


def selftest(payload):
    """The corrector against the codec's own definition: every single-symbol
    class in a codeword, plus the two-symbol class the code cannot see. The
    two-symbol row is the one that matters -- it must come back confidently
    WRONG, which is what makes the CRC gate load-bearing rather than
    decorative."""
    d = split(payload)
    x0 = 12345
    cases = [('clean', [], (0, 0), True),
             ('d0', [0], (1, 0), True), ('d1', [1], (1, 0), True),
             ('d2', [2], (1, 0), True), ('d3', [3], (1, 0), True),
             ('p1', [4], (0, 1), True), ('p2', [5], (0, 1), True),
             ('p4', [6], (0, 1), True),
             ('two symbols in one codeword', [0, 1], (1, 0), False),
             # The blind spot, and it is quieter than leg G's mis-fix. With the
             # SAME value in d0, d1, d2 and nothing in d3: s1=f0^f1^f3=0,
             # s2=f0^f2^f3=0, s4=f1^f2^f3=0. Three payload bytes are wrong and
             # the corrector reports a clean codeword -- ECC=0, PAR=0, exactly
             # what an undamaged medium prints. Only the CRC gate can see this
             # class, which is why ECC sits after the read and never in front
             # of the gate. bm602_mkimg.py makes a boot leg of it.
             ('d0=d1=d2 equal faults: all syndromes zero', [0, 1, 2],
              (0, 0), False)]
    for name, symbols, want, restores in cases:
        planes = [bytearray(b) for b in d] + [bytearray(b) for b in parity(d)]
        for s in symbols:
            planes[s][x0] ^= 0xA5
        got, fixed, par = correct([bytes(b) for b in planes[:4]],
                                 [bytes(b) for b in planes[4:]])
        if (fixed, par) != want:
            raise AssertionError(f'{name}: counted {(fixed, par)}, want {want}')
        same = join(got) == join(d)
        if same != restores:
            raise AssertionError(
                f'{name}: payload restored={same}, expected {restores}')
    return (f'{len(cases)} codeword classes pinned: single-symbol faults fixed, '
            'a two-symbol codeword confidently mis-fixed, and the equal-triple '
            'fault reported as clean -- the last two for the gate to catch')


def main() -> int:
    payload, table, initrd_len, pm_len = pxc1.build_payload()
    d = split(payload)
    plane = len(d[0])
    ngroups = len(payload) // pxc1.GROUP_BYTES
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    assert plane % pxc1.CHUNK_BYTES == 0, 'a plane is not a whole number of chunks'
    assert plane % SECTOR == 0, 'a plane is not a whole number of sectors'
    assert len(payload) % pxc1.BANK_BYTES == 0, 'payload is not whole banks'

    med = encode(b'\x00' * SECTOR, b'', payload)
    assert len(med) == (BASE_LBA + PLANES * (plane // SECTOR)) * SECTOR
    rp = read_planes(med)
    assert join(rp[:4]) == payload, 'seven-plane round-trip BROKEN'
    assert correct(rp[:4], rp[4:]) == (rp[:4], 0, 0), \
        'the corrector changed a CLEAN medium'
    covered = selftest(payload)
    # The claim worth making is not that this payload equals a fresh
    # re-derivation of itself, but that it equals the bytes the LANDED PXC1
    # medium carries -- the ones BM903's 42-leg gate booted byte-identical.
    landed = RUNG9 / 'bm903_px_payload.bin'
    assert landed.exists(), f'{landed.name} missing: nothing to be identical to'
    pxc1_blob = landed.read_bytes()
    assert pxc1_blob == payload, \
        f'the ECC payload differs from the landed PXC1 payload ' \
        f'({len(pxc1_blob):,} B vs {len(payload):,} B) -- a sub-image changed ' \
        'under both codecs, so this row is not measuring the same medium'
    pxc1_sha = hashlib.sha256(pxc1_blob).hexdigest()

    (HERE / 'bm602_px_payload.bin').write_bytes(payload)
    (HERE / 'bm602_px_meta.json').write_text(json.dumps({
        'convention': f'{CONTAINER} (PXC1 four-plane interleave + 3 parity planes)',
        'container_tag': hex(TAG), 'planes': PLANES, 'data_planes': DATA_PLANES,
        'parity_planes': PARITY_PLANES, 'base_lba': BASE_LBA, 'sector': SECTOR,
        'chunk_sectors': pxc1.CHUNK_BYTES // SECTOR,
        'group_bytes': pxc1.GROUP_BYTES, 'payload_len': len(payload),
        'groups': ngroups, 'plane_bytes': plane, 'plane_sectors': plane // SECTOR,
        'medium_sectors': len(med) // SECTOR, 'medium_bytes': len(med),
        'parity_bytes': plane * PARITY_PLANES,
        'capacity_over_payload': f'{plane * PARITY_PLANES / len(payload):.1%}',
        'reads_per_group': PLANES,
        'subimages': [{'start_group': g, 'groups': n, 'dst': hex(dst),
                       'src': name} for (g, n, dst), name in zip(table, SUB_NAMES)],
        'payload_crc32': f'{crc:08X}',
        'payload_sha256': hashlib.sha256(payload).hexdigest(),
        'pxc1_payload_sha256': pxc1_sha,
        'same_payload_as_the_landed_pxc1_medium': payload == pxc1_blob,
        'corrector_selftest': covered,
    }, indent=1) + '\n')

    rows = [f'%define SUB{i}_GROUP {g}\n%define SUB{i}_NGROUPS {n}\n'
            f'%define SUB{i}_DEST {hex(dst)}'
            for i, (g, n, dst) in enumerate(table)]
    (HERE / 'bm602_px_layout.inc').write_text(
        '; generated by bm602_pxcodec.py -- DO NOT EDIT\n'
        f'%define PX_CONTAINER {TAG}\n'
        f'%define PX_TAG_OFF {TAG_OFF}\n'
        f'%define PX_BASE_LBA {BASE_LBA}\n'
        f'%define PX_PLANE_SECTORS {plane // SECTOR}\n'
        f'%define PX_CHUNK_SECTORS {pxc1.CHUNK_BYTES // SECTOR}\n'
        f'%define PX_GROUP_BYTES {pxc1.GROUP_BYTES}\n'
        f'%define PX_GROUPS {ngroups}\n'
        f'%define PX_PLANES {PLANES}\n'
        f'%define PX_PAYLOAD_BYTES {len(payload)}\n'
        '%define PB0 0x30000\n%define PB1 0x31000\n'
        '%define PB2 0x32000\n%define PB3 0x33000\n'
        '%define PP1 0x38000\n%define PP2 0x39000\n%define PP4 0x3A000\n'
        f'%define PX_SINK {hex(pxc1.SINK)}\n'
        f'%define PX_SUBIMAGE_COUNT {len(table)}\n'
        + '\n'.join(rows) + '\n'
        f'%define EXPECTED_CRC 0x{crc:08X}\n'
        f'%define INITRD_BYTES {initrd_len}\n'
        f'%define HDR_SCRATCH {hex(pxc1.HDR_SCRATCH)}\n')
    print(f'{CONTAINER}: payload {len(payload):,} B / {ngroups} groups identical '
          f'to PXC1 (sha256 {hashlib.sha256(payload).hexdigest()[:12]}), '
          f'{PLANES} planes x {plane:,} B = medium {len(med) // SECTOR:,} sectors '
          f'= {len(med) / 1e6:.2f} MB (+{plane * PARITY_PLANES / len(payload):.0%} '
          f'parity, {PLANES} reads per group), CRC={crc:08X}')
    print(f'corrector selftest: {covered}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
