"""probe34: full BM901 oracle capture — registers + zeropage + cmdline.

Same 2-stop structure as probe33 (stop 0 = isolinux trampoline, stop 1 =
kernel PM handoff with HdrS). At stop 1 the kernel has executed 24+ more
insns and is about to re-trigger the bp; we 'stepi 0x666' forward FIRST so
the 0x100000 bp is behind us, then set a SECOND bp deeper into the stub
(0x100053, measured in probe33 line 17: the address right after the entry
pushes) — simpler: single-step exactly 83 insns (0x100053-0x100000=0x53,
unknown insn count) — no: use 'until *0x100053'.

Registers at 0x100053: post-first-instructions state. The TRUE handoff
state is what we sampled at the ORIGINAL probe33 capture moment: rip was
0x100053 after stepi 24 — i.e. the bp re-fire interrupted the kernel AFTER
it had executed 0x53 bytes. The kernel's architectural handoff state is
defined at its FIRST instruction (rip=0x100000, before any insn). To catch
that exact instant we must stop ON 0x100000 without re-fire corruption:
impossible with a code bp at the entry itself (re-fire happens on continue,
but the STOP ITSELF is at the right instant!). probe33's stop-1 registers
(line 13-17 of the log: rax/rbx/... captured AFTER 'stepi 24') were post-
step. Correct approach: at stop 1, capture 'info registers' IMMEDIATELY
(before stepi). The stepi+continue was only needed to make the NEXT stop
happen; for the final leg we stop at stop1 and just capture.

New structure per leg:
  break *0x100000; continue          -> stop 0 (isolinux): verify rsi!=HdrS
  stepi 24; continue                 -> stop 1 (kernel): capture NOW
    - info registers (full, incl. cr0/3/4, eflags, segs)
    - dump zeropage from $rsi (4KB)
    - dump cmdline from cmd_line_ptr (512B)
"""
import signal
import subprocess
import sys
import time

PORT_BASE = 12440

for leg in range(2):
    port = PORT_BASE + leg
    zpf = f'oracle_zp_leg{leg}.bin'
    cmdf = f'oracle_cmdline_leg{leg}.bin'
    logf = f'probe34_leg{leg}.log'

    cmds = [
        'set pagination off',
        'set architecture i386:x86-64',
        f'target remote :{port}',
        'break *0x100000',
        'continue',
        'printf "=== STOP0 isolinux rsi=0x%x\\n", $rsi',
        'x/4cb $rsi+0x202',
        'stepi 24',
        'continue',
        f'printf "=== CAPTURE leg {leg} ===\\n"',
        'printf "STOP1 rsi=0x%x rip=0x%x\\n", $rsi, $rip',
        'x/4cb $rsi+0x202',
        'printf "RAX=0x%x RBX=0x%x RCX=0x%x RDX=0x%x\\n", $rax,$rbx,$rcx,$rdx',
        'printf "RSI=0x%x RDI=0x%x RBP=0x%x RSP=0x%x\\n", $rsi,$rdi,$rbp,$rsp',
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

    qemu = subprocess.Popen([
        'qemu-system-x86_64', '-M', 'pc', '-m', '512',
        '-cdrom', '../rung7/TinyCore-current.iso', '-display', 'none',
        '-no-reboot', '-S', '-gdb', f'tcp::{port}',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        with open(logf, 'w') as f:
            rc = subprocess.call(
                ['timeout', '120', 'gdb', '-batch', '-nx'] +
                sum([['-ex', c] for c in cmds], []),
                stdout=f, stderr=subprocess.STDOUT)
    finally:
        qemu.send_signal(signal.SIGTERM)
        qemu.wait(timeout=10)
    print(f'leg {leg} gdb rc={rc}')
    for line in open(logf).read().splitlines():
        if line.startswith(('===', 'STOP1', 'RAX=', 'RSI=', 'EFLAGS=',
                            'CR0=', 'CMDPTR=', '0x1f800')) or 'HdrS' in line:
            print(' ', line[:130])

print('done')
