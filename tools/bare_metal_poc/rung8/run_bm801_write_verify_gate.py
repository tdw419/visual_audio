#!/usr/bin/env python3
"""run_bm801_write_verify_gate.py -- prove the read-back check can bite.

A verification step that has never been seen to fail is decoration. Each leg
below writes an image onto a file standing in for a medium, then breaks the
result in one of the ways ROADMAP names for real silicon -- partial write on
power loss, a controller that reports completion it did not earn -- and the leg
passes only if the tool catches it at the right offset. Legs 0a/0b come first
because the dangerous failure of this tool is not a wrong verdict, it is
writing somewhere it should not.

Everything here runs against ordinary files under a per-run mktemp -d. No loop
device, no mount, no /dev write, no substrate, no boot.

Run: python3 rung8/run_bm801_write_verify_gate.py        (~9 MiB of bakes)
"""

import json
import os
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'bm801_write_verify.py')
SRC_BYTES = 4 << 20
RESULTS = []


def say(kind, name, detail):
    print('%-4s %-22s %s' % (kind, name, detail))
    if kind in ('PASS', 'FAIL'):
        RESULTS.append((name, kind == 'PASS'))


def predict(name, text):
    print('--> %-20s predicts: %s' % (name, text))


def run(args, want_code=None):
    p = subprocess.run([sys.executable, TOOL] + args, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def make_source(path):
    """Deterministic, and not all-zero: a zero-filled image hides a zero-fill bug."""
    block = 4096
    with open(path, 'wb') as fh:
        for i in range(SRC_BYTES // block):
            fh.write(bytes((i * 7 + j) % 251 for j in range(block)))
    return path


def flip(path, off):
    """XOR one byte, through a descriptor opened for both directions."""
    fd = os.open(path, os.O_RDWR)
    try:
        os.pwrite(fd, bytes([os.pread(fd, 1, off)[0] ^ 0xFF]), off)
    finally:
        os.close(fd)


def main():
    run_dir = tempfile.mkdtemp(prefix='bm801_wv.')
    src = make_source(os.path.join(run_dir, 'gate-validated.raw'))
    print('# bm801 write-verify gate | run dir %s | source %s (%d B)' %
          (run_dir, os.path.basename(src), os.path.getsize(src)))
    try:
        # ---- leg 0a: the tool must not open a block device it was not told to
        devs = sorted('/dev/%s' % d for d in os.listdir('/dev')
                      if d.startswith('loop') and not d.startswith('loop-control')
                      and stat.S_ISBLK(os.stat('/dev/%s' % d).st_mode))
        predict('0a block-refusal', 'refusal by name, before any open, on a device this user '
                                    'could not write anyway -- so a PermissionError would prove the guard lost')
        if not devs:
            say('SKIP', '0a block-refusal', 'no /dev/loop* on this box: the leg did not run')
        else:
            dev = devs[0]
            writable = os.access(dev, os.W_OK)
            rc, out = run(['--source', src, '--target', dev])
            say('PASS' if (rc == 2 and 'REFUSE-BLOCK-DEVICE' in out and not writable) else 'FAIL',
                '0a block-refusal',
                '%s rc=%d guard-fired=%s os.access(W_OK)=%s %s' %
                (dev, rc, 'REFUSE-BLOCK-DEVICE' in out, writable,
                 '(the refusal is the tool talking, not the kernel)' if not writable
                 else '(W_OK says this user CAN write it, so only the guard stands between)'))

        # ---- leg 0b: a target under git is refused -- that is where the live VM's disk is
        predict('0b in-repo-refusal', 'rc=2, REFUSE-IN-REPO, and the path never created')
        inside = os.path.join(HERE, 'bm801_MUST_NOT_EXIST.raw')
        root = subprocess.run(['git', '-C', HERE, 'rev-parse', '--show-toplevel'],
                              capture_output=True, text=True)
        if root.returncode != 0:
            say('SKIP', '0b in-repo-refusal',
                '%s is not inside a git tree (an exported copy), so the guard has no repo to '
                'refuse -- the leg cannot mean anything here' % HERE)
        else:
            rc, out = run(['--source', src, '--target', inside])
            say('PASS' if rc == 2 and 'REFUSE-IN-REPO' in out and not os.path.exists(inside) else 'FAIL',
                '0b in-repo-refusal',
                'rc=%d refused=%s target-created=%s root=%s' %
                (rc, 'REFUSE-IN-REPO' in out, os.path.exists(inside), root.stdout.strip()))

        # ---- leg 1: clean bake verifies, and by digest not just by length
        predict('1 clean-bake', 'rc=0, VERIFIED, source and target digests equal')
        t = os.path.join(run_dir, 'm1.img')
        rc, out = run(['--source', src, '--target', t])
        rep = json.loads(out.splitlines()[0]) if out.startswith('{') else {}
        say('PASS' if rc == 0 and rep.get('ok') and
            rep['source_sha256'] == rep['target_sha256'] and rep['target_size'] == os.path.getsize(src)
            else 'FAIL', '1 clean-bake',
            'rc=%d ok=%s size=%d sha=%s...' % (rc, rep.get('ok'), rep.get('target_size', -1),
                                               str(rep.get('target_sha256'))[:12]))

        # ---- leg 2: a byte that changed after the sync (false completion, corrupted sector)
        predict('2 late-flip', 'rc=1 and first_mismatch == the offset that was flipped')
        off = (SRC_BYTES // 2) | 1
        flip(t, off)
        rc, out = run(['--source', src, '--target', t, '--verify-only'])
        rep = json.loads(out.splitlines()[0]) if out.startswith('{') else {}
        say('PASS' if rc == 1 and rep.get('first_mismatch') == off and rep.get('differing_bytes') == 1
            else 'FAIL', '2 late-flip',
            'rc=%d reported=%d flipped=%d n=%s' % (rc, rep.get('first_mismatch', -1), off,
                                                   rep.get('differing_bytes')))

        # ---- leg 3: the medium is smaller than the image (bad flash sector, short device)
        predict('3 truncated', 'rc=1, caught by length, differing bytes counted to the end')
        t3 = os.path.join(run_dir, 'm3.img')
        run(['--source', src, '--target', t3])
        os.truncate(t3, SRC_BYTES - 4096)
        rc, out = run(['--source', src, '--target', t3, '--verify-only'])
        rep = json.loads(out.splitlines()[0]) if out.startswith('{') else {}
        say('PASS' if rc == 1 and rep['target_size'] < rep['source_size'] else 'FAIL',
            '3 truncated', 'rc=%d sizes %s/%s first_mismatch=%s' %
            (rc, rep.get('source_size'), rep.get('target_size'), rep.get('first_mismatch')))

        # ---- leg 4: power loss mid-write -- dd itself stops short and reports success
        predict('4 short-write', 'rc=1; a bake that wrote 1 MiB of 4 must not be called verified')
        t4 = os.path.join(run_dir, 'm4.img')
        rc, out = run(['--source', src, '--target', t4, '--short-bytes', '1048576'])
        rep = json.loads(out.splitlines()[0]) if out.startswith('{') else {}
        say('PASS' if rc == 1 and rep['target_size'] == 1 << 20 else 'FAIL', '4 short-write',
            'rc=%d target_size=%d' % (rc, rep.get('target_size', -1)))

        # ---- leg 5: mutated through a second fd AFTER the sync returned 0
        predict('5 after-sync-mutation', 'rc=1 with the exact offset: dd said done, the read-back '
                                         'says otherwise, which is the whole point of the discipline')
        t5 = os.path.join(run_dir, 'm5.img')
        run(['--source', src, '--target', t5])
        fd = os.open(t5, os.O_WRONLY)          # opened before, written after the sync
        os.pwrite(fd, b'\x5a', SRC_BYTES - 7)
        os.close(fd)
        rc, out = run(['--source', src, '--target', t5, '--verify-only'])
        rep = json.loads(out.splitlines()[0]) if out.startswith('{') else {}
        say('PASS' if rc == 1 and rep.get('first_mismatch') == SRC_BYTES - 7 else 'FAIL',
            '5 after-sync-mutation', 'rc=%d reported=%s expected=%d' %
            (rc, rep.get('first_mismatch'), SRC_BYTES - 7))

        # ---- leg 6: the same discipline against a real gate-validated medium, if present
        real = os.path.join(HERE, '..', 'rung5', 'rung5_medium.raw')
        predict('6 real-medium', 'report-only: bake+cmp a ladder .raw; SKIP when the tree has no such '
                                 'artifact, so this gate still runs from the commit alone')
        if os.path.exists(real):
            size = os.path.getsize(real)
            t6 = os.path.join(run_dir, 'm6.img')
            rc, out = run(['--source', real, '--target', t6])
            rep = json.loads(out.splitlines()[0]) if out.startswith('{') else {}
            print('INFO 6 real-medium            %s %d B rc=%d ok=%s sha=%s...' %
                  (os.path.relpath(real, HERE), size, rc, rep.get('ok'),
                   str(rep.get('target_sha256'))[:12]))
        else:
            say('SKIP', '6 real-medium', '%s is not in this tree' % os.path.relpath(real, HERE))

        n_ok = sum(1 for _, ok in RESULTS if ok)
        print('RESULT %d/%d scored legs pass' % (n_ok, len(RESULTS)))
        return 0 if n_ok == len(RESULTS) else 1
    finally:
        subprocess.run(['rm', '-rf', run_dir])


if __name__ == '__main__':
    sys.exit(main())
