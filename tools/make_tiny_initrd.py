#!/usr/bin/env python3
"""Build a tiny newc cpio archive + gzip it, for the small-initrd A/B test.

IMPORTANT: kernel 6.12's cpio parser aligns names with
    N_ALIGN(len) = ((len + 1) & ~3) + 2   (init/initramfs.c)
which is NOT standard newc (standard pads names to 4). The Alpine initrd uses
the kernel convention (busybox entry: namesize=10, name field = 10 bytes, next
entry at header+110+10). This builder must match, or the kernel misparses the
archive and reports "junk within compressed archive".

Usage: python3 tools/make_tiny_initrd.py [out_path]
"""
import gzip
import struct
import sys
from pathlib import Path


def nalign(l: int) -> int:  # kernel 6.12 N_ALIGN
    return ((l + 1) & ~3) + 2


def newc_entry(name: bytes, data: bytes, mode: int = 0o100644, ino: int = 1) -> bytes:
    namesize = len(name) + 1  # include NUL
    header = struct.pack(
        '<6s8s8s8s8s8s8s8s8s8s8s8s8s8s',
        b'070701',
        f'{ino:08x}'.encode(),       # ino
        f'{mode:08x}'.encode(),      # mode
        b'00000000',                 # uid
        b'00000000',                 # gid
        b'00000001',                 # nlink
        b'00000000',                 # mtime
        f'{len(data):08x}'.encode(), # filesize
        b'00000000',                 # devmajor
        b'00000000',                 # devminor
        b'00000000',                 # rdevmajor
        b'00000000',                 # rdevminor
        f'{namesize:08x}'.encode(),  # namesize
        b'00000000',                 # check
    )
    assert len(header) == 110, len(header)
    name_field = name + b'\x00' + b'\x00' * (nalign(namesize) - namesize)
    assert len(name_field) == nalign(namesize)
    data_padded = data + b'\x00' * ((4 - len(data) % 4) % 4)
    return header + name_field + data_padded


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/tiny_initrd.cpio.gz')

    files = [
        (b'hello.txt', b'hello from tiny initrd\n', 0o100644),
        (b'init', b'#!/bin/sh\necho TINY_INITRD_BOOTED\nexit 0\n', 0o100755),
    ]
    archive = b''.join(newc_entry(name, data, mode=m) for name, data, m in files)
    archive += newc_entry(b'TRAILER!!!', b'')
    # newc convention: pad the archive tail to 4-byte alignment
    while len(archive) % 4:
        archive += b'\x00'
    print(f'cpio archive: {len(archive)} bytes')

    # verify with the kernel's parse convention (N_ALIGN)
    pos = 0
    n = 0
    while pos + 110 <= len(archive):
        if archive[pos:pos + 6] == b'070701':
            namesize = int(archive[pos + 94:pos + 102], 16)
            body_len = int(archive[pos + 54:pos + 62], 16)
            name = archive[pos + 110:pos + 110 + namesize - 1]
            nxt = pos + 110 + nalign(namesize) + body_len
            nxt = (nxt + 3) & ~3
            print(f'  entry {n}: {name!r} namesize={namesize} body={body_len} next={nxt}')
            n += 1
            pos = nxt
        else:
            if archive[pos] == 0:
                pos += 1
                continue
            print('  PARSER STOPPED at', pos, 'byte', archive[pos])
            break
    print(f'parsed {n} entries to pos {pos} of {len(archive)}')

    gz = gzip.compress(archive, compresslevel=9)
    out.write_bytes(gz)
    print(f'wrote {out} ({len(gz)} bytes)')

    back = gzip.decompress(gz)
    assert back == archive, 'roundtrip mismatch'
    print('roundtrip OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
