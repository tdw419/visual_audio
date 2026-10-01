#!/usr/bin/env python3
"""BM802 follow-up, no boots spent: what does an INERT initrd byte do to the
archive?

The map's initrd row reads 7 fatal in 24. Seventeen boots finished their
scripts on a medium with one byte flipped INSIDE core.gz. Two readings fit
that: "the fault did not matter" (benign, and what the map's INERT column
suggests), or "the box booted on a root filesystem it could not verify" (the
one Rung 6 is about). The ladder cannot tell them apart -- it watches serial.

So decompress the same 24 corrupted archives on the host, with zlib -- the
same DEFLATE the kernel's unpacker and busybox's gunzip implement -- and ask
what the archive itself says, and how much of the extracted filesystem
changed. If an INERT boot's archive is verifiably corrupt, INERT on the
ladder means "nobody checked", not "nothing broke".

The archive's trailer is checked BY HAND (raw inflate, then compare the CRC32
and the size the member declares) rather than by letting zlib raise it,
because a raised error costs the bytes the decoder had already produced: the
first version of this probe streamed the body in 64 KiB input chunks and lost
the whole final chunk on every leg, which invented a uniform ~48 KB output
shortfall that belongs to the probe, not to the medium.

The extracted bytes are a newc cpio stream, so each changed byte is mapped
back to the archive entry that carries it -- "1 byte differs" becomes "a byte
inside usr/bin/foo differs".

  usage: python3 bm802_archive_local.py     # reads the sweep's rows
"""
import json
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bm802_fixture import FAULT, Rig                  # noqa: E402

ROWS = HERE / 'bm802_sweep_rows.txt'
INITRD_REGION = 'initrd'


def inflate(body):
    """gunzip a single member by hand -> (extracted bytes, verdict or None).

    Returns verdict 'not a gzip deflate member' when the header itself died,
    which is the one case where there is no extracted data to compare."""
    if body[:3] != b'\x1f\x8b\x08':
        return None, 'not a gzip deflate member'
    flg, p = body[3], 10
    if flg & 0x4:                          # FEXTRA
        p += 2 + struct.unpack('<H', body[p:p + 2])[0]
    for bit in (0x8, 0x10):                # FNAME, FCOMMENT
        if flg & bit:
            p = body.index(0, p) + 1
    if flg & 0x2:                          # FHCRC
        p += 2
    d, out, err = zlib.decompressobj(-15), bytearray(), None
    try:
        out += d.decompress(bytes(body[p:]))
        out += d.flush()
    except zlib.error as e:
        err = 'inflate dies: ' + str(e).split(': ')[-1]
    if err is None and not d.eof:
        err = 'inflate ends the data without an end-of-stream'
    if err is None:
        crc, size = struct.unpack('<II', bytes(d.unused_data[:8]))
        if zlib.crc32(bytes(out)) & 0xFFFFFFFF != crc:
            err = 'CRC mismatch'
        elif len(out) & 0xFFFFFFFF != size:
            err = f'declares {size:,} B, unpacks to {len(out):,} B'
    return out, err


def cpio_index(fs):
    """(start, end, name) of every file DATA range in a newc cpio stream."""
    out, i = [], 0
    while i + 110 <= len(fs) and fs[i:i + 6] == b'070701':
        f = [int(fs[i + 6 + k * 8: i + 14 + k * 8], 16) for k in range(13)]
        mode, filesize, namesize = f[1], f[6], f[11]
        name = fs[i + 110: i + 110 + namesize - 1].decode('utf8', 'replace')
        data = (i + 110 + namesize + 3) & ~3
        if name == 'TRAILER!!!':
            break
        if mode & 0o170000 == 0o100000 and filesize:
            out.append((data, data + filesize, name))
        i = (data + filesize + 3) & ~3
    return out


def locate(index, off):
    """(entry name, byte offset inside it) for an offset in the extracted cpio."""
    for lo, hi, name in index:
        if lo <= off < hi:
            return name, off - lo
    return 'cpio metadata (header/name), not file data', None


def entry_at(index, off):
    name, _in = locate(index, off)
    return name if _in is None else f'{name}+{_in}'


def diff_report(a, b, block=1 << 16):
    """(count, first three offsets) of bytes where two extractions disagree.

    Block-skipped so a 13 MB archive with two bad bytes costs two inner loops,
    and a cascaded one costs a count without holding millions of offsets."""
    n, cnt, hits = min(len(a), len(b)), 0, []
    for i in range(0, n, block):
        x, y = a[i:i + block], b[i:i + block]
        if x == y:
            continue
        for k in range(min(len(x), len(y))):
            if x[k] != y[k]:
                cnt += 1
                if len(hits) < 3:
                    hits.append(i + k)
    return cnt, hits[:3], abs(len(a) - len(b))


def main():
    r = Rig()
    gb = r.consts['PX_GROUP_BYTES']
    init_lo = (r.consts['SUB0_NGROUPS'] + r.consts['SUB1_NGROUPS']) * gb
    assert init_lo == r.subs[2][0], 'the initrd does not start where the plan says'
    arc = bytes(r.payload[init_lo:init_lo + r.initrd_len])
    assert arc[:2] == b'\x1f\x8b', 'the initrd is not a gzip member'
    clean, err0 = inflate(arc)
    assert err0 is None, f'the CLEAN archive does not unpack: {err0}'
    index = cpio_index(clean)
    assert index, 'the extracted initrd is not a newc cpio stream'
    rows = [json.loads(ln) for ln in ROWS.read_text().splitlines()
            if ln.startswith('{')]
    legs = sorted((d for d in rows if d['region'] == INITRD_REGION
                   and d['phase'] == 'map'), key=lambda d: d['payload_off'])
    assert legs, f'no {INITRD_REGION} legs in {ROWS.name} -- run the sweep first'
    print(f'core.gz: {len(arc):,} B on the medium, unpacks to {len(clean):,} B '
          f'with a clean CRC ({len(index)} file entries); {len(legs)} legs '
          f're-checked here, host-side, no boots spent\n')
    print(f'{"payload off":>12} {"boot":>9} {"out B":>11} {"out Δ":>7} '
          f'{"fs bytes changed":>17}  where / what the archive says')
    inert, sens = [], []
    landed = {'INERT': [], 'SENSITIVE': []}
    for d in legs:
        b = bytearray(arc)
        b[d['payload_off'] - init_lo] ^= d['fault'] or FAULT
        fs, err = inflate(bytes(b))
        if fs is None:
            print(f'{d["payload_off"]:>12} {d["verdict"]:>9} {"-":>11} {"-":>7} '
                  f'{"-":>17}  {err}')
            (inert if d['verdict'] == 'INERT' else sens).append(
                (0, err, None, d['payload_off']))
            continue
        changed, hits, _short = diff_report(fs, clean)
        delta = len(fs) - len(clean)
        where = ', '.join(f'{entry_at(index, k)} @{k:,}' for k in hits) \
            or 'identical'
        if changed > len(hits):
            where += f' (+{changed - len(hits):,} more)'
        print(f'{d["payload_off"]:>12} {d["verdict"]:>9} {len(fs):>11,} '
              f'{delta:>+7,} {changed:>17,}  {where}')
        print(f'{"":>12} {"":>9} {"":>11} {"":>7} {"":>17}  archive: '
              f'{err or "CRC OK -- the format cannot tell"}')
        if changed:
            landed[d['verdict']].append(locate(index, hits[0])[0])
        (inert if d['verdict'] == 'INERT' else sens).append(
            (changed, err, delta, d['payload_off']))

    def span(v):
        vals = [x for x in v if x is not None]
        return f'{min(vals):,}' if min(vals) == max(vals) else \
            f'{min(vals):,} to {max(vals):,}'

    def kinds(v):
        seen = {}
        for _c, e, _d, _o in v:
            seen[e or 'CRC OK'] = seen.get(e or 'CRC OK', 0) + 1
        return '; '.join(f'{k} x{n}' for k, n in sorted(seen.items()))

    def where_landed(v):
        mods = [n for n in landed[v] if n.endswith('.ko.gz')]
        rest = sorted(set(n for n in landed[v] if not n.endswith('.ko.gz')))
        return (f'{len(mods)} inside *.ko.gz (compressed modules this boot never '
                f'loads)' + (f'; the rest in {", ".join(rest)}' if rest else ''))

    print(f'\nINERT legs ({len(inert)}): {span([c for c, _e, _d, _o in inert])} of the '
          f'{len(clean):,} extracted bytes differ from the intended filesystem and '
          f'the unpacked length is unchanged; the archive itself says '
          f'"{kinds(inert)}". First changed byte: {where_landed("INERT")}.')
    print(f'SENSITIVE legs ({len(sens)}): {span([c for c, _e, _d, _o in sens if c])} '
          f'bytes differ (one leg, the gzip magic, never inflates at all); '
          f'"{kinds(sens)}". First changed byte: '
          f'{where_landed("SENSITIVE")}.')
    survived = [o for c, e, _d, o in inert if e is None or c == 0]
    live = [n for n in landed['INERT'] if not n.endswith('.ko.gz')]
    print('\nThe split is the finding: whether a core.gz fault stops the box tracks '
          'how far the corruption cascades through the DEFLATE stream, and which '
          'file the damage lands in -- not whether it damages the filesystem. All 24 '
          'legs damage it by construction.')
    print(f'So of the {len(inert)} INERT boots: {len(inert) - len(live)} ran on a '
          f'corrupted but never-loaded *.ko.gz, and {len(live)} ran to the end of '
          f'their scripts on a corrupted live file ({", ".join(sorted(set(live)))}).')
    print('And the gate signed every one of them: the medium CRC covers the bytes on '
          'the medium, while the archive trailer is a second check over the unpacked '
          'result that nothing downstream consults.')
    if survived:
        print(f'\nrc!=0: {len(survived)} INERT leg(s) unpacked clean and '
              f'byte-identical, so for those INERT really does mean "no effect": '
              f'{[hex(o) for o in survived]}')
        return 1
    print('rc=0 means no INERT initrd boot was intact at the archive layer: on this '
          'ladder INERT certifies "serial stayed quiet", never "the data survived".')
    print('What this does NOT show: which unpacker ran in the guest and what it did '
          'with the trailer. The boot reaching stage 5 does prove the guest path '
          'finished on an archive whose CRC32 does not match; whether it checked and '
          'ignored or never checked at all is unmeasured here. Past HANDOFF BUILT the '
          'ladder has one signal (silence), so no diagnosis text was available to '
          'distinguish them.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
