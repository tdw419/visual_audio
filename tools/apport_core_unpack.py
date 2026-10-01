#!/usr/bin/env python3
"""Unpack the core dump out of an apport .crash report.

Written 2026-09-13 for DEFECT-22 (intermittent SIGSEGV inside GlyphCPUv2.step):
the ticket had recorded "a core file is not the practical route" after seeing
`ulimit -c 0`; the report on disk proved otherwise.  /var/crash holds a full
557 MB report (1.19 GB decompressed core) for the 05:18:10 arc-leg-A crash,
matching output/arc_legA_194844c_run2.txt to the second.

Format notes (measured, two wrong attempts before this worked):
  * `CoreDump: base64` is the LAST field of the report, and its payload is NOT a
    single base64 stream — apport writes it as a sequence of *independently*
    encoded base64 chunks, one per line, each prefixed with a single space.
    Concatenating the chunks and decoding once corrupts the stream
    ("invalid code lengths set"); decode each line separately and concatenate
    the BYTES.
  * The decoded payload is a gzip stream; it inflates to an ELF core.

Usage:
    python3 tools/apport_core_unpack.py <report.crash> <out.core>
Then:
    gdb -batch -q -ex "set pagination off" -ex "info threads" -ex "bt 22" \\
        /usr/bin/python3 <out.core>

Verified on /var/crash/_usr_lib_python3_dist-packages_pytest___init__.py.1000.crash
-> 417,704,731 B gzip -> 1,193,254,912 B ELF core, gdb loads it and reports
SIGSEGV with the faulthandler re-raise frames.
"""
import base64
import os
import sys
import zlib

MARKER = b"\nCoreDump: base64\n"


def extract(src: str, dst: str) -> int:
    with open(src, "rb") as f:
        blob = f.read()
    i = blob.find(MARKER)
    if i < 0:
        raise SystemExit("CoreDump field not found (not an apport report?)")
    region = blob[i + len(MARKER):]
    chunks = []
    for line in region.split(b"\n"):
        if line == b"":
            continue
        if not line.startswith(b" "):
            break  # next header field (or EOF)
        chunks.append(base64.b64decode(line[1:]))
    raw = b"".join(chunks)
    if raw[:2] != b"\x1f\x8b":
        raise SystemExit(f"decoded payload is not gzip (magic={raw[:4]!r})")
    d = zlib.decompressobj(31)  # gzip wrapper
    total = 0
    with open(dst, "wb") as out:
        for off in range(0, len(raw), 1 << 20):
            data = d.decompress(raw[off:off + (1 << 20)])
            if data:
                out.write(data)
                total += len(data)
            if d.eof:
                break
        out.write(d.flush())
    with open(dst, "rb") as f:
        magic = f.read(4)
    if magic != b"\x7fELF":
        print(f"WARNING: recovered file does not start with an ELF magic ({magic!r})")
    return total


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    n = extract(src, dst)
    print(f"core: {src} -> {dst} ({os.path.getsize(dst)} B on disk, {n} B inflated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
