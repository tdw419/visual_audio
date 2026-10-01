#!/usr/bin/env python3
"""
SFR field-diffusion lockstep : GPU sfr_diffuse.wgsl vs CPU reference _diffuse.

Diffusion is f32 on both sides but accumulation order differs, so this is a
tolerance check, not bit-exact:
  * float field   : max abs err  (expect < 1e-4)
  * Q16 snapshot  : rint(field * FQ) must match within +/-1  (this is what
                    routing consumes; >1 could flip a routing tie)

Scenario: static wells at three corners + one well that jumps at frame 40,
run 100 frames, worst error over the whole run.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import wgpu
import wgpu.utils
from sfr_reference import SFR, GRID, FQ

WGSL = (Path(__file__).parent / "sfr_diffuse.wgsl").read_text()


class GpuDiffuser:
    def __init__(self, n: int, jacobi_it: int, max_wells: int = 256):
        self.n = n
        self.it = jacobi_it
        self.sizes = [n, n // 2, n // 4]   # 3-level V-cycle, mirrors SFR._diffuse
        self.dev = wgpu.utils.get_default_device()
        St = wgpu.BufferUsage.STORAGE
        self.CH = 4                 # field channels (vec4<f32> per cell)
        mk = lambda sz: self.dev.create_buffer(
            size=sz * sz * 4 * self.CH,
            usage=St | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC)
        s1, s2 = n // 2, n // 4
        self.b_f = mk(n)            # L0 fine field
        self.b_r0 = mk(s1)         # restrict(f)          -- kept for correction
        self.b_c1 = mk(s1)         # L1 working
        self.b_r1 = mk(s2)         # restrict(c1)         -- kept for correction
        self.b_c2 = mk(s2)         # L2 working (coarsest)
        self.scratch = mk(n)       # jacobi ping-pong (any level)
        self.wells = self.dev.create_buffer(
            size=max_wells * 16, usage=St | wgpu.BufferUsage.COPY_DST)  # vec4<u32>
        self.unif = self.dev.create_buffer(
            size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)

        self.bgl = self.dev.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": wgpu.flags.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
            {"binding": 1, "visibility": wgpu.flags.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.storage}},
            {"binding": 2, "visibility": wgpu.flags.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.read_only_storage}},
            {"binding": 3, "visibility": wgpu.flags.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.uniform}},
        ])
        pl = self.dev.create_pipeline_layout(bind_group_layouts=[self.bgl])
        mod = self.dev.create_shader_module(code=WGSL)
        self.pipe = {e: self.dev.create_compute_pipeline(
            layout=pl, compute={"module": mod, "entry_point": e})
            for e in ("restrict_level", "jacobi", "repin", "prolongate",
                      "sub_inplace", "prolong_add")}

    def _bg(self, in_buf, out_buf):
        return self.dev.create_bind_group(layout=self.bgl, entries=[
            {"binding": 0, "resource": {"buffer": in_buf}},
            {"binding": 1, "resource": {"buffer": out_buf}},
            {"binding": 2, "resource": {"buffer": self.wells}},
            {"binding": 3, "resource": {"buffer": self.unif}},
        ])

    def _dispatch(self, entry, bg, gx, gy=1):
        enc = self.dev.create_command_encoder()
        p = enc.begin_compute_pass()
        p.set_pipeline(self.pipe[entry])
        p.set_bind_group(0, bg)
        p.dispatch_workgroups(gx, gy)
        p.end()
        self.dev.queue.submit([enc.finish()])

    def _u(self, size, scale, nwells):
        self.dev.queue.write_buffer(self.unif, 0, np.array(
            [size, scale, nwells, 0], np.uint32).tobytes())

    def _g8(self, sz):
        return (sz + 7) // 8

    def _copy(self, src, dst, nbytes):
        enc = self.dev.create_command_encoder()
        enc.copy_buffer_to_buffer(src, 0, dst, 0, nbytes)
        self.dev.queue.submit([enc.finish()])

    def _smooth(self, buf, sz, it, nw):
        """`it` Jacobi sweeps on `buf` (sz x sz), well re-pinned after each."""
        for _ in range(it):
            self._u(sz, 0, 0)
            self._dispatch("jacobi", self._bg(buf, self.scratch),
                           self._g8(sz), self._g8(sz))
            self._copy(self.scratch, buf, sz * sz * 4 * self.CH)
            if nw:
                self._u(sz, self.n // sz, nw)
                self._dispatch("repin", self._bg(self.scratch, buf),
                               (nw + 63) // 64)

    def diffuse(self, pre: np.ndarray,
                wells: list[tuple[int, int, int]]) -> np.ndarray:
        """pre : (n, n, 4) float32 ; wells : list of (x, y, chan)."""
        q = self.dev.queue
        n = self.n
        s1, s2 = n // 2, n // 4
        it = self.it
        nw = len(wells)
        q.write_buffer(self.b_f, 0, np.ascontiguousarray(pre, np.float32).tobytes())
        if nw:
            w = np.zeros((nw, 4), np.uint32)
            w[:, :3] = np.asarray(wells, np.uint32)
            q.write_buffer(self.wells, 0, w.tobytes())

        # 3-level V-cycle, mirrors SFR._diffuse
        self._smooth(self.b_f, n, it, nw)                        # f = smooth(f)
        self._u(s1, 0, 0)                                        # r0 = restrict(f)
        self._dispatch("restrict_level", self._bg(self.b_f, self.b_r0),
                       self._g8(s1), self._g8(s1))
        self._copy(self.b_r0, self.b_c1, s1 * s1 * 4 * self.CH)  # c1 = r0
        self._smooth(self.b_c1, s1, it, nw)                      # c1 = smooth(c1)
        self._u(s2, 0, 0)                                        # r1 = restrict(c1)
        self._dispatch("restrict_level", self._bg(self.b_c1, self.b_r1),
                       self._g8(s2), self._g8(s2))
        self._copy(self.b_r1, self.b_c2, s2 * s2 * 4 * self.CH)  # c2 = r1
        self._smooth(self.b_c2, s2, it * 2, nw)                  # c2 = smooth(c2, 2it)

        self._u(s2, 0, 0)                                        # c2 -= r1  (corr)
        self._dispatch("sub_inplace", self._bg(self.b_r1, self.b_c2),
                       self._g8(s2), self._g8(s2))
        self._u(s1, 0, 0)                                        # c1 += P(c2)
        self._dispatch("prolong_add", self._bg(self.b_c2, self.b_c1),
                       self._g8(s1), self._g8(s1))
        self._smooth(self.b_c1, s1, it, nw)                      # c1 = smooth(...)

        self._u(s1, 0, 0)                                        # c1 -= r0  (corr)
        self._dispatch("sub_inplace", self._bg(self.b_r0, self.b_c1),
                       self._g8(s1), self._g8(s1))
        self._u(n, 0, 0)                                         # f += P(c1)
        self._dispatch("prolong_add", self._bg(self.b_c1, self.b_f),
                       self._g8(n), self._g8(n))
        self._smooth(self.b_f, n, it, nw)                        # f = smooth(...)

        raw = q.read_buffer(self.b_f)
        return np.frombuffer(raw, np.float32).reshape(n, n, self.CH).copy()


def run(frames=100, jacobi_it=2, verbose=True):
    s = SFR(GRID, seed=0, jacobi_it=jacobi_it)
    # one well per channel (+ a 4th on ch0 that jumps at frame 40) -- exercises
    # all four vec4 lanes and the per-channel repin.
    s.wells = {(4, 4): 9**9, (GRID - 5, 4): 9**9, (4, GRID - 5): 9**9,
               (GRID // 2, GRID // 2): 9**9}
    s.wchan = {(4, 4): 0, (GRID - 5, 4): 1, (4, GRID - 5): 2,
               (GRID // 2, GRID // 2): 3}
    gpu = GpuDiffuser(GRID, jacobi_it)
    worst_f, worst_q, worst_q_cells = 0.0, 0, 0
    for f in range(frames):
        if f == 40:
            del s.wells[(GRID // 2, GRID // 2)]
            s.wchan.pop((GRID // 2, GRID // 2))
            s.wells[(GRID - 5, GRID - 5)] = 9**9
            s.wchan[(GRID - 5, GRID - 5)] = 3
        s._decay_and_stamp()
        pre = s.fieldv.copy()
        wl = [(x, y, s.wchan[(x, y)]) for (x, y) in s.wells]
        s._diffuse()
        cpu = s.fieldv.copy()
        g = gpu.diffuse(pre, wl)
        ferr = float(np.abs(cpu - g).max())
        qc = np.rint(cpu * FQ).astype(np.int64)
        qg = np.rint(g * FQ).astype(np.int64)
        qerr = int(np.abs(qc - qg).max())
        worst_f = max(worst_f, ferr)
        worst_q = max(worst_q, qerr)
        worst_q_cells = max(worst_q_cells, int((qc != qg).sum()))
        s.frame += 1
    ok = worst_f < 1e-4 and worst_q <= 1
    if verbose:
        print(f"[diffuse it={jacobi_it}] {frames} frames  "
              f"max_float_err={worst_f:.2e}  max_Q16_err={worst_q}  "
              f"Q16_cells_off<= {worst_q_cells}/{GRID*GRID}  "
              f"{'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    import sys
    ok = run(jacobi_it=2) & run(jacobi_it=3)
    sys.exit(0 if ok else 1)
