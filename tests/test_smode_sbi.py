#!/usr/bin/env python3
"""
GPU test suite for S-mode (supervisor CSRs, SRET, trap delegation, privilege
enforcement) and the inline WGSL SBI firmware in RISCV_CPU_MMU.wgsl.

Reuses the GpuCpu harness and mini-assembler from test_csr_m_extension.py.

Run: python3 tools/test_smode_sbi.py
"""

import sys, os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
sys.path.insert(0, str(Path(__file__).parent))
from test_csr_m_extension import (GpuCpu, reg64, field64, i_type,
                                  ADDI, CSRRW, CSRRS, MASK64)

ECALL = 0x00000073
SRET = 0x10200073
MRET = 0x30200073

SSTATUS, SIE_CSR, STVEC, SSCRATCH = 0x100, 0x104, 0x105, 0x140
SEPC, SCAUSE, STVAL = 0x141, 0x142, 0x143
MSCRATCH, MTVEC, MEDELEG, MSTATUS = 0x340, 0x305, 0x302, 0x300

SBI_BASE, SBI_DBCN, SBI_SRST, SBI_HSM = 0x10, 0x4442434E, 0x53525354, 0x48534D

failures = []


def check(name, actual, expected):
    ok = actual == expected
    print(f'  [{"PASS" if ok else "FAIL"}] {name}: got 0x{actual:016x}' +
          ('' if ok else f', expected 0x{expected:016x}'))
    if not ok:
        failures.append(name)


def main():
    gpu = GpuCpu()
    print(f'Device: {gpu.device.adapter.info.device}\n')

    # --- SBI console -------------------------------------------------------
    print('SBI console (legacy putchar + DBCN):')
    st = gpu.run([ECALL], 1, priv=1, regs={17: 0x01, 10: ord('H')})
    check('putchar wrote to UART', int(gpu.last_output[0]), ord('H'))
    check('putchar returned 0 in a0', reg64(st, 10), 0)
    check('putchar resumed at pc+4', reg64(st, 0) + int(st['pc'][0]), 4)
    check('still running (no trap)', int(st['running']), 1)
    check('still in S-mode', int(st['priv_mode']), 1)

    msg = b'GPU says hi\n'
    st = gpu.run([ECALL], 1, priv=1,
                 regs={17: SBI_DBCN, 16: 0, 10: len(msg), 11: 0x800},
                 data={0x800: msg})
    check('DBCN wrote all bytes (a1)', reg64(st, 11), len(msg))
    check('DBCN success (a0=0)', reg64(st, 10), 0)
    got = bytes(gpu.last_output[:len(msg)])
    ok = got == msg
    print(f'  [{"PASS" if ok else "FAIL"}] DBCN console output: {got!r}')
    if not ok:
        failures.append('DBCN output')

    # --- SBI base extension ------------------------------------------------
    print('SBI base extension:')
    st = gpu.run([ECALL], 1, priv=1, regs={17: SBI_BASE, 16: 0})
    check('spec_version = 2.0', reg64(st, 11), 2 << 24)
    check('spec_version err = 0', reg64(st, 10), 0)
    st = gpu.run([ECALL], 1, priv=1, regs={17: SBI_BASE, 16: 3, 10: SBI_DBCN})
    check('probe(DBCN) = 1', reg64(st, 11), 1)
    st = gpu.run([ECALL], 1, priv=1, regs={17: SBI_BASE, 16: 3, 10: SBI_HSM})
    check('probe(HSM) = 0', reg64(st, 11), 0)
    st = gpu.run([ECALL], 1, priv=1, regs={17: SBI_HSM, 16: 0})
    check('HSM call -> NOT_SUPPORTED (-2)', reg64(st, 10), (-2) & MASK64)
    st = gpu.run([ECALL], 1, priv=1, regs={17: SBI_SRST, 16: 0})
    check('SRST halts the machine', int(st['running']), 0)

    # --- S-mode CSRs -------------------------------------------------------
    print('S-mode CSRs:')
    prog = [
        CSRRW(0, SSCRATCH, 1),   # sscratch = x1
        CSRRS(5, SSCRATCH, 0),   # x5 = sscratch
        CSRRW(0, SSTATUS, 2),    # sstatus = x2 (SIE bit)
        CSRRS(6, SSTATUS, 0),    # x6 = sstatus (UXL reads as 2)
        CSRRW(0, STVEC, 3),      # stvec = x3
    ]
    st = gpu.run(prog, len(prog), priv=1,
                 regs={1: 0x1234567890ABCDEF, 2: 0x2, 3: 0x1000})
    check('sscratch round-trip', reg64(st, 5), 0x1234567890ABCDEF)
    check('sstatus.SIE set via view', reg64(st, 6), (2 << 32) | 0x2)
    check('mstatus mirrors sstatus.SIE', field64(st, 'mstatus') & 0x2, 0x2)
    check('stvec stored', field64(st, 'stvec'), 0x1000)

    # --- Privilege enforcement ---------------------------------------------
    print('Privilege enforcement:')
    # S-mode touching mscratch (M-only) with illegal-instr delegated -> stvec
    prog = [0] * 32
    prog[0] = CSRRW(0, STVEC, 1)      # stvec = 0x40
    prog[1] = CSRRS(5, MSCRATCH, 0)   # M-only CSR from S-mode -> trap
    prog[16] = CSRRS(6, SCAUSE, 0)    # handler: x6 = scause
    prog[17] = CSRRS(7, SEPC, 0)      # x7 = sepc
    st = gpu.run(prog, 4, priv=1, regs={1: 0x40}, csrs={'medeleg': 1 << 2})
    check('S->M CSR access trapped: scause=2', reg64(st, 6), 2)
    check('sepc = faulting pc', reg64(st, 7), 4)
    check('stval = instr word', field64(st, 'stval'), CSRRS(5, MSCRATCH, 0))
    check('trap stayed in S-mode', int(st['priv_mode']), 1)
    # Same fault NOT delegated -> lands in M-mode at mtvec
    prog2 = [0] * 32
    prog2[0] = CSRRS(5, MSCRATCH, 0)
    prog2[16] = ADDI(6, 0, 55)
    st = gpu.run(prog2, 2, priv=1, csrs={'mtvec': 0x40})
    check('undelegated trap -> M-mode', int(st['priv_mode']), 3)
    check('mcause = 2', field64(st, 'mcause'), 2)
    check('mstatus.MPP = S (1)', (int(st['mstatus'][0]) >> 11) & 3, 1)
    check('M handler executed', reg64(st, 6), 55)

    # --- U-mode ECALL delegation + SRET round trip -------------------------
    print('U-mode ECALL -> S-mode handler -> SRET:')
    prog = [0] * 32
    prog[0] = ECALL                   # U-mode ecall -> trap (cause 8) -> stvec
    prog[1] = ADDI(11, 0, 42)         # executed after SRET returns here
    prog[16] = CSRRS(6, SCAUSE, 0)    # handler (S-mode): x6 = scause
    prog[17] = CSRRS(7, SEPC, 0)      # x7 = sepc
    prog[18] = ADDI(8, 7, 4)
    prog[19] = CSRRW(0, SEPC, 8)      # sepc += 4
    prog[20] = SRET
    st = gpu.run(prog, 7, priv=0,
                 csrs={'stvec': 0x40, 'medeleg': 1 << 8})
    check('scause = ecall-from-U (8)', reg64(st, 6), 8)
    check('sepc = ecall pc', reg64(st, 7), 0)
    check('handler ran in S-mode -> SRET', reg64(st, 11), 42)
    check('SRET restored U-mode (SPP=0)', int(st['priv_mode']), 0)

    # --- SRET from S back to S (SPP=1) -------------------------------------
    print('SRET with SPP=1:')
    # sstatus.SPP=1 (bit 8) preset; SRET must stay in S-mode
    prog = [CSRRW(0, SEPC, 1), SRET, 0, ADDI(5, 0, 9)]
    st = gpu.run(prog, 3, priv=1,
                 regs={1: 0xC}, csrs={'mstatus': 0x100})
    check('SRET honored sepc', reg64(st, 5), 9)
    check('SRET kept S-mode (SPP=1)', int(st['priv_mode']), 1)
    check('SPP cleared after SRET', (field64(st, 'mstatus') >> 8) & 1, 0)

    # --- SRET/MRET privilege guards ----------------------------------------
    print('xRET privilege guards:')
    prog = [0] * 32
    prog[0] = MRET                     # MRET in S-mode -> illegal -> stvec
    prog[16] = CSRRS(6, SCAUSE, 0)
    st = gpu.run(prog, 2, priv=1, csrs={'stvec': 0x40, 'medeleg': 1 << 2})
    check('MRET from S-mode is illegal', reg64(st, 6), 2)

    # --- Linux boot protocol ------------------------------------------------
    print('Linux boot protocol (make_linux_boot_state + DTB in S-mode):')
    from riscv_gpu_cpu import make_linux_boot_state
    bs = make_linux_boot_state(0x200000, 0xFFFBF0)
    check('boot: priv = S-mode', int(bs[0]['priv_mode']), 1)
    check('boot: pc = kernel entry', int(bs[0]['pc'][0]), 0x200000)
    check('boot: a0 = hart 0', int(bs[0]['regs'][10][0]), 0)
    check('boot: a1 = DTB address', int(bs[0]['regs'][11][0]), 0xFFFBF0)
    check('boot: satp = 0 (MMU off)', int(bs[0]['satp'][0]) | int(bs[0]['satp'][1]), 0)
    check('boot: medeleg like OpenSBI', int(bs[0]['medeleg'][0]), 0xB109)
    check('boot: mideleg like OpenSBI', int(bs[0]['mideleg'][0]), 0x222)

    # S-mode kernel's first act: read the FDT magic through a1
    dtb_path = Path(__file__).parent.parent / 'gpu_machine.dtb'
    dtb = dtb_path.read_bytes()[:16] if dtb_path.exists() else b'\xd0\x0d\xfe\xed'
    LW = lambda rd, rs1, imm: i_type(0x03, rd, 2, rs1, imm)
    st = gpu.run([LW(5, 11, 0)], 1, priv=1, regs={11: 0x800}, data={0x800: dtb})
    check('DTB magic readable via a1', reg64(st, 5) & 0xFFFFFFFF, 0xEDFE0DD0)

    print()
    if failures:
        print(f'{len(failures)} FAILED: {failures}')
        sys.exit(1)
    print('ALL S-MODE + SBI TESTS PASSED')


if __name__ == '__main__':
    main()
