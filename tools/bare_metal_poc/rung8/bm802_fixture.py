#!/usr/bin/env python3
"""BM802 fixture rig: build a pixel medium that carries ONE corrupted payload
byte and still passes the guest's CRC32 gate, so kernel sensitivity becomes
observable at all.

Why this file exists (the finding recorded in the ROADMAP's BM802 cell): with
BM903's gate as shipped, a single flipped payload byte anywhere is refused
before a handoff exists -- so a fault-sensitivity sweep over that medium can
only ever measure "the gate works", which L6 already proved. Every offset
classifies SENSITIVE and the map is vacuous.

The fixture is rung-5's non-vacuity pattern, applied to the medium instead of
the gate script: the loader's EXPECTED_CRC is re-baked to the CRC the corrupted
payload actually computes, so
  * the guest's CRC32 check is still a REAL check (it computes over 13.6 MB and
    compares), it has simply been told a different truth;
  * the loader text, the codec, the geometry and every other byte are the
    committed ones -- rung9/ is read-only input here, nothing is edited in
    place; the rig is assembled in a scratch dir;
  * build_fixture(None) must reproduce rung9/bm903_medium_px.raw byte for byte,
    which is the leg that proves the fixture rig and the committed rig differ
    ONLY in that constant.

  usage (library):  from bm802_fixture import Rig; r = Rig(); r.build(off, med, stage2_bin)
  usage (selftest): python3 bm802_fixture.py            # 3 legs, exit 0
"""
import hashlib
import json
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
COMMITTED = RUNG9 / 'bm903_medium_px.raw'
RIG = Path('/tmp/bm802_rig')
# copied verbatim out of rung9 except for the one constant rewritten per sample
RIG_FILES = ['bm903_stage1.asm', 'bm903_stage2_px.asm', 'bm903_layout.inc',
             'bm903_px_layout.inc', 'bm903_crc32tab.inc', 'bm903_cmdline.inc',
             'bm903_e820.inc', 'bm903_layout.json']
# What assembling rung9's verbatim stage1.asm has to give: the sha256 of
# rung9/bm903_stage1.bin, hashed 2026-09-20 off the file this tree's rung9
# wrote on 2026-09-19. This
# row assembles stage1 itself, so the number is a check on this rig's own bytes,
# not a read of someone else's working file. It replaces
# `if (RUNG9/'bm903_stage1.bin').exists(): assert s1 == ...`, which compared
# against a build output nothing tracks -- in a clean checkout the guard was
# false and the comparison quietly stopped existing (ROADMAP TASK_BM001, the
# ancestor-reference class BM653 found). A nasm or flag change goes RED here,
# which is the same failure that comparison was for.
STAGE1_SHA = 'f0e7d7e1c6ab4536852d3c7de33b5e4136db647d6d46d00019a1bec13d991c7b'

sys.path.insert(0, str(RUNG9))
import bm903_pxcodec as codec          # noqa: E402  (rung9 is read-only input)

CLEAN_CRC = re.search(r'%define EXPECTED_CRC (0x[0-9A-F]+)',
                      (RUNG9 / 'bm903_px_layout.inc').read_text())

# The fault primitive: a single medium byte, altered by a fixed nonzero XOR, so
# every sample in the map is the same size of hole in a different place. 0xA5
# is a 3-bit flip -- a pit/land error, not a bit-flip -- and the sweep spot-
# checks XOR 0x01 against it so the map does not quietly assume multi-bit damage.
FAULT = 0xA5


class Rig:
    """Holds the clean payload once; each build() flips one byte and rebuilds."""

    def __init__(self, quiet=True):
        RIG.mkdir(parents=True, exist_ok=True)
        for f in RIG_FILES:
            (RIG / f).write_bytes((RUNG9 / f).read_bytes())
        self.inc = RIG / 'bm903_px_layout.inc'
        self.inc_text = self.inc.read_text()
        self.consts = {m.group(1): int(m.group(2), 0) for m in re.finditer(
            r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$', self.inc_text, re.M)}
        self.base = self.consts['PX_BASE_LBA']
        self.band_bytes = self.base * 512          # stage1 + stage2 image
        self.payload, _, self.initrd_len, self.pm_len = codec.build_payload()
        self.clean_crc = zlib.crc32(self.payload) & 0xFFFFFFFF
        assert f'0x{self.clean_crc:08X}' == CLEAN_CRC.group(1), \
            'the committed gate constant is not this payload\'s CRC'
        # region table straight out of the layout .inc the loader reads
        gb = self.consts['PX_GROUP_BYTES']
        subs = [(self.consts[f'SUB{i}_GROUP'], self.consts[f'SUB{i}_NGROUPS'],
                 self.consts[f'SUB{i}_DEST']) for i in range(3)]
        self.subs = [(a * gb, n * gb, d) for a, n, d in subs]
        self.n_groups = self.consts['PX_GROUPS']

    # -- one sample -------------------------------------------------------
    def build(self, offset, med_path, rebake=True, fault=FAULT):
        """Corrupt payload byte `offset` (None = clean control) and write the
        medium. `rebake=False` keeps the COMMITTED gate constant, so the guest
        is told the real truth about the corrupted stream -- that is the clean
        loader, and the boot-side non-vacuity leg needs it.
        """
        payload = bytearray(self.payload)
        if offset is not None:
            old = payload[offset]
            payload[offset] ^= fault                 # deterministic, nonzero
            assert payload[offset] != old
        crc = zlib.crc32(payload) & 0xFFFFFFFF if rebake else self.clean_crc
        self.inc.write_text(re.sub(r'^%define EXPECTED_CRC .*$',
                                   f'%define EXPECTED_CRC 0x{crc:08X}',
                                   self.inc_text, flags=re.M))
        for src, dst in (('bm903_stage1.asm', 'bm802_stage1.bin'),
                         ('bm903_stage2_px.asm', 'bm802_stage2_px.bin')):
            r = subprocess.run(['nasm', '-f', 'bin', '-o', str(RIG / dst),
                                '-I', str(RIG) + '/', str(RIG / src)],
                               capture_output=True, text=True)
            if r.returncode or r.stderr.strip():
                raise SystemExit(f'nasm {src} failed/warned:\n{r.stderr}')
        s1 = (RIG / 'bm802_stage1.bin').read_bytes()
        s2 = (RIG / 'bm802_stage2_px.bin').read_bytes()
        h = hashlib.sha256(s1).hexdigest()
        assert h == STAGE1_SHA, \
            f'fixture stage1 sha256 {h} != the pinned {STAGE1_SHA}'
        med = codec.encode(s1, s2, bytes(payload), self.base)
        # the fixture must still decode to what we claim, or the sweep is
        # measuring an addressing bug instead of kernel sensitivity
        back = codec.decode(med, self.base, len(payload))
        assert back == bytes(payload), 'fixture codec round-trip broken'
        assert zlib.crc32(back) & 0xFFFFFFFF == zlib.crc32(payload) & 0xFFFFFFFF
        return self.write(med_path, med, {
            'offset': offset, 'mode': 'payload', 'rebake': rebake,
            'crc': crc, 'bytes': len(med)})

    def build_band(self, med_offset, med_path, fault=FAULT):
        """XOR one RAW medium byte inside the loader band (bytes
        [0, PX_BASE_LBA*512) = stage1 + the stage2 image). The payload and the
        gate constant are untouched -- a band fault cannot change a CRC computed
        over the payload, so no rebake is involved and the committed loader is
        used verbatim. This is the other half of the fault model: the medium can
        decay anywhere, not only where the payload lives."""
        med = bytearray(self.control())
        assert med_offset < self.band_bytes, 'that is a payload byte, use build()'
        assert fault, 'a zero fault is not a fault'
        med[med_offset] ^= fault
        med = bytes(med)
        assert sum(a != b for a, b in zip(med, self.control())) == 1
        return self.write(med_path, med, {
            'offset': med_offset, 'mode': 'band', 'rebake': False,
            'crc': self.clean_crc, 'bytes': len(med)})

    def control(self):
        """The fixture's own byte-for-byte replica of the committed medium,
        built once and held in memory so band samples differ from it exactly."""
        if not hasattr(self, '_control'):
            self.build(None, RIG / 'bm903_bm802_control.raw')
            got = (RIG / 'bm903_bm802_control.raw').read_bytes()
            assert got == COMMITTED.read_bytes(), 'control fixture != committed medium'
            self._control = got
        return self._control

    def write(self, med_path, med, facts):
        Path(med_path).write_bytes(med)
        facts['medium'] = str(med_path)
        return facts

    # -- where the corruption lands ---------------------------------------
    def region(self, offset):
        for start, length, dst in self.subs:
            if start <= offset < start + length:
                return f'{dst:#x}+{offset - start:#x}', dst
        return 'filler', 0


def selftest():
    r = Rig()
    nfail = 0

    def leg(name, ok, detail):
        nonlocal nfail
        nfail += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}: {detail}")

    # 1. the rig reproduces the committed medium exactly
    med = '/tmp/bm802_rig/control.raw'
    r.build(None, med)
    a = Path(med).read_bytes()
    b = COMMITTED.read_bytes()
    leg('rig equivalence', a == b,
        f'control fixture == rung9/{COMMITTED.name} byte for byte '
        f'({len(a):,} B) -- the only difference downstream is the constant')

    # 2. a flipped payload byte changes exactly ONE medium byte in the payload
    #    region, at the plane the PXC1 mapping predicts -- plus, in the stage2
    #    band, the bytes of the re-baked constant. The 8 band bytes were not
    #    expected when this leg was written; the RED said so first-hand, and the
    #    leg now asserts the two populations separately instead of "1 byte".
    off = 4_000_000
    fx = r.build(off, '/tmp/bm802_rig/flip.raw')
    c = Path('/tmp/bm802_rig/flip.raw').read_bytes()
    A = np.frombuffer(a, np.uint8)
    B = np.frombuffer(c, np.uint8)
    diff = np.flatnonzero(A != B)
    plane, in_plane = off % 4, off // 4
    plane_bytes = (len(a) - r.base * 512) // 4
    want = r.base * 512 + plane * plane_bytes + in_plane
    band_hi = 512 + 16 * 512                      # MBR + stage2_sectors
    payload_hits = [int(x) for x in diff if x >= band_hi]
    band_hits = {int(x) for x in diff if x < band_hi}
    # every band difference must belong to an occurrence of the old gate
    # constant, and land on the same byte index of the new one
    old_le, new_le = struct.pack('<I', r.clean_crc), struct.pack('<I', fx['crc'])
    starts, owners = [], set()
    pos = a.find(old_le)
    while pos >= 0:
        starts.append(pos)
        owners |= set(range(pos, pos + 4))
        pos = a.find(old_le, pos + 1)
    exact = bool(band_hits)
    for x in sorted(band_hits):
        s = max(st for st in starts if st <= x <= st + 3)  # which occurrence
        if A[x] != old_le[x - s] or B[x] != new_le[x - s]:
            exact = False
            break
    leg('one payload byte -> one medium byte',
        payload_hits == [want] and exact and old_le != new_le,
        f'payload {off} -> medium byte {want} (plane {plane}); payload region: '
        f'{len(payload_hits)} byte(s) changed; stage2 band: '
        f'{len(band_hits)} byte(s), all inside the '
        f'{len(starts)} occurrence(s) of the little-endian gate constant '
        f'{old_le.hex()} -> {new_le.hex()}')

    # 3. non-vacuity: the committed (clean-CRC) loader must still REFUSE the
    #    flipped medium -- the fixture is a different truth, not a disabled
    #    check. Host-side arithmetic here; the boot-side proof is the sweep's
    #    N-V leg, which boots the flipped medium under the clean loader.
    flipped_crc = fx['crc']
    leg('gate still a gate', flipped_crc != r.clean_crc,
        f'flipped payload computes {flipped_crc:08X}, committed constant '
        f'{r.clean_crc:08X}: the clean loader refuses it (BM903 L6), the '
        f'fixture loader is merely told the new truth')

    # 4. band mode: one raw medium byte in the loader, payload untouched. The
    #    gate cannot help here -- it checksums the payload, so a decaying loader
    #    is a fault the design does not see at all. That is why the map samples
    #    the band separately.
    boff = 512 + 2048
    bx = r.build_band(boff, '/tmp/bm802_rig/band.raw')
    D = Path('/tmp/bm802_rig/band.raw').read_bytes()
    hits = [int(x) for x in np.flatnonzero(A != np.frombuffer(D, np.uint8))]
    band_hi = r.band_bytes
    leg('band fault is one medium byte', hits == [boff] and bx['crc'] == r.clean_crc,
        f'medium byte {boff} (stage2 image offset {boff - 512}) is the only '
        f'difference from the control; the payload CRC still reads '
        f'{bx["crc"]:08X}, so the gate passes a broken loader -- the band needs '
        f'its own sensitivity numbers')

    # 5. rebake=False really is the committed loader: same first bytes, wrong
    #    truth for a flipped payload byte -> the guest must refuse.
    r.build(6_000_000, '/tmp/bm802_rig/cleanloader.raw', rebake=False)
    E = Path('/tmp/bm802_rig/cleanloader.raw').read_bytes()
    flipped = codec.decode(E, r.base, len(r.payload))
    leg('rebake=False ships the committed gate',
        E[:band_hi] == a[:band_hi] and (zlib.crc32(flipped) & 0xFFFFFFFF) != r.clean_crc,
        f'band byte-identical to the control ({band_hi} B) and the payload it '
        f'will checksum computes {zlib.crc32(flipped) & 0xFFFFFFFF:08X} against '
        f'a baked {r.clean_crc:08X}: the guest refuses (the sweep boots this leg)')

    print(f'\nBM802 FIXTURE TALLY: {nfail} red')
    return 0 if nfail == 0 else 1


if __name__ == '__main__':
    sys.exit(selftest())
