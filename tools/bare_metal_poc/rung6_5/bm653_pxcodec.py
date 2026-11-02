#!/usr/bin/env python3
"""BM653: the PXC2-E medium with an EXECUTABLE image in it -- BM652 option C.

One change to rung 6's medium, and it is the change BM652 measured rather than
feared: PXC1's payload has always ended with whole 16 KiB groups of bank
padding -- read off the pixels, corrected by pass 1, summed into the gate CRC,
and dropped at PX_SINK for want of a destination. Here one of those groups
becomes the destination. The medium does not grow by a byte: same payload
length, same 7 planes, same 46,609 sectors, same 5,824 reads. The image region
costs nothing because it EMPLOYS capacity the medium already wastes.

So this file does not fork `bm903_pxcodec.build_payload`. It calls it, imports
`bm602_pxcodec` (which imports pxc1) for the plane algebra, and patches the
built payload:

  * the target group must be UNCLAIMED by the sub-image table and must still
    hold exactly the PATTERN padding it was built from -- the patch proves it
    is employing padding, not overwriting somebody's kernel, before it writes
    anything;
  * the delta against rung6's LANDED payload is scanned, not asserted in prose
    (R-SCOPE-10): N bytes differ, all of them inside the image group, and
    `bm602_pxcodec`'s own claim -- "the ECC medium carries the bytes the
    proven medium carries" -- carries over in that bounded form instead of
    being deleted;
  * both gate constants come out of the same build: `EXPECTED_CRC` over the
    patched 13,631,488 payload bytes, and `EXPECTED_EXEC_NID`, the 16-bit fold
    of the image's own CRC32 that the image is handed and must echo (BM651's
    contract, unchanged). One emitter, so a variant image and another variant's
    expectation cannot be paired by accident.

Parity is derived from the patched payload by the imported codec, so the three
parity planes change exactly where the image changed -- and are still never
CRC'd: the gate keeps running over the decoded, corrected PAYLOAD bytes.

`build_all()`/`inc_text()` are importable on purpose: BM653 has four media
combinations (green image, the BEE-OFF control over the same damage, the halt
image, the scribbler), and each needs its own `.inc`. One emitter for all four
is what makes "the gate constant matches the image in this medium" a property
of the build rather than of somebody's copy-and-paste.

  usage: python3 bm653_pxcodec.py [img2.bin]  # no argument: BM651's green image
                                              # is BUILT here, not read off disk
                                              # payload + .inc + meta, no boots
"""
import hashlib
import json
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG6 = HERE.parent / 'rung6'
sys.path.insert(0, str(RUNG6))
import bm602_pxcodec as codec                                       # noqa: E402
import bm903_pxcodec as pxc1                                        # noqa: E402
sys.path.insert(0, str(HERE))
import bm653_img2 as img2mod                                         # noqa: E402

IMG2_DST = 0x50000        # BM652 §5: the one low address with no collision
IMG2_LEN = 2048           # BM651's proven image size; the group could hold 16 KiB
GROUP = pxc1.GROUP_BYTES


def first_free_group(payload, table):
    """The first padding group -- the one the patch goes into.

    build_payload pads to whole 4-group banks, so the free groups are the tail
    [sum(ngroups), PX_GROUPS). Naming the index by ARITHMETIC on the table, not
    by a literal, is what keeps this honest if the kernel or initrd ever changes
    size: the image follows the padding instead of colliding with a sub-image.
    """
    claimed = sum(n for _, n, _ in table)
    total = len(payload) // GROUP
    assert claimed < total, f'no padding group left: {claimed} of {total} claimed'
    return claimed, total


def patch(payload, img2, group):
    """Put the image bytes into `group`, refusing unless the bytes they replace
    are the padding they are supposed to be."""
    assert len(img2) <= GROUP, f'{len(img2)} B does not fit one {GROUP} B group'
    lo = group * GROUP
    was = payload[lo:lo + len(img2)]
    pattern = (pxc1.PATTERN * (len(img2) // 16 + 1))[:len(img2)]
    assert was == pattern, (
        f'group {group} does not hold bank padding: {sum(a != b for a, b in zip(was, pattern))} '
        'bytes differ from PATTERN -- the image would overwrite a sub-image')
    return payload[:lo] + img2 + payload[lo + len(img2):]


def build_payload(img2):
    """(patched payload, 4-row sub-image table, image group, initrd bytes, pm bytes)."""
    payload, table, initrd_len, pm_len = pxc1.build_payload()
    g, total = first_free_group(payload, table)
    assert len(img2) == IMG2_LEN, f'image is {len(img2)} B, consts expect {IMG2_LEN}'
    patched = patch(payload, img2, g)
    assert len(patched) == len(payload), 'the patch changed the payload length'
    table4 = list(table) + [(g, 1, IMG2_DST)]
    return patched, table4, g, initrd_len, pm_len


def nid_of(crc):
    return ((crc & 0xFFFF) ^ (crc >> 16)) & 0xFFFF


def landed_delta(patched, group):
    """R-SCOPE-10. rung6's assertion was `payload == bm602_px_payload.bin`; this
    row cannot keep that equality and still add an image, so the assertion gets
    BOUNDED, not dropped: scan the two payloads, and require that every
    differing byte lies inside the image group. A sub-image that moved under
    both codecs still fails here."""
    landed = RUNG6 / 'bm602_px_payload.bin'
    assert landed.exists(), f'{landed} missing: nothing to be a delta against'
    base = landed.read_bytes()
    assert len(base) == len(patched), \
        f'payload length moved: {len(base):,} B landed vs {len(patched):,} B here'
    lo, hi = group * GROUP, group * GROUP + IMG2_LEN
    diff = [i for i in range(len(base)) if base[i] != patched[i]]
    outside = [i for i in diff if not lo <= i < hi]
    assert not outside, (
        f'{len(outside)} differing byte(s) OUTSIDE the image group, first at '
        f'{outside[0]:,} (group {outside[0] // GROUP}): a sub-image changed under '
        'both codecs, so this medium is no longer rung 6\'s medium plus an image')
    return len(base), len(diff), (lo, hi)


def build_all(img2, label):
    """One image -> one payload, both gate constants, and every refusal this
    file knows about applied before it returns.

    mkimg calls this per image variant, so each variant's medium carries its
    OWN CRC and its OWN NID out of ONE emitter. That is what makes "the gate
    constant matches the image in this medium" a property of the build instead
    of a property of somebody copying a hex constant between two files.
    """
    payload, table, g, initrd_len, pm_len = build_payload(img2)
    plane = len(payload) // codec.DATA_PLANES   # one DATA plane; the medium
    ngroups = len(payload) // GROUP             # carries PLANES of them
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    img_crc = zlib.crc32(img2) & 0xFFFFFFFF
    nid = nid_of(img_crc)

    total_b, n_diff, (lo, hi) = landed_delta(payload, g)
    # The claim that decides whether the medium grew: it did not.
    d = codec.split(payload)
    assert len(d[0]) == plane, 'plane size drifted'
    med = codec.encode(b'\x00' * codec.SECTOR, b'', payload)
    assert len(med) == (codec.BASE_LBA + codec.PLANES * (plane // codec.SECTOR)) * \
        codec.SECTOR, 'medium geometry changed'
    rp = codec.read_planes(med)
    assert codec.join(rp[:4]) == payload, 'seven-plane round-trip BROKEN'
    assert codec.correct(rp[:4], rp[4:]) == (rp[:4], 0, 0), \
        'the corrector changed a CLEAN patched medium'
    # The image's own bytes survive the plane algebra in both directions: what
    # the walk will store at IMG2_DST is the file, byte for byte.
    assert payload[lo:hi] == img2, 'the image is not contiguous in payload order'
    assert img2 not in (payload[:lo] + payload[hi:]), \
        'the image appears twice -- the leg would not know which bytes ran'
    return {'label': label, 'image': img2, 'payload': payload, 'table': table,
            'group': g, 'span': (lo, hi), 'plane': plane, 'ngroups': ngroups,
            'initrd_len': initrd_len, 'pm_len': pm_len, 'crc': crc,
            'img_crc': img_crc, 'nid': nid, 'medium_bytes': len(med),
            'delta': (total_b, n_diff)}


def inc_text(b):
    """The loader's geometry for one variant. The NAMES are bm602's; the values
    are this medium's. Whatever the forked asm reads, it reads from here."""
    rows = [f'%define SUB{i}_GROUP {s}\n%define SUB{i}_NGROUPS {n}\n'
            f'%define SUB{i}_DEST {hex(dst)}'
            for i, (s, n, dst) in enumerate(b['table'])]
    return (
        '; generated by bm653_pxcodec.py -- DO NOT EDIT\n'
        '; BM602 geometry, unchanged, plus the fourth sub-image row and the two\n'
        '; constants the exec leg needs. Both CRCs come out of ONE build.\n'
        f'%define PX_CONTAINER {codec.TAG}\n'
        f'%define PX_TAG_OFF {codec.TAG_OFF}\n'
        f'%define PX_BASE_LBA {codec.BASE_LBA}\n'
        f'%define PX_PLANE_SECTORS {b["plane"] // codec.SECTOR}\n'
        f'%define PX_CHUNK_SECTORS {pxc1.CHUNK_BYTES // codec.SECTOR}\n'
        f'%define PX_GROUP_BYTES {GROUP}\n'
        f'%define PX_GROUPS {b["ngroups"]}\n'
        f'%define PX_PLANES {codec.PLANES}\n'
        f'%define PX_PAYLOAD_BYTES {len(b["payload"])}\n'
        '%define PB0 0x30000\n%define PB1 0x31000\n'
        '%define PB2 0x32000\n%define PB3 0x33000\n'
        '%define PP1 0x38000\n%define PP2 0x39000\n%define PP4 0x3A000\n'
        f'%define PX_SINK {hex(pxc1.SINK)}\n'
        f'%define PX_SUBIMAGE_COUNT {len(b["table"])}\n'
        + '\n'.join(rows) + '\n'
        f'%define EXPECTED_CRC 0x{b["crc"]:08X}\n'
        f'%define INITRD_BYTES {b["initrd_len"]}\n'
        f'%define HDR_SCRATCH {hex(pxc1.HDR_SCRATCH)}\n'
        f'%define IMG2_DST {hex(IMG2_DST)}\n'
        f'%define IMG2_LEN {IMG2_LEN}\n'
        f'%define IMG2_GROUP {b["group"]}\n'
        f'%define IMG2_LBA '
        f'{codec.BASE_LBA + b["group"] * (pxc1.CHUNK_BYTES // codec.SECTOR)}\n'
        f'%define EXPECTED_EXEC_NID 0x{b["nid"]:04X}\n')


def meta(b):
    total_b, n_diff = b['delta']
    lo, hi = b['span']
    return {
        'container': f'{codec.CONTAINER} + executable image group',
        'image_src': b['label'], 'image_bytes': len(b['image']),
        'image_group': b['group'], 'image_dst': hex(IMG2_DST),
        'image_payload_span': [lo, hi],
        'image_crc32': f'{b["img_crc"]:08X}', 'exec_nid': f'{b["nid"]:04X}',
        'image_sha256': hashlib.sha256(b['image']).hexdigest(),
        'medium_bytes': b['medium_bytes'],
        'medium_sectors': b['medium_bytes'] // codec.SECTOR,
        'payload_bytes': len(b['payload']), 'groups': b['ngroups'],
        'free_padding_groups_before': b['ngroups'] - b['group'],
        'free_padding_groups_after': b['ngroups'] - b['group'] - 1,
        'delta_vs_rung6_payload': {
            'total_bytes': total_b, 'bytes_differing': n_diff,
            'all_inside_image_span': True,
            'note': 'R-SCOPE-10: the equality bm602 asserted is kept in bounded '
                    'form -- nothing outside the image group differs'},
        'payload_crc32': f'{b["crc"]:08X}',
        'payload_sha256': hashlib.sha256(b['payload']).hexdigest(),
        'subimages': [{'start_group': s, 'groups': n, 'dst': hex(dst), 'src': src}
                      for (s, n, dst), src in
                      zip(b['table'], ['kernel setup+header', 'kernel pm payload',
                                       'initrd', 'img2 (executed)'])],
    }


def main(argv) -> int:
    if len(argv) > 1:                           # an image named by hand: read it
        img2f = Path(argv[1])
        img2 = img2f.read_bytes()
    else:
        # Build BM651's green image rather than reading one off the disk. The
        # name `img2_green.bin` is BM651's too, in the same directory, so a
        # stale copy from that row -- or from a half-deleted checkout -- would
        # otherwise become this medium's silent input. `build()` is the one
        # emitter, and bm653_img2.py is the file that checks its output against
        # BM651's landed evidence.
        img2f = HERE / 'img2_green.bin'
        ondisk = img2f.read_bytes() if img2f.exists() else None
        img2, _, _ = img2mod.build(img2mod.SRC, [], img2f)
        assert ondisk is None or ondisk == img2, (
            f'{img2f.name} on disk is not what {img2mod.SRC.name} assembles: a '
            'stale image would have been patched into the medium instead of the '
            'one this build made')
    b = build_all(img2, img2f.name)
    lo, hi = b['span']
    total_b, n_diff = b['delta']

    (HERE / 'bm653_px_payload.bin').write_bytes(b['payload'])
    (HERE / 'bm653_px_meta.json').write_text(json.dumps(meta(b), indent=1) + '\n')
    (HERE / 'bm653_px_layout.inc').write_text(inc_text(b))
    print(f'{codec.CONTAINER}+img2: {len(b["image"])} B from {img2f.name} into '
          f'padding group {b["group"]} (of {b["ngroups"]}; dst {IMG2_DST:#x}), '
          f'payload {len(b["payload"]):,} B UNCHANGED -> medium '
          f'{b["medium_bytes"]:,} B / {b["medium_bytes"] // codec.SECTOR:,} sectors '
          f'/ {b["ngroups"] * codec.PLANES:,} reads, CRC={b["crc"]:08X} '
          f'NID={b["nid"]:04X}')
    print(f'R-SCOPE-10 delta vs rung6/bm602_px_payload.bin: {n_diff:,} of '
          f'{total_b:,} bytes differ, all inside [{lo:#x},{hi:#x}) '
          '-- nothing else on the medium moved')
    print(f'wrote bm653_px_payload.bin, bm653_px_meta.json, bm653_px_layout.inc '
          f'({len(b["table"])} sub-image rows, '
          f'IMG2_LBA={codec.BASE_LBA + b["group"] * 8})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
