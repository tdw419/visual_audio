#!/usr/bin/env python3
"""MEASURE the Tiny Core autologin race, per medium.

L3 went RED on the pixel medium in run 3 while the step-1 medium went GREEN in
the same run. The initrd source says why (extracted to /tmp/bm903_initrd):

    # /etc/inittab — both lines exec the SAME autologin:
    tty1::respawn:/sbin/getty -nl /sbin/autologin 38400 tty1
    ttyS0::respawn:/sbin/getty -nl /sbin/autologin 115200 ttyS0

    # /sbin/autologin
    if [ -f /var/log/autologin ] ; then exec /sbin/getty 38400 tty1
    else touch /var/log/autologin; exec login -f root; fi

Whichever getty reaches the `touch` first owns `login -f root`, and login prints
its own controlling terminal into the syslog line that both cases emit on
serial: `root login on 'ttyS0'` (the serial console gets the banner and the
tc@box prompt) or `root login on 'tty1'` (serial goes silent forever — the loser
re-execs onto tty1, so no prompt is ever drawn on ttyS0).

So 'tc@box on serial' is a guest-side scheduling outcome, not a property of our
loader. This probe measures the rate per medium instead of guessing: N boots,
short budget, one line each, and it never runs beside another bm903 boot.

usage: bm903_tty_race.py <medium>... -n <reps> [-b budget_s]
"""
import atexit
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'tools' / 'bare_metal_poc' / 'rung9'
QEMU = 'qemu-system-x86_64'
# EXTRA_QEMU='-vga none' lets one probe answer "does the device model decide the
# winner?" without duplicating the boot loop.
EXTRA = [a for a in __import__('os').environ.get('EXTRA_QEMU', '').split() if a]
WIN = re.compile(rb"login on '(\w+)'")


def boot(medium: Path, log: Path, budget: int) -> dict:
    qemu = subprocess.Popen(
        [QEMU, '-M', 'pc', '-m', '512',
         '-drive', f'file={medium},format=raw,if=ide',
         '-display', 'none', '-no-reboot', '-no-shutdown',
         '-serial', f'file:{log}'] + EXTRA,
        stdout=subprocess.DEVNULL,
        stderr=open(f'{log}.qemu.err', 'w'))
    t0 = time.time()
    anchor_at = None
    logins = []
    try:
        while time.time() - t0 < budget:
            time.sleep(0.5)
            if not log.exists():
                continue
            blob = log.read_bytes()
            logins = [m.decode() for m in re.findall(rb"login on '(\w+)'", blob)]
            if b'tc@box' in blob and anchor_at is None:
                anchor_at = time.time() - t0      # keep polling: the prompt is
                #    not the end of the story, and cutting early here would hide
                #    how long the SECOND respawn cycle takes when it loses.
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=10)
        except subprocess.TimeoutExpired:
            qemu.kill()
            qemu.wait(timeout=10)
    return {'anchor': anchor_at, 'logins': logins,
            't': time.time() - t0,
            'bytes': log.stat().st_size if log.exists() else 0}


def main(argv: list) -> int:
    args = [a for a in argv[1:]]
    reps, budget, media = 6, 45, []
    while args:
        a = args.pop(0)
        if a == '-n':
            reps = int(args.pop(0))
        elif a == '-b':
            budget = int(args.pop(0))
        else:
            media.append(Path(a).resolve())
    assert media, __doc__
    lane_py = (HERE / 'bm903_lane.py') if (HERE / 'bm903_lane.py').exists() \
        else RUNG9 / 'bm903_lane.py'
    lane = subprocess.run([sys.executable, str(lane_py)],
                          capture_output=True, text=True)
    print(lane.stdout.strip() + (f'  extra qemu args: {EXTRA}' if EXTRA else ''))
    if lane.returncode != 0:
        return 3
    # HEAD wrote /tmp/bm903_race_{med.stem}_{i}.log — unique inside one invocation,
    # fixed across invocations — and boot() unlinked that name first, so a second
    # run deleted the first one's transcripts mid-flight. Per-run directory instead;
    # the prefix keeps the 'bm903' substring bm903_lane.py:35 scans qemu argv for.
    run_dir = Path(tempfile.mkdtemp(prefix='bm903_race_'))
    atexit.register(shutil.rmtree, run_dir, ignore_errors=True)
    print(f'serial transcripts in {run_dir} (removed at exit)')
    tally = {}
    for i in range(reps):                     # interleave the media: host load
        for med in media:                     # is then a shared condition
            r = boot(med, run_dir / f'{med.stem}_{i}.log', budget)
            a = r['anchor']
            verdict = f'anchor @{a:5.1f}s' if a else f'NO ANCHOR in {budget}s'
            tally[(med.name, bool(a))] = tally.get((med.name, bool(a)), 0) + 1
            print(f'{med.name:22} boot {i}: {verdict}  '
                  f'logins={"→".join(r["logins"]) or "none":28} '
                  f'{r["bytes"]} B', flush=True)
    print('--- summary ---')
    for (name, hit), n in sorted(tally.items()):
        print(f'  {name:22} anchor={"yes" if hit else "no ":3} x{n}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
