"""Side-measurement for the BM653 receipt: does the scribbler's poison MATTER?

The leg itself is judged at the handoff, so the shipped gate never asks what the
kernel does with a zero page whose 0x1f1/0x1f4 the image rewrote -- it stops
watching at 1.3 s, long before a boot could fail. One boot each answers it, and
answers it the same way the gate does not: same boot function, same budget, green
medium against scribbler medium, ALTERNATING, because Tiny Core's autologin wins
the tty1/ttyS0 argument often enough that a single sample of either is worth
nothing. (An earlier draft of this probe let two runs share one log path and
truncate each other; every byte per boot is therefore named with its own file.)

Read-only w.r.t. the row's artifacts; writes only `logs/longwatch/`. NOT part of
the gate, and deliberately not wired into `run_bm653_e2e.sh`: its result is a
count out of 8 and Tiny Core's autologin coin decides part of it, so it can
report either way without anything being wrong. `RECEIPT_BM653.md` quotes it.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bm653_gate as gate                                          # noqa: E402
import bm653_lane as lane                                          # noqa: E402

BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 75.0
OUT = HERE / 'logs' / 'longwatch'
OUT.mkdir(exist_ok=True)

alive = lane.live_boots()
if alive:
    sys.exit(f'lane busy: {alive}')

# 4 of each, alternating, so a run of lost autologin coins cannot land on one
# medium alone.
plan = ['exec_green', 'exec_scribbler'] * 4
for n, combo in enumerate(plan, 1):
    med = HERE / 'fixtures' / f'{combo}.raw'
    log = OUT / f'{n:02d}_{combo}.serial'
    el, blob, trace = gate.boot_once(med, log, BUDGET,
                                     lambda b: gate.ANCHOR in b)
    marks = ', '.join(f'{k}@{v:.1f}s' for k, v in
                      sorted(trace.items(), key=lambda kv: kv[1]))
    hit = gate.ANCHOR in blob
    print(f'{n} {combo:16s} {el:5.1f}s anchor={"YES" if hit else "NO "} '
          f'{len(blob):,} B  {marks}', flush=True)
    if not hit:
        tail = [ln for ln in blob.splitlines() if ln.strip()][-3:]
        print('    no shell; last lines: ' + ' // '.join(t.strip()[:88]
                                                        for t in tail),
              flush=True)
