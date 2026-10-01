#!/usr/bin/env python3
"""BM653 gate: boot one fixture and read the wire against bm653_fixtures.json,
written by bm653_mkimg.py from its own host replay BEFORE any qemu ran.

The rule BM602 stated is inherited unchanged: the expectation arrives from a
different program, a different implementation, and an earlier clock, so the gate
can fail. What BM653 adds is the half of the wire that only exists if the
repaired bytes ran, and its checks are ordered ones.

  walk done  `BM903-S2 PIXEL WALK DONE`
  counters   `BM903-S2 ECC=<8 hex> PAR=<8 hex>`
  gate       `BM903-S2 GATE2 CRC=<computed> EXP=<expected>`
  verdict    `GATE2=PASS` / `GATE2=FAIL -- NO HANDOFF JUMP`
  banner     `IMG2EXEC BANNER NID=<4 hex>`      (from the IMAGE, not the loader)
  exec       `BM903-S2 EXEC=OK` / `EXEC=BAD-MAILBOX <got> EXP <want>` /
             `EXEC=NO-BANNER <got> EXP <want>`
  handoff    `BM903-S2 HANDOFF BUILT`
  anchor     `tc@box`

Three orders are the claim, not decoration, and all three are measured as byte
offsets in the log:

  * counters before the gate line, gate line before its verdict -- rung 4's
    DEFECT-R4PRINT, inherited;
  * the image's banner before the loader's EXEC= verdict about it: the loader
    can only judge a print that already happened;
  * EXEC=OK before HANDOFF BUILT. That is option C's whole shape in one
    inequality -- the handoff is built AFTER the image has run, which is also
    what makes the scribbler leg possible at all.

And the absence legs, which are the row's non-vacuity half: a medium the gate
refused prints no banner and no EXEC line; the BEE-OFF control prints the same
medium's damage with ECC=0 and is refused; and the halt image banners with its
own NID and then never lets the loader come back, so it prints no EXEC line and
no HANDOFF -- over a full budget of wall clock the host itself has to stop
counting. Nothing inside the guest can time that out, which is why the leg's
`--budget` is its evidence rather than its nuisance.

  usage: python3 bm653_gate.py <fixture> [--attempts 8] [--budget 45] [-v]
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXJSON = HERE / 'bm653_fixtures.json'
LOGS = HERE / 'logs'
ANCHOR = 'tc@box'

# The BM903-S2 prefix is inherited from rung6 on purpose: a leg may differ from
# the gated loader only in the text after it, so the stage ladder still reads.
RE = {
    's2enter':   re.compile(r'BM903-S2 ENTER'),
    'walk':      re.compile(r'BM903-S2 PIXEL WALK DONE'),
    'ecc':       re.compile(r'BM903-S2 ECC=([0-9A-F]{8}) PAR=([0-9A-F]{8})'),
    'gate':      re.compile(r'BM903-S2 GATE2 CRC=([0-9A-F]{8}) EXP=([0-9A-F]{8})'),
    'pass':      re.compile(r'BM903-S2 GATE2=PASS'),
    'fail':      re.compile(r'BM903-S2 GATE2=FAIL'),
    'banner':    re.compile(r'IMG2EXEC BANNER NID=([0-9A-F]{4})'),
    'execok':    re.compile(r'BM903-S2 EXEC=OK'),
    'execbad':   re.compile(r'BM903-S2 EXEC=BAD-MAILBOX ([0-9A-F]{4}) '
                            r'EXP=([0-9A-F]{4})'),
    'execnob':   re.compile(r'BM903-S2 EXEC=NO-BANNER ([0-9A-F]{4}) '
                            r'EXP=([0-9A-F]{4})'),
    'handoff':   re.compile(r'BM903-S2 HANDOFF BUILT'),
    'container': re.compile(r'BM903-S2 CONTAINER=([0-9A-F]{8}) EXP=([0-9A-F]{8})'),
    'anchor':    re.compile(re.escape(ANCHOR)),
}
EXEC_KEYS = ('execok', 'execbad', 'execnob')
# the markers the boot loop timestamps: the difference between 'the walk is
# slow' and 'the guest stalled after the walk', and for the halt leg between
# 'the image hung' and 'the loader never got that far'.
TRACE = (('s2 enter', RE['s2enter']), ('walk done', RE['walk']),
         ('verdict', RE['pass']), ('verdict', RE['fail']),
         ('banner', RE['banner']), ('exec', RE['execok']),
         ('exec', RE['execbad']), ('exec', RE['execnob']),
         ('handoff', RE['handoff']), ('refused', RE['container']))


def at(rx, blob):
    m = rx.search(blob)
    return (m.start(), m) if m else (None, None)


def boot_once(med, log, budget, stop_at):
    """One boot, log truncated first, decided by wall clock, never by
    'probably still running'. Returns (elapsed, transcript, first-seen trace)."""
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
            for mark, rx in TRACE:
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
    """(checks, loader_ok). The first six checks are BM602's, unchanged, so a
    regression in the medium reader still reads as one."""
    pos, mat = {}, {}
    for k, rx in RE.items():
        pos[k], mat[k] = at(rx, blob)
    chk = []

    def c(label, ok, detail=''):
        chk.append((label, bool(ok), detail))

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
      f'wire {mat["ecc"].group(1)}, predicted {leg["ecc"]} '
      f'({"pass 1 modelled" if leg["pass1"] else "pass 1 NOPed"})')
    c('PAR= matches the replay', mat['ecc'].group(2) == leg['par'],
      f'wire {mat["ecc"].group(2)}, predicted {leg["par"]}')
    c('computed CRC matches the replay',
      mat['gate'].group(1) == leg['computed_crc'],
      f'wire {mat["gate"].group(1)}, predicted {leg["computed_crc"]}')
    c('expected CRC is the constant baked into THIS combo',
      mat['gate'].group(2) == leg['expected_crc'],
      f'wire {mat["gate"].group(2)}, .inc {leg["expected_crc"]} '
      f'(combo {leg["combo"]})')

    want = leg['exec_expect']
    seen = [k for k in EXEC_KEYS if pos[k] is not None]
    c('at most one EXEC line', len(seen) <= 1, f'{seen}')
    if want == 'OK':
        c('the image banner printed, with the predicted NID',
          mat['banner'] is not None and mat['banner'].group(1) == leg['exec_nid'],
          f'wire {mat["banner"].group(1) if mat["banner"] else None}, '
          f'predicted {leg["exec_nid"]} from crc32(img2)={leg["image_crc32"]}')
        c('EXEC=OK', seen == ['execok'], f'saw {seen}')
        if pos['banner'] is not None and pos['execok'] is not None:
            c('banner BEFORE the verdict about the image',
              pos['banner'] < pos['execok'],
              f'banner at {pos["banner"]}, EXEC at {pos["execok"]}')
        if pos['pass'] is not None and pos['execok'] is not None:
            c('gate verdict BEFORE the EXEC verdict', pos['pass'] < pos['execok'],
              f'GATE2=PASS at {pos["pass"]}, EXEC at {pos["execok"]}')
    elif want is None:
        c('no banner from a medium the gate refused', pos['banner'] is None,
          'the image ran anyway -- the leg ordering is not what the fork claims')
        c('no EXEC line at all', not seen, f'saw {seen}')
    else:                                     # 'HALT'
        c('the halt image printed its banner',
          mat['banner'] is not None and mat['banner'].group(1) == leg['exec_nid'],
          f'wire {mat["banner"].group(1) if mat["banner"] else None}, predicted '
          f'{leg["exec_nid"]}')
        c('the gate passed BEFORE the image hung',
          pos['pass'] is not None and (mat['banner'] is None
                                       or pos['pass'] < pos['banner']),
          f'GATE2=PASS at {pos["pass"]}, banner at {pos["banner"]}')
        c('no EXEC line: the loader never came back', not seen, f'saw {seen}')
    handoff_wanted = leg['verdict'] == 'PASS' and want != 'HALT'
    c('handoff iff the gate passed AND the image returned',
      (pos['handoff'] is not None) == handoff_wanted,
      f'HANDOFF BUILT={pos["handoff"] is not None}, verdict={leg["verdict"]}, '
      f'exec={want}')
    if pos['execok'] is not None and pos['handoff'] is not None:
        c('EXEC=OK BEFORE HANDOFF BUILT', pos['execok'] < pos['handoff'],
          f'EXEC at {pos["execok"]}, handoff at {pos["handoff"]}')
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
    med = HERE / 'fixtures' / leg['medium']
    assert med.exists(), f'{med} missing: run bm653_mkimg.py first'
    log = LOGS / f'{name}.serial'
    log.parent.mkdir(exist_ok=True)

    lane = subprocess.run([sys.executable, str(HERE / 'bm653_lane.py')],
                          capture_output=True, text=True)
    if lane.returncode:
        print(lane.stdout.strip())
        print(f'  [RED ] {name}: the lane is busy, and a boot beside another '
              'boot is not evidence in either direction')
        return 1

    # The terminal event, per leg. An anchor leg is not over until the guest
    # draws a prompt; a PASS leg that never boots Tiny Core is over when the
    # handoff exists; a refusal is over when the gate speaks. The halt leg has
    # NO terminal event -- it is measured by the host giving up, which is the
    # only outside judge this design has.
    if leg['anchor_required']:
        stop_at = lambda b: ANCHOR in b
    elif leg['exec_expect'] == 'HALT':
        stop_at = lambda b: False
    else:
        stop_at = lambda b: ('GATE2=FAIL' in b or 'CONTAINER=' in b
                             or 'HANDOFF BUILT' in b)
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
          f'boots={boots} combo={leg["combo"]} predicted ECC={leg["ecc"]} '
          f'PAR={leg["par"]} verdict={leg["verdict"]} exec={leg["exec_expect"]}')
    print(f'    trace (last boot, 0.25 s polling): {marks}')
    if '-v' in argv:
        print('  --- transcript ---')
        for line in blob.splitlines():
            print('   ', line[:160])
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
