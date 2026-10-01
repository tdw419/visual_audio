#!/usr/bin/env python3
"""orch_grfloor_falsifier_af3e_20260921.py — explain the 111 vs 482us gap.

The recalibrated floor says glyphrunner_wgsl_step = 482.0us, but the probe's
timed leg (same protocol, same process count) measures 111.0us -> 0.23x
"below floor". One of them is not measuring what we think. Hypotheses:
  H1: image buffer size matters (calibrator used 64px; probe uses the real
      resident image, thousands of px).
  H2: run-order/GPU-state (calibrator ran after 90 other timed reps).
  H3: the calibrator's u-buffer dims (1,1) hit a different shader path
      (e.g. workgroup count derived from image size).
Test: alternate timed steps of both shapes in ONE process, interleaved,
so order and GPU state are shared.
"""
import statistics
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import wgpu
import wgpu.utils

from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
from tools.glyph_isa_v2 import OpcodeMapV2

device = wgpu.utils.get_default_device()
queue = device.queue
usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
         | wgpu.BufferUsage.COPY_SRC)
cpu_state, cpu_dtype = make_cpu_state_array(1)
mmio = np.zeros(160, np.uint32)
ram = np.zeros(16384, np.uint32)
dt = np.dtype([('image_width', np.uint32), ('image_height', np.uint32),
               ('output_buffer_size', np.uint32)])


def build(n_px, hw, hh):
    rgba = np.zeros((n_px, 4), np.uint32)
    bufs = {}
    for name, arr, extra in (
            ("img", rgba, 0), ("cpu", cpu_state, 0),
            ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
            ("u", np.array([(hw, hh, 64)], dt), wgpu.BufferUsage.UNIFORM),
            ("ram", ram, 0)):
        b = device.create_buffer(size=arr.nbytes, usage=usage | extra)
        queue.write_buffer(b, 0, arr.tobytes())
        bufs[name] = b
    bgl = device.create_bind_group_layout(entries=[
        {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
         'buffer': {'type': 'storage' if i != 3 else 'uniform'}}
        for i in range(6)])
    pipe = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bgl]),
        compute={'module': device.create_shader_module(
            code=build_shader(OpcodeMapV2())), 'entry_point': 'main'})
    bg = device.create_bind_group(layout=bgl, entries=[
        {'binding': 0, 'resource': {'buffer': bufs["img"], 'offset': 0, 'size': rgba.nbytes}},
        {'binding': 1, 'resource': {'buffer': bufs["cpu"], 'offset': 0, 'size': cpu_state.nbytes}},
        {'binding': 2, 'resource': {'buffer': bufs["out"], 'offset': 0, 'size': 256}},
        {'binding': 3, 'resource': {'buffer': bufs["u"], 'offset': 0, 'size': bufs["u"].size}},
        {'binding': 4, 'resource': {'buffer': bufs["mmio"], 'offset': 0, 'size': mmio.nbytes}},
        {'binding': 5, 'resource': {'buffer': bufs["ram"], 'offset': 0, 'size': ram.nbytes}}])
    rb = device.create_buffer(size=cpu_state.nbytes,
                              usage=wgpu.BufferUsage.COPY_DST
                              | wgpu.BufferUsage.MAP_READ)

    def once():
        enc = device.create_command_encoder()
        p = enc.begin_compute_pass()
        p.set_pipeline(pipe)
        p.set_bind_group(0, bg)
        p.dispatch_workgroups(1)
        p.end()
        enc.copy_buffer_to_buffer(bufs["cpu"], 0, rb, 0, cpu_state.nbytes)
        queue.submit([enc.finish()])
        rb.map_sync(mode=wgpu.MapMode.READ)
        np.frombuffer(bytes(rb.read_mapped()), dtype=cpu_dtype)[0]
        rb.unmap()

    return once


# resident-image scale: match the probe (check actual shape below); the
# resident queue bake geometry — read it from the probe path if cheap.
small = build(64, 1, 1)          # calibrator shape
big = build(16384, 128, 128)     # resident-scale image buffer

for f in (small, big):
    for _ in range(5):
        f()
        time.sleep(0.005)

ts, tb = [], []
for _ in range(30):
    t0 = time.perf_counter(); small(); ts.append((time.perf_counter() - t0) * 1e6)
    time.sleep(0.002)
    t0 = time.perf_counter(); big(); tb.append((time.perf_counter() - t0) * 1e6)
    time.sleep(0.002)

print(f"small(64px, calibrator shape)  median {statistics.median(ts):8.1f} us")
print(f"big(16384px, resident scale)   median {statistics.median(tb):8.1f} us")
print(f"ratio big/small = {statistics.median(tb)/statistics.median(ts):.2f}x")
