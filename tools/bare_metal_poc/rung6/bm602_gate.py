#!/usr/bin/env python3
"""BM602 gate: boot one fixture and read the wire against a prediction that was
written to bm602_fixtures.json BEFORE this file ran.

That ordering is the point. bm602_mkimg.py replayed the loader's own walk -- the
seven plane reads, the corrector's dispatch transcribed from the asm, the
de-interleave, the CRC8 -- and recorded the ECC=, PAR= and computed CRC each
fixture must print. If the gate derived its expectations from the transcript it
was checking, it could not fail. Here the numbers arrive from a different
program, a different implementation, and an earlier clock.

What each leg requires, all of it out of one serial transcript:

  walk done    `BM903-S2 PIXEL WALK DONE`
  counters     `BM903-S2 ECC=<8 hex> PAR=<8 hex>`
  gate         `BM903-S2 GATE2 CRC=<computed> EXP=<expected>`
  verdict      `GATE2=PASS` / `GATE2=FAIL -- NO HANDOFF JUMP`
  handoff      `BM903-S2 HANDOFF BUILT`          (PASS legs only)
  anchor       `tc@box`                          (recoverable legs only)
  container    `BM903-S2 CONTAINER=<seen> EXP=<wanted>`, and NOTHING after it

Plus the ORDER, measured as byte offsets in the log: the counters must precede
the gate line, and the gate line must precede the verdict. That is rung-4's
DEFECT-R4PRINT rule applied to the new line -- the corrector's own report cannot
be a post-hoc echo of a decision the gate had already taken.

The anchor is the one allowance. Tiny Core's autologin picks tty1 or ttyS0 by a
race inside the guest (measured in BM903: 3/8 and 5/8 boots reach `tc@box`), so
a boot that got every loader line right and then lost the race is re-run, up to
--attempts times. A boot that got a loader line WRONG is not re-run: the gate is
deterministic, and re-rolling a die is how a flaky rig hides a real failure.

  usage: python3 bm602_gate.py <fixture> [--attempts 8] [--budget 45] [-v]
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXJSON = HERE / 'bm602_fixtures.json'
ANCHOR = 'tc@box'

# The strings the loader prints. The BM903-S2 prefix is deliberate: the only
# thing a leg may differ from the proven loader in is the text after it.
RE = {
    's1':        re.compile(r'BM903-S1'),
    's2enter':   re.compile(r'BM903-S2 ENTER'),
    'walk':      re.compile(r'BM903-S2 PIXEL WALK DONE'),
    'ecc':       re.compile(r'BM903-S2 ECC=([0-9A-F]{8}) PAR=([0-9A-F]{8})'),
    'gate':      re.compile(r'BM903-S2 GATE2 CRC=([0-9A-F]{8}) EXP=([0-9A-F]{8})'),
    'pass':      re.compile(r'BM903-S2 GATE2=PASS'),
    'fail':      re.compile(r'BM903-S2 GATE2=FAIL'),
    'handoff':   re.compile(r'BM903-S2 HANDOFF BUILT'),
    'container': re.compile(r'BM903-S2 CONTAINER=([0-9A-F]{8}) EXP=([0-9A-F]{8})'),
    'anchor':    re.compile(re.escape(ANCHOR)),
}
NOT_AFTER_TAG = ('walk', 'ecc', 'gate', 'pass', 'fail', 'handoff', 'anchor')


def at(rx, blob):
    m = rx.search(blob)
    return (m.start(), m) if m else (None, None)


def boot_once(med, log, budget, stop_at):
    """One boot, log truncated first, decided by wall clock, never by
    'probably still running'. Returns (elapsed, transcript, trace) where trace
    maps a marker to the second it FIRST appeared -- the difference between
    'the walk is slow' and 'the guest stalled after the walk'."""
    log.write_bytes(b'')
    qemu = subprocess.Popen(
        ['qemu-system-x86_64', '-M', 'pc', '-m', '512',
         '-drive', f'file={med},format=raw,if=ide',
         '-display', 'none', '-no-reboot', '-no-shutdown',
         '-serial', f'file:{log}'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    trace = {}
    try:
        while time.time() - t0 < budget:
            time.sleep(0.25)
            blob = log.read_bytes().decode('latin-1')
            for mark, rx in (('s2 enter', RE['s2enter']), ('walk done', RE['walk']),
                             ('verdict', RE['pass']), ('verdict', RE['fail']),
                             ('refused', RE['container'])):
                if mark not in trace and rx.search(blob):
                    trace[mark] = time.time() - t0
            if stop_at(blob):
                break
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=10)
        except subprocess.TimeoutExpired:
            qemu.kill()
            qemu.wait(timeout=10)
    return time.time() - t0, log.read_bytes().decode('latin-1'), trace


def evaluate(leg, blob):
    """(checks, loader_ok). `checks` is a list of (label, ok, detail)."""
    pos, mat = {}, {}
    for k, rx in RE.items():
        pos[k], mat[k] = at(rx, blob)
    chk = []

    def c(label, ok, detail=''):
        chk.append((label, bool(ok), detail))

    if leg['kind'] == 'tag':
        m = mat['container']
        c('stage1 ran', pos['s1'] is not None)
        c('stage2 ran and reached the check', pos['s2enter'] is not None)
        c('container line printed', m is not None,
          f'tail={blob[-96:]!r}')
        if m:
            c('names the medium it was handed', m.group(1) == leg['container_shows'],
              f'wire {m.group(1)}, sector 0 of a PXC1 medium holds '
              f'{leg["container_shows"]}')
            c('names what it wanted', m.group(2) == leg['wanted_tag'],
              f'EXP={m.group(2)}, the loader was built for {leg["wanted_tag"]}')
            c('nothing after the refusal', all(pos[k] is None for k in NOT_AFTER_TAG),
              'the loader hung instead of walking on')
        return chk, all(o for _, o, _ in chk)

    c('walk done', pos['walk'] is not None, f'tail={blob[-96:]!r}')
    c('ECC/PAR line printed', mat['ecc'] is not None)
    c('gate line printed', mat['gate'] is not None)
    if mat['ecc'] is None or mat['gate'] is None:
        return chk, False
    c('counters BEFORE the gate line', pos['ecc'] < pos['gate'],
      f'ECC at byte {pos["ecc"]}, CRC at {pos["gate"]}')
    verdicts = [p for p in (pos['pass'], pos['fail']) if p is not None]
    c('exactly one verdict', len(verdicts) == 1, f'{len(verdicts)} found')
    if verdicts:
        c('gate line BEFORE the verdict', pos['gate'] < verdicts[0],
          f'CRC at {pos["gate"]}, verdict at {verdicts[0]}')
        c('verdict matches the prediction',
          (pos['pass'] is not None) == (leg['verdict'] == 'PASS'),
          f'wire={"PASS" if pos["pass"] is not None else "FAIL"}, '
          f'predicted={leg["verdict"]}')
    c('ECC= matches the replay', mat['ecc'].group(1) == leg['ecc'],
      f'wire {mat["ecc"].group(1)}, predicted {leg["ecc"]}')
    c('PAR= matches the replay', mat['ecc'].group(2) == leg['par'],
      f'wire {mat["ecc"].group(2)}, predicted {leg["par"]}')
    c('computed CRC matches the replay',
      mat['gate'].group(1) == leg['computed_crc'],
      f'wire {mat["gate"].group(1)}, predicted {leg["computed_crc"]}')
    c('expected CRC is the baked constant',
      mat['gate'].group(2) == leg['expected_crc'],
      f'wire {mat["gate"].group(2)}, .inc {leg["expected_crc"]}')
    c('handoff iff the gate passed',
      (pos['handoff'] is not None) == (leg['verdict'] == 'PASS'),
      f'HANDOFF BUILT={pos["handoff"] is not None}, verdict={leg["verdict"]}')
    if leg['verdict'] == 'FAIL':
        c('no anchor from a refused medium', pos['anchor'] is None)
    return chk, all(o for _, o, _ in chk)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    name = argv[0]
    attempts, budget = 8, 45.0
    if '--attempts' in argv:
        attempts = int(argv[argv.index('--attempts') + 1])
    if '--budget' in argv:
        budget = float(argv[argv.index('--budget') + 1])

    fx = json.loads(FIXJSON.read_text())
    leg = next((f for f in fx['fixtures'] if f['name'] == name), None)
    if leg is None:
        print(f'  [RED ] no fixture {name!r} in {FIXJSON.name}: '
              f'{[f["name"] for f in fx["fixtures"]]}')
        return 1
    leg['wanted_tag'] = f'{int(fx["tag"], 16):08X}'
    # every fixture, the clean one included, is a file under fixtures/: the leg
    # boots the same path the prediction was made from, with no special case.
    med = HERE / 'fixtures' / leg['medium']
    # The serial transcript gets its own file name. It used to share one with
    # the caller's stdout redirect, and the two writers -- qemu holding a fixed
    # offset, the shell holding another, over a truncate between boots --
    # overwrote each other, so the evidence for the byte-identity leg was
    # garbage. rung9 dodged the same hole by writing its reports to
    # `${logf}.att$a`, i.e. a different path.
    log = HERE / 'logs' / f'{name}.serial'
    log.parent.mkdir(exist_ok=True)

    lane = subprocess.run([sys.executable, str(HERE / 'bm602_lane.py')],
                          capture_output=True, text=True)
    if lane.returncode:
        print(lane.stdout.strip())
        print(f'  [RED ] {name}: the lane is busy, and a boot beside another '
              'boot is not evidence in either direction')
        return 1

    stop_at = ((lambda b: ANCHOR in b) if leg['anchor_required']
               else (lambda b: 'GATE2=' in b or 'CONTAINER=' in b))
    total, boots, chk, loader_ok, blob, trace = 0.0, 0, [], False, '', {}
    for boots in range(1, attempts + 1):
        el, blob, trace = boot_once(med, log, budget, stop_at)
        total += el
        chk, loader_ok = evaluate(leg, blob)
        if not loader_ok:
            print(f'      boot {boots}: a loader line is wrong -- not retrying')
            break
        if not leg['anchor_required'] or RE['anchor'].search(blob):
            break
        print(f'      boot {boots}/{attempts}: every loader line right, no '
              f'{ANCHOR} inside {el:.1f}s (guest autologin race)')
    if leg['anchor_required']:
        chk.append((f'anchor {ANCHOR}', RE['anchor'].search(blob) is not None,
                    f'{boots} boot(s), {attempts} allowed'))

    rc = 0
    for label, ok, detail in chk:
        print(f'  {"[ok]  " if ok else "[FAIL]"} {label}'
              + (f'  -- {detail}' if detail else ''))
        rc |= 0 if ok else 1
    marks = ' '.join(f'{k}@{v:.1f}s' for k, v in sorted(trace.items(),
                                                       key=lambda kv: kv[1]))
    print(f'{name}: {"GREEN" if rc == 0 else "RED"}  wall={total:.1f}s '
          f'boots={boots} predicted ECC={leg["ecc"]} PAR={leg["par"]} '
          f'verdict={leg["verdict"]}')
    print(f'    trace (last boot, 0.25 s polling): {marks}')
    if '-v' in argv:
        print('  --- transcript ---')
        for line in blob.splitlines():
            print('   ', line[:160])
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
