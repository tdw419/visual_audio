#!/usr/bin/env python3
"""
Item 5b.3 — the parallelism question, measured.

  Does K-parallel SHA-256 on the WGSL glyph kernel beat K serial hashes on
  GlyphCPUv2 (the Python interpreter), given item 5's finding that
  per-instruction the glyph kernel loses ~3-4x?

Method (kept honest):
  * Curve over K (1,2,4,8,16,32,64,128,256), not a point. Crossover K is the
    answer; a single K would be cherry-picking.
  * Wall-clock end-to-end per batch: assemble once (excluded), then buffer
    upload + dispatch loop + readback + digest extraction all INCLUDED. The
    WGSL runner steps one instruction per dispatch (parity model), so the GPU
    side pays ~8,760 dispatch round-trips per block — the honest integration
    cost under the current step-locked design.
  * Baselines per K: GlyphCPUv2-serial (headline, the real alternative),
    hashlib (sanity floor / "why offload at all" anchor).
  * Digests verified against hashlib for every K on every engine.

Notes:
  * Serial-on-GPU (K=1) vs Python-serial isolates the "GPU step-locked
    interpreter" cost; the K curve shows whether SIMT scaling can overcome it.
  * SHA-256 is the BEST CASE for SIMT: branch-light, lockstep-uniform, zero
    divergence. If the GPU loses here it loses everywhere; if it wins, the
    win is a lower bound for branchier kernels with the same structure.
"""
import contextlib
import hashlib
import io
import sys
import time
from pathlib import Path

import numpy as np

_THIS = Path(__file__).resolve()
_GD_ROOT = _THIS.parents[1]
_REPO_ROOT = _THIS.parents[2]
for p in (str(_REPO_ROOT / "tools"), str(_REPO_ROOT), str(_GD_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "parity", _GD_ROOT / "tests" / "test_item5b_wgsl_parity.py")
_parity = _ilu.module_from_spec(_spec)
sys.modules["parity"] = _parity
_spec.loader.exec_module(_parity)
WORDBASE_DB = _parity.WORDBASE_DB
WgslRunner = _parity.WgslRunner
_opmap = _parity._opmap
from src.glyph.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2  # noqa: E402
from src.glyph.sha256_kernel import (  # noqa: E402
    BLK_BASE, BCNT_ADDR, K_BASE, OUT_BASE, _K, _pad,
    build_sha256_glyph_program)
from src.glyph.wgsl_glyph_isa_v2 import make_cpu_state_array  # noqa: E402

WIDTH = 64          # kernel layout width
N_BLOCKS = 1        # one 512-bit block per hash (55-byte messages max)
KS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
REPS = 3            # per-K repeats; report min (least-noise)
STEPS_PER_DISPATCH = 128   # shader instructions per dispatch (batched mode)


def build_kernel_image():
    op = _opmap()
    try:
        asm = GlyphAssemblerV2(op)
        return asm.assemble(build_sha256_glyph_program(WIDTH),
                            width_instrs=WIDTH)
    finally:
        op.close()


def seed_message(ram: np.ndarray, msg: bytes):
    """Seed K independent copies of the same message (homogeneous batch —
    the SHA-256 kernel's own block loop handles multi-block; here each of
    the K lanes gets its own message region so lanes are independent)."""
    padded = _pad(msg)
    nblocks = len(padded) // 64
    words = np.frombuffer(padded, dtype=">u4").astype(np.uint32)
    return nblocks, words


def gpu_batch(runner, image, msgs, max_instructions=400_000):
    """Run K hashes in parallel; wall-clock includes upload+dispatch+readback.
    Each lane gets its own RAM copy (4096 words), message seeded per lane.
    Returns (digests, wall_seconds)."""
    import wgpu
    device, queue = runner.device, runner.device.queue
    K = len(msgs)

    rows, width_px, _ = image.shape
    w, h = width_px, rows
    img_u32 = np.zeros((h, w, 4), dtype=np.uint32)
    img_u32[:, :, :3] = np.ascontiguousarray(image)
    img_flat = img_u32.reshape(-1)

    cpus, dtype = make_cpu_state_array(K)
    out_words = 256 * K
    RAM_WORDS = 4096

    t0 = time.perf_counter()

    img_buf = device.create_buffer(
        size=img_flat.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST |
              wgpu.BufferUsage.COPY_SRC)
    queue.write_buffer(img_buf, 0, img_flat.tobytes())
    cpu_buf = device.create_buffer(
        size=cpus.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST |
              wgpu.BufferUsage.COPY_SRC)
    out_buf = device.create_buffer(
        size=out_words * 4,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC |
              wgpu.BufferUsage.COPY_DST)
    # per-lane RAM: lane k addresses ram[k*4096 .. k*4096+4095]; matches
    # GlyphCPUv2 where each lane is a separate instance with its own memory
    uni = np.array([w, h, out_words, STEPS_PER_DISPATCH, RAM_WORDS],
                   dtype=np.uint32)
    uni_buf = device.create_buffer(
        size=uni.nbytes, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
    queue.write_buffer(uni_buf, 0, uni.tobytes())
    ram = np.zeros((K, RAM_WORDS), dtype=np.uint32)
    for k, msg in enumerate(msgs):
        padded = _pad(msg)
        nblocks = len(padded) // 64
        ram[k, K_BASE:K_BASE + len(_K)] = np.array(_K, dtype=np.uint32)
        ram[k, BCNT_ADDR] = nblocks
        ram[k, BLK_BASE:BLK_BASE + nblocks * 16] = np.frombuffer(
            padded, dtype=">u4").astype(np.uint32)
    ram_buf = device.create_buffer(
        size=ram.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST |
              wgpu.BufferUsage.COPY_SRC)
    queue.write_buffer(ram_buf, 0, ram.tobytes())

    bgl = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
        {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
    ])
    bg = device.create_bind_group(layout=bgl, entries=[
        {'binding': 0, 'resource': {'buffer': img_buf, 'offset': 0, 'size': img_buf.size}},
        {'binding': 1, 'resource': {'buffer': cpu_buf, 'offset': 0, 'size': cpu_buf.size}},
        {'binding': 2, 'resource': {'buffer': out_buf, 'offset': 0, 'size': out_buf.size}},
        {'binding': 3, 'resource': {'buffer': uni_buf, 'offset': 0, 'size': uni_buf.size}},
        {'binding': 4, 'resource': {'buffer': ram_buf, 'offset': 0, 'size': ram_buf.size}},
    ])
    pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bgl]),
        compute={"module": runner.shader, "entry_point": "main"})

    # Batched execution: STEPS_PER_DISPATCH instructions per dispatch, all K
    # lanes in lockstep. Halt check once per dispatch (host readback), which
    # is the natural integration granularity — per-instruction host sync
    # (the parity oracle's mode) costs ~165 ms/round-trip on this driver and
    # is not a serious execution strategy.
    steps_done = 0
    while True:
        if steps_done >= max_instructions:
            raise RuntimeError(f"did not halt within {max_instructions} steps")
        steps_done += STEPS_PER_DISPATCH
        queue.write_buffer(cpu_buf, 0, cpus.tobytes())
        enc = device.create_command_encoder()
        p = enc.begin_compute_pass()
        p.set_pipeline(pipeline)
        p.set_bind_group(0, bg)
        p.dispatch_workgroups(K)
        p.end()
        queue.submit([enc.finish()])

        flat = np.frombuffer(queue.read_buffer(cpu_buf), dtype=np.uint32).reshape(K, -1)
        if not flat[:, 34].any():     # all halted (lockstep-uniform kernel)
            # read digest words from ram (kernel STs byte-serialised H to OUT)
            ram_out = np.frombuffer(queue.read_buffer(ram_buf), dtype=np.uint32).reshape(K, RAM_WORDS)
            dt = time.perf_counter() - t0
            digests = []
            for k in range(K):
                # kernel stores 32 bytes as 32 single-byte STs at OUT_BASE..
                words = ram_out[k, OUT_BASE:OUT_BASE + 32]
                digests.append(bytes(int(x) & 0xFF for x in words))
            return digests, dt
        cpus = flat

def _unused(): pass


def serial_batch(msgs, max_instructions=400_000):
    """K serial GlyphCPUv2 hashes. Wall-clock end-to-end (assemble excluded,
    identical to GPU treatment)."""
    op = _opmap()
    try:
        asm = GlyphAssemblerV2(op)
        image = asm.assemble(build_sha256_glyph_program(WIDTH), width_instrs=WIDTH)
        t0 = time.perf_counter()
        digests = []
        for msg in msgs:
            cpu = GlyphCPUv2(op, WIDTH)
            for i, kv in enumerate(_K):
                cpu.memory[K_BASE + i] = kv
            padded = _pad(msg)
            cpu.memory[BCNT_ADDR] = len(padded) // 64
            cpu.memory[BLK_BASE:BLK_BASE + (len(padded) // 64) * 16] = np.frombuffer(
                padded, dtype=">u4").astype(np.uint32)
            with contextlib.redirect_stdout(io.StringIO()):
                cpu.run(image, max_instructions=max_instructions)
            digests.append(bytes(cpu.memory[OUT_BASE:OUT_BASE + 32]))
        return digests, time.perf_counter() - t0
    finally:
        op.close()


def main():
    msg = b"abc"                       # 1 block after padding
    want = hashlib.sha256(msg).digest()
    image = build_kernel_image()

    print(f"kernel: {len(build_sha256_glyph_program(WIDTH))} static instrs, "
          f"~8760 dynamic/block (item 5a); message {msg!r} (1 block/hash)")
    print(f"{'K':>5} {'GPU (s)':>12} {'serial (s)':>12} {'GPU/serial':>11} "
          f"{'hashlib (us)':>13} {'GPU us/hash':>12} {'serial us/hash':>15}")
    rows = []
    for K in KS:
        msgs = [msg] * K

        # correctness first: digests must match hashlib on both engines
        g_d, g_t = gpu_batch(gpu, image, msgs) if (gpu := runner) else ([], 0)
        assert all(d == want for d in g_d), f"GPU digest wrong at K={K}"
        s_d, s_t = serial_batch(msgs)
        assert all(d == want for d in s_d), f"serial digest wrong at K={K}"

        t_h0 = time.perf_counter()
        for _ in range(REPS):
            [hashlib.sha256(msg).digest() for _ in range(K)]
        t_h = (time.perf_counter() - t_h0) / REPS

        rows.append((K, g_t, s_t, t_h))
        print(f"{K:>5} {g_t:>12.3f} {s_t:>12.3f} {g_t/s_t:>10.1f}x "
              f"{t_h*1e6:>13.1f} {g_t/K*1e6:>12.1f} {s_t/K*1e6:>15.1f}")

    # crossover
    cross = next((K, g, s) for K, g, s, _ in rows if g <= s)
    print(f"\ncrossover K (GPU first beats serial): {cross[0]}")
    print(f"GPU per-lane throughput at largest K: {rows[-1][1]/rows[-1][0]*1e6:.0f} us/hash")
    print(f"serial per-hash: {rows[-1][2]/rows[-1][0]*1e3:.1f} ms/hash")


if __name__ == "__main__":
    # one shared runner (shader compile excluded from timings)
    runner = WgslRunner()
    main()
