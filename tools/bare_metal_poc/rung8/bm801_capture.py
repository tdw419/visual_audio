#!/usr/bin/env python3
"""bm801_capture.py -- boot a medium headless and take one text-mode screendump.

Everything the receipt channel knows about the guest arrives as pixels, so this
is the only thing standing between a real box and a false 'it booted'. It is
deliberately hostile to leftovers: the scratch dir, monitor socket and PPM are
per-run mktemp names, and the only process ever signalled is the one Popen
returned -- never a pgrep sweep, which is how another lane's boot dies.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

QEMU = 'qemu-system-x86_64'


class CaptureError(Exception):
    pass


def _rpc(sock_path, line, timeout=6.0):
    deadline = time.time() + timeout
    conn = None
    while conn is None and time.time() < deadline:
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.connect(sock_path)
        except OSError:
            conn.close()
            conn = None
            time.sleep(0.25)
    if conn is None:
        raise CaptureError('no monitor at %s within %.1fs' % (sock_path, timeout))
    conn.settimeout(timeout)
    try:
        conn.sendall((line + '\n').encode())
        time.sleep(0.4)
        buf = b''
        while True:
            try:
                d = conn.recv(65536)
            except socket.timeout:
                break
            if not d:
                break
            buf += d
    finally:
        conn.close()
    return buf


def capture(image, settle=4.0, run_dir=None, keep=False, extra=()):
    """Boot `image` read-only, return the path of a 720x400 text-mode PPM.

    `-snapshot` means the medium is never written: the frame is a receipt about
    a boot, not an intervention in it. `extra` lets a caller add qemu arguments
    (never a -drive, which this function owns).
    """
    run_dir = run_dir or tempfile.mkdtemp(prefix='bm801_cap.')
    os.makedirs(run_dir, exist_ok=True)
    # every name in this run is per-process: no socket, PPM or scratch dir is
    # shared with another boot on this box
    sock_path = os.path.join(run_dir, 'mon-%d.sock' % os.getpid())
    out = os.path.join(run_dir, 'screen.ppm')
    for p in (sock_path, out):
        if os.path.exists(p):
            os.unlink(p)
    cmd = [QEMU, '-display', 'none', '-vga', 'std',
           '-monitor', 'unix:%s,server,nowait' % sock_path,
           '-drive', 'file=%s,format=raw,if=ide' % image,
           '-snapshot', '-boot', 'c', '-m', '16',
           '-no-reboot', '-serial', 'null'] + list(extra)
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        t0 = time.time()
        while time.time() - t0 < settle:
            if proc.poll() is not None:
                raise CaptureError('qemu exited rc=%s: %s' %
                                   (proc.returncode, proc.stderr.read()[-400:].decode('utf8', 'replace')))
            time.sleep(0.2)
        reply = _rpc(sock_path, 'screendump %s' % out)
        if not os.path.exists(out):
            raise CaptureError('screendump wrote nothing; monitor said %r' % reply[-200:])
        return out
    finally:
        try:
            _rpc(sock_path, 'quit', timeout=3.0)
        except CaptureError:
            pass
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        if not keep:
            try:
                os.unlink(out)
            except OSError:
                pass


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    dst = sys.argv[2] if len(sys.argv) > 2 else 'screen.ppm'
    src = capture(sys.argv[1], settle=float(sys.argv[3]) if len(sys.argv) > 3 else 4.0, keep=True)
    shutil.move(src, dst)
    print(dst)
