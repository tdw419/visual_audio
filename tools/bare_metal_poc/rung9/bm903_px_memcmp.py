#!/usr/bin/env python3
"""PROBE (BM903 step 2): did the PXC1 walk put the right bytes in RAM?

The CRC gate says the DECODED stream matched the expected digest, and the image
builder's replay says each sub-image owns its own group range. What the gate
cannot say on its own is that the store landed where the table said it should,
so this dumps all three destinations out of the running guest at the handoff
stop and byte-compares them against the host blobs:

  0x20000   kernel setup+header band  (sub-image 0 -- step 1 read this via
                                       int 13h; here it arrives by pixel walk)
  0x100000  protected-mode kernel      (sub-image 1)
  0x10000000 initrd                    (sub-image 2)

Shape copied from bm903_dbg_memcmp.py (the step-1 probe) with the medium and
the third region added; that file stays as step 1 left it.
"""
import atexit
import json
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUNG9 = Path('/home/jericho/projects/zion/projects/visual_audio/tools/bare_metal_poc/rung9')
MEDIUM = RUNG9 / 'bm903_medium_px.raw'
PORT = 12474
# HEAD used the fixed directory /tmp/bm903_px_memcmp and swept every *.bin out of
# it before dumping, which destroyed whatever a concurrent or earlier run had left
# there (13.5 MB of Sep-19 dumps, plus any foreign file sharing the name). Per-run
# directory instead, so the sweep is unnecessary; the prefix keeps the 'bm903'
# substring bm903_lane.py:35 scans qemu argv for.
OUT = Path(tempfile.mkdtemp(prefix='bm903_px_memcmp_'))
atexit.register(shutil.rmtree, OUT, ignore_errors=True)

kern = (RUNG9 / 'vmlinuz64.extracted').read_bytes()
initrd = (RUNG9.parent / 'rung7' / 'core.gz').read_bytes()
setup_bytes = (kern[0x1f1] + 1) * 512
REGIONS = [
    ('header band @0x20000',  0x20000,     kern[:setup_bytes]),
    ('kernel pm  @0x100000',  0x100000,    kern[setup_bytes:]),
    ('initrd     @0x10000000', 0x10000000, initrd),
]
# The guest's own destination table, read from the generated .inc the loader
# %includes -- so this probe checks the SAME numbers the loader used.
inc = (RUNG9 / 'bm903_px_layout.inc').read_text()
d = {m.group(1): int(m.group(2), 0)
     for m in re.finditer(r'^%define (\w+) (-?0x[0-9A-Fa-f]+|\d+)$', inc, re.M)}
assert d['SUB0_DEST'] == 0x20000 and d['SUB1_DEST'] == 0x100000 \
    and d['SUB2_DEST'] == 0x10000000, 'probe regions drifted from the .inc table'

sys.path.insert(0, str(RUNG9))
import bm903_lane
if bm903_lane.live_boots():
    sys.exit('lane busy: another bm903 boot is alive (bm903_lane.py)')

cmds = ['set pagination off', 'set architecture i386:x86-64',
        f'target remote :{PORT}', 'hbreak *0x100000', 'continue']
for i, (_, addr, blob) in enumerate(REGIONS):
    cmds.append(f'dump binary memory {OUT}/r{i}.bin {addr:#x} {addr + len(blob):#x}')
cmds += ['printf "DUMPED\\n"', 'detach', 'quit']

qemu = subprocess.Popen([
    'qemu-system-x86_64', '-M', 'pc', '-m', '512',
    '-drive', f'file={MEDIUM},format=raw,if=ide',
    '-display', 'none', '-no-reboot', '-no-shutdown',
    '-serial', f'file:{OUT}/serial.log', '-S', '-gdb', f'tcp::{PORT}',
], stdout=subprocess.DEVNULL, stderr=open(OUT / 'qemu.log', 'w'))
time.sleep(1.5)
log = OUT / 'gdb.log'
try:
    with open(log, 'w') as f:
        subprocess.call(['timeout', '-s', 'KILL', '300', 'gdb', '-batch', '-nx'] +
                        sum([['-ex', c] for c in cmds], []),
                        stdout=f, stderr=subprocess.STDOUT)
finally:
    qemu.send_signal(signal.SIGTERM)
    try:
        qemu.wait(timeout=10)
    except subprocess.TimeoutExpired:
        qemu.kill()
        qemu.wait(timeout=10)

rc = 0
for i, (name, addr, want) in enumerate(REGIONS):
    p = OUT / f'r{i}.bin'
    if not p.exists():
        print(f'{name}: NO DUMP -- gdb never stopped? see {log} '
              f'(this run\'s dir is removed at exit)')
        rc = 1
        continue
    have = p.read_bytes()
    if have == want:
        print(f'{name}: {len(have)} B BYTE-IDENTICAL to the host blob')
        continue
    diffs = [j for j in range(min(len(have), len(want))) if have[j] != want[j]]
    print(f'{name}: RED, {len(diffs)} differing byte(s) of {len(want)}'
          + (f', first at {diffs[0]:#x}' if diffs else ' (length only)'))
    rc = 1
print('MEMCMP', 'PASS' if rc == 0 else 'FAIL', f'({sum(len(w) for _,_,w in REGIONS)} B '
      f'of guest RAM compared against {MEDIUM.name})')
sys.exit(rc)
