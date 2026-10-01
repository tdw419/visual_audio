#!/usr/bin/env python3
"""PROBE: how long does OUR handoff take to reach the tc@box prompt?

Step 3's L3 leg must state a wall-clock timeout, and a stated timeout is a
measurement, not a guess: boot the step-1 medium N times, poll the serial
transcript for the anchor, and report the per-run elapsed seconds so the gate
can pin a budget with margin instead of a number tuned to pass.
"""
import atexit
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUNG9 = Path('/home/jericho/projects/zion/projects/visual_audio/tools/bare_metal_poc/rung9')
MEDIUM = RUNG9 / 'bm903_medium.raw'
ANCHOR = re.compile(rb'tc@box')
CAP = 360
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 2

# HEAD wrote /tmp/bm903_time_run{n}.log and unlinked that fixed name first, so a
# run destroyed the previous run's transcript, and then read the name back at
# :45 with no guard — with nothing on the other end of a failed boot it raised
# FileNotFoundError instead of printing NEVER. Per-run directory instead.
# The prefix keeps the 'bm903' substring bm903_lane.py:35 scans qemu argv for.
RUN_DIR = Path(tempfile.mkdtemp(prefix='bm903_time_'))
atexit.register(shutil.rmtree, RUN_DIR, ignore_errors=True)
print(f'serial transcripts in {RUN_DIR} (removed at exit)')

for n in range(RUNS):
    log = RUN_DIR / f'run{n}.log'
    t0 = time.time()
    p = subprocess.Popen(['qemu-system-x86_64', '-M', 'pc', '-m', '512',
                          '-drive', f'file={MEDIUM},format=raw,if=ide',
                          '-display', 'none', '-no-reboot', '-no-shutdown',
                          '-serial', f'file:{log}'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen = None
    while time.time() - t0 < CAP:
        if log.exists() and ANCHOR.search(log.read_bytes()):
            seen = time.time() - t0
            break
        time.sleep(1.0)
    p.terminate()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=10)
    alive = log.exists()
    size = log.stat().st_size if alive else 0
    text = log.read_text(errors='replace') if alive else ''
    print(f'run {n}: anchor {"at %.1fs" % seen if seen else "NEVER (cap %ds)" % CAP} '
          f'— transcript {size} B, handoff checkpoints present: '
          f'{"HANDOFF BUILT" in text}')
print('done')
