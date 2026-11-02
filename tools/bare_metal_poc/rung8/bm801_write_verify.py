#!/usr/bin/env python3
"""bm801_write_verify.py -- ROADMAP's pre-registered BM801 discipline, as a tool.

The row says: after `dd` + sync, read the physical medium back and `cmp` against
the gate-validated `.raw` BEFORE any boot attempt. Never boot an unverified
medium. This is that sentence, so the discipline is a command rather than a
paragraph someone remembers at the box.

Two refusals come before any write, because the target of this tool is a device
that may hold something else's data:

  REFUSE-BLOCK-DEVICE  a block-device target needs --device said out loud
  REFUSE-IN-REPO       a target inside the repository working tree is refused

The second is the guardrail that matters most on this box: the live pixel VM's
only disk is `ubuntu_desktop_pxc1_v3_selfhost/`, and it is a file in a directory
under git. A bake tool that will write anywhere its argument points is one typo
from destroying a running guest.

Exit codes: 0 verified, 1 MISMATCH (medium is not the image -- do not boot it),
2 refused before writing, 3 the tool itself failed.
"""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys

REFUSE_BLOCK = 'REFUSE-BLOCK-DEVICE'
REFUSE_REPO = 'REFUSE-IN-REPO'
CHUNK = 1 << 20


def repo_root(path=None):
    """The ladder's git root, resolved by asking git rather than by counting '..'s."""
    out = subprocess.run(['git', '-C', path or os.path.dirname(os.path.abspath(__file__)),
                          'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True)
    return os.path.realpath(out.stdout.strip()) if out.returncode == 0 else None


def is_block_device(path):
    try:
        return stat.S_ISBLK(os.stat(path).st_mode)
    except FileNotFoundError:
        return False


def refuse(target, allow_device, allow_repo, here):
    """Return (label, detail) if this target must not be written, else (None, ...)."""
    real = os.path.realpath(target)
    root = repo_root(here)
    if root and (real == root or real.startswith(root + os.sep)):
        if not allow_repo:
            return REFUSE_REPO, ('%s resolves inside the repository tree %s; the live '
                                 'pixel VM disk and every validated medium live there' % (real, root))
    if is_block_device(real) and not allow_device:
        return REFUSE_BLOCK, ('%s is a block device; pass --device to write it' % real)
    return None, ''


def digest(path, length=None):
    h = hashlib.sha256()
    read = 0
    with open(path, 'rb') as fh:
        while True:
            buf = fh.read(CHUNK)
            if not buf:
                break
            h.update(buf)
            read += len(buf)
            if length is not None and read >= length:
                break
    return h.hexdigest(), read


def bake(source, target, block_size=4 << 20, count_bytes=None):
    """`dd` the image onto the target and force it out, the way the row says.

    conv=fsync plus a bare `sync`: the completion the firmware reports is a
    claim, and the read-back below is the only thing that checks it.
    `count_bytes` exists so a gate can reproduce a short write on purpose.
    """
    cmd = ['dd', 'if=%s' % source, 'of=%s' % target, 'bs=%d' % block_size, 'conv=fsync']
    if count_bytes is not None:
        block_size = 4096                     # so a short write is short to the byte, not the block
        cmd[3] = 'bs=%d' % block_size
        cmd.append('count=%d' % -(-count_bytes // block_size))
    cmd.append('status=none')
    subprocess.run(cmd, check=True)
    subprocess.run(['sync'], check=True)


def compare(source, target):
    """Byte-exact read-back. Returns a dict; 'ok' is the only answer that permits a boot."""
    ssz, tsz = os.path.getsize(source), os.path.getsize(target)
    first = None
    differing = 0
    off = 0
    with open(source, 'rb') as fs, open(target, 'rb') as ft:
        while True:
            a, b = fs.read(CHUNK), ft.read(CHUNK)
            n = max(len(a), len(b))
            if not n:
                break
            a, b = a.ljust(n, b'\0'), b.ljust(n, b'\0')
            for i in range(n):
                if a[i] != b[i]:
                    differing += 1
                    if first is None:
                        first = off + i
            off += n
    th, tread = digest(target)
    sh, sread = digest(source)
    return {
        'ok': first is None and ssz == tsz and tread == tsz and sh == th,
        'source_size': ssz, 'target_size': tsz,
        'short_read': tsz - tread,
        'first_mismatch': first, 'differing_bytes': differing,
        'source_sha256': sh, 'target_sha256': th,
    }


def main(argv=None):
    me = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--source', required=True, help='the gate-validated .raw to bake')
    ap.add_argument('--target', required=True, help='medium, file, or device to bake onto')
    ap.add_argument('--device', action='store_true', help='permit a block-device target')
    ap.add_argument('--allow-in-repo', action='store_true', help='permit a target under git')
    ap.add_argument('--verify-only', action='store_true', help='skip the bake; read back and cmp')
    ap.add_argument('--short-bytes', type=int, default=None,
                    help='bake only this many bytes -- a test hook, and it must be caught')
    a = ap.parse_args(argv)

    label, detail = refuse(a.target, a.device, a.allow_in_repo, me)
    if label:
        print('%s %s' % (label, detail))
        return 2
    if not os.path.exists(a.source):
        print('no such source: %s' % a.source)
        return 3
    if os.path.realpath(a.source) == os.path.realpath(a.target):
        print('source and target are the same file')
        return 2

    if not a.verify_only:
        bake(a.source, a.target, count_bytes=a.short_bytes)
    rep = compare(a.source, a.target)
    rep['baked'] = not a.verify_only
    rep['short_bake_bytes'] = a.short_bytes
    print(json.dumps(rep, sort_keys=True))
    if rep['ok']:
        print('VERIFIED %s == %s (%d B); the medium may be booted' %
              (a.target, a.source, rep['target_size']))
        return 0
    print('MISMATCH first diff at %s, %d byte(s) differ, sizes %d/%d; NEVER BOOT THIS MEDIUM' %
          (rep['first_mismatch'], rep['differing_bytes'], rep['source_size'], rep['target_size']))
    return 1


if __name__ == '__main__':
    sys.exit(main())
