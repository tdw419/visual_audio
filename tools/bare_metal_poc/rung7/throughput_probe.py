#!/usr/bin/env python3
"""Measure raw NBD read throughput over the rung-1 pixel plugin (nbdkit)."""
import socket
import struct
import time

SOCK = '/tmp/r7_tp.sock'
SIZE = 28135424
CHUNK = 4096


def nbd_connect():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    # newstyle handshake: IHAVEOPT magic
    s.sendall(b'NBDMAGIC')
    s.sendall(struct.pack('>Q', 0x49484156454F5054))  # IHAVEOPT
    s.sendall(struct.pack('>I', 1))  # client flags: fixed newstyle? actually 1=NBD_FLAG_C_FIXED_NEWSTYLE
    magic = s.recv(8)
    assert magic == b'NBDMAGIC', magic
    return s


# simpler: shell out to qemu-io if present, else skip handshake subtleties
import subprocess
r = subprocess.run(['which', 'qemu-io'], capture_output=True, text=True)
if r.stdout.strip():
    t0 = time.time()
    p = subprocess.run(['qemu-io', '-f', 'raw', '-c',
                        f'read -v 0 {SIZE}', 'nbd:unix:' + SOCK],
                       capture_output=True, text=True)
    dt = time.time() - t0
    print('qemu-io rc', p.returncode, 'in %.2fs' % dt)
    print('throughput: %.0f KB/s' % (SIZE / 1024 / dt))
else:
    print('qemu-io not available')
