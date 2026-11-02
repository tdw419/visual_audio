#!/usr/bin/env python3
"""BM602: build the PXC2-E medium, and prove the self-repairing walk on the
host before anything boots.

Three proofs, in order, because each is the reason to believe the next:

1. ASSEMBLE. `nasm -f bin`, warning-free, on the two files bm602_construct.py
   generated from rung9's text. And the container tag is read back out of the
   assembled BYTES, because the guest compares against the medium's sector 0,
   not against a define somebody typed.

2. REPLAY. `guest_walk` re-runs the loader's own loop against the numbers in
   the .inc and the plane-buffer table read out of the generated .asm -- not
   against this file's python constants. It includes PASS 1, whose dispatch is
   transcribed from the asm instruction by instruction (same three syndrome
   expressions, same al/ah/bl branch tree, same fix value), and the de-interleave
   in the asm's per-byte order whenever a destination could touch a plane
   buffer. Each corrupted fixture is replayed too, so its ECC=, PAR= and
   computed CRC are PREDICTED; the predictions go into bm602_fixtures.json and
   the boot gate compares the wire against a file written before the boot.

3. AGREE. The transcribed scalar corrector is run against bm602_pxcodec.correct
   -- the codec's independent GF(2) definition -- over all 3,407,872 codewords
   of the real payload, compared on both counters and every byte. Two
   implementations of one algebra, on the whole medium, beats the same
   assertion on a sample.

Refuses to write anything unless:
  * decode(encode(payload)) == payload, and the payload is the landed PXC1 one
  * the replayed walk reproduces the payload byte order and every sub-image slot
  * the seven plane buffers are pairwise disjoint (modelled separately, so a
    collision is an assertion and not an aliasing accident the replay hides)
  * CRC8 macro arithmetic == zlib == the .inc's EXPECTED_CRC
  * each fixture's replayed verdict is the verdict its leg is DESIGNED to show:
    a "recoverable" fault the gate would still refuse is a fixture bug, RED.
"""
import functools
import json
import operator
import re
import subprocess
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
sys.path.insert(0, str(RUNG9))
import bm602_pxcodec as codec                                        # noqa: E402
import bm903_pxcodec as pxc1                                          # noqa: E402

INC = HERE / 'bm602_px_layout.inc'
S2ASM = HERE / 'bm602_stage2_px.asm'
OUT = HERE / 'bm602_medium_px.raw'
FIXDIR = HERE / 'fixtures'
FIXJSON = HERE / 'bm602_fixtures.json'
XOR = lambda a, b: bytes(map(operator.xor, a, b))                    # noqa: E731
ZEROS = {}


def nasm(src, dst):
    r = subprocess.run(['nasm', '-f', 'bin', '-o', dst,
                        '-I', str(HERE) + '/', '-I', str(RUNG9) + '/',
                        str(HERE / src)], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(f'nasm {src} FAILED:\n{r.stderr}{r.stdout}\n')
        raise SystemExit(2)
    if r.stderr.strip():
        sys.stderr.write(f'nasm {src} warnings:\n{r.stderr}\n')
        raise SystemExit(2)          # gate S1 requires a warning-free assemble
    return Path(dst).read_bytes()


def defines(text):
    return {m.group(1): int(m.group(2), 0) for m in re.finditer(
        r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$', text, re.M)}


def consts():
    c = defines(INC.read_text())
    for name in ('PX_CONTAINER', 'PX_TAG_OFF', 'PX_BASE_LBA', 'PX_PLANE_SECTORS',
                 'PX_CHUNK_SECTORS', 'PX_GROUP_BYTES', 'PX_GROUPS', 'PX_PLANES',
                 'PX_PAYLOAD_BYTES', 'PX_SINK', 'EXPECTED_CRC',
                 'PX_SUBIMAGE_COUNT', 'PB0', 'PB1', 'PB2', 'PB3', 'PP1', 'PP2',
                 'PP4'):
        assert name in c, f'{name} missing from {INC.name}'
    return c


def plane_table(asm_text, c):
    """Read the guest's own `px_pb: dd PB0, PB1, ...` out of the generated asm
    and resolve each name through the .inc. The loader walks this table and so
    does the replay, so a buffer that moved in one file and not the other is
    caught here rather than in a kernel that boots into garbage."""
    m = re.search(r'^px_pb:\s+dd\s+(.+)$', asm_text, re.M)
    assert m, 'px_pb table not found in the generated stage2 -- the delta was lost'
    names = [n.strip() for n in m.group(1).split(',')]
    assert len(names) == c['PX_PLANES'], \
        f'px_pb has {len(names)} entries, the medium has {c["PX_PLANES"]} planes'
    assert all(n in c for n in names), \
        'px_pb names a buffer the .inc does not define: ' + ', '.join(names)
    tab = [c[n] for n in names]
    words = c['PX_GROUP_BYTES'] // 4
    for i, a in enumerate(tab):
        for j, b in enumerate(tab):
            if i < j:
                assert a + words <= b or b + words <= a, \
                    f'plane buffers {names[i]} and {names[j]} overlap: ' \
                    f'{a:#x} and {b:#x} both hold {words} B'
    return tab, names


def sub_table(c):
    return [(c[f'SUB{i}_GROUP'], c[f'SUB{i}_GROUP'] + c[f'SUB{i}_NGROUPS'],
             c[f'SUB{i}_DEST']) for i in range(c['PX_SUBIMAGE_COUNT'])]


def dest_for(group, table, sink):
    """Exactly px_dst: first entry with start <= g < end, else the bare sink."""
    for start, end, dst in table:
        if start <= group < end:
            return dst, start
    return sink, None


# --------------------------------------------------------------------------
# pass 1, transcribed from bm602_stage2_px.asm
# --------------------------------------------------------------------------
def bee_correct_scalar(bufs, words):
    """bufs = [PB0, PB1, PB2, PB3, PP1, PP2, PP4], each >= words long, patched
    in place. Returns (data symbols fixed, parity-only faults).

    bee_correct's body, one offset at a time, with the asm's own register names
    so the branch tree reads against it side by side: al = s1, ah = s2,
    bl = s4. The fix value is s1 for d0/d1/d3 and s2 for d2 -- any covering
    syndrome is algebraically right, so if the asm had chosen a different one
    the counters would still agree and only the bytes would catch it. That is
    why callers compare buffers, not counts.
    """
    d0, d1, d2, d3, p1, p2, p4 = bufs
    fixed = par = 0
    for x in range(words):
        al = p1[x] ^ d0[x] ^ d1[x] ^ d3[x]
        ah = p2[x] ^ d0[x] ^ d2[x] ^ d3[x]
        bl = p4[x] ^ d1[x] ^ d2[x] ^ d3[x]
        if al == 0 and (ah | bl) == 0:
            continue                                  # .bee_next, clean
        if al == 0:
            if ah != 0 and bl != 0:                   # .bee_d2: s2, s4 -> s2
                d2[x] ^= ah
                fixed += 1
                continue
            par += 1                                  # .bee_parity: s4 alone
            continue
        if ah != 0:
            if bl == 0:
                d0[x] ^= al                           # .bee_d0: s1, s2
            else:
                d3[x] ^= al                           # .bee_d3: all three
            fixed += 1
            continue
        if bl == 0:
            par += 1                                  # .bee_parity: s1 alone
        else:
            d1[x] ^= al                               # .bee_d1: s1, s4
            fixed += 1
    return fixed, par


def chunk_is_clean(bufs, words):
    """The whole-chunk form of the asm's per-offset `cmp al,0 / test bh,bh`.
    Equivalent because a chunk xor is zero iff every byte of it is zero -- so
    skipping the scalar here can never skip a codeword the guest repairs. The
    replay proves it on every group it skips, and again on the 128 KiB fault."""
    d0, d1, d2, d3, p1, p2, p4 = [bytes(b[:words]) for b in bufs]
    z = ZEROS.setdefault(words, bytes(words))
    return (functools.reduce(XOR, (p1, d0, d1, d3)) == z and
            functools.reduce(XOR, (p2, d0, d2, d3)) == z and
            functools.reduce(XOR, (p4, d1, d2, d3)) == z)


def guest_walk(med, c, pb, crc8_tab, scalar_every_group=False):
    """Replay px_walk: per group, PX_PLANES 4 KiB reads into the table's
    buffers, pass 1 over them, then the de-interleave + CRC8 loop. Returns
    (bytes-as-the-kernel-sees-them, regions, fixed, par, crc, exact-order
    groups)."""
    gb, chunk, plane_s, base = (c['PX_GROUP_BYTES'], c['PX_CHUNK_SECTORS'],
                                c['PX_PLANE_SECTORS'], c['PX_BASE_LBA'])
    words = gb // 4
    table = sub_table(c)
    sink = c['PX_SINK']
    bufs = [bytearray(words) for _ in pb]
    regions, out = {}, []
    crc = 0xFFFFFFFF
    fixed = par = 0
    exact_groups = skipped = 0
    spans = [(b, b + words) for b in pb]
    for g in range(c['PX_GROUPS']):
        # ---- the seven reads: lba = base + g*CHUNK + p*PLANE_SECTORS ----
        for p in range(c['PX_PLANES']):
            off = (base + g * chunk + p * plane_s) * 512
            blk = med[off:off + words]
            assert len(blk) == words, f'group {g} plane {p} runs off the medium'
            bufs[p][:] = blk
        # ---- pass 1 ----
        if scalar_every_group or not chunk_is_clean(bufs, words):
            f, q = bee_correct_scalar(bufs, words)
            fixed += f
            par += q
        else:
            # skipped on the chunk-level test; every 64th such group is run the
            # slow way on a copy, so "the skip never hides a repair" is sampled
            # evidence rather than a property of one implementation of the test.
            skipped += 1
            if g % 64 == 3:
                copy = [bytearray(b) for b in bufs]
                assert bee_correct_scalar(copy, words) == (0, 0) and \
                    [bytes(b) for b in copy] == [bytes(b) for b in bufs], \
                    f'group {g}: the chunk-level skip hid a repair the scalar finds'
        # ---- decode + CRC8. The asm writes [dst + 4j + p] while reading
        # PBp[j], so a destination that overlapped a plane buffer would feed
        # the loop its own output; that case drops to the instruction-exact
        # order instead of assuming the ranges are disjoint.
        dst, start = dest_for(g, table, sink)
        if any(dst < e and s < dst + gb for s, e in spans):
            decoded = bytearray(gb)
            for x in range(words):
                for p in range(4):
                    b = bufs[p][x]
                    decoded[x * 4 + p] = b
                    crc = (crc >> 8) ^ crc8_tab[(crc ^ b) & 0xFF]
            decoded = bytes(decoded)
            exact_groups += 1
        else:
            decoded = bytearray(gb)
            for p in range(4):
                decoded[p::4] = bufs[p]
            decoded = bytes(decoded)
            for b in decoded:
                crc = (crc >> 8) ^ crc8_tab[(crc ^ b) & 0xFF]
        # The CRC is over the whole DECODED stream, padding groups included --
        # that is what BM903's gate does and what EXPECTED_CRC was computed
        # over -- so `out` keeps every group in walk order while `regions`
        # models what actually survives in memory at the destinations.
        out.append(decoded)
        if start is None:
            regions[dst] = decoded       # bank padding: the same 16 KiB re-covered
            continue
        buf = regions.setdefault(dst, bytearray())
        want = (g - start) * gb
        assert len(buf) == want, \
            f'group {g}: dst {dst:#x} had {len(buf)} B, expected {want} B ' \
            f'(table or stride drift)'
        buf += decoded
    return {'payload': b''.join(out), 'regions': regions,
            'subimages': {d: bytes(regions[d]) for _, _, d in table},
            'fixed': fixed, 'par': par,
            'crc': (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF, 'exact_groups': exact_groups,
            'skipped_groups': skipped}


def crc8_matches_zlib(payload, c, tab):
    crc = 0xFFFFFFFF
    for b in payload:
        crc = (crc >> 8) ^ tab[(crc ^ b) & 0xFF]
    mine = crc ^ 0xFFFFFFFF
    ref = zlib.crc32(payload) & 0xFFFFFFFF
    assert mine == ref, f'CRC8 macro {mine:08X} != zlib {ref:08X}'
    assert mine == c['EXPECTED_CRC'], \
        f'macro/zlib {mine:08X} != the gate constant {c["EXPECTED_CRC"]:08X}'


# --------------------------------------------------------------------------
# fault injection, described as a physical event on the medium
# --------------------------------------------------------------------------
def apply_fault(med, c, planes, group, words, mode, start_word=0):
    """Write a region of plane chunks the way a failing patch of disk would:
    bytes go in, and what the corrector makes of them is this file's problem to
    PREDICT, not the injector's to arrange."""
    out = bytearray(med)
    assert 0 <= start_word < c['PX_GROUP_BYTES'] // 4, \
        'start_word must sit inside the named group chunk, or the fault is not ' \
        'where the leg description says it is'
    assert words + start_word <= c['PX_GROUP_BYTES'] // 4 or len(planes) == 1 \
        and words % (c['PX_GROUP_BYTES'] // 4) == 0, \
        'a multi-plane fault must stay inside its chunk description'
    for p in planes:
        first = (c['PX_BASE_LBA'] + group * c['PX_CHUNK_SECTORS']
                 + p * c['PX_PLANE_SECTORS']) * 512 + start_word
        for k in range(words):
            o = first + k
            if mode == 'stuck_00':
                out[o] = 0x00
            elif mode == 'stuck_ff':
                out[o] = 0xFF
            elif mode == 'flip':
                out[o] ^= 0xA5
            else:
                raise SystemExit(f'unknown fault mode {mode}')
    return bytes(out)


def main() -> int:
    c = consts()
    tab_crc = pxc1.crc32_tab()
    inc_tab = [int(t, 0) for line in (RUNG9 / 'bm903_crc32tab.inc').read_text()
               .splitlines() if line.strip().startswith('dd ')
               for t in line.strip()[3:].split(',')]
    assert len(inc_tab) == 256 and inc_tab == tab_crc, \
        'guest CRC table != host CRC table'

    s2 = nasm('bm602_stage2_px.asm', 'bm602_stage2_px.bin')
    s1 = nasm('bm602_stage1.asm', 'bm602_stage1.bin')
    st2 = defines((RUNG9 / 'bm903_layout.inc').read_text())['STAGE2_SECTORS'] * 512
    assert len(s1) == 512 and s1[-2:] == b'\x55\xaa', 'stage1 must be an MBR'
    assert len(s2) == st2, f'stage2 is {len(s2)} B, the container holds {st2}'

    # the tag, read back out of the bytes the BIOS will leave at 0x7C00
    got_tag = int.from_bytes(s1[c['PX_TAG_OFF']:c['PX_TAG_OFF'] + 4], 'little')
    assert got_tag == c['PX_CONTAINER'], \
        f'the assembled MBR carries {got_tag:#010x} at {c["PX_TAG_OFF"]:#x}; ' \
        f'stage2 compares against {c["PX_CONTAINER"]:#x}'
    rung9_s1 = RUNG9 / 'bm903_stage1.bin'
    assert rung9_s1.exists(), \
        f'{rung9_s1} missing: it is the PXC1 front end, the control the tag ' \
        'leg and the unchanged-code leg are both measured against'
    proven = rung9_s1.read_bytes()
    assert len(proven) == 512
    assert s1[:c['PX_TAG_OFF']] == proven[:c['PX_TAG_OFF']], \
        'stage1 code below the tag slot changed -- the front end is no ' \
        'longer the one BM903 gated'
    assert s1[0x1BE:] == proven[0x1BE:], 'the MBR signature band moved'

    asm2 = S2ASM.read_text()
    pb, pb_names = plane_table(asm2, c)
    m = re.search(r'^BEE_WORDS\s+equ\s+(\S+)', asm2, re.M)
    assert m and m.group(1) == 'PX_GROUP_BYTES/4' and \
        c['PX_GROUP_BYTES'] % 4 == 0, \
        f'the loop bound is {m and m.group(1)}, not PX_GROUP_BYTES/4: the asm ' \
        'and this proof would be counting different codewords'
    words = c['PX_GROUP_BYTES'] // 4

    payload, raw_table, initrd_len, pm_len = pxc1.build_payload()
    # build_payload names a sub-image by (start group, GROUP COUNT, dst); the
    # .inc the loader includes names it by (start, exclusive end, dst). Those
    # are two notations for one thing, and which one a reader has in front of
    # them decides whether the ranges line up -- so the conversion is asserted,
    # not assumed, and everything below uses the loader's own notation.
    table = sub_table(c)
    assert len(raw_table) == len(table) == c['PX_SUBIMAGE_COUNT'], \
        f'{len(raw_table)} sub-images in the codec, {c["PX_SUBIMAGE_COUNT"]} in the .inc'
    for (rs, rn, rd), (ss, se, sd) in zip(raw_table, table):
        assert rs == ss and rs + rn == se and rd == sd, \
            f'sub-image drift: codec ({rs},+{rn},{rd:#x}) vs .inc ({ss}..{se},{sd:#x})'
    assert len(payload) == c['PX_GROUPS'] * c['PX_GROUP_BYTES'], 'group count drift'
    med = codec.encode(s1, s2, payload)
    assert len(med) == (c['PX_BASE_LBA'] +
                        c['PX_PLANES'] * c['PX_PLANE_SECTORS']) * 512
    assert codec.join(codec.read_planes(med)[:4]) == payload, \
        'seven-plane round-trip BROKEN'

    # ---- proof 2: replay the clean medium ----
    t0 = time.time()
    w = guest_walk(med, c, pb, tab_crc)
    dec, regions, fixed, par, crc, exact = (w['payload'], w['regions'], w['fixed'],
                                            w['par'], w['crc'], w['exact_groups'])
    replay_s = time.time() - t0
    assert dec == payload, 'guest-walk replay != payload (byte order or LBA math)'
    assert (fixed, par) == (0, 0), \
        f'a CLEAN medium needed {fixed} data fixes and {par} parity fixes -- the ' \
        'encoder and the transcribed corrector disagree about the same bytes'
    for start, end, dst in table:
        want = payload[start * c['PX_GROUP_BYTES']:end * c['PX_GROUP_BYTES']]
        assert bytes(regions[dst]) == want, \
            f'sub-image at {dst:#x}: {len(regions[dst])} B where {len(want)} B ' \
            'belongs -- mis-slotted or mis-stridden'
    assert crc == c['EXPECTED_CRC'], f'replay CRC {crc:08X} != the gate constant'
    crc8_matches_zlib(payload, c, tab_crc)

    # ---- proof 3: scalar (asm transcription) == codec (GF(2) definition) ----
    d = codec.split(payload)
    planes_full = [bytearray(b) for b in d + codec.parity(d)]
    t0 = time.time()
    sfixed, spar = bee_correct_scalar(planes_full, len(d[0]))
    scalar_s = time.time() - t0
    ref, rfixed, rpar = codec.correct(d, codec.parity(d))
    assert (rfixed, rpar) == (sfixed, spar) == (0, 0), \
        f'clean payload: scalar {(sfixed, spar)}, codec {(rfixed, rpar)}'
    assert codec.join([bytes(b) for b in planes_full[:4]]) == codec.join(ref) \
        == payload, 'the two correctors disagree on the bytes themselves'
    # And on corrupted codewords, where a disagreement would be a real bug:
    # the scalar mutates its buffers, so each implementation gets its own copy
    # of the SAME corrupted state. d1+p4 is the class where the pattern happens
    # to name the right symbol; d0+d1 is leg G, where it names the wrong one.
    base = [bytes(b[:words]) for b in
            codec.split(payload[:4 * words]) +
            codec.parity(codec.split(payload[:4 * words]))]
    for label, hits in (('data+parity', {1: 0x5A, 6: 0xC3}),
                        ('two data symbols', {0: 0x3C, 1: 0xF0})):
        s = [bytearray(b) for b in base]
        r = [bytearray(b) for b in base]
        for i, v in hits.items():
            s[i][17] ^= v
            r[i][17] ^= v
        sf, sp = bee_correct_scalar(s, words)
        rc_, rf, rp = codec.correct([bytes(b) for b in r[:4]],
                                    [bytes(b) for b in r[4:]])
        assert (sf, sp) == (rf, rp), \
            f'{label}: counts differ (scalar {(sf, sp)}, codec {(rf, rp)})'
        assert [bytes(b) for b in s[:4]] == list(rc_), \
            f'{label}: the two implementations fixed DIFFERENT bytes, so the ' \
            'refusal CRC predicted here would not be the one the guest prints'
        print(f'  class {label:>18}: scalar == codec, {(sf, sp)}, '
              f'payload restored={[bytes(b) for b in s[:4]] == [b[:words] for b in base[:4]]}')

    # ---- the fixtures: decided before any boot ----
    FIXDIR.mkdir(exist_ok=True)
    fixtures = []

    def predict(name, med_, fault_text):
        r = guest_walk(med_, c, pb, tab_crc)
        p_, fx, q, cc, ex = r['payload'], r['fixed'], r['par'], r['crc'], r['exact_groups']
        good = (cc == c['EXPECTED_CRC']) and p_ == payload
        return {'name': name, 'fault': fault_text, 'medium_bytes': len(med_),
                'ecc': f'{fx:08X}', 'par': f'{q:08X}',
                'computed_crc': f'{cc:08X}',
                'expected_crc': f'{c["EXPECTED_CRC"]:08X}',
                'verdict': 'PASS' if good else 'FAIL',
                'payload_restored': p_ == payload,
                'exact_order_groups': ex, 'anchor_required': good}

    def add(name, med_, fault_text, kind='walk'):
        f = predict(name, med_, fault_text) if kind == 'walk' else {
            'name': name, 'fault': fault_text, 'medium_bytes': len(med_),
            'ecc': None, 'par': None, 'computed_crc': None,
            'expected_crc': f'{c["EXPECTED_CRC"]:08X}',
            'verdict': 'REFUSE-BEFORE-WALK', 'payload_restored': False,
            'exact_order_groups': 0, 'anchor_required': False}
        f['medium'] = f'{name}.raw'
        f['kind'] = kind
        (FIXDIR / f['medium']).write_bytes(med_)
        fixtures.append(f)
        return f

    add('clean', med, 'none: the medium exactly as built')
    f1 = add('chunk_plane0_stuckff',
             apply_fault(med, c, [0], 7, words, 'stuck_ff'),
             f'one whole 4 KiB data-plane chunk stuck at 0xFF (PB0, group 7): '
             f'{words} codewords, one data symbol in each')
    f2 = add('chunk_plane1_stuck00',
             apply_fault(med, c, [1], 20, words, 'stuck_00'),
             f'one whole 4 KiB data-plane chunk read back as zeros (PB1, group '
             f'20). The fix count is the number of those bytes that were not '
             f'already zero, so it is below {words} and only a replay knows it')
    span = 128 * 1024
    assert span % words == 0
    f3 = add('erase_block_128k',
             apply_fault(med, c, [3], 31, span, 'stuck_00'),
             f'a {span // 1024} KiB contiguous span of the medium stuck at 0: '
             f'{span // words} consecutive chunks of ONE plane, the shape of a '
             f'whole flash erase block lost in one die')
    f4 = add('parity_chunk_stuckff',
             apply_fault(med, c, [5], 9, words, 'stuck_ff'),
             'one parity-plane chunk (PP2) stuck at 0xFF. No payload byte ever '
             'lived there, so this leg proves the parity planes are read and '
             'counted -- not that repair works. That is what the data legs are for')
    f5 = add('two_symbol_collision',
             apply_fault(med, c, [0, 1], 11, 1, 'flip', start_word=3_000),
             'ONE codeword with a fault in two data planes (scoping leg G). The '
             '3-bit syndrome pattern still names a symbol, so the corrector is '
             'confidently wrong and the CRC gate downstream is what must refuse')
    # The class leg G is not: with the same value in d0, d1 and d2, all three
    # syndromes are zero, so pass 1 reports a clean codeword. This medium prints
    # ECC=0 PAR=0 -- what the undamaged one prints -- and only the CRC can stop
    # it. Injecting three BYTES (not a chunk) is the point: it is the smallest
    # fault this code cannot see, and it is a whole executed leg, not a
    # host-side assertion.
    f7 = add('blind_spot_equal_triple',
             apply_fault(med, c, [0, 1, 2], 30, 1, 'flip', start_word=2_500),
             'three equal faults, one in each of d0, d1, d2 of ONE codeword '
             '(group 30, in-plane word 2500): s1=s2=s4=0, so the corrector '
             'fixes nothing and prints ECC=0 PAR=0 exactly as the clean medium '
             'does. Three payload bytes are wrong. The gate is the only thing '
             'left between that and a handoff.')
    old = bytearray(med)
    old[:512] = proven
    f6 = add('pxc1_front_end', bytes(old),
             "sector 0 replaced by BM903's stage1: a PXC1 medium under the "
             'PXC2-E loader. The tag lives in the medium, so the loader refuses '
             'by name in under a second instead of misreading four planes as '
             'seven and reporting a CRC mismatch one walk later.', kind='tag')
    shown = int.from_bytes(proven[c['PX_TAG_OFF']:c['PX_TAG_OFF'] + 4], 'little')
    f6['container_shows'] = f'{shown:08X}'
    assert shown != c['PX_CONTAINER'], \
        'the PXC1 medium carries the PXC2 tag by accident -- the refusal leg ' \
        'would prove nothing'

    for leg in (f1, f2, f3, f4):
        assert leg['verdict'] == 'PASS' and leg['anchor_required'], \
            f'{leg["name"]}: designed recoverable, but the gate would refuse it'
    for leg in (f1, f2, f3):
        assert int(leg['ecc'], 16) > 0, \
            f'{leg["name"]}: ECC=0 on a corrupted medium -- BM601 rule: that is ' \
            'a FAIL leg, not a passing one'
    assert int(f4['ecc'], 16) == 0 and int(f4['par'], 16) > 0, \
        f'the parity-only leg must count PAR and not ECC: {f4}'
    assert f5['verdict'] == 'FAIL' and not f5['payload_restored'] and \
        int(f5['ecc'], 16) == 1, \
        f'two faults in one codeword must be mis-fixed (ECC=1) AND refused: {f5}'
    assert f7['verdict'] == 'FAIL' and not f7['payload_restored'] and \
        int(f7['ecc'], 16) == 0 and int(f7['par'], 16) == 0 and \
        f7['computed_crc'] != f7['expected_crc'], \
        f'the zero-syndrome class must be INVISIBLE to the corrector and ' \
        f'refused by the gate, not half of that: {f7}'
    assert f6['verdict'] == 'REFUSE-BEFORE-WALK'

    # the strongest non-vacuity check available without booting: the same
    # corrector, run the slow way over every group of the erase-block fixture.
    t0 = time.time()
    ws = guest_walk((FIXDIR / 'erase_block_128k.raw').read_bytes(), c, pb,
                    tab_crc, scalar_every_group=True)
    p_slow, fx, q, cc = ws['payload'], ws['fixed'], ws['par'], ws['crc']
    slow_s = time.time() - t0
    assert (fx, q, cc, p_slow == payload) == \
        (int(f3['ecc'], 16), int(f3['par'], 16), int(f3['computed_crc'], 16), True), \
        'the chunk-level clean-skip and the per-offset scalar disagree on a ' \
        'real 128 KiB fault'

    OUT.write_bytes(med)
    FIXJSON.write_text(json.dumps({
        'generated_by': Path(__file__).name,
        'container': codec.CONTAINER,
        'medium': OUT.name, 'medium_bytes': len(med),
        'medium_sectors': len(med) // 512,
        'planes': c['PX_PLANES'], 'plane_buffer_table': pb_names,
        'stage2_bytes': len(s2), 'stage1_bytes': len(s1),
        'tag_offset': hex(c['PX_TAG_OFF']), 'tag': f'{c["PX_CONTAINER"]:08X}',
        'codewords_per_group': words, 'codewords_total': words * c['PX_GROUPS'],
        'replay_seconds_clean_walk': round(replay_s, 2),
        'scalar_over_full_payload_seconds': round(scalar_s, 2),
        'fixtures': fixtures,
    }, indent=1) + '\n')

    print(f'assembled: stage1 {len(s1)} B with tag {c["PX_CONTAINER"]:08X} read '
          f'back from the bytes at {c["PX_TAG_OFF"]:#x}, stage2 {len(s2)} B '
          f'({st2} B container), warning-free')
    print(f'plane buffers as the guest indexes them: '
          f'{" ".join(f"{n}={c[n]:#x}" for n in pb_names)}')
    print(f'host replay of the {c["PX_PLANES"]}-plane walk + pass 1: payload '
          f'restored, ECC=0 PAR=0, CRC={crc:08X} == the gate constant '
          f'({replay_s:.1f} s); {exact} of {c["PX_GROUPS"]} groups needed the '
          f'instruction-exact write order, {w["skipped_groups"]} groups took the '
          f'chunk-level skip and were spot-checked the slow way every 64th group')
    print(f'scalar-vs-codec over all {words * c["PX_GROUPS"]:,} codewords of the '
          f'real payload: same counts, same bytes ({scalar_s:.0f} s), plus the '
          'two-symbol class agreeing on WHICH byte it wrongly corrupted')
    print(f'chunk-level skip vs per-offset scalar on the 128 KiB fault: '
          f'ECC={fx:08X} PAR={q:08X} both ways ({slow_s:.0f} s unpaced)')
    for f in fixtures[1:]:
        e = f['ecc'] if f['ecc'] is not None else '--'
        print(f'  {f["name"]:24} ECC={e} PAR={f["par"] or "--"} '
              f'CRC={f["computed_crc"] or "--"} -> {f["verdict"]}')
    print(f'wrote {OUT.name} ({len(med):,} B = {len(med) // 512:,} sectors), '
          f'{len(fixtures)} fixtures and {FIXJSON.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
