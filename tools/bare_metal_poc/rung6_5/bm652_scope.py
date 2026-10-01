#!/usr/bin/env python3
"""BM652 -- the Rung 6.5 option C design pass: what an executable image region
actually costs the PXC2-E medium, measured from the landed trees.

BM650 filed option C and could not price it: "it needs a new region in
rung9/bm903_pxcodec.py's build_payload -- the locked payload builder -- so it is
its own design pass" (BM650_SCOPING.md, 'What this pass cannot tell you'). This
pass prices it. Seven sections:

  1  GEOMETRY     where an image region can come from, and what each source
                   costs the medium (bytes, sectors, reads)
  2  FORK         the payload-builder fork expressed as a byte delta against the
                   landed PXC1 payload -- what the locked builder's output does
                   and does not have to become
  3  PIXELS       which physical pixels carry the image's bytes, so "the pixels
                   were wrong" names addresses rather than a mood
  4  REPLAY       the claim itself, host-side and pre-boot: damage the image's
                   pixels, run the loader's own walk, and show the repaired
                   bytes ARE the bytes the leg jumps into -- plus the control
                   that makes it mean something (corrector off => the gate
                   refuses and no EXEC line can exist)
  5  MAP          the low-memory map during the handoff: where a real-mode image
                   can be executed from without colliding with anything
  6  CODE         the leg assembled (scope652/bm652_probe_leg.asm) against the
                   matched baseline, plus the control build's recipe proved to be
                   size-identical
  7  BUDGET       boots and seconds, from the landed receipts' own measurements

`rung6/` and `rung9/` are read-only inputs and are IMPORTED, not copied (the
BM602 discipline). Writes nothing outside scope652/. Boots nothing -- boots are
the row this note is the precondition for.

  usage: python3 bm652_scope.py
"""
import hashlib
import json
import re
import subprocess
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
POC = HERE.parent
RUNG5, RUNG6, RUNG9 = POC / 'rung5', POC / 'rung6', POC / 'rung9'
SCOPE = HERE / 'scope652'
SCOPE.mkdir(exist_ok=True)

sys.path.insert(0, str(RUNG9))
sys.path.insert(0, str(RUNG6))
import bm903_pxcodec as pxc1                                        # noqa: E402
import bm602_pxcodec as codec                                        # noqa: E402
import bm602_mkimg as mk                                             # noqa: E402
sys.path.insert(0, str(HERE))
import bm650_scope as scope650                                       # noqa: E402

ok, note, red, hr = scope650.ok, scope650.note, scope650.red, scope650.hr
nasm, sect_sizes = scope650.nasm, scope650.sect_sizes

IMG2_ASM = HERE / 'bm651_img2.asm'
IMG_LEN = 2048
IMG_DST = 0x50000                    # candidate: the paragraph BM651 already uses
RESULTS = {}


def fold(blob):
    """BM651's NID: one 16-bit fold of the CRC32 the gate already checks."""
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    return crc, ((crc & 0xFFFF) ^ (crc >> 16)) & 0xFFFF


LST_TIMES = re.compile(r'^\s*\d+\s+([0-9A-Fa-f]{8})\s+.*\btimes\b')


def list_end(lst_path):
    """Where nasm says the code stops: the offset on the file's own `times`
    padding line. Byte-counting the binary cannot answer this -- a real-mode
    image and a handoff both contain legitimate zero bytes -- but the assembler
    knows exactly where it started padding."""
    hits = [int(m.group(1), 16)
            for line in Path(lst_path).read_text().splitlines()
            if (m := LST_TIMES.match(line))]
    if not hits:
        raise AssertionError(f'no `times` padding line found in {lst_path.name}')
    return max(hits)                 # the padding is the last thing in the file


def walk_with(med, c, pb, tab, correct=True):
    """mk.guest_walk, optionally with pass 1 switched off -- the host mirror of
    the control build (`call bee_correct` replaced by five NOPs). Patched and
    restored around one call, so the repair-then-refuse pair differs in exactly
    that one decision and in nothing else."""
    real = mk.bee_correct_scalar
    if not correct:
        mk.bee_correct_scalar = lambda bufs, words: (0, 0)
    try:
        return mk.guest_walk(med, c, pb, tab)
    finally:
        mk.bee_correct_scalar = real


def main() -> int:
    hr('0. INPUTS: the landed PXC2-E books, read not retyped')
    c = mk.consts()                                   # rung6/bm602_px_layout.inc
    asm602 = mk.S2ASM.read_text()
    pb, pb_names = mk.plane_table(asm602, c)
    table = mk.sub_table(c)
    tab_crc = pxc1.crc32_tab()
    ok(f'{mk.INC.name}: {c["PX_PLANES"]} planes x {c["PX_PLANE_SECTORS"]:,} '
       f'sectors, base LBA {c["PX_BASE_LBA"]}, {c["PX_GROUPS"]} groups of '
       f'{c["PX_GROUP_BYTES"]:,} B, gate EXP=0x{c["EXPECTED_CRC"]:08X}')
    ok(f'sub-images as the loader indexes them: '
       + ', '.join(f'{s}..{e}->{d:#x}' for s, e, d in table))
    ok(f'plane buffers: {" ".join(f"{n}={c[n]:#x}" for n in pb_names)}')

    img2 = (SCOPE / 'img2_green.bin')
    nasm(IMG2_ASM, img2, lst=SCOPE / 'img2_green.lst')
    blob = img2.read_bytes()
    crc_img, nid = fold(blob)
    assert len(blob) == IMG_LEN, f'img2 is {len(blob)} B, not {IMG_LEN}'
    ok(f'the image is BM651\'s own source, assembled here warning-free: '
       f'{len(blob):,} B, CRC32={crc_img:08X}, NID={nid:04X}')
    RESULTS['img2'] = {'bytes': len(blob), 'crc32': f'{crc_img:08X}',
                       'nid': f'{nid:04X}',
                       'sha256': hashlib.sha256(blob).hexdigest()}

    # ------------------------------------------------------------------ 1
    hr('1. GEOMETRY: where an image region can come from, and what each '
       'size costs the medium')
    payload, raw_table, initrd_len, pm_len = pxc1.build_payload()
    G = pxc1.GROUP_BYTES
    content_groups = sum(n for _, n, _ in raw_table)
    filler = c['PX_GROUPS'] - content_groups
    g_img = raw_table[-1][0] + raw_table[-1][1]        # first spare group
    assert 0 <= g_img < c['PX_GROUPS'] and filler > 0
    ok(f'the payload is {content_groups} groups of real sub-image + '
       f'{filler} groups of bank padding (PATTERN bytes), and the padding is '
       f'already read, already corrected and already inside the CRC: '
       f'{filler * G:,} B of the medium carries nothing anyone wants')

    def medium_for(content):
        """The landed codec's own arithmetic: whole banks of 4 groups."""
        pad = (-content) % 4
        ngroups = content + pad
        plane = ngroups * G // pxc1.PLANES
        assert plane % pxc1.CHUNK_BYTES == 0 and plane % 512 == 0
        return ngroups, plane, (c['PX_BASE_LBA'] + codec.PLANES * (plane // 512)) * 512

    n0, pl0, med0 = medium_for(content_groups)
    assert n0 == c['PX_GROUPS'] and med0 == c['PX_PAYLOAD_BYTES'] // 4 * 7 + \
        c['PX_BASE_LBA'] * 512, 'the model above does not reproduce the landed medium'
    ok(f'model agrees with the landed books: {n0} groups, plane {pl0:,} B, '
       f'medium {med0:,} B = {med0 // 512:,} sectors')

    rows = []
    for label, image_bytes in (('BM651\'s 2 KiB image', IMG_LEN),
                               ('16 KiB image', 16 * 1024),
                               ('32 KiB image', 32 * 1024),
                               ('64 KiB image', 64 * 1024),
                               ('128 KiB image', 128 * 1024)):
        groups = -(-image_bytes // G)                  # whole groups only
        spare = filler * G
        extra = max(0, groups * G - spare) // G        # beyond the padding
        n_, pl_, med_ = medium_for(content_groups + extra)
        rows.append({'label': label, 'image_bytes': image_bytes,
                     'groups_consumed': groups, 'extra_content_groups': extra,
                     'groups': n_, 'plane_bytes': pl_, 'medium_bytes': med_,
                     'medium_sectors': med_ // 512,
                     'delta_bytes': med_ - med0,
                     'delta_sectors': (med_ - med0) // 512,
                     'delta_reads': (med_ - med0) // 512 // 8,
                     'pct_of_medium': 100.0 * (med_ - med0) / med0})
    for r in rows:
        verdict = ('FREE' if r['delta_bytes'] == 0 else
                   f"+{r['delta_bytes']:,} B / {r['delta_sectors']} sectors / "
                   f"{r['delta_reads']} reads = {r['pct_of_medium']:.2f}%")
        ok(f"image {r['label']}: {r['groups_consumed']} group(s), "
           f"{r['extra_content_groups']} past the padding -> medium "
           f"{r['medium_bytes']:,} B  [{verdict}]")
    def med_for_groups(groups):
        extra = max(0, groups * G - filler * G) // G
        return medium_for(content_groups + extra)[2]

    free_groups = max(g_ for g_ in range(1, 13) if med_for_groups(g_) == med0)
    jump = med_for_groups(free_groups + 1) - med0
    ok(f'the bank quantum, scanned: an image up to {free_groups} group(s) = '
       f'{free_groups * G // 1024} KiB grows the medium by nothing at all: '
       f'{med0:,} B either way. The group past that costs {jump:,} B = '
       f'{jump // 512} sectors = {jump // 512 // 8} reads, because PXC1 pads to '
       f'whole 4-group banks and the padding has run out')
    RESULTS['geometry'] = {'filler_groups': filler, 'image_group': g_img,
                           'medium_bytes_as_landed': med0, 'rows': rows,
                           'free_image_groups': free_groups,
                           'first_group_past_free_bytes': jump,
                           'bank_quantum_groups': 4,
                           'group_bytes': G,
                           'subimage_row_bytes_in_stage2': 12,
                           'px_dst_scan_cost': '3 cmp/jae + 12 B per row: O(rows), '
                                               'a constant 4 vs 3 comparisons'}

    # ------------------------------------------------------------------ 2
    hr('2. THE FORK: the locked builder, post-patched, as a byte delta')
    landed = (RUNG9 / 'bm903_px_payload.bin').read_bytes()
    assert landed == payload, 'the landed PXC1 payload differs from a fresh build'
    ok(f'pxc1.build_payload() reproduces rung9/bm903_px_payload.bin exactly '
       f'({len(landed):,} B, sha256 {hashlib.sha256(landed).hexdigest()[:12]}...)')
    region = slice(g_img * G, (g_img + 1) * G)
    assert bytes(payload[region]) == (pxc1.PATTERN * (G // 16))
    ok(f'group {g_img} is the padding: its {G:,} B are the PATTERN cycle '
       f'{pxc1.PATTERN[:4].hex(" ")}... repeated -- no sub-image claims it, '
       f'px_dst drops it at PX_SINK {c["PX_SINK"]:#x}')

    p2 = bytearray(payload)
    p2[g_img * G: g_img * G + len(blob)] = blob
    p2 = bytes(p2)
    diffs = [i for i in range(0, len(p2), 64) if p2[i:i + 64] != payload[i:i + 64]]
    changed = sum(1 for a, b in zip(p2, payload) if a != b)
    lo, hi = min(diffs), max(diffs)
    assert lo >= region.start and hi < region.stop, 'the fork reached outside its group'
    crc2 = zlib.crc32(p2) & 0xFFFFFFFF
    ok(f'the fork: write {len(blob):,} B of img2 at group {g_img}\'s first byte. '
       f'{changed:,} bytes of the 13,631,488 differ, all inside one 16 KiB group '
       f'[{lo - region.start}..{hi - region.start + 63}], and len is unchanged')
    ok(f'EXPECTED_CRC becomes 0x{crc2:08X} (was 0x{c["EXPECTED_CRC"]:08X}) -- '
       f'emitted by the consts script from these same bytes, never hand-edited '
       f'(run-13), and EXPECTED_EXEC_NID={nid:04X} comes from the same build')
    note('BM602\'s codec asserts `payload == the landed PXC1 payload`. The fork '
         'keeps that assertion in its weaker, checkable form: the two differ in '
         'N bytes and every one of them is inside the image group. A rewrite of '
         'build_payload would not be able to say that.')
    RESULTS['fork'] = {'bytes_changed': changed,
                       'first_diff': lo, 'last_diff': hi,
                       'region': [region.start, region.stop],
                       'payload_len': len(p2), 'new_crc32': f'{crc2:08X}',
                       'old_crc32': f'{c["EXPECTED_CRC"]:08X}'}

    # ------------------------------------------------------------------ 3
    hr('3. PIXELS: where img2 physically is')
    base_byte = c['PX_BASE_LBA'] * 512
    plane_bytes = c['PX_PLANE_SECTORS'] * 512
    x0 = (g_img * G) // pxc1.PLANES                    # in-plane offset of byte 0
    med0_byte = base_byte + x0
    pix0, ch0 = med0_byte // 4, med0_byte % 4
    frame_w = 4096
    ok(f'payload byte 0 of the image is medium byte {med0_byte:,} == plane 0 '
       f'in-plane offset {x0:,} == pixel x={pix0 % frame_w}, y={pix0 // frame_w}, '
       f'channel {ch0} (RGBA) of a 4096-wide frame')
    span = len(blob) // pxc1.PLANES                    # 512 B per plane
    for p in range(pxc1.PLANES):
        m = base_byte + p * plane_bytes + x0
        ok(f'  plane {p} ({pb_names[p]}): medium bytes {m:,}..{m + span - 1:,} '
           f'= LBA {m // 512}+{(m % 512) // 8} carry img2 bytes '
           f'{p}::{pxc1.PLANES} of the image, {span} B, contiguous')
    ok(f'so img2\'s {len(blob):,} bytes are 4 contiguous 512 B runs, one per '
       f'data plane, {plane_bytes:,} B apart on the medium -- and a contiguous '
       f'run inside one plane is ONE symbol in each of many codewords, which is '
       f'exactly the class Hamming(7,4) over byte symbols repairs')
    note('the converse, and the honest boundary: damage that hits the SAME '
         'in-plane offset in two data planes is two symbols in one codeword -- '
         'BM602\'s leg G, mis-fixed and refused. That shape is four bytes '
         f'{plane_bytes:,} B apart, not a scratch; the medium\'s own geometry '
         'decides which faults are in the story.')
    RESULTS['pixels'] = {'medium_byte_of_img2_0': med0_byte,
                         'pixel': [pix0 % frame_w, pix0 // frame_w],
                         'channel': ch0,
                         'plane_spans': [base_byte + p * plane_bytes + x0
                                         for p in range(pxc1.PLANES)],
                         'run_bytes_per_plane': span}

    # ------------------------------------------------------------------ 4
    hr('4. REPLAY: the loader\'s own walk, on the host, on the image region')
    s1 = nasm(RUNG6 / 'bm602_stage1.asm', SCOPE / 'bm602_stage1.bin',
              cwd=RUNG6, incs=(RUNG6, RUNG9))
    s2 = nasm(RUNG6 / 'bm602_stage2_px.asm', SCOPE / 'bm602_stage2_px.bin',
              cwd=RUNG6, incs=(RUNG6, RUNG9))
    assert s1.stat().st_size == 512 and s2.stat().st_size == c['PX_BASE_LBA'] * 512 - 512
    c2 = dict(c)
    c2['PX_SUBIMAGE_COUNT'] = 4
    c2['SUB3_GROUP'], c2['SUB3_NGROUPS'], c2['SUB3_DEST'] = g_img, 1, IMG_DST
    table2 = mk.sub_table(c2)
    assert table2[-1] == (g_img, g_img + 1, IMG_DST), 'the new row did not land'
    med = codec.encode(s1.read_bytes(), s2.read_bytes(), p2)
    ok(f'built scope652 media: stage1 {s1.stat().st_size} B (tag read at '
       f'{c["PX_TAG_OFF"]:#x}), stage2 {s2.stat().st_size:,} B, medium '
       f'{len(med):,} B, '
       f'4-row sub-image table with the image group at {IMG_DST:#x}')

    def replay(name, med_, correct=True, want=None):
        t0 = time.time()
        r = walk_with(med_, c2, pb, tab_crc, correct=correct)
        dt = time.time() - t0
        img_here = bytes(r['regions'].get(IMG_DST, b''))[:len(blob)]
        gate = r['crc'] == crc2
        got = (gate, img_here == blob, r['fixed'])
        say = ok if want is None or want == got else red
        say(f'{name:26} ECC={r["fixed"]:8d} PAR={r["par"]:8d} '
            f'crc={"PASS" if gate else format(r["crc"], "08X") + " FAIL"} '
            f'image_at_dst={"== img2" if img_here == blob else "DIFFERS"} '
            f'({dt:.1f} s)')
        if want is not None and want != got:
            say(f'{name:26} predicted {want}, got {got}')
        RESULTS.setdefault('replay', {})[name] = {
            'ecc': r['fixed'], 'par': r['par'], 'crc': f'{r["crc"]:08X}',
            'gate_passes': gate, 'image_intact': img_here == blob,
            'exact_order_groups': r['exact_groups'], 'seconds': round(dt, 2)}
        return r, gate, img_here

    r_clean, g_, i_ = replay('clean', med, want=(True, True, 0))
    assert g_ and i_ == blob and r_clean['fixed'] == 0
    assert r_clean['exact_groups'] == 0, \
        'the image dst aliased a plane buffer: the walk would feed itself'
    ok('  (the dst the map will justify in section 5 also keeps the replay out '
       'of the instruction-exact path: 0 of 832 groups needed it)')

    # a scratch across the image: 256 contiguous medium bytes in plane 1, from
    # the group's first in-plane byte (start_word is inside the group's chunk)
    faulted = mk.apply_fault(med, c2, [1], g_img, 256, 'flip', start_word=0)
    assert faulted != med
    r_f, g2, i2 = replay('scratch_256B_plane1', faulted, want=(True, True, 256))
    assert g2 and i2 == blob and r_f['fixed'] == 256, \
        'a 256-byte scratch in one plane must be 256 single-symbol fixes'
    ok('  the damaged image, after pass 1, is byte-identical to the image the '
       'gate was built with, so the leg\'s `call IMG2_SEG:0` jumps into repaired '
       'bytes and the NID it must echo is computed from them')

    r_c, g3, i3 = replay('scratch_control_off', faulted, correct=False,
                         want=(False, False, 0))
    assert not g3 and r_c['fixed'] == 0, \
        'the control must refuse: corrector off, same medium, ECC=0, gate FAIL'
    ok('  -> the non-vacuity control: the SAME medium with `call bee_correct` '
       'NOPed prints ECC=0 and dies at the gate, so no EXEC line exists. '
       'Repair is what buys the boot, not the print')

    # the boundary, inside the image: two planes, same in-plane offsets
    two = bytearray(med)
    for p in (1, 2):
        o = (c2['PX_BASE_LBA'] + g_img * c2['PX_CHUNK_SECTORS']
             + p * c2['PX_PLANE_SECTORS']) * 512
        two[o] ^= 0xA5
        two[o + 1] ^= 0xA5
    r_t, g4, i4 = replay('two_symbols_in_image', bytes(two), want=(False, False, 2))
    assert not g4 and r_t['fixed'] == 2, \
        f'two symbols in one codeword must be mis-fixed and refused: {r_t["fixed"]}'
    ok('  -> two symbols in one codeword inside the image: mis-fixed, refused at '
       'the gate, and the refusal happens BEFORE the leg, so the image never '
       'runs. Same algebra BM602 booted as leg G, now on bytes that get executed')

    blind = mk.apply_fault(med, c2, [0, 1, 2], g_img, 1, 'flip', start_word=4)
    r_b, g5, i5 = replay('blind_spot_in_image', blind, want=(False, False, 0))
    assert not g5 and r_b['fixed'] == 0 and r_b['par'] == 0, \
        'the equal-triple class must be invisible to the corrector'
    ok('  -> the equal-triple blind spot inside the image prints ECC=0 PAR=0, '
       'what the clean medium prints, and the gate is what stops it')
    RESULTS['replay']['_note'] = (
        'four of these five legs are also boot legs; the host replay is the '
        'prediction the boot is compared against, written before any qemu runs')

    # ------------------------------------------------------------------ 5
    hr('5. MAP: what a real-mode destination can be')
    lay9 = mk.defines((RUNG9 / 'bm903_layout.inc').read_text())
    s2_len = lay9['STAGE2_SECTORS'] * 512
    live = [
        (0x0600, 0x7BFF, 'BIOS data area, untouched by either loader'),
        (0x7C00, 0x7DFF, 'stage1 / MBR copy (the container tag is read from here)'),
        (0x8000, 0x8000 + s2_len - 1, 'stage2 itself (ORG 0x8000)'),
        (lay9['ZP_ADDR'], lay9['ZP_ADDR'] + 4095, 'kernel zero page (built post-leg)'),
        (lay9['CMDLINE_ADDR'], lay9['CMDLINE_ADDR'] + lay9['CMDLINE_BYTES'] - 1,
         'cmdline buffer'),
        (0x1F000, 0x1F783, 'the 32-bit stack, down from STACK_TOP 0x1f784'),
        (c['SUB0_DEST'], c['SUB0_DEST'] + c['SUB0_NGROUPS'] * G - 1,
         'sub-image 0: the kernel header band'),
        (c['PX_SINK'], c['PX_SINK'] + G - 1, 'PX_SINK: padding groups land here'),
        (IMG_DST, IMG_DST + G - 1, 'THE IMAGE GROUP (proposed dst)'),
    ] + [(c[n], c[n] + 4095, f'{n}: plane chunk buffer') for n in pb_names]
    live.sort()
    for s, e, what in live:
        ok(f'  {s:#07x}..{e:#07x}  {e - s + 1:>6,} B  {what}')
    img_span = (IMG_DST, IMG_DST + G - 1)
    hits = [(live[i], live[i + 1]) for i in range(len(live) - 1)
            if live[i][0] != live[i + 1][0] and live[i][1] >= live[i + 1][0]]
    if any(img_span in pair for pair in hits):
        red(f'{IMG_DST:#x} collides: {hits}')
    else:
        ok(f'no live region overlaps {IMG_DST:#x}..{IMG_DST + G - 1:#x}, and no '
           f'pair among the {len(live)} claims overlaps either: {len(hits)} '
           f'collisions, so the map is a map')
    gaps = [(live[i][1] + 1, live[i + 1][0] - 1) for i in range(len(live) - 1)
            if live[i + 1][0] - live[i][1] > 1]
    big = max((e - s + 1, s, e) for s, e in gaps if s < 0x100000)
    ok(f'largest free run under 1 MiB after those claims: {big[1]:#x}..{big[2]:#x} '
       f'= {big[0]:,} B -- the walk\'s destinations all live below 1 MiB except '
       f'the kernel (0x100000) and the initrd (0x10000000), so the image has to '
       f'share the first megabyte and this is the room it has')
    ok(f'the constraint the mode-exit actually carries: the GDT\'s 16-bit code '
       f'descriptor is `dq 0x00009A000000FFFF` -> limit 0xFFFF, so the landing '
       f'label of the 66-EA jump must sit below linear 0x10000. stage2 is at '
       f'0x8000..{0x8000 + s2_len - 1:#x}: {"OK" if 0x8000 + s2_len <= 0x10000 else "OVERFLOW"}, '
       f'{0x10000 - (0x8000 + s2_len):,} B of headroom')
    ok(f'the block at IMG2_SEG:{G - 16:#x} (linear {IMG_DST + G - 16:#x}) is '
       f'inside the group\'s own window, above the {len(blob):,} B image, and '
       f'written AFTER the walk summed the CRC -- so writing it cannot move a '
       f'gate value, which is the property R-SCOPE-2 was about on rung 6.5 A')
    note('R-SCOPE-7, the correction this pass exists to file: BM651 put the '
         'block at IMG2_SEG+IMG2_LEN (2,048) because its own window was 2 KiB. '
         'On the ECC medium the region is a whole 16 KiB group and the image is '
         'only its first 2 KiB -- the block belongs at the TOP of the group, or '
         'a later 8 KiB image walks over it. See the note.')
    RESULTS['map'] = {'dst': hex(IMG_DST), 'block_offset': hex(G - 16),
                      'live_regions': [[hex(s), hex(e), w] for s, e, w in live],
                      'collisions': len(hits),
                      'largest_free_run': [hex(big[1]), hex(big[2]), big[0]],
                      'stage2_top': hex(0x8000 + s2_len),
                      'headroom_under_64k': 0x10000 - (0x8000 + s2_len)}

    # ------------------------------------------------------------------ 6
    hr('6. CODE: the leg assembled, and the control build proved')
    base = (SCOPE / 'bm602_stage2_px.bin').read_bytes()
    lst_base = SCOPE / 'bm602_stage2_px.lst'
    nasm(RUNG6 / 'bm602_stage2_px.asm', SCOPE / 'bm602_stage2_px.lst.bin',
         lst=lst_base, cwd=RUNG6, incs=(RUNG6, RUNG9))
    pad_at = list_end(lst_base)
    assert len(base[pad_at:]) == 8192 - pad_at and not any(base[pad_at:]), \
        f'what the list calls the end of code at {pad_at} is not padding'
    ok(f'matched baseline: rung6\'s stage2 assembles warning-free; the list '
       f'file\'s own `times` line sits at {pad_at:,} B and the rest of the '
       f'{len(base):,} B container is zero padding -- {8192 - pad_at:,} B free')
    if pad_at == 3776:
        ok('  and that number is BM650\'s: it measured this same file at 3,776 B '
           'code / 4,416 B free, so the method here agrees with the ladder\'s '
           'books rather than inventing a third yardstick')
    else:
        red(f'BM650 measured 3,776 B of code in this file; the list says {pad_at} '
            f'B -- one of the two is reading something the other is not')
    probe = nasm(SCOPE / 'bm652_probe_leg.asm', SCOPE / 'bm652_probe_leg.bin',
                 lst=SCOPE / 'bm652_probe_leg.lst')
    total = probe.stat().st_size
    marks = ['pmode_to_real', 'real_exec_leg', 'back_to_pmode', 'helpers16',
             'strings_here', 'data_here']
    a = sect_sizes(SCOPE / 'bm652_probe_leg.lst', marks)
    order = [m for m in marks if m in a]
    secs = {}
    for i, m in enumerate(order[:-1]):
        secs[m] = a[order[i + 1]] - a[m]
    secs['data_here'] = total - a['data_here']
    leg_total = sum(v for k, v in secs.items() if k != 'data_here')
    for m in marks:
        ok(f'  {m:16} {secs[m]:>4} B')
    ok(f'the whole option-C leg, code + strings: {leg_total} B '
       f'(BM651\'s landed leg was 230 B, of which 12 B was the copy-down this '
       f'base has no use for and 54 B the arg block it still writes)')
    free = 8192 - pad_at
    ok(f'cost against the free budget: {leg_total} B of {free:,} B = '
       f'{100.0 * leg_total / free:.1f}% -- as at rung 6.5, code size is not '
       f'the constraint; the mode-return is {secs["pmode_to_real"] + secs["back_to_pmode"]} B '
       f'of it, the price of running a 16-bit image off a 32-bit walk')
    RESULTS['code'] = {'baseline_code_bytes': pad_at,
                       'baseline_container_bytes': len(base),
                       'free_bytes': free,
                       'sections': secs, 'leg_total': leg_total,
                       'mode_switch_bytes': secs['pmode_to_real'] + secs['back_to_pmode']}

    ctrl_src = SCOPE / 'bm602_stage2_px_beeoff.asm'
    txt = asm602
    assert txt.count('    call bee_correct\n') == 1, \
        'the control delta is not a one-place text edit any more'
    ctrl_src.write_text(txt.replace(
        '    call bee_correct\n',
        '    times 5 nop              ; BEE-OFF: the control build skips pass 1\n'))
    ctrl = nasm(ctrl_src, SCOPE / 'bm602_stage2_px_beeoff.bin',
                lst=SCOPE / 'bm602_stage2_px_beeoff.lst',
                cwd=RUNG6, incs=(RUNG6, RUNG9))
    cb = ctrl.read_bytes()
    ctrl_end = list_end(SCOPE / 'bm602_stage2_px_beeoff.lst')
    nd = sum(1 for x, y in zip(cb, base) if x != y)
    if len(cb) == len(base) and ctrl_end == pad_at and 0 < nd <= 8:
        ok(f'control build: one named textual delta, {len(cb):,} B and the end '
           f'of code at {ctrl_end:,} B both == baseline, {nd} bytes differ (the '
           f'5-byte call -> 5 NOPs) -- no relayout, so every other anchor BM602 '
           f'landed still lines up: the differ and the identity legs transfer')
    else:
        red(f'control build differs structurally: {len(base)} vs {len(cb)} B, '
            f'code end {pad_at} vs {ctrl_end}, {nd} bytes')
    RESULTS['control_build'] = {'size_equal': len(cb) == len(base),
                                'code_end_equal': ctrl_end == pad_at,
                                'bytes_differing': nd,
                                'recipe': 'call bee_correct -> times 5 nop'}

    # ------------------------------------------------------------------ 7
    hr('7. BUDGET: boots and seconds, from the landed measurements')
    legs = [('green', 'clean medium, image runs, EXEC=OK, then the handoff', 1, 11.5),
            ('repaired', '256 B scratch across the image\'s plane 1: ECC>0, '
                         'EXEC=OK, and the handoff dumps still equal green', 1, 11.5),
            ('bee-off control', 'same faulted medium, pass 1 NOPed: ECC=0, '
                                'GATE2=FAIL, no EXEC line', 1, 1.3),
            ('two-symbol', 'leg G inside the image: refused before the leg', 1, 1.3),
            ('blind-spot', 'equal-triple inside the image: ECC=0, refused', 1, 1.3),
            ('halt image', 'the image never returns: the host times out, and the '
                           'kernel never boots -- new failure mode, see the note',
             1, 30.0),
            ('scribbler', 'an image that writes over HDR_SCRATCH/kernel/zero page: '
                          'EXEC=OK and the handoff dump DIFFERS -- proves the '
                          'identity legs are load-bearing on this base', 1, 11.5),
            ('identity', 'no boot: transcripts and dumps vs the clean leg, '
                         'BM602\'s bm602_identity.py', 0, 0)]
    n_boots = sum(l[2] for l in legs)
    est = sum(l[3] for l in legs)
    for name, what, k, secs_ in legs:
        ok(f'  {name:14} {k} boot @ ~{secs_} s: {what}')
    ok(f'{n_boots} boots. Per-leg seconds are BM602\'s measured wall times for '
       f'the same shapes (`clean` 11.3/12.3 s to tc@box, the refusal legs '
       f'1.3 s, the container refusal 0.3 s), so this row is ~{est:.0f} s '
       f'x2 passes = ~{2 * est:.0f} s, plus Tiny Core\'s autologin race, which '
       f'is what made BM602\'s pass B 340 s against pass A\'s 296 s')
    ok(f'added wire on the green path: BM651 measured 33 B = 2.86 ms at 115200 '
       f'8N1; option C prints the same three lines in real mode plus the '
       f'EXEC verdict, so the transcript grows by the same order and the '
       f'anchor budget BM602 needed (8 x 45 s) is untouched by milliseconds')
    note('and one thing money cannot buy: on this base the image runs BEFORE '
         'the kernel handoff, so a hung or hostile image is a failed Linux boot, '
         'not a 16-bit receipt with nothing behind it. That is the composition '
         'BM650 called worth more than option A, and it is also the reason the '
         'halt and scribbler legs are not optional.')
    RESULTS['budget'] = {'boots': n_boots, 'estimate_seconds_one_pass': est,
                         'legs': [{'name': l[0], 'boots': l[2],
                                   'seconds': l[3], 'what': l[1]} for l in legs]}

    # ------------------------------------------------------------------ out
    (SCOPE / 'bm652_scope.json').write_text(json.dumps(RESULTS, indent=1) + '\n')
    inc_lines = [f'%define SUB{i}_GROUP {g}\n%define SUB{i}_NGROUPS {n}\n'
                 f'%define SUB{i}_DEST {hex(d)}'
                 for i, (g, n, d) in enumerate(table2)]
    (SCOPE / 'bm652_px_layout_preview.inc').write_text(
        '; PREVIEW ONLY -- what the option-C codec would emit. Not included by '
        'anything; the row that implements this re-derives it.\n'
        + '\n'.join(inc_lines) + f'\n%define PX_SUBIMAGE_COUNT 4\n'
        f'%define EXPECTED_CRC 0x{crc2:08X}\n')
    print()
    n = scope650.FAILS[0]
    print(f'BM652_SCOPE: {"GREEN" if n == 0 else f"RED {n}"}')
    return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main())
