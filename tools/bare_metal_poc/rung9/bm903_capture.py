#!/usr/bin/env python3
"""BM903 step 1: capture OUR executed handoff at the kernel's first insn.

Copy-by-shape of probe34_capture.py (its capture structure is LOCKED: same
gdb -batch -nx session, same stop, same $rsi-keyed 4 KB zeropage dump, same
*( $rsi+0x228 )-keyed 512 B cmdline dump). Two deliberate deviations, both
required by the difference between watching someone else's loader and running
our own:

  * `hbreak` (hardware execute breakpoint) instead of `break`: our stage2
    WRITES 4.28 MB across 0x100000 with `rep insw`, so a software bp (an
    int3 opcode) would be overwritten by the kernel bytes it is meant to
    interrupt. A Z1 execute bp also cannot fire on those writes.
  * single stop: the oracle leg needed two stops because isolinux's own
    trampoline also hits 0x100000; our stage2 enters it exactly once.

Serial is captured alongside so the receipt can show the checkpoints came
from EXECUTED code (BM903-S2 HANDOFF BUILT) rather than host construction.

Per leg writes: bm903_zp_leg<N>.bin, bm903_cmdline_leg<N>.bin,
bm903_regs_leg<N>.json (same schema as bm902_regs.json), bm903_capture_leg<N>.log.
Exit 0 only if both legs produced a full register set with HdrS at $rsi.
"""
import json
import re
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# argv: [medium] [prefix] -- defaults are the step-1 shapes, so the step-1 gate
# keeps calling this file exactly as before while step 2 captures the pixel
# handoff into its own bm903_px_* evidence files.
MEDIUM = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "bm903_medium.raw"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else 'bm903'
# A RED leg (L6) EXPECTS no stop, so it needs a short, stated wait rather
# than the 120 s a green leg gets.
GDB_TIMEOUT_S = int(sys.argv[3]) if len(sys.argv) > 3 else 120
# Ladder gdb TCP port map — machine-scoped names, one block per claiming script,
# disjoint by construction: probe34 12440-41 | rung 6 12460-63 | rung 6.5
# 12464-67 | rung 9 12468-75 (this capture 12468-69, the three singles
# 12470/12472/12474). The text below is identical in all three captures because
# the map only holds if they do; rung 6 and 6.5 inherit it from here by fork.
PORT_BASE = 12468  # this rung's block start; the legs take +0 and +1
ENTRY = 0x100000
BOOT_WAIT_S = 1.5

REG_LINE = re.compile(r'^(RAX|RSI|EFLAGS|CR0|CMDPTR)=')


def live_count() -> int:
    import bm903_lane
    return len(bm903_lane.live_boots())



def gdb_cmds(leg: int) -> list[str]:
    zpf = f'{PREFIX}_zp_leg{leg}.bin'
    cmdf = f'{PREFIX}_cmdline_leg{leg}.bin'
    return [
        'set pagination off',
        'set architecture i386:x86-64',
        f'target remote :{PORT_BASE + leg}',
        f'hbreak *{ENTRY:#x}',
        'continue',
        f'printf "=== CAPTURE leg {leg} ===\\n"',
        'printf "STOP rsi=0x%x rip=0x%x\\n", $rsi, $rip',
        'x/4cb $rsi+0x202',
        'printf "RAX=0x%x RBX=0x%x RCX=0x%x RDX=0x%x\\n", $rax,$rbx,$rcx,$rdx',
        'printf "RSI=0x%x RDI=0x%x RBP=0x%x RSP=0x%x\\n", $rsi,$rdi,$rbp,$rsp',
        'printf "R8=0x%x R9=0x%x R10=0x%x R11=0x%x\\n", $r8,$r9,$r10,$r11',
        'printf "R12=0x%x R13=0x%x R14=0x%x R15=0x%x\\n", $r12,$r13,$r14,$r15',
        'printf "EFLAGS=0x%x CS=0x%x SS=0x%x DS=0x%x ES=0x%x\\n", $eflags,$cs,$ss,$ds,$es',
        'printf "CR0=0x%x CR3=0x%x CR4=0x%x\\n", $cr0,$cr3,$cr4',
        f'dump binary memory {zpf} $rsi ($rsi+0x1000)',
        'set $cmdptr = *(unsigned int *)($rsi+0x228)',
        'printf "CMDPTR=0x%x\\n", $cmdptr',
        f'dump binary memory {cmdf} $cmdptr ($cmdptr+512)',
        'x/s $cmdptr',
        'kill',
        'quit',
    ]


def parse_regs(log: str) -> dict | None:
    """Rebuild the bm902_regs.json schema from the printf lines."""
    blob = ' '.join(log.splitlines())
    want = {
        'rax': r'RAX=0x([0-9a-f]+)', 'rbx': r'RBX=0x([0-9a-f]+)',
        'rcx': r'RCX=0x([0-9a-f]+)', 'rdx': r'RDX=0x([0-9a-f]+)',
        'rsi': r'RSI=0x([0-9a-f]+)', 'rdi': r'RDI=0x([0-9a-f]+)',
        'rbp': r'RBP=0x([0-9a-f]+)', 'rsp': r'RSP=0x([0-9a-f]+)',
        'r8': r'R8=0x([0-9a-f]+)', 'r9': r'R9=0x([0-9a-f]+)',
        'r10': r'R10=0x([0-9a-f]+)', 'r11': r'R11=0x([0-9a-f]+)',
        'r12': r'R12=0x([0-9a-f]+)', 'r13': r'R13=0x([0-9a-f]+)',
        'r14': r'R14=0x([0-9a-f]+)', 'r15': r'R15=0x([0-9a-f]+)',
        'eflags': r'EFLAGS=0x([0-9a-f]+)', 'cs': r'CS=0x([0-9a-f]+)',
        'ss': r'SS=0x([0-9a-f]+)', 'ds': r'DS=0x([0-9a-f]+)',
        'es': r'ES=0x([0-9a-f]+)', 'cr0': r'CR0=0x([0-9a-f]+)',
        'cr3': r'CR3=0x([0-9a-f]+)', 'cr4': r'CR4=0x([0-9a-f]+)',
    }
    regs = {}
    for name, pat in want.items():
        m = re.search(pat, blob)
        if not m:
            print(f'  capture parse: missing {name}')
            return None
        regs[name] = int(m.group(1), 16)
    m = re.search(r'STOP rsi=0x([0-9a-f]+) rip=0x([0-9a-f]+)', blob)
    if not m:
        print('  capture parse: missing STOP line (breakpoint never fired?)')
        return None
    regs['rip'] = int(m.group(2), 16)
    if regs['rsi'] != int(m.group(1), 16):
        print('  capture parse: RSI disagrees with the STOP line')
        return None
    return regs


def main() -> int:
    import bm903_lane
    if bm903_lane.main([str(MEDIUM)]) or live_count():
        print('lane busy: another bm903 boot has the medium locked -- legs run '
              'sequentially (see bm903_lane.py)')
        return 3
    lay = json.loads((HERE / "bm903_layout.json").read_text())
    assert MEDIUM.exists(), f'build the medium first (bm903_mkimg*.py): {MEDIUM} missing'
    rc_all = 0
    busy = False   # a refused port outranks any later leg result; see ROADMAP's contract
    for leg in range(2):
        logf = HERE / f'{PREFIX}_capture_leg{leg}.log'
        serf = HERE / f'{PREFIX}_serial_leg{leg}.log'
        qerrf = HERE / f'{PREFIX}_qemu_stderr_leg{leg}.log'
        with open(qerrf, 'wb') as qerr:
            qemu = subprocess.Popen([
                'qemu-system-x86_64', '-M', 'pc', '-m', '512',
                '-drive', f'file={MEDIUM},format=raw,if=ide',
                '-display', 'none', '-no-reboot',
                '-serial', f'file:{serf}',
                '-S', '-gdb', f'tcp::{PORT_BASE + leg}',
            ], stdout=subprocess.DEVNULL, stderr=qerr)
        time.sleep(BOOT_WAIT_S)
        if qemu.poll() is not None:
            # qemu binds the gdb port before the guest runs and exits 1 on
            # EADDRINUSE. That message went to DEVNULL, so a port collision
            # resurfaced GDB_TIMEOUT_S later as "gdb never stopped on the
            # handoff" -- indistinguishable from a hung loader. 3 is this
            # file's own lane-busy code.
            print(f'leg {leg}: qemu died at startup rc={qemu.returncode}: '
                  f'{qerrf.read_text(errors="replace").strip()[:200]}')
            rc_all = 3
            busy = True
            continue
        t_run = time.time()
        try:
            with open(logf, 'w') as f:
                subprocess.call(
                    ['timeout', str(GDB_TIMEOUT_S), 'gdb', '-batch', '-nx'] +
                    sum([['-ex', c] for c in gdb_cmds(leg)], []),
                    stdout=f, stderr=subprocess.STDOUT)
        finally:
            qemu.send_signal(signal.SIGTERM)
            try:
                qemu.wait(timeout=10)
            except subprocess.TimeoutExpired:
                qemu.kill()
                qemu.wait(timeout=10)
        # Where did the executed code get to, and how long did it take to get
        # there? The checkpoint list is the loader's own serial trace, so a leg
        # that hangs mid-walk is distinguishable from one that builds the
        # handoff and then never stops (the latter is kernel-side, not ours).
        ser = serf.read_text(errors='replace')
        ckpts = [c for c in ('BM903-S2 ENTER', 'BM903-S2 PMODE', 'BM903-S2 A20 OK',
                             'BM903-S2 PIXEL WALK DONE', 'BM903-S2 GATE2',
                             'BM903-S2 HANDOFF BUILT') if c in ser]
        log0 = logf.read_text()
        stop = ('stopped on the handoff' if '=== CAPTURE' in log0
                else 'NO STOP (timeout or hung loader)')
        print(f'  leg {leg}: last-checkpoint='
              f'{ckpts[-1] if ckpts else "none"} ({len(ckpts)}/6) '
              f'stop={stop} wall={time.time() - t_run:.1f}s')
        log = log0
        for line in log.splitlines():
            if REG_LINE.match(line) or line.startswith(('===', 'STOP', 'CMDPTR')):
                print(' ', line[:150])
        regs = parse_regs(log)
        if regs is None:
            print(f'leg {leg}: NO CAPTURE (gdb never stopped on the handoff)')
            rc_all = 1
            continue
        zp = HERE / f'{PREFIX}_zp_leg{leg}.bin'
        cmd = HERE / f'{PREFIX}_cmdline_leg{leg}.bin'
        if not (zp.exists() and zp.stat().st_size == 4096):
            print(f'leg {leg}: zeropage dump missing/short')
            rc_all = 1
            continue
        if not (cmd.exists() and cmd.stat().st_size == 512):
            print(f'leg {leg}: cmdline dump missing/short')
            rc_all = 1
            continue
        hdr = zp.read_bytes()[0x202:0x206]
        if hdr != b'HdrS':
            print(f'leg {leg}: no HdrS at $rsi+0x202 ({hdr!r}) — wrong page')
            rc_all = 1
            continue
        regs['loader_meta'] = {
            'zp_addr': lay['zp_addr'], 'cmdline_addr': lay['cmdline_addr'],
            'stack_top': 0x1f784, 'type_of_loader': 0xff,
            'captured_by': 'bm903_capture.py (executed stage2)',
        }
        (HERE / f'{PREFIX}_regs_leg{leg}.json').write_text(
            json.dumps(regs, indent=1, sort_keys=True) + '\n')
        print(f'leg {leg}: CAPTURED rip={regs["rip"]:#x} rsi={regs["rsi"]:#x} '
              f'rsp={regs["rsp"]:#x} cr0={regs["cr0"]:#x} '
              f'eflags={regs["eflags"]:#x}')
    done = 'BUSY (a gdb port was already taken; legs beside it are not measurements)'
    print('done', done if busy else ('OK' if rc_all == 0 else 'RED'))
    return 3 if busy else rc_all


if __name__ == '__main__':
    sys.exit(main())
