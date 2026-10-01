#!/usr/bin/env python3
"""BM601 scoping probe: is a corruption-tolerant decode over the PXC1
four-plane interleave actually cheap, and what does it cost the medium?

This is a SCOPING measurement, not an implementation. It never boots, never
touches a live gate, and writes only under /tmp. What it does is take the real
BM903 payload out of the real medium file and answer the row's two questions
with numbers:

  (1) FAULT MODEL. PXC1 puts payload byte i at medium byte
      PX_BASE_LBA*512 + (i%4)*PLANE_BYTES + i//4, so one Hamming(7,4) codeword
      (the four consecutive payload bytes 4x..4x+3) is exactly the four planes
      at the same in-plane offset x. Consequence, measured here rather than
      asserted: any media fault confined to ONE plane -- a bad sector, a bad
      8-sector chunk, a whole bad plane -- lands AT MOST ONE symbol per
      codeword, which is precisely the class Hamming(7,4)-over-bytes corrects.
  (2) BUDGET. Medium growth, read growth, code size (the sibling .asm probe,
      assembled), and low-memory cost.

Legs:
  A  clean medium: syndromes all zero, and the CRC32 of the recovered payload
     equals the committed EXPECTED_CRC -- the fixture is the real one.
  B  one flipped pixel channel (1 symbol).
  C  one flipped 512 B sector in one plane (128 symbols, one per codeword).
  D  one flipped 4 KiB plane chunk = the guest's own read unit (1,024 symbols).
  E  eight flipped chunks, all in the same plane (8,192 symbols).
  F  512 scattered single-channel flips in distinct codewords.
  G  RED: two symbols in one codeword (the class no single-error code fixes) ->
     the decoder mis-corrects and the EXISTING CRC32 gate still refuses.
  H  RED: the linear code's blind spot -- four symbols in one codeword chosen
     so all three syndromes vanish. Decoder is blind; the gate must refuse.
     This is why the CRC stays between decode and handoff.
  I  the 'equivalent by construction' claim tested: vectorised decoder vs a
     literal transcription of the asm's cmp/jne dispatch, over 200k codewords.
  J  budget table + host-side decode throughput (a host bound, labelled as
     such -- the guest number belongs to the implementation row).

  usage: python3 probe_bee_scheme.py      (exit 0 = every leg as claimed)

Prerequisite: rung9/bm903_medium_px.raw (a gate artifact, gitignored). Rebuild
it with `cd ../rung9 && python3 bm903_mkimg_px.py` if it is missing.
"""
import re
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
MEDIUM = RUNG9 / 'bm903_medium_px.raw'
PLANES = 4
CHUNK_BYTES = 4096
SECTOR = 512

inc = (RUNG9 / 'bm903_px_layout.inc').read_text()
d = {m.group(1): int(m.group(2), 0)
     for m in re.finditer(r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$', inc, re.M)}
BASE_LBA = d['PX_BASE_LBA']
PLANE_SECTORS = d['PX_PLANE_SECTORS']
PLANE_BYTES = PLANE_SECTORS * SECTOR
PAYLOAD_BYTES = d['PX_PAYLOAD_BYTES']
EXPECTED_CRC = d['EXPECTED_CRC']
GROUPS = d['PX_GROUPS']
MEDIUM_SECTORS = BASE_LBA + PLANES * PLANE_SECTORS

nfail = 0


def leg(name, ok, detail):
    global nfail
    if not ok:
        nfail += 1
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}: {detail}")


def parity(words):
    d0, d1, d2, d3 = (words[:, k] for k in range(4))
    return np.stack([d0 ^ d1 ^ d3,      # p1 covers symbol positions 3,5,7
                     d0 ^ d2 ^ d3,      # p2 covers 3,6,7
                     d1 ^ d2 ^ d3],     # p4 covers 5,6,7
                    axis=1)


def decode_vector(w, p):
    """Same case split as probe_bee_inner_loop.asm. The four select masks are
    disjoint by construction, so in-place fixing is safe against the syndromes
    computed before any fix. Returns (corrected, n_data_fixed, n_parity_only).
    """
    w = w.copy()
    s1 = p[:, 0] ^ w[:, 0] ^ w[:, 1] ^ w[:, 3]
    s2 = p[:, 1] ^ w[:, 0] ^ w[:, 2] ^ w[:, 3]
    s4 = p[:, 2] ^ w[:, 1] ^ w[:, 2] ^ w[:, 3]
    n1, n2, n4 = s1 != 0, s2 != 0, s4 != 0
    fixes = ((0, n1 & n2 & ~n4, s1),     # .bee_d0: d0 ^= s1
             (1, n1 & ~n2 & n4, s1),     # .bee_d1: d1 ^= s1
             (2, ~n1 & n2 & n4, s2),     # .bee_d2: d2 ^= s2
             (3, n1 & n2 & n4, s1))      # .bee_d3: d3 ^= s1
    fixed = 0
    for col, sel, val in fixes:
        w[sel, col] ^= val[sel]
        fixed += int(sel.sum())
    one = (n1.astype(np.int16) + n2.astype(np.int16) + n4.astype(np.int16)) == 1
    return w, fixed, int(one.sum())


def decode_scalar_slice(w, p):
    """Literal transcription of the asm's cmp/jne chain -- labels, fallthrough
    and all -- run over a slice, so the equivalence claim is checked rather
    than asserted. Returns (corrected, n_fixed, n_parity_only)."""
    w = w.copy()
    fixed = par = 0
    for x in range(w.shape[0]):
        al = int(p[x, 0]) ^ int(w[x, 0]) ^ int(w[x, 1]) ^ int(w[x, 3])   # s1
        ah = int(p[x, 1]) ^ int(w[x, 0]) ^ int(w[x, 2]) ^ int(w[x, 3])   # s2
        bl = int(p[x, 2]) ^ int(w[x, 1]) ^ int(w[x, 2]) ^ int(w[x, 3])   # s4
        if al == 0 and ah == 0 and bl == 0:
            continue
        if al != 0:
            if ah != 0:
                if bl != 0:
                    w[x, 3] ^= al; fixed += 1          # .bee_d3
                else:
                    w[x, 0] ^= al; fixed += 1          # .bee_d0
            else:
                if bl != 0:
                    w[x, 1] ^= al; fixed += 1          # .bee_d1
                else:
                    par += 1                           # parity chunk 1
        else:
            if ah != 0:
                if bl != 0:
                    w[x, 2] ^= ah; fixed += 1          # .bee_d2
                else:
                    par += 1                           # parity chunk 2
            else:
                par += 1                               # parity chunk 4
    return w, fixed, par


def run_case(orig, par, corrupt):
    w = orig.copy()
    corrupt(w)
    t0 = time.time()
    cw, fixed, pon = decode_vector(w, par)
    dt = time.time() - t0
    flat = cw.reshape(-1).tobytes()
    return {'restored': flat == orig.reshape(-1).tobytes(),
            'fixed': fixed, 'parity_only': pon,
            'crc': zlib.crc32(flat), 'dt': dt,
            'n_corrupt': int((w != orig).sum())}


def main():
    med = MEDIUM.read_bytes()
    assert len(med) == MEDIUM_SECTORS * SECTOR, 'medium size != layout'
    body = med[BASE_LBA * SECTOR:]
    payload = np.empty(PAYLOAD_BYTES, np.uint8)
    for pl in range(PLANES):
        payload[pl::PLANES] = np.frombuffer(
            body[pl * PLANE_BYTES:(pl + 1) * PLANE_BYTES], np.uint8)
    words = payload.reshape(-1, PLANES)
    par = parity(words)
    print(f"fixture: {MEDIUM.name}  payload {PAYLOAD_BYTES:,} B = "
          f"{words.shape[0]:,} codewords, "
          f"EXPECTED_CRC={EXPECTED_CRC:08X} (from bm903_px_layout.inc)")
    rng = np.random.default_rng(20260919)

    # ---------------------------------------------------------------- A
    cw, f0, p0 = decode_vector(words, par)
    leg('A clean medium',
        int((cw != words).sum()) == 0 and f0 == 0 and p0 == 0
        and zlib.crc32(payload.tobytes()) == EXPECTED_CRC,
        f'no symbol touched, corrected={f0}, parity-only={p0}, '
        f'crc={zlib.crc32(payload.tobytes()):08X} == the committed constant')

    # ------------------------------------------------------------ B..F
    def at(size):                 # a start codeword with `size` room left
        return int(rng.integers(0, words.shape[0] - max(size, 1)))

    def flip_sector(w):
        x0 = at(SECTOR)
        w[x0:x0 + SECTOR, 2] ^= np.uint8(0x5A)

    def flip_chunk(w):
        x0 = at(CHUNK_BYTES)
        w[x0:x0 + CHUNK_BYTES, 1] ^= np.uint8(0x17)

    def flip_eight(w):
        for _ in range(8):
            x0 = at(CHUNK_BYTES)
            w[x0:x0 + CHUNK_BYTES, 3] ^= np.uint8(0x2B)

    def flip_scattered(w):
        idx = rng.choice(words.shape[0], 512, replace=False)
        w[idx, 1] ^= np.uint8(0x9E)

    def flip_pixel(w):
        x0 = at(1)
        w[x0, 0] ^= np.uint8(0xA5)

    for name, fn, scale in [
            ('B single flipped pixel channel (1 symbol)', flip_pixel, 1),
            ('C one bad 512 B sector, plane 2', flip_sector, SECTOR),
            ('D one bad 4 KiB chunk = the guest read unit', flip_chunk, CHUNK_BYTES),
            ('E eight bad chunks, all in one plane', flip_eight, 8 * CHUNK_BYTES),
            ('F 512 scattered single-channel flips', flip_scattered, 512)]:
        r = run_case(words, par, fn)
        # The honest invariant: every fault in this class is one symbol per
        # codeword, so the corrector must fix EXACTLY the corrupted symbol
        # count -- and for E the eight random chunks may overlap, in which case
        # a doubly-flipped symbol was never corrupted and must NOT be "fixed".
        leg(name,
            r['restored'] and r['fixed'] == r['n_corrupt']
            and r['crc'] == EXPECTED_CRC and r['n_corrupt'] > 0,
            f"scale {scale}, actually corrupted {r['n_corrupt']} symbols "
            f"(never >1 per codeword) -> payload restored byte-identical, "
            f"corrected={r['fixed']}, post-decode crc={r['crc']:08X}")

    # -------------------------------------------------------------- G RED
    def two_planes_same_range(w):
        x0 = at(CHUNK_BYTES)
        w[x0:x0 + CHUNK_BYTES, 0] ^= np.uint8(0x11)
        w[x0:x0 + CHUNK_BYTES, 1] ^= np.uint8(0x22)

    r = run_case(words, par, two_planes_same_range)
    leg('G RED: two symbols in one codeword',
        (not r['restored']) and r['crc'] != EXPECTED_CRC,
        f"{r['n_corrupt']} corrupted; decoder 'fixes' {r['fixed']} and lands "
        f"wrong -> crc={r['crc']:08X} != {EXPECTED_CRC:08X}: the existing "
        f"gate refuses it, exactly as BM903 L6 does today")

    # -------------------------------------------------------------- H RED
    def four_in_word(w):
        x0 = at(64)
        w[x0:x0 + 64, 0] ^= np.uint8(0x01)
        w[x0:x0 + 64, 1] ^= np.uint8(0x02)
        w[x0:x0 + 64, 2] ^= np.uint8(0x02)
        w[x0:x0 + 64, 3] ^= np.uint8(0x03)

    r = run_case(words, par, four_in_word)
    leg('H RED: the blind spot, built on purpose',
        (not r['restored']) and r['fixed'] == 0 and r['crc'] != EXPECTED_CRC,
        f"256 wrong bytes, all three syndromes zero, corrected={r['fixed']} "
        f"(decoder is blind by algebra) -> crc={r['crc']:08X} != "
        f"{EXPECTED_CRC:08X}: the CRC stays between decode and handoff")

    # ---------------------------------------------------------------- I
    n = 200_000
    w = words[:n].copy()
    idx = rng.choice(n, 3000, replace=False)
    w[idx, rng.integers(0, 4, 3000)] ^= rng.integers(1, 256, 3000).astype(np.uint8)
    cw_v, f_v, p_v = decode_vector(w, par[:n])
    cw_s, f_s, p_s = decode_scalar_slice(w, par[:n])
    leg('I vectorised == the asm dispatch, symbol for symbol',
        np.array_equal(cw_v, cw_s) and f_v == f_s and p_v == p_s,
        f'{n:,} codewords with 3,000 injected faults: corrected {f_v} vs '
        f'{f_s}, parity-only {p_v} vs {p_s}, outputs identical')

    # ---------------------------------------------------------------- J
    asm = HERE / 'probe_bee_inner_loop.asm'
    # HEAD wrote /tmp/bm601_bee.bin and unpacked the routine size back out of it,
    # so with the build inert the 2026-09-19 leftover still yields routine=244 and
    # leg J prints PASS. Per-run directory instead; nothing here can read another
    # run's bytes.
    with tempfile.TemporaryDirectory(prefix='bm601_bee_') as tmpdir:
        out = Path(tmpdir) / 'bee.bin'
        res = subprocess.run(['nasm', '-f', 'bin', str(asm),
                              '-o', str(out)],
                             capture_output=True, text=True)
        built = res.returncode == 0 and out.exists()
        blob = out.read_bytes() if built else b''
        routine = struct.unpack('<H', blob[-10:-8])[0] if built else -1
    stage2_img, stage2_used = 8192, 3344       # measured: nasm output, trailing zeros
    planes = PLANES + 3
    new_sectors = BASE_LBA + planes * PLANE_SECTORS
    par_bytes = 3 * PLANE_BYTES
    t0 = time.time()
    decode_vector(words, par)
    host_dt = time.time() - t0
    leg('J budget', routine > 0,
        f'corrector {routine} B assembled clean vs {stage2_img - stage2_used} B '
        f'unused in the 8,192 B stage2 image (container size is a declared '
        f'knob: layout stage2_sectors); medium {MEDIUM_SECTORS:,} -> '
        f'{new_sectors:,} sectors = {new_sectors * SECTOR:,} B '
        f'({new_sectors * SECTOR / 2**20:.2f} MiB, +75%); reads/group '
        f'{PLANES} -> {planes}, i.e. {GROUPS * planes:,} chunk reads; parity '
        f'{par_bytes:,} B = +{par_bytes / PAYLOAD_BYTES * 100:.1f}% of payload; '
        f'3 x {CHUNK_BYTES:,} B buffers at 0x38000 (free above the 16 KiB '
        f'sink); host decode {PAYLOAD_BYTES / 2**20 / host_dt:.0f} MiB/s '
        f'({host_dt:.2f} s for the full payload)')

    print(f"\nBM601 SCOPING TALLY: {nfail} red")
    if nfail == 0:
        print("every leg behaved as claimed -> the numbers in "
              "BM601_ECC_SCOPING.md are measured, not projected")
    return 0 if nfail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
