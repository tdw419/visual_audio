#!/usr/bin/env python3
"""
SFR lockstep harness : GPU routing kernel (sfr_step.wgsl) vs CPU reference
(sfr_reference.py), compared frame by frame, bit-exact on the packet layer.

The field is produced by the CPU reference (authoritative) and its Q16 snapshot
is uploaded to the GPU each frame, so the only thing under test here is the
deflection routing step -- which is pure integer and must match exactly.

Scenarios:
  A  general delivery         (200 packets -> one corner)
  B  line-contention deadlock (full row racing to a single dest cell)
  C  age-guard stress         (packets boxed behind a wall of stalled packets)

First divergence prints frame + cell + both packet words, then aborts.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import wgpu
import wgpu.utils

sys.path.insert(0, str(Path(__file__).parent))
from sfr_reference import SFR, FQ, K_ROUNDS, GRID

WGSL = (Path(__file__).parent / "sfr_step.wgsl").read_text()
ENTRIES = ["deliver", "clear_claims", "claim_round", "resolve",
           "apply_vacate", "pick_oldest", "find_p", "displace", "age_tick"]


class GpuRouter:
    def __init__(self, n: int, hidx: np.ndarray):
        self.n = n
        self.dev = wgpu.utils.get_default_device()
        cells = n * n
        mk = lambda nb: self.dev.create_buffer(
            size=nb, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
            | wgpu.BufferUsage.COPY_SRC)
        self.b_pk     = mk(cells * 16)
        self.b_field  = mk(cells * 16)   # vec4<i32> : 4 channels/cell
        self.b_hidx   = mk(cells * 4)
        self.b_placed = mk(cells * 4)
        self.b_settled = mk(cells * 4)
        self.b_claim  = mk(cells * 4)
        self.b_vacate = mk(cells * 4)
        self.b_ctrl   = mk(16)   # ctrl[0..3]
        self.dev.queue.write_buffer(self.b_hidx, 0,
                                    hidx.astype(np.int32).tobytes())

        ro = {1, 2}   # fieldq, hidx are read-only storage in the shader
        bgl = self.dev.create_bind_group_layout(entries=[
            {"binding": b, "visibility": wgpu.flags.ShaderStage.COMPUTE,
             "buffer": {"type": wgpu.BufferBindingType.read_only_storage if b in ro
                        else wgpu.BufferBindingType.storage}}
            for b in range(8)])
        self.bg = self.dev.create_bind_group(layout=bgl, entries=[
            {"binding": 0, "resource": {"buffer": self.b_pk}},
            {"binding": 1, "resource": {"buffer": self.b_field}},
            {"binding": 2, "resource": {"buffer": self.b_hidx}},
            {"binding": 3, "resource": {"buffer": self.b_placed}},
            {"binding": 4, "resource": {"buffer": self.b_settled}},
            {"binding": 5, "resource": {"buffer": self.b_claim}},
            {"binding": 6, "resource": {"buffer": self.b_vacate}},
            {"binding": 7, "resource": {"buffer": self.b_ctrl}},
        ])
        pl = self.dev.create_pipeline_layout(bind_group_layouts=[bgl])
        mod = self.dev.create_shader_module(code=WGSL)
        consts = {"GRID": int(n)}
        self.pipe = {e: self.dev.create_compute_pipeline(
            layout=pl, compute={"module": mod, "entry_point": e,
                                "constants": consts})
            for e in ENTRIES}
        self.groups = (n + 7) // 8

    def _run(self, enc, name):
        p = enc.begin_compute_pass()
        p.set_pipeline(self.pipe[name])
        p.set_bind_group(0, self.bg)
        p.dispatch_workgroups(self.groups, self.groups)
        p.end()

    def route(self, pk_in: np.ndarray, fieldq: np.ndarray) -> np.ndarray:
        q = self.dev.queue
        q.write_buffer(self.b_pk, 0, np.ascontiguousarray(
            pk_in.reshape(-1, 4).astype(np.uint32)).tobytes())
        q.write_buffer(self.b_field, 0, np.ascontiguousarray(
            fieldq.astype(np.int32)).tobytes())
        q.write_buffer(self.b_ctrl, 0, np.zeros(4, np.uint32).tobytes())

        enc = self.dev.create_command_encoder()
        self._run(enc, "deliver")
        q.submit([enc.finish()])
        for r in range(K_ROUNDS):
            q.write_buffer(self.b_ctrl, 0, np.uint32(r).tobytes())
            enc = self.dev.create_command_encoder()
            self._run(enc, "clear_claims")
            self._run(enc, "claim_round")
            self._run(enc, "resolve")
            self._run(enc, "apply_vacate")
            q.submit([enc.finish()])
        # forced displacement: one packet per frame
        q.write_buffer(self.b_ctrl, 8,
                       np.array([0, 0xFFFFFFFF], np.uint32).tobytes())  # ctrl[2],[3]
        enc = self.dev.create_command_encoder()
        self._run(enc, "pick_oldest")
        self._run(enc, "find_p")
        self._run(enc, "displace")
        q.submit([enc.finish()])
        enc = self.dev.create_command_encoder()
        self._run(enc, "age_tick")
        q.submit([enc.finish()])

        raw = self.dev.queue.read_buffer(self.b_pk)
        return np.frombuffer(raw, np.uint32).reshape(self.n, self.n, 4).copy()


def lockstep(scenario, name, max_frames=600):
    s = SFR(GRID, seed=0)
    scenario(s)
    gpu = GpuRouter(GRID, s._hidx)
    for f in range(max_frames):
        s._decay_and_stamp()
        s._diffuse()
        fq = np.rint(s.fieldv * FQ).astype(np.int32)
        pk_before = s.packet.copy()
        s._route()
        cpu_after = s.packet.copy()
        gpu_after = gpu.route(pk_before, fq)
        if not np.array_equal(cpu_after, gpu_after):
            diff = np.argwhere(np.any(cpu_after != gpu_after, axis=-1))
            y, x = diff[0]
            print(f"[{name}] DIVERGENCE frame {f} cell ({x},{y})")
            print(f"   cpu={cpu_after[y, x].tolist()}  gpu={gpu_after[y, x].tolist()}")
            print(f"   {len(diff)} cell(s) differ")
            return False
        s.frame += 1
        if s.in_flight() == 0 and f > 2:
            print(f"[{name}] lockstep OK, {f + 1} frames, "
                  f"{len(s.delivered)} delivered")
            return True
    print(f"[{name}] lockstep OK through {max_frames} frames, "
          f"{s.in_flight()} still in flight")
    return True


# ---- scenarios ------------------------------------------------------------
def scen_general(s: SFR):
    dest = (GRID - 1, GRID - 1)
    free = [(x, y) for y in range(GRID) for x in range(GRID) if (x, y) != dest]
    s.rng.shuffle(free)
    for i in range(200):
        x, y = free[i]
        s.inject(x, y, dest, handle=i + 1, prio=int(s.rng.integers(0, 8)))


def scen_line_contention(s: SFR):
    # entire top row races to one bottom-centre cell -- classic deflection
    # deadlock candidate: 63 packets, one throat.
    dest = (GRID // 2, GRID - 1)
    h = 1
    for x in range(GRID):
        if (x, 0) == dest:
            continue
        s.inject(x, 0, dest, handle=h); h += 1


def scen_age_guard(s: SFR):
    # a wall of packets with a far dest, then late packets boxed behind them;
    # only the age guard (strict steepest descent) should free the box.
    dest = (GRID - 1, GRID // 2)
    h = 1
    for y in range(GRID):
        s.inject(2, y, dest, handle=h); h += 1
    for y in range(0, GRID, 2):
        s.inject(0, y, dest, handle=h); h += 1


def scen_multichannel(s: SFR):
    # 4 wells, one per field channel; every packet carries the channel of its
    # own destination.  Exercises per-channel field selection in the router:
    # a packet must descend ITS channel, ignoring a spatially closer well on
    # another channel.
    wells = [(4, 4), (GRID - 5, 4), (4, GRID - 5), (GRID - 5, GRID - 5)]
    free = [(x, y) for y in range(GRID) for x in range(GRID)
            if (x, y) not in wells]
    s.rng.shuffle(free)
    for i in range(200):
        x, y = free[i]
        k = int(s.rng.integers(4))
        s.inject(x, y, wells[k], handle=i + 1, prio=int(s.rng.integers(0, 8)),
                 chan=k)


def scen_jam(s: SFR):
    # the saturation-livelock topology: two close wells on different channels
    # near the top edge, the top four rows packed solid with equal-age packets.
    # Only forced displacement can drain this.  Must go bit-exact AND drain.
    wa, wb = (4, 4), (14, 4)
    h = 1
    for y in range(4):
        for x in range(GRID):
            if (x, y) in (wa, wb):
                continue
            k = x & 1
            s.inject(x, y, wa if k == 0 else wb, handle=h, chan=k); h += 1


def scen_pingpong(s: SFR):
    # a dense channel-0 slab funnelling to ONE well, plus two adjacent packets
    # dead-centre whose steepest-descent directions are exactly opposed (one
    # wants the other's cell).  With one forced displacement per frame a true
    # 2-cycle is impossible by construction; this asserts the (age, handle)
    # order actually breaks the pair and both drain.
    well = (2, GRID // 2)
    for y in range(GRID // 2 - 3, GRID // 2 + 4):
        for x in range(2, 10):
            if (x, y) == well:
                continue
            s.inject(x, y, well, handle=(y * GRID + x) + 1, chan=0)


if __name__ == "__main__":
    ok = True
    ok &= lockstep(scen_general, "A general")
    ok &= lockstep(scen_line_contention, "B line-contention")
    ok &= lockstep(scen_age_guard, "C age-guard")
    ok &= lockstep(scen_multichannel, "D multichannel")
    ok &= lockstep(scen_jam, "E saturation-jam")
    ok &= lockstep(scen_pingpong, "F pingpong")
    print("\nALL LOCKSTEP GREEN" if ok else "\nLOCKSTEP FAILED")
    sys.exit(0 if ok else 1)
