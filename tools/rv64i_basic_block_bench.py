#!/usr/bin/env python3
"""
rv64i_basic_block_bench.py — RV64I analog of
systems/geos_pixel_v5/examples/basic_block_rv32i_bench.rs (commit f4e49ee).

Runs the SAME idea (a tiny "sum 1..N" program, decoded ONCE on the host into
DecodedOp and executed by every GPU lane from a shared read-only buffer — no
per-instruction bitfield decode) but with genuinely 64-bit registers, so every op
also pays the vec2<u32> 64-bit-arithmetic cost that SPATIAL_RV64I.wgsl pays and the
32-bit benchmark never did. Isolates the question: does removing the decode tax
still cross 1.0x vs CPU once every op also carries that emulation overhead?

Each of N independent instances gets 2 dwords of scratch RAM: in[0]=the value to
sum 1..that_value, out[1]=the computed sum. All instances run the identical program;
only the input differs, so the workgroup does the same real work as N genuinely
separate program executions (not N copies of one precomputed answer).

CPU baseline: a numba-JIT-compiled scalar interpretation of the exact same DecodedOp
array — one native CPU thread per instance, the RV64I counterpart of the RV32I Rust
baseline (examples/basic_block_rv32i_bench.rs). This is a genuinely representative CPU
reference (native compiled code), so the reported speedup is an honest "GPU vs real
CPU" ratio rather than the inflated figure a slow Python/numpy-vectorized proxy would
give (a prior version used that proxy and reported 700-1600x, which overstates the
real CPU-comparison margin — see PIXEL_GPU_COMPUTE_RECEIPT.md §8.1).

Usage: python3 tools/rv64i_basic_block_bench.py [N1 N2 ...]
"""
import sys
import time
import numpy as np
from numba import njit
import wgpu
import wgpu.utils
from pathlib import Path

# --- Program: sum 1..input in RV64I DecodedOp form (see basic_block_rv64i.wgsl) ---
# op: 0=ADDI 1=LD 2=SD 3=BLT 4=JAL 5=ADD 6=HALT
# x1=sum x2=i x3=N(loaded from ram[0]); SD's "rd" field is the *value* register per
# the same convention as the RV32I original.
PROGRAM = [
    # idx 0: LD x3, 0(x0)        x3 = ram[base+0] = N
    dict(op=1, rd=3, rs1=0, rs2=0, imm=0),
    # idx 1: ADDI x1, x0, 0      sum = 0
    dict(op=0, rd=1, rs1=0, rs2=0, imm=0),
    # idx 2: ADDI x2, x0, 1      i = 1
    dict(op=0, rd=2, rs1=0, rs2=0, imm=1),
    # idx 3 (loop_check): BLT x3 < x2 -> exit(idx 7)   i.e. jump out once i > N
    dict(op=3, rd=3, rs1=2, rs2=0, imm=7),
    # idx 4: ADD x1, x1, x2      sum += i
    dict(op=5, rd=1, rs1=1, rs2=2, imm=0),
    # idx 5: ADDI x2, x2, 1      i++
    dict(op=0, rd=2, rs1=2, rs2=0, imm=1),
    # idx 6: JAL -> idx 3 (loop_check)
    dict(op=4, rd=0, rs1=0, rs2=0, imm=3),
    # idx 7 (exit): SD ram[base+8] = x1   (byte offset 8 -> dword index 1)
    dict(op=2, rd=1, rs1=0, rs2=0, imm=8),
    # idx 8: HALT
    dict(op=6, rd=0, rs1=0, rs2=0, imm=0),
]
STEP_BUDGET = 1000  # must exceed 4*max_N + prologue/epilogue for every instance's N


def program_arrays():
    op = np.array([p['op'] for p in PROGRAM], dtype=np.int64)
    rd = np.array([p['rd'] for p in PROGRAM], dtype=np.int64)
    rs1 = np.array([p['rs1'] for p in PROGRAM], dtype=np.int64)
    rs2 = np.array([p['rs2'] for p in PROGRAM], dtype=np.int64)
    imm = np.array([p['imm'] for p in PROGRAM], dtype=np.int64)
    return op, rd, rs1, rs2, imm


def program_bytes():
    """DecodedOp is 6 x u32 = 24 bytes: op, rd, rs1, rs2, imm_lo, imm_hi."""
    words = []
    for p in PROGRAM:
        imm = p['imm'] & 0xFFFFFFFFFFFFFFFF
        words += [p['op'], p['rd'], p['rs1'], p['rs2'], imm & 0xFFFFFFFF, (imm >> 32) & 0xFFFFFFFF]
    return np.array(words, dtype=np.uint32).tobytes()


@njit
def _cpu_ref(op, rd, rs1, rs2, imm, values, step_budget):
    """Compiled (numba) scalar interpretation of the DecodedOp array — one CPU thread
    per instance, the direct RV64I counterpart of the RV32I Rust baseline in
    examples/basic_block_rv32i_bench.rs. Semantics mirror the WGSL kernel exactly
    (same op ordering, same BLT 'regs[rd] < regs[rs1]' convention, same SD 'rd-is-the-
    value-register' convention, LD/SD address = (rs1 + imm)>>3 dword index). This is a
    genuinely representative CPU reference — native scalar code, not a slow vectorized
    proxy — so the speedup it yields is an honest 'GPU vs real CPU' ratio."""
    n = values.shape[0]
    n_ops = op.shape[0]
    out = np.zeros(n, dtype=np.int64)
    regs = np.zeros(32, dtype=np.int64)
    ram = np.zeros(2, dtype=np.int64)
    for inst in range(n):
        regs[:] = 0
        ram[0] = values[inst]
        ram[1] = 0
        pc = 0
        for _ in range(step_budget):
            o = op[pc]
            if o == 6:  # HALT
                break
            r = rd[pc]
            s1 = rs1[pc]
            s2 = rs2[pc]
            im = imm[pc]
            if o == 0:                      # ADDI rd = rs1 + imm
                regs[r] = regs[s1] + im
            elif o == 5:                    # ADD rd = rs1 + rs2
                regs[r] = regs[s1] + regs[s2]
            elif o == 1:                    # LD rd = ram[(rs1 + imm)>>3]
                a = (regs[s1] + im) >> 3
                regs[r] = ram[a] if 0 <= a < 2 else 0
            elif o == 2:                    # SD ram[(rs1 + imm)>>3] = value reg (rd)
                a = (regs[s1] + im) >> 3
                if 0 <= a < 2:
                    ram[a] = regs[r]
            elif o == 3:                    # BLT: branch if regs[rd] < regs[rs1]
                if regs[r] < regs[s1]:
                    pc = im
                    continue
            elif o == 4:                    # JAL: unconditional
                pc = im
                continue
            pc += 1
        out[inst] = ram[1]
    return out


def run_cpu(n: int, values: np.ndarray) -> np.ndarray:
    """Compiled scalar CPU interpretation of PROGRAM for all n instances (numba)."""
    op, rd, rs1, rs2, imm = program_arrays()
    op_i = op.astype(np.int64)
    return _cpu_ref(op_i, rd, rs1, rs2, imm, values, STEP_BUDGET)


def run_gpu(n: int, values: np.ndarray) -> tuple[np.ndarray, float]:
    device = wgpu.utils.get_default_device()
    queue = device.queue

    prog_bytes = program_bytes()
    prog_buf = device.create_buffer(
        size=len(prog_bytes), usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
    )
    queue.write_buffer(prog_buf, 0, prog_bytes)

    ram = np.zeros((n, 2, 2), dtype=np.uint32)  # [instance][dword: in/out][lo,hi]
    ram[:, 0, 0] = values.astype(np.uint32)
    ram_bytes = ram.tobytes()
    ram_buf = device.create_buffer(
        size=len(ram_bytes),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC,
    )
    queue.write_buffer(ram_buf, 0, ram_bytes)

    shader_code = (Path(__file__).parent / 'basic_block_rv64i.wgsl').read_text()
    module = device.create_shader_module(code=shader_code)

    layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
    ])
    bind_group = device.create_bind_group(layout=layout, entries=[
        {'binding': 0, 'resource': {'buffer': prog_buf, 'offset': 0, 'size': prog_buf.size}},
        {'binding': 1, 'resource': {'buffer': ram_buf, 'offset': 0, 'size': ram_buf.size}},
    ])
    pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[layout]),
        compute={'module': module, 'entry_point': 'main'},
    )

    workgroups = (n + 63) // 64
    t0 = time.time()
    encoder = device.create_command_encoder()
    pass_ = encoder.begin_compute_pass()
    pass_.set_pipeline(pipeline)
    pass_.set_bind_group(0, bind_group)
    pass_.dispatch_workgroups(workgroups)
    pass_.end()
    queue.submit([encoder.finish()])
    out_bytes = queue.read_buffer(ram_buf)  # blocking; forces sync
    t1 = time.time()

    out = np.frombuffer(out_bytes, dtype=np.uint32).reshape((n, 2, 2))
    sums = out[:, 1, 0].astype(np.int64) | (out[:, 1, 1].astype(np.int64) << 32)
    return sums, (t1 - t0)


def bench(n: int):
    rng = np.random.default_rng(42)
    values = rng.integers(1, 200, size=n).astype(np.int64)  # keep well under STEP_BUDGET/4
    expected = values * (values + 1) // 2

    t0 = time.time()
    cpu_sums = run_cpu(n, values)
    cpu_elapsed = time.time() - t0
    cpu_ok = np.array_equal(cpu_sums, expected)

    gpu_sums, gpu_elapsed = run_gpu(n, values)
    gpu_ok = np.array_equal(gpu_sums, expected)

    speedup = cpu_elapsed / gpu_elapsed if gpu_elapsed > 0 else float('inf')
    print(f"N={n:>9,}  CPU={cpu_elapsed:7.3f}s  GPU={gpu_elapsed:7.3f}s  "
          f"speedup={speedup:5.2f}x  cpu_correct={cpu_ok}  gpu_correct={gpu_ok}")
    if not (cpu_ok and gpu_ok):
        print("  !! MISMATCH — do not trust this speedup number until fixed")
        bad = np.where(gpu_sums != expected)[0][:5]
        for i in bad:
            print(f"     instance {i}: value={values[i]} expected={expected[i]} got={gpu_sums[i]}")


if __name__ == '__main__':
    ns = [int(x) for x in sys.argv[1:]] or [100_000, 1_000_000, 2_000_000, 4_000_000]
    for n in ns:
        bench(n)
