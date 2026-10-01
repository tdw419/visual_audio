#!/usr/bin/env python3
"""PROBE: is our ATA-PIO load actually correct?

Dump the two regions stage2 filled (kernel payload at 0x100000, initrd at
0x10000000) at the 0x100000 handoff stop and byte-compare against the medium's
own file bytes. If the images are right, the silence is a kernel-side problem;
if they are not, the differ's HdrS match was only proving the first 2 sectors
survived, not the 4.28 MB behind them.
"""
import atexit
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUNG9 = Path('/home/jericho/projects/zion/projects/visual_audio/tools/bare_metal_poc/rung9')
PORT = 12472
KERN_ADDR = 0x100000
INITRD_ADDR = 0x10000000
# HEAD dumped into the fixed directory /tmp/bm903_dbg and compared against it, so
# when gdb never ran the two dumps from 2026-09-19 were still there and the probe
# reported them as this boot's result. Per-run directory instead; the prefix keeps
# the 'bm903' substring bm903_lane.py:35 scans qemu argv for.
OUT = Path(tempfile.mkdtemp(prefix='bm903_dbg_'))
atexit.register(shutil.rmtree, OUT, ignore_errors=True)

print(f'dumps + logs in {OUT} (removed at exit)')
kern = (RUNG9 / 'vmlinuz64.extracted').read_bytes()
initrd = (RUNG9.parent / 'rung7' / 'core.gz').read_bytes()
payload_off = (kern[0x1f1] + 1) * 512
payload = kern[payload_off:]
print(f'expect: payload {len(payload)} B @ {KERN_ADDR:#x}, '
      f'initrd {len(initrd)} B @ {INITRD_ADDR:#x}')

cmds = [
    'set pagination off',
    'set architecture i386:x86-64',
    f'target remote :{PORT}',
    'hbreak *0x100000',
    'continue',
    f'dump binary memory {OUT}/kern.bin {KERN_ADDR:#x} {KERN_ADDR + len(payload):#x}',
    f'dump binary memory {OUT}/initrd.bin {INITRD_ADDR:#x} {INITRD_ADDR + len(initrd):#x}',
    'printf "DUMPED\\n"',
    'detach',
    'quit',
]
qemu = subprocess.Popen([
    'qemu-system-x86_64', '-M', 'pc', '-m', '512',
    '-drive', f'file={RUNG9}/bm903_medium.raw,format=raw,if=ide',
    '-display', 'none', '-no-reboot', '-no-shutdown',
    '-serial', f'file:{OUT}/serial2.log', '-S', '-gdb', f'tcp::{PORT}',
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
print('\n'.join(log.read_text().splitlines()[-6:]))

for name, want, got in (('kernel-payload', payload, OUT / 'kern.bin'),
                        ('initrd', initrd, OUT / 'initrd.bin')):
    p = Path(got)
    if not p.exists():
        print(f'{name}: NO DUMP (gdb failed)')
        continue
    have = p.read_bytes()
    if have == want:
        print(f'{name}: {len(have)} B BYTE-IDENTICAL to the medium')
        continue
    diffs = [i for i in range(min(len(have), len(want))) if have[i] != want[i]]
    print(f'{name}: {len(diffs)} diff(s) of {len(want)} B, '
          f'first at {diffs[0]:#x}' if diffs else f'{name}: length only '
          f'({len(have)} vs {len(want)})')
    for i in diffs[:8]:
        print(f'   {i:#08x} guest={have[i]:#04x} file={want[i]:#04x}')
