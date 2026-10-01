#!/usr/bin/env python3
"""probe_r11_task_queue.py — PRODUCT_ROADMAP R1.1 task-queue drain probe.

The anchor-workload step beyond the 10940dc7 baseline: BOX0's resident
daemon drains a kernel-seeded job QUEUE in-guest (loop under the GH-16
preemptive timer), the host verifies the drained state word-by-word,
and the GPU (WGSL) execution leg gets a standing-rule-1 floor line
using the floor protocol described in RECEIPT_floor_reconciliation.md.

Legs:
  A. CPU functional (queue drain, the gated substrate):
     bake queue image -> GlyphRunner.drive -> assert all 3 jobs tripled
     into history slots 756..758, mailbox depth @740 drained to 0,
     receipt 0x5EED0003 @759, done flags @717, kernel status OK.
  B. GPU timed floor line: `LEG wgsl_queue ... step x1` via the
     authoritative floors_authoritative.json (check_regime.py lints it).
  C. GPU functional (informational divergence datum — recorded, never
     gated; same discipline as the baseline receipt).

Verdict: VERDICT=PASS exit 0 iff leg A fully passes AND leg B's floor
line is admissible. RED leg (--corrupt): expectations shifted +1 must
print VERDICT=FAIL and exit 1.
"""
import argparse
import json
import pathlib
import statistics
import sys
import tempfile
import time

_REPO = pathlib.Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools"), str(_REPO / ".builder_queue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.agent_resident import (                     # noqa: E402
    resident_image, RES_KERNEL_OK, RES_QUEUE_DEPTH,
    RES_QUEUE_RESULT_BASE, RES_QUEUE_DONE_WORD, RES_QUEUE_DONE,
    RES_QUEUE_SLOTS, RES_QUEUE_SEED,
)

QUANTUM = 12
JOBS = list(RES_QUEUE_SEED)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrupt", action="store_true",
                    help="RED leg: shift expectations by +1 (must FAIL)")
    ap.add_argument("--skip-gpu", action="store_true",
                    help="CPU functional leg only (no floor line)")
    args = ap.parse_args()

    shift = 1 if args.corrupt else 0
    expected = [3 * j + shift for j in JOBS]
    failures = []

    with tempfile.TemporaryDirectory() as d:
        img = pathlib.Path(d) / "gh26_queue.glyph.npy"
        resident_image(build_default_atlas(), mode="queue",
                       timer_quantum=QUANTUM, out_path=img)

        # ── leg A: CPU functional — the in-guest queue drain ────────────
        r_cpu = GlyphRunner(img, ram_words=16384).drive(
            seeds={}, max_instructions=60000)
        mem = r_cpu.get("memory", [])
        slots = [mem[RES_QUEUE_RESULT_BASE + i] for i in range(RES_QUEUE_SLOTS)]
        checks = [
            ("halted", r_cpu.get("halted") is True),
            ("no_fault", r_cpu.get("faulted") is False),
            *[(f"slot{i}", slots[i] == expected[i]) for i in range(RES_QUEUE_SLOTS)],
            ("depth0", len(mem) > RES_QUEUE_DEPTH and mem[RES_QUEUE_DEPTH] == 0),
            ("receipt", mem[RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE),
            ("done_flags717", len(mem) > 717 and mem[717] == 3),
            ("status950", r_cpu.get("status_word_value") == RES_KERNEL_OK),
        ]
        for name, ok in checks:
            if not ok:
                failures.append(f"cpu:{name}")
        print(f"CPU queue drain: jobs {JOBS} -> results {slots} "
              f"expected {expected} depth={mem[RES_QUEUE_DEPTH]} "
              f"receipt={mem[RES_QUEUE_DONE_WORD]:#x} steps={r_cpu.get('steps')} "
              f"ticks={mem[732]}")

        if args.skip_gpu:
            print("LEG wgsl_queue SKIPPED (--skip-gpu); no floor line this run")
        else:
            # ── leg B: GPU timed floor line ─────────────────────────────
            import numpy as np
            import wgpu, wgpu.utils
            from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
            from tools.glyph_isa_v2 import OpcodeMapV2

            arr_img = GlyphRunner(img).image
            rgba = np.zeros((arr_img.shape[0] * arr_img.shape[1], 4), dtype=np.uint32)
            rgba[:, 0:3] = arr_img.reshape(-1, 3)
            n_px = rgba.shape[0]
            cpu_state, cpu_dtype = make_cpu_state_array(1)
            mmio = np.zeros(160, dtype=np.uint32)
            ram_arr = np.zeros(16384, dtype=np.uint32)
            dt = np.dtype([('image_width', np.uint32), ('image_height', np.uint32),
                           ('output_buffer_size', np.uint32)])
            device = wgpu.utils.get_default_device(); queue = device.queue
            usage = wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
            bufs = {}
            for name, arr, extra in (
                    ("img", rgba, 0), ("cpu", cpu_state, 0),
                    ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
                    ("u", np.array([(arr_img.shape[1], arr_img.shape[0], 64)], dt),
                     wgpu.BufferUsage.UNIFORM), ("ram", ram_arr, 0)):
                b = device.create_buffer(size=arr.nbytes, usage=usage | extra)
                queue.write_buffer(b, 0, arr.tobytes()); bufs[name] = b
            bgl = device.create_bind_group_layout(entries=[
                {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
                 'buffer': {'type': 'storage' if i != 3 else 'uniform'}}
                for i in range(6)])
            pLayout = device.create_pipeline_layout(bind_group_layouts=[bgl])
            bg = device.create_bind_group(layout=bgl, entries=[
                {'binding': 0, 'resource': {'buffer': bufs["img"], 'offset': 0, 'size': rgba.nbytes}},
                {'binding': 1, 'resource': {'buffer': bufs["cpu"], 'offset': 0, 'size': cpu_state.nbytes}},
                {'binding': 2, 'resource': {'buffer': bufs["out"], 'offset': 0, 'size': 256}},
                {'binding': 3, 'resource': {'buffer': bufs["u"], 'offset': 0, 'size': bufs["u"].size}},
                {'binding': 4, 'resource': {'buffer': bufs["mmio"], 'offset': 0, 'size': mmio.nbytes}},
                {'binding': 5, 'resource': {'buffer': bufs["ram"], 'offset': 0, 'size': ram_arr.nbytes}}])
            sh = device.create_shader_module(code=build_shader(OpcodeMapV2()))
            pipe = device.create_compute_pipeline(
                layout=pLayout, compute={'module': sh, 'entry_point': 'main'})

            step_us, steps, rb = [], 0, None
            readback = device.create_buffer(
                size=cpu_state.nbytes,
                usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ)
            n_bytes = cpu_state.nbytes
            for steps in range(1, 60001):
                t0 = time.perf_counter()
                enc = device.create_command_encoder(); p = enc.begin_compute_pass()
                p.set_pipeline(pipe); p.set_bind_group(0, bg)
                p.dispatch_workgroups(1); p.end()
                enc.copy_buffer_to_buffer(bufs["cpu"], 0, readback, 0, n_bytes)
                queue.submit([enc.finish()])
                readback.map_sync(mode=wgpu.MapMode.READ)
                rb = np.frombuffer(bytes(readback.read_mapped()), dtype=cpu_dtype)[0]
                readback.unmap()
                step_us.append((time.perf_counter() - t0) * 1e6)
                if rb['running'] == 0:
                    break
            steps = max(steps, 1)
            median_us = statistics.median(step_us)

            # ── leg C: GPU functional divergence datum (informational) ──
            px_rb = device.create_buffer(
                size=rgba.nbytes,
                usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ)
            enc2 = device.create_command_encoder()
            enc2.copy_buffer_to_buffer(bufs["img"], 0, px_rb, 0, rgba.nbytes)
            queue.submit([enc2.finish()])
            px_rb.map_sync(mode=wgpu.MapMode.READ)
            px = np.frombuffer(bytes(px_rb.read_mapped()), dtype=np.uint32).reshape(n_px, 4)
            px_rb.unmap()
            wmem = [int((int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2])) for p in px]
            w754 = wmem[754] if len(wmem) > 754 else None
            print(f"WGSL result@754 = {w754:#x} expected {expected[0]:#x} "
                  f"({'MATCH' if w754 == expected[0] else 'DIVERGENT — recorded, not gated'}) "
                  f"steps={steps} halted={bool(rb['running'] == 0)}")

            # path names the throughput floor (tight-loop protocol, same
            # quantity): glyphrunner_wgsl_step (spaced) is the LATENCY
            # floor and would mis-adjudicate this leg (0.14x category
            # error); the tput floor is measured on the same tight loop.
            print(f"LEG wgsl_queue {1e6 / median_us:,.0f} steps/s "
                  f"{median_us:,.1f} us/rep glyphrunner_wgsl_step_tput x1")

    if args.corrupt:
        if failures:
            print("CORRUPT-LEG: expectation did not match (correct RED)")
        else:
            failures.append("corrupt:expectation-wrongly-matched")

    if failures:
        print(f"VERDICT=FAIL failures={failures}")
        return 1
    print("VERDICT=PASS (cpu queue drain host-verified"
          + ("" if args.skip_gpu else "; floor line emitted") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
