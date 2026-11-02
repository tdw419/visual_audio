#!/usr/bin/env python3
"""BM903 step 2/3 probe: boot a medium with NO debugger attached and report
whether the serial transcript reaches the TinyCore anchor, with the elapsed
seconds and the stage2 checkpoint lines.

  usage: bm903_anchor_boot.py <medium> <log> [budget_s]

The wall-clock budget is the judge: no anchor inside it is a FAIL naming the
budget, never "probably still running". Both BM903 media (step-1 contiguous and
step-2 pixel) go through here so a control and a leg differ only by the file
they boot.
"""
import re
import subprocess
import sys
import time
from pathlib import Path

RUNG9 = Path(__file__).resolve().parent
MEDIUM = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNG9 / "bm903_medium_px.raw"
LOG = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/bm903_anchor_boot.log")
DUE = float(sys.argv[3]) if len(sys.argv) > 3 else 240.0

CHECKS = [('walk done', r'BM903-S2 PIXEL WALK DONE'),
          ('gate line', r'BM903-S2 GATE2 CRC=([0-9A-F]{8}) EXP=([0-9A-F]{8})'),
          ('pass verdict', r'BM903-S2 GATE2=PASS'),
          ('handoff', r'BM903-S2 HANDOFF BUILT'),
          ('anchor', r'tc@box')]
# Wall-clock when each marker FIRST appears: where the boot spends its time is
# the difference between "the walk is slow" and "the kernel stalled".
TRACE = [('stage2 enter', r'BM903-S2 ENTER'),
         ('a20 ok', r'BM903-S2 A20 OK'),
         ('walk done', r'BM903-S2 PIXEL WALK DONE'),
         ('gate verdict', r'BM903-S2 GATE2=(?:CRC|PASS|FAIL)'),
         ('handoff', r'BM903-S2 HANDOFF BUILT'),
         ('busybox init', r'init started: BusyBox'),
         ('extensions', r'Loading extensions'),
         ('login msg', r"login\[\d+\]: root login"),
         ('anchor', r'tc@box')]

sys.path.insert(0, str(RUNG9))
import bm903_lane
if bm903_lane.live_boots():
    sys.exit('lane busy: another bm903 boot is alive (bm903_lane.py)')
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_bytes(b'')                  # truncate BEFORE qemu opens it
qemu = subprocess.Popen(['qemu-system-x86_64', '-M', 'pc', '-m', '512',
                         '-drive', f'file={MEDIUM},format=raw,if=ide',
                         '-display', 'none', '-no-reboot', '-no-shutdown',
                         '-serial', f'file:{LOG}'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
t0 = time.time()
seen_at = {}
try:
    while time.time() - t0 < DUE:
        time.sleep(1.0)
        blob = LOG.read_bytes().decode('latin-1')
        for name, pat in TRACE:
            if name not in seen_at and re.search(pat, blob):
                seen_at[name] = time.time() - t0
                print(f'  [+{seen_at[name]:6.1f}s] {name}')
        if re.search(CHECKS[-1][1], blob) or 'GATE2=FAIL' in blob:
            break
    blob = LOG.read_bytes().decode('latin-1')
finally:
    qemu.terminate()
    try:
        qemu.wait(timeout=10)
    except subprocess.TimeoutExpired:
        qemu.kill()
        qemu.wait(timeout=10)

elapsed = time.time() - t0
rc = 0
px = 'px' in MEDIUM.name              # the pixel medium owes us the gate lines
for name, pat in CHECKS:
    if name in ('walk done', 'gate line', 'pass verdict') and not px:
        continue
    m = re.search(pat, blob)
    print(f'  {name:12} {"seen" if m else "MISSING"}')
    rc |= 0 if m else 1
    if m and name == 'gate line':
        got, exp = m.group(1), m.group(2)
        print(f'               computed={got} expected={exp} '
              f'{"MATCH" if got == exp else "MISMATCH"}')
        rc |= 0 if got == exp else 1
print(f'medium={MEDIUM.name} log={LOG} elapsed={elapsed:.1f}s rc={rc}')
if '-v' in sys.argv:
    print('  --- transcript ---')
    for line in blob.splitlines():
        print('   ', line[:160])
sys.exit(rc)
