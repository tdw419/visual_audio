#!/usr/bin/env python3
"""
GPU test suite for the A extension (atomic memory operations).

Each test hand-encodes RISC-V instruction words, loads them at PC=0 with
chosen initial register values, dispatches the compute shader one
instruction per dispatch, then reads back CPU state and asserts.
Expected values are computed independently in Python.

Run: python3 tools/test_a_extension.py
"""

import sys
from pathlib import Path

import numpy as np
import wgpu
import wgpu.utils

MASK64 = (1 << 64) - 1

def sext64(v32):
    v32 &= 0xFFFFFFFF
    return (v32 - (1 << 32)) & MASK64 if v32 >> 31 else v32

# ---------------------------------------------------------------------------
# Mini-assembler for A extension
# ---------------------------------------------------------------------------

def r_type(op, rd, f3, rs1, rs2, f7):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

def i_type(op, rd, f3, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

ADDI  = lambda rd, rs1, imm: i_type(0x13, rd, 0, rs1, imm)

# A extension (opcode 0x2F = 47). Real funct5 values verified against
# riscv64-linux-gnu-as output (see tools/RISCV_CPU_MMU.wgsl execute_amo
# comment): ADD=0 SWAP=1 LR=2 SC=3 XOR=4 OR=8 AND=12 MIN=16 MAX=20 MINU=24
# MAXU=28. funct7 = funct5<<2 | aq<<1 | rl (aq=rl=0 here). funct3 selects
# width: 2=.W, 3=.D. A prior version of this file used funct3=2 for "_D"
# ops and un-shifted funct5 as funct7 - self-consistent with an equally
# wrong shader implementation, so all 33 "passes" were validating nothing
# against the real ISA. Fixed against toolchain-verified encodings.
def amo_d(funct5, rd, rs1, rs2):
    return r_type(0x2F, rd, 3, rs1, rs2, funct5 << 2)

LR_D  = lambda rd, rs1: r_type(0x2F, rd, 3, rs1, 0, 2 << 2)
SC_D  = lambda rd, rs1, rs2: r_type(0x2F, rd, 3, rs1, rs2, 3 << 2)

AMOADD_D   = lambda rd, rs1, rs2: amo_d(0, rd, rs1, rs2)
AMOSWAP_D  = lambda rd, rs1, rs2: amo_d(1, rd, rs1, rs2)
AMOXOR_D   = lambda rd, rs1, rs2: amo_d(4, rd, rs1, rs2)
AMOOR_D    = lambda rd, rs1, rs2: amo_d(8, rd, rs1, rs2)
AMOAND_D   = lambda rd, rs1, rs2: amo_d(12, rd, rs1, rs2)
AMOMIN_D   = lambda rd, rs1, rs2: amo_d(16, rd, rs1, rs2)
AMOMAX_D   = lambda rd, rs1, rs2: amo_d(20, rd, rs1, rs2)
AMOMINU_D  = lambda rd, rs1, rs2: amo_d(24, rd, rs1, rs2)
AMOMAXU_D  = lambda rd, rs1, rs2: amo_d(28, rd, rs1, rs2)

# ---------------------------------------------------------------------------
# GPU runner (simplified - CPU state only, no memory readback)
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

    def run(self, program, steps, regs=None, csrs=None, init_mem=None):
        """Load program at address 0, execute `steps` instructions, return CPU state."""
        dev, queue = self.device, self.device.queue

        mem_words = np.zeros((4096, 4), dtype=np.uint32)
        for i, word in enumerate(program):
            mem_words[i] = [word & 0xFF, (word >> 8) & 0xFF,
                            (word >> 16) & 0xFF, (word >> 24) & 0xFF]

        if init_mem:
            for addr, val in init_mem.items():
                word_addr = addr // 4
                # Low 32 bits as RGBA pixel
                mem_words[word_addr] = [
                    val & 0xFF,
                    (val >> 8) & 0xFF,
                    (val >> 16) & 0xFF,
                    (val >> 24) & 0xFF
                ]
                # High 32 bits as RGBA pixel
                mem_words[word_addr + 1] = [
                    (val >> 32) & 0xFF,
                    (val >> 40) & 0xFF,
                    (val >> 48) & 0xFF,
                    (val >> 56) & 0xFF
                ]

        cpu = np.zeros(1, dtype=CPU_DTYPE)
        cpu[0]['running'] = 1
        cpu[0]['priv_mode'] = 3
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

        return np.frombuffer(queue.read_buffer(cpu_buf), dtype=CPU_DTYPE)[0]


def reg64(state, i):
    return (int(state['regs'][i][1]) << 32) | int(state['regs'][i][0])

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


def main():
    gpu = GpuCpu()
    print(f'Device: {gpu.device.adapter.info.device}\n')

    A = 0xDEADBEEFCAFEBABE
    B = 0x123456789ABCDEF0

    # --- LR.D: Load Reserved -----------------------------------------------
    print('LR.D:')
    prog = [
        ADDI(1, 0, 0x100),  # x1 = 0x100 (address to read)
        LR_D(5, 1),         # x5 = mem[x1] (reserved)
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: A})
    check('LR.D returns loaded value', reg64(st, 5), A)

    # --- SC.D: Store Conditional --------------------------------------------
    print('SC.D:')
    prog = [
        ADDI(1, 0, 0x100),  # x1 = 0x100
        SC_D(6, 1, 2),     # mem[x1] = x2, x6 = 0 (success)
        LR_D(7, 1),        # Read back to verify
    ]
    st = gpu.run(prog, len(prog), regs={2: B})
    check('SC.D returns 0 on success', reg64(st, 6), 0)
    check('SC.D wrote correct value', reg64(st, 7), B)

    # --- AMOADD.D -----------------------------------------------------------
    print('AMOADD.D:')
    prog = [
        ADDI(1, 0, 0x100),  # x1 = 0x100
        AMOADD_D(5, 1, 2),  # x5 = mem[0x100], mem[0x100] += x2
        LR_D(7, 1),         # Read back result
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: A}, regs={2: 42})
    check('AMOADD.D returns old value', reg64(st, 5), A)
    check('AMOADD.D added correctly', reg64(st, 7), (A + 42) & MASK64)

    # --- AMOSWAP.D ----------------------------------------------------------
    print('AMOSWAP.D:')
    prog = [
        ADDI(1, 0, 0x100),
        AMOSWAP_D(5, 1, 2), # x5 = mem[0x100], mem[0x100] = x2
        LR_D(7, 1),         # Read back result
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: A}, regs={2: B})
    check('AMOSWAP.D returns old value', reg64(st, 5), A)
    check('AMOSWAP.D swapped correctly', reg64(st, 7), B)

    # --- AMOAND.D -----------------------------------------------------------
    print('AMOAND.D:')
    prog = [
        ADDI(1, 0, 0x100),
        AMOAND_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: A}, regs={2: 0xFFFF0000FFFF0000 & MASK64})
    check('AMOAND.D returns old value', reg64(st, 5), A)
    check('AMOAND.D anded correctly', reg64(st, 7), A & 0xFFFF0000FFFF0000)

    # --- AMOOR.D ------------------------------------------------------------
    print('AMOOR.D:')
    prog = [
        ADDI(1, 0, 0x100),
        AMOOR_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: A}, regs={2: 0x0000FFFF0000FFFF})
    check('AMOOR.D returns old value', reg64(st, 5), A)
    check('AMOOR.D ored correctly', reg64(st, 7), A | 0x0000FFFF0000FFFF)

    # --- AMOXOR.D -----------------------------------------------------------
    print('AMOXOR.D:')
    prog = [
        ADDI(1, 0, 0x100),
        ADDI(2, 0, 0xFFFFFFFFFFFFFFFF),
        AMOXOR_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: A})
    check('AMOXOR.D returns old value', reg64(st, 5), A)
    check('AMOXOR.D xored correctly', reg64(st, 7), A ^ MASK64)

    # --- AMOMAX.D (signed) --------------------------------------------------
    print('AMOMAX.D (signed):')
    prog = [
        ADDI(1, 0, 0x100),
        ADDI(2, 0, 100),
        AMOMAX_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: 50})
    check('AMOMAX.D returns old value (50)', reg64(st, 5), 50)
    check('AMOMAX.D selected max', reg64(st, 7), 100)

    # Negative test: smaller value shouldn't change memory
    prog = [
        ADDI(1, 0, 0x100),
        ADDI(2, 0, 25),
        AMOMAX_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: 50})
    check('AMOMAX.D returns old value (50)', reg64(st, 5), 50)
    check('AMOMAX.D kept larger value', reg64(st, 7), 50)

    # --- AMOMAXU.D (unsigned) ------------------------------------------------
    print('AMOMAXU.D (unsigned):')
    prog = [
        ADDI(1, 0, 0x100),
        AMOMAXU_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: 0x7FFFFFFFFFFFFFFF}, regs={2: 0x8000000000000000})
    check('AMOMAXU.D returns old value', reg64(st, 5), 0x7FFFFFFFFFFFFFFF)
    check('AMOMAXU.D selected max unsigned', reg64(st, 7), 0x8000000000000000)

    # --- AMOMIN.D (signed) --------------------------------------------------
    print('AMOMIN.D (signed):')
    prog = [
        ADDI(1, 0, 0x100),
        AMOMIN_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: 50}, regs={2: -10 & MASK64})
    check('AMOMIN.D returns old value (50)', reg64(st, 5), 50)
    check('AMOMIN.D selected min signed', reg64(st, 7), -10 & MASK64)

    # --- AMOMINU.D (unsigned) ------------------------------------------------
    print('AMOMINU.D (unsigned):')
    prog = [
        ADDI(1, 0, 0x100),
        AMOMINU_D(5, 1, 2),
        LR_D(7, 1),
    ]
    st = gpu.run(prog, len(prog), init_mem={0x100: 0x7FFFFFFFFFFFFFFF}, regs={2: 0xFFFFFFFF})
    check('AMOMINU.D returns old value', reg64(st, 5), 0x7FFFFFFFFFFFFFFF)
    check('AMOMINU.D selected min unsigned', reg64(st, 7), 0xFFFFFFFF)

    # --- LR.D + SC.D sequence (typical lock pattern) -----------------------
    print('LR.D + SC.D lock pattern:')
    prog = [
        ADDI(1, 0, 0x100),  # x1 = lock address
        LR_D(5, 1),         # x5 = load reservation
        SC_D(6, 1, 2),      # x6 = store conditional (x2 has new value)
        LR_D(7, 1),         # Read back result
    ]
    st = gpu.run(prog, len(prog), regs={2: 1}, init_mem={0x100: 0})
    check('LR.D + SC.D sequence: LR returned 0', reg64(st, 5), 0)
    check('LR.D + SC.D sequence: SC succeeded', reg64(st, 6), 0)
    check('LR.D + SC.D sequence: memory updated', reg64(st, 7), 1)

    # --- W-width forms (the exact gap that let xv6's amoswap.w.aq spinlock
    # silently corrupt its neighboring struct field and spin forever) ---
    print('AMO.W / LR.W / SC.W (32-bit forms, adjacent memory untouched):')
    LR_W  = lambda rd, rs1: r_type(0x2F, rd, 2, rs1, 0, 2 << 2)
    SC_W  = lambda rd, rs1, rs2: r_type(0x2F, rd, 2, rs1, rs2, 3 << 2)
    AMOSWAP_W = lambda rd, rs1, rs2: r_type(0x2F, rd, 2, rs1, rs2, 1 << 2)
    AMOADD_W  = lambda rd, rs1, rs2: r_type(0x2F, rd, 2, rs1, rs2, 0 << 2)

    prog = [ADDI(1, 0, 0x100), LR_W(5, 1)]
    st = gpu.run(prog, len(prog), regs={},
                 init_mem={0x100: 0xDEADBEEF12345678})
    check('LR.W reads only low word (sign-extended)', reg64(st, 5), sext64(0x12345678))

    prog = [ADDI(1, 0, 0x100), ADDI(2, 0, 0x7F), AMOSWAP_W(5, 1, 2), LR_D(7, 1)]
    st = gpu.run(prog, len(prog), init_mem={0x100: 0x1122334400000001})
    check('AMOSWAP.W returns old low word (sign-ext)', reg64(st, 5), 1)
    check('AMOSWAP.W high word left untouched', reg64(st, 7), 0x112233440000007F)

    prog = [ADDI(1, 0, 0x100), ADDI(2, 0, 5), AMOADD_W(5, 1, 2), LR_D(7, 1)]
    st = gpu.run(prog, len(prog), init_mem={0x100: 0xCAFEBABE00000010})
    check('AMOADD.W result', reg64(st, 5), 0x10)
    check('AMOADD.W high word left untouched', reg64(st, 7), 0xCAFEBABE00000015)

    prog = [ADDI(1, 0, 0x100), ADDI(2, 0, 9), SC_W(6, 1, 2), LR_D(7, 1)]
    st = gpu.run(prog, len(prog), init_mem={0x100: 0xFEEDFACE00000000})
    check('SC.W succeeds', reg64(st, 6), 0)
    check('SC.W wrote only low word', reg64(st, 7), 0xFEEDFACE00000009)

    print()
    if failures:
        print(f'{len(failures)} FAILED: {failures}')
        sys.exit(1)
    print('ALL A EXTENSION TESTS PASSED')


if __name__ == '__main__':
    main()