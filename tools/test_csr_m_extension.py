#!/usr/bin/env python3
"""
GPU test suite for the CSR system + M extension in RISCV_CPU_MMU.wgsl.

Each test hand-encodes RISC-V instruction words, loads them at PC=0 with
chosen initial register values, dispatches the compute shader one
instruction per dispatch, then reads back CPU state and asserts.
Expected values are computed independently in Python.

Run: python3 tools/test_csr_m_extension.py
"""

import sys
from pathlib import Path

import numpy as np
import wgpu
import wgpu.utils

MASK64 = (1 << 64) - 1

# ---------------------------------------------------------------------------
# Mini-assembler
# ---------------------------------------------------------------------------

def r_type(op, rd, f3, rs1, rs2, f7):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

def i_type(op, rd, f3, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

def b_type(f3, rs1, rs2, imm):
    imm &= 0x1FFF
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | \
           (rs2 << 20) | (rs1 << 15) | (f3 << 12) | \
           (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63

ADDI  = lambda rd, rs1, imm: i_type(0x13, rd, 0, rs1, imm)
SLLI  = lambda rd, rs1, sh:  i_type(0x13, rd, 1, rs1, sh)
SRAI  = lambda rd, rs1, sh:  i_type(0x13, rd, 5, rs1, sh | 0x400)
BGE   = lambda rs1, rs2, imm: b_type(5, rs1, rs2, imm)
BLT   = lambda rs1, rs2, imm: b_type(4, rs1, rs2, imm)

# M extension (funct7 = 1)
MUL    = lambda rd, rs1, rs2: r_type(0x33, rd, 0, rs1, rs2, 1)
MULH   = lambda rd, rs1, rs2: r_type(0x33, rd, 1, rs1, rs2, 1)
MULHSU = lambda rd, rs1, rs2: r_type(0x33, rd, 2, rs1, rs2, 1)
MULHU  = lambda rd, rs1, rs2: r_type(0x33, rd, 3, rs1, rs2, 1)
DIV    = lambda rd, rs1, rs2: r_type(0x33, rd, 4, rs1, rs2, 1)
DIVU   = lambda rd, rs1, rs2: r_type(0x33, rd, 5, rs1, rs2, 1)
REM    = lambda rd, rs1, rs2: r_type(0x33, rd, 6, rs1, rs2, 1)
REMU   = lambda rd, rs1, rs2: r_type(0x33, rd, 7, rs1, rs2, 1)
MULW   = lambda rd, rs1, rs2: r_type(0x3B, rd, 0, rs1, rs2, 1)
DIVW   = lambda rd, rs1, rs2: r_type(0x3B, rd, 4, rs1, rs2, 1)
DIVUW  = lambda rd, rs1, rs2: r_type(0x3B, rd, 5, rs1, rs2, 1)
REMW   = lambda rd, rs1, rs2: r_type(0x3B, rd, 6, rs1, rs2, 1)
REMUW  = lambda rd, rs1, rs2: r_type(0x3B, rd, 7, rs1, rs2, 1)

# CSR instructions (SYSTEM, funct3 selects op; rs1 doubles as zimm)
CSRRW  = lambda rd, csr, rs1: i_type(0x73, rd, 1, rs1, csr)
CSRRS  = lambda rd, csr, rs1: i_type(0x73, rd, 2, rs1, csr)
CSRRC  = lambda rd, csr, rs1: i_type(0x73, rd, 3, rs1, csr)
CSRRWI = lambda rd, csr, z:   i_type(0x73, rd, 5, z, csr)
CSRRSI = lambda rd, csr, z:   i_type(0x73, rd, 6, z, csr)
CSRRCI = lambda rd, csr, z:   i_type(0x73, rd, 7, z, csr)
MRET   = 0x30200073
WFI    = 0x10500073
FENCE  = 0x0000000F

MSCRATCH, MTVEC, MEPC, MCAUSE, MTVAL = 0x340, 0x305, 0x341, 0x342, 0x343
MSTATUS, MHARTID, MISA = 0x300, 0xF14, 0x301

# ---------------------------------------------------------------------------
# GPU runner
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import CPU_DTYPE


class GpuCpu:
    def __init__(self):
        self.device = wgpu.utils.get_default_device()
        shader_path = Path(__file__).parent / 'RISCV_CPU_MMU.wgsl'
        self.module = self.device.create_shader_module(code=shader_path.read_text())
        self.layout = self.device.create_bind_group_layout(entries=[
            {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'storage' if i < 3 else 'uniform'}}
            for i in range(4)
        ])
        self.pipeline = self.device.create_compute_pipeline(
            layout=self.device.create_pipeline_layout(bind_group_layouts=[self.layout]),
            compute={'module': self.module, 'entry_point': 'main'},
        )

    def run(self, program, steps, regs=None, csrs=None, priv=3, data=None):
        """Load program at address 0, execute `steps` instructions, return CPU state.

        `data`: optional {byte_addr: bytes} to place in memory.
        After the run, self.last_output holds the raw UART output buffer bytes.
        """
        dev, queue = self.device, self.device.queue

        mem_words = np.zeros((4096, 4), dtype=np.uint32)
        for i, word in enumerate(program):
            mem_words[i] = [word & 0xFF, (word >> 8) & 0xFF,
                            (word >> 16) & 0xFF, (word >> 24) & 0xFF]
        for addr, blob in (data or {}).items():
            for j, b in enumerate(blob):
                mem_words[(addr + j) // 4][(addr + j) % 4] = b

        cpu = np.zeros(1, dtype=CPU_DTYPE)
        cpu[0]['running'] = 1
        cpu[0]['priv_mode'] = priv
        for reg, val in (regs or {}).items():
            cpu[0]['regs'][reg] = [val & 0xFFFFFFFF, (val >> 32) & 0xFFFFFFFF]
        for name, val in (csrs or {}).items():
            cpu[0][name] = [val & 0xFFFFFFFF, (val >> 32) & 0xFFFFFFFF]

        mem_buf = dev.create_buffer(size=mem_words.nbytes,
                                    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST)
        queue.write_buffer(mem_buf, 0, mem_words.tobytes())
        cpu_buf = dev.create_buffer(
            size=cpu.nbytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC)
        queue.write_buffer(cpu_buf, 0, cpu.tobytes())
        out_buf = dev.create_buffer(size=65536,
                                    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)
        uni = np.array([1_000_000], dtype=np.uint32)
        uni_buf = dev.create_buffer(size=uni.nbytes,
                                    usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        queue.write_buffer(uni_buf, 0, uni.tobytes())

        bind_group = dev.create_bind_group(layout=self.layout, entries=[
            {'binding': 0, 'resource': {'buffer': mem_buf, 'offset': 0, 'size': mem_words.nbytes}},
            {'binding': 1, 'resource': {'buffer': cpu_buf, 'offset': 0, 'size': cpu.nbytes}},
            {'binding': 2, 'resource': {'buffer': out_buf, 'offset': 0, 'size': 65536}},
            {'binding': 3, 'resource': {'buffer': uni_buf, 'offset': 0, 'size': uni.nbytes}},
        ])

        encoder = dev.create_command_encoder()
        for _ in range(steps):
            p = encoder.begin_compute_pass()
            p.set_pipeline(self.pipeline)
            p.set_bind_group(0, bind_group)
            p.dispatch_workgroups(1)
            p.end()
        queue.submit([encoder.finish()])

        self.last_output = np.frombuffer(queue.read_buffer(out_buf), dtype=np.uint8)
        return np.frombuffer(queue.read_buffer(cpu_buf), dtype=CPU_DTYPE)[0]


def reg64(state, i):
    return (int(state['regs'][i][1]) << 32) | int(state['regs'][i][0])

def field64(state, name):
    return (int(state[name][1]) << 32) | int(state[name][0])

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

failures = []

def check(name, actual, expected):
    ok = actual == expected
    status = 'PASS' if ok else 'FAIL'
    print(f'  [{status}] {name}: got 0x{actual:016x}' +
          ('' if ok else f', expected 0x{expected:016x}'))
    if not ok:
        failures.append(name)


def sext64(v):
    v &= MASK64
    return v - (1 << 64) if v >> 63 else v

def py_divw(a32, b32):
    """RISC-V DIVW reference (32-bit signed, sign-extended)."""
    a = a32 - (1 << 32) if a32 >> 31 else a32
    b = b32 - (1 << 32) if b32 >> 31 else b32
    if b == 0:
        return MASK64  # -1
    if a == -(1 << 31) and b == -1:
        return (a & MASK64)
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q & MASK64


def main():
    gpu = GpuCpu()
    print(f'Device: {gpu.device.adapter.info.device}\n')

    A = 0xDEADBEEFCAFEBABE  # negative as i64
    B = 0x123456789ABCDEF0  # positive
    sA, sB = sext64(A), sext64(B)

    # --- M extension, 64-bit -------------------------------------------------
    print('M extension (64-bit):')
    prog = [MUL(5, 1, 2), MULH(6, 1, 2), MULHU(7, 1, 2), MULHSU(8, 1, 2),
            DIV(9, 1, 2), DIVU(10, 1, 2), REM(11, 1, 2), REMU(12, 1, 2)]
    st = gpu.run(prog, len(prog), regs={1: A, 2: B})
    check('MUL', reg64(st, 5), (sA * sB) & MASK64)
    check('MULH', reg64(st, 6), ((sA * sB) >> 64) & MASK64)
    check('MULHU', reg64(st, 7), ((A * B) >> 64) & MASK64)
    check('MULHSU', reg64(st, 8), ((sA * B) >> 64) & MASK64)
    # Python // floors; RISC-V truncates toward zero
    q = abs(sA) // abs(sB) * (-1 if (sA < 0) != (sB < 0) else 1)
    r = sA - q * sB
    check('DIV', reg64(st, 9), q & MASK64)
    check('DIVU', reg64(st, 10), (A // B) & MASK64)
    check('REM', reg64(st, 11), r & MASK64)
    check('REMU', reg64(st, 12), (A % B) & MASK64)

    print('M extension (spec edge cases):')
    prog = [DIV(5, 1, 0), REM(6, 1, 0), DIVU(7, 1, 0), REMU(8, 1, 0),
            DIV(9, 3, 4), REM(10, 3, 4)]
    st = gpu.run(prog, len(prog),
                 regs={1: A, 3: 0x8000000000000000, 4: MASK64})
    check('DIV/0 -> -1', reg64(st, 5), MASK64)
    check('REM/0 -> dividend', reg64(st, 6), A)
    check('DIVU/0 -> all ones', reg64(st, 7), MASK64)
    check('REMU/0 -> dividend', reg64(st, 8), A)
    check('INT64_MIN / -1 -> INT64_MIN', reg64(st, 9), 0x8000000000000000)
    check('INT64_MIN % -1 -> 0', reg64(st, 10), 0)

    # --- M extension, W forms ------------------------------------------------
    print('M extension (W forms):')
    a32, b32 = 0xFFFFFFF9, 0x00000003  # -7, 3
    prog = [MULW(5, 1, 2), DIVW(6, 1, 2), REMW(7, 1, 2),
            DIVUW(8, 1, 2), REMUW(9, 1, 2), DIVW(10, 1, 0), REMUW(11, 1, 0)]
    st = gpu.run(prog, len(prog), regs={1: a32, 2: b32})
    check('MULW -7*3', reg64(st, 5), (-21) & MASK64)
    check('DIVW -7/3', reg64(st, 6), (-2) & MASK64)
    check('REMW -7%3', reg64(st, 7), (-1) & MASK64)
    check('DIVUW', reg64(st, 8), (a32 // b32) & MASK64 if (a32 // b32) >> 31 == 0 else 0)
    check('REMUW', reg64(st, 9), a32 % b32)
    check('DIVW/0 -> -1', reg64(st, 10), MASK64)
    check('REMUW/0 -> dividend (sext)', reg64(st, 11), sext64(a32 | 0xFFFFFFFF00000000) & MASK64)

    # --- CSRs ---------------------------------------------------------------
    print('CSRs:')
    prog = [
        CSRRS(5, MHARTID, 0),    # x5 = mhartid (0)
        CSRRW(0, MSCRATCH, 1),   # mscratch = x1
        CSRRS(6, MSCRATCH, 2),   # x6 = old mscratch; mscratch |= x2
        CSRRC(7, MSCRATCH, 2),   # x7 = old; mscratch &= ~x2
        CSRRWI(8, MSCRATCH, 21), # x8 = old; mscratch = 21
        CSRRSI(9, MSCRATCH, 10), # x9 = 21; mscratch |= 10
        CSRRS(10, MISA, 0),      # x10 = misa
    ]
    st = gpu.run(prog, len(prog), regs={1: 0xAAAA0000AAAA0000, 2: 0x5555000055550000})
    check('CSRR mhartid', reg64(st, 5), 0)
    check('CSRRS returns old', reg64(st, 6), 0xAAAA0000AAAA0000)
    check('CSRRS set bits', reg64(st, 7), 0xFFFF0000FFFF0000)
    check('CSRRC cleared bits', reg64(st, 8), 0xAAAA0000AAAA0000)
    check('CSRRWI wrote imm', reg64(st, 9), 21)
    check('CSRRSI final mscratch', field64(st, 'mscratch'), 21 | 10)
    check('misa = RV64 A+I+M+S+U', reg64(st, 10),
          (2 << 62) | (1 << 0) | (1 << 8) | (1 << 12) | (1 << 18) | (1 << 20))

    # --- Trap + MRET ---------------------------------------------------------
    print('Trap and MRET:')
    # mtvec = 0x40 (word 16). Illegal instruction at PC=8 traps there;
    # handler reads mcause and MRETs back to PC=12; ADDI at 12 proves return.
    prog = [0] * 32
    prog[0] = i_type(0x13, 5, 0, 0, 0x40)   # ADDI x5, x0, 0x40
    prog[1] = CSRRW(0, MTVEC, 5)            # mtvec = 0x40
    prog[2] = 0xFFFFFFFF                    # illegal -> trap
    prog[3] = ADDI(11, 0, 99)               # executed after MRET
    prog[16] = CSRRS(6, MCAUSE, 0)          # handler: x6 = mcause
    prog[17] = CSRRS(7, MEPC, 0)            # x7 = mepc
    prog[18] = ADDI(8, 7, 4)                # x8 = mepc + 4
    prog[19] = CSRRW(0, MEPC, 8)            # mepc += 4 (skip bad instr)
    prog[20] = MRET
    st = gpu.run(prog, 9)  # 3 + 5 handler + 1 after return
    check('mcause = illegal (2)', reg64(st, 6), 2)
    check('mepc = faulting PC', reg64(st, 7), 8)
    check('mtval = instr word', field64(st, 'mtval'), 0xFFFFFFFF)
    check('MPP saved as M (3)', (int(st['mstatus'][0]) >> 11) & 3, 0)  # cleared by MRET
    check('resumed after MRET', reg64(st, 11), 99)
    check('priv restored to M', int(st['priv_mode']), 3)

    # --- Regression: fixed RV64I bugs ---------------------------------------
    print('RV64I regressions (branch/shift fixes):')
    prog = [
        BGE(1, 1, 8),                        # equal -> must branch (skip next)
        ADDI(5, 0, 1),                       # skipped if BGE works
        BLT(2, 3, 8),                        # -1 < 1 signed -> must branch
        ADDI(6, 0, 1),                       # skipped if BLT works
        SRAI(7, 4, 4),                       # 0x8000... >> 4 arithmetic
        SLLI(8, 3, 0),                       # shift by 0 must not corrupt
    ]
    st = gpu.run(prog, 4, regs={1: 5, 2: MASK64, 3: 1, 4: 0x8000000000000000})
    check('BGE taken on equal', reg64(st, 5), 0)
    check('BLT signed taken', reg64(st, 6), 0)
    st = gpu.run(prog, 6, regs={1: 5, 2: 0, 3: 1, 4: 0x8000000000000000})
    check('SRAI negative shamt<32', reg64(st, 7), 0xF800000000000000)
    check('SLLI shamt=0 identity', reg64(st, 8), 1)

    # Regression: sign_extend_12/21 masks were each off by one bit width,
    # forcing extra bits set (corrupting bits just below the sign bit) for
    # small-magnitude negative immediates - e.g. -212 as a 21-bit JAL offset
    # landed 2MB short of its real target. Only shows up when those bits are 0.
    JAL = lambda rd, imm: (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3FF) << 21) | \
                           (((imm >> 11) & 1) << 20) | (((imm >> 12) & 0xFF) << 12) | (rd << 7) | 0x6F
    st = gpu.run([ADDI(5, 0, -212 & 0xFFF)], 1)
    check('ADDI small negative imm (-212)', reg64(st, 5), (-212) & MASK64)
    st = gpu.run([JAL(6, -212)], 1)
    check('JAL small negative offset (-212)', int(st['pc'][0]), (-212) & 0xFFFFFFFF)

    # --- WFI / FENCE are NOPs -----------------------------------------------
    print('Misc:')
    prog = [WFI, FENCE, ADDI(5, 0, 7)]
    st = gpu.run(prog, 3)
    check('WFI+FENCE fall through', reg64(st, 5), 7)

    print()
    if failures:
        print(f'{len(failures)} FAILED: {failures}')
        sys.exit(1)
    print('ALL TESTS PASSED')


if __name__ == '__main__':
    main()
