#!/usr/bin/env python3
"""BM802 probe: boot a medium and report HOW FAR it got, as one machine-
readable verdict. Sensitivity needs a graded result, not a coin flip.

Why not `tc@box`: BM903 measured that which console draws the Tiny Core prompt
is a guest-side race (tty1 and ttyS0 through one /sbin/autologin flag file,
5/8 on serial), so "no prompt" would be a false SENSITIVE an eighth of the time.
The markers below all appear BEFORE that race, on every boot of a healthy
kernel, so the ladder is deterministic and the prompt is recorded only as a
bonus column.

  stage 0  silence        nothing on serial inside the budget
  stage 1  refuse         the CRC gate said no -- the payload is known-bad and
                          the loader never jumps
  stage 2  handoff        BM903-S2 HANDOFF BUILT -- the loader built the
                          protocol handoff and jumped
  stage 3  init           "init started: BusyBox" -- kernel decompressed, ran
                          /init, so the initrd was readable
  stage 4  extensions     "Loading extensions" -- deep into the boot scripts
  stage 5  hostname       "Setting hostname to box" -- boot scripts finished
  stage 6  prompt         tc@box (race-dependent, NOT required)

  usage: bm802_boot_class.py <medium> <log> [budget_s]   -> one VERDICT line
  library: from bm802_boot_class import run_boot
"""
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
sys.path.insert(0, str(RUNG9))
import bm903_lane                                       # noqa: E402

STAGES = [('handoff', r'BM903-S2 HANDOFF BUILT', 2),
          ('init', r'init started: BusyBox', 3),
          ('extensions', r'Loading extensions', 4),
          ('hostname', r'Setting hostname to', 5),
          ('prompt', r'tc@box', 6)]
DIAG = [('kernel panic', r'Kernel panic'),
        ('oops', r'Oops|general protection|invalid opcode'),
        ('initrd corrupt', r'not a valid|broken|gzip|decompression'),
        ('no rootfs', r'VFS: Unable to mount root fs'),
        ('gate line', r'BM903-S2 GATE2 CRC=([0-9A-F]{8}) EXP=([0-9A-F]{8})')]
CEILING = 5                        # stage 5 is what a healthy boot always shows


class LaneBusy(Exception):
    """Another boot is alive; a leg run beside it cannot be trusted either way
    (BM903 measured three TCG guests pushing an 11 s boot past 240 s)."""


def run_boot(medium, log, budget=30.0, poll=0.5):
    """Boot `medium`, watch `log`, return the graded verdict as a dict.
    Raises LaneBusy rather than measuring beside someone else's guest."""
    medium, log = Path(medium), Path(log)
    if bm903_lane.live_boots():
        raise LaneBusy(f'{medium.name}: another bm903/bm802 boot is alive')
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b'')                  # truncate BEFORE qemu opens it
    # NB the scratch media are named bm903_bm802_* so qemu's argv carries the
    # marker bm903_lane.live_boots() looks for: a sweep boot advertises itself
    # to rung9's guard instead of silently stealing the lane.
    qemu = subprocess.Popen(['qemu-system-x86_64', '-M', 'pc', '-m', '512',
                            '-drive', f'file={medium},format=raw,if=ide',
                            '-display', 'none', '-no-reboot', '-no-shutdown',
                            '-serial', f'file:{log}'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0, top, seen = time.time(), 0, {}
    blob = ''
    try:
        while time.time() - t0 < budget:
            time.sleep(poll)
            blob = log.read_bytes().decode('latin-1')
            if 'BM903-S2 GATE2=FAIL' in blob:
                top, seen['refuse'] = max(top, 1), True
                break
            for name, pat, rank in STAGES:
                if name not in seen and re.search(pat, blob):
                    seen[name] = time.time() - t0
                    top = max(top, rank)
            if top >= CEILING:
                break
        blob = log.read_bytes().decode('latin-1')
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=10)
        except subprocess.TimeoutExpired:
            qemu.kill()
            qemu.wait(timeout=10)
    flags = []
    for name, pat in DIAG:
        m = re.search(pat, blob)
        if m:
            flags.append(name if name != 'gate line' else
                         ('gate-match' if m.group(1) == m.group(2) else
                          'gate-MISMATCH'))
    tail = [ln for ln in blob.splitlines() if ln.strip()][-1:] or ['<none>']
    return {'stage': top, 'bytes': len(blob), 't': time.time() - t0,
            'prompt': 'prompt' in seen, 'flags': flags,
            'gate': (re.search(r'GATE2 CRC=([0-9A-F]{8})', blob) or
                     [None, ''])[1],
            'last': tail[0][:70]}


def main() -> int:
    med = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNG9 / 'bm903_medium_px.raw'
    log = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/tmp/bm802_boot.log')
    due = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
    try:
        r = run_boot(med, log, due)
    except LaneBusy as e:
        print(f'VERDICT stage=ERR note=lane-busy {e}')
        return 3
    print(f'VERDICT stage={r["stage"]} bytes={r["bytes"]} t={r["t"]:.1f}s '
          f'prompt={"y" if r["prompt"] else "n"} '
          f'flags={",".join(r["flags"]) or "-"} last={r["last"]!r}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
