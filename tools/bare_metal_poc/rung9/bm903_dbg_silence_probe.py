#!/usr/bin/env python3
"""PROBE (not a gate artifact): why is the kernel silent after our handoff?

The step-1 medium reaches BM903-S2 HANDOFF BUILT and jumps, but 170 s of wall
clock buys no serial byte. The pinned cmdline carries loglevel=3, which
suppresses every kernel message above KERN_CRIT, so silence is not evidence.
This probe keeps the pinned build untouched and rewrites the cmdline buffer
IN GUEST MEMORY at the 0x100000 stop (after the frozen dumps are already
taken by bm903_capture.py), adding loglevel=8 + earlyprintk, then lets the
kernel run. If it is alive we get a trace; if it dies we get the last words.
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
DBG = (b'loglevel=8 earlyprintk=ttyS0,115200 keep_bootcon cde '
       b'console=ttyS0,115200 initrd=/boot/core.gz BOOT_IMAGE=/boot/vmlinuz')
CMD_ADDR = 0x1f800
BUF = DBG + b'\0' * (256 - len(DBG))
PORT = 12470
RUN_S = int(sys.argv[1]) if len(sys.argv) > 1 else 90

# HEAD wrote /tmp/bm903_dbg_cmd.bin and read /tmp/bm903_dbg_{serial,gdb}.log back out
# of fixed names, so an inert rig still printed the 2026-09-19 transcript and
# restored a stale cmdline; :28 also unlinked another run's serial log. One per-run
# directory instead, removed at exit.
RUN_DIR = Path(tempfile.mkdtemp(prefix='bm903_dbg_silence_'))
atexit.register(shutil.rmtree, RUN_DIR, ignore_errors=True)
CMD_BIN = RUN_DIR / 'cmd.bin'
CMD_BIN.write_bytes(BUF)
serial = RUN_DIR / 'serial.log'

cmds = [
    'set pagination off',
    'set architecture i386:x86-64',
    f'target remote :{PORT}',
    'hbreak *0x100000',
    'continue',
    'printf "=== handoff seen rsi=0x%x, rewriting cmdline ===\\n", $rsi',
    f'restore {CMD_BIN} binary {hex(CMD_ADDR)}',
    'x/s ' + hex(CMD_ADDR),
    'continue',
]
qemu = subprocess.Popen([
    'qemu-system-x86_64', '-M', 'pc', '-m', '512',
    '-drive', f'file={RUNG9}/bm903_medium.raw,format=raw,if=ide',
    '-display', 'none', '-no-reboot', '-no-shutdown',
    '-serial', f'file:{serial}', '-S', '-gdb', f'tcp::{PORT}',
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
log = RUN_DIR / 'gdb.log'
try:
    with open(log, 'w') as f:
        subprocess.call(['timeout', '-s', 'KILL', str(RUN_S), 'gdb', '-batch', '-nx'] +
                        sum([['-ex', c] for c in cmds], []),
                        stdout=f, stderr=subprocess.STDOUT)
finally:
    qemu.send_signal(signal.SIGTERM)
    try:
        qemu.wait(timeout=10)
    except subprocess.TimeoutExpired:
        qemu.kill()
        qemu.wait(timeout=10)

print('--- gdb tail ---')
print('\n'.join(log.read_text().splitlines()[-12:]))
if serial.exists():
    print(f'--- serial ({serial.stat().st_size} B) ---')
    txt = serial.read_text()
    print(txt[:6000])
    if len(txt) > 6000:
        print(f'... [{len(txt) - 6000} more chars] ...')
        print(txt[-3000:])
