#!/usr/bin/env python3
"""Build the GPU-shell LNX container (h12).

Takes the canonical Alpine LNX blob, extracts its real initramfs (the gzip
stream past the 32MB kernel padding — see the offset fix in
boot_alpine_gpu_fixed.py), overlays a shell-init cpio (newc concat: later
archives overwrite earlier entries), and repacks the container with the
new gzip stream at the same 32MB boundary. The canonical blob and the
frozen BOOT_SMOKE md5 gate are never touched.

Usage:
    python3 tools/build_gpu_shell_blob.py -o /tmp/h12/alpine_shell.lnx.bin
    python3 tools/boot_offload_alpine.py --allow-missing-disk \
        --kernel /tmp/h12/alpine_shell.lnx.bin --max-steps 1500000000
"""
from __future__ import annotations

import argparse
import gzip
import io
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
CANONICAL = _REPO / "boot_images/alpine_riscv64.lnx.bin"
INITRD_MIN_OFFSET = 0x1000000   # gzip stream lives past the 32MB-padded kernel
INITRD_OFF = 0x2000000          # canonical container places it exactly here

# The overlay init: mounts the pseudo-filesystems, prints a scripted
# "getting started" session (write, read back, list, compute), then drops
# into the interactive busybox shell on the serial console.
INIT = """#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
B=/bin/busybox
$B mount -t proc proc /proc 2>/dev/null
$B mount -t sysfs sysfs /sys 2>/dev/null
# Expose every busybox applet as a real command so typed input works:
$B --install -s /bin 2>/dev/null
for a in ls cat free uname date ps mkdir echo grep find vi cp mv touch head tail ln sleep; do
  [ -e /bin/$a ] || $B ln -s /bin/busybox /bin/$a
done
echo
echo "=============================================="
echo "  GPU userspace shell - Alpine Linux on RISC-V"
echo "  running on the WGSL GPU RV64 core"
echo "=============================================="
echo
echo "gpu-rv64:~# uname -a"
$B uname -a
echo
echo "gpu-rv64:~# head -3 /proc/cpuinfo"
$B head -3 /proc/cpuinfo
echo
echo "gpu-rv64:~# echo 'hello GPU' > note.txt && cat note.txt"
echo 'hello GPU' > note.txt
$B cat note.txt
echo
echo "gpu-rv64:~# ls /"
$B ls /
echo
echo "gpu-rv64:~# expr 40 + 2"
$B expr 40 + 2
echo
echo "gpu-rv64:~# uptime"
$B uptime
echo
echo "--- interactive shell: type a command ---"
# The UART runs without an RX IRQ (no interrupt in the DTB), so pending RX
# bytes are only drained by the 8250 driver during console TX. A background
# flusher emits CRs to keep that drain flowing while `read` blocks.
( while :; do sleep 1; printf '\\r' > /dev/console; done ) &
while :; do
  printf 'gpu-rv64:~# '
  read line
  eval "$line"
done
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--canonical", default=str(CANONICAL))
    args = ap.parse_args()

    d = Path(args.canonical).read_bytes()
    assert d[:4] == b"LNX\x00", f"not an LNX container: {args.canonical}"
    ko, ks, irs = struct.unpack("<III", d[4:16])

    gz_off = d.find(b"\x1f\x8b\x08", INITRD_MIN_OFFSET)
    if gz_off < 0:
        raise SystemExit("no initramfs gzip stream in LNX container")
    initramfs_gz = d[gz_off:gz_off + irs]
    base_cpio = gzip.decompress(initramfs_gz)

    with tempfile.TemporaryDirectory() as td:
        ov = Path(td) / "overlay"
        (ov / "dev").mkdir(parents=True)
        init = ov / "init"
        init.write_text(INIT)
        os.chmod(init, 0o755)
        frag = subprocess.run(
            f'cd "{ov}" && find . | cpio -o -H newc --quiet',
            shell=True, check=True, capture_output=True).stdout
    new_cpio = base_cpio + frag

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
        f.write(new_cpio)
    new_gz = buf.getvalue()

    out = bytearray(len(d))
    out[: INITRD_OFF] = d[: INITRD_OFF]
    need = INITRD_OFF + len(new_gz)
    if need > len(out):
        out.extend(b"\x00" * (need - len(out)))
    out[INITRD_OFF: need] = new_gz
    struct.pack_into("<I", out, 12, len(new_gz))  # header irs = new length

    Path(args.output).write_bytes(out)
    print(f"wrote {args.output}: {len(out):,} bytes "
          f"(initramfs {len(initramfs_gz):,} -> {len(new_gz):,} bytes gz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
