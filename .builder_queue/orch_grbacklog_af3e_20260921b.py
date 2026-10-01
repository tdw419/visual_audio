#!/usr/bin/env python3
"""orch_grbacklog_af3e_20260921b.py — decisive probe for the 111-vs-482us gap.

Hypothesis (H4): the probe's timed leg undercounts because it maps EVERY
step in a tight loop but exits after 198 steps while GPU backlog remains;
map_sync per-step then only reflects CPU submission pipelining, not GPU
step cost. True cost = (total wall time to actually complete N steps) / N.

Measure both quantities for the SAME N=198 the probe ran:
  A) pipelined: per-step dispatch + map (probe protocol) -> expect ~111us
  B) drained:   total time for N dispatches + ONE final blocking sync
                -> if ~500-600us/step, H4 confirmed and the floor stands.
"""
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
rgba = np.zeros((16384, 4), np.uint32)
dt = np.dtype([('image_width', np.uint32), ('image_height', np.uint32),
               ('output_buffer_size', np.uint32)])
bufs = {}
for name, arr, extra in (
        ("img", rgba, 0), ("cpu", cpu_state, 0),
        ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
        ("u", np.array([(128, 128, 64)], dt), wgpu.BufferUsage.UNIFORM),
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
N = cpu_state.nbytes

# warm
for _ in range(5):
    enc = device.create_command_encoder()
    p = enc.begin_compute_pass()
    p.set_pipeline(pipe); p.set_bind_group(0, bg); p.dispatch_workgroups(1); p.end()
    enc.copy_buffer_to_buffer(bufs["cpu"], 0, rb, 0, N)
    queue.submit([enc.finish()])
    rb.map_sync(mode=wgpu.MapMode.READ); rb.read_mapped(); rb.unmap()
    time.sleep(0.005)

# A) probe protocol: per-step map, tight loop, 198 steps
t0 = time.perf_counter()
per_step = []
for _ in range(198):
    s = time.perf_counter()
    enc = device.create_command_encoder()
    p = enc.begin_compute_pass()
    p.set_pipeline(pipe); p.set_bind_group(0, bg); p.dispatch_workgroups(1); p.end()
    enc.copy_buffer_to_buffer(bufs["cpu"], 0, rb, 0, N)
    queue.submit([enc.finish()])
    rb.map_sync(mode=wgpu.MapMode.READ)
    np.frombuffer(bytes(rb.read_mapped()), dtype=cpu_dtype)[0]
    rb.unmap()
    per_step.append((time.perf_counter() - s) * 1e6)
tA = time.perf_counter() - t0
import statistics
print(f"A) pipelined per-step-map, 198 steps: total {tA*1e3:.1f} ms, "
      f"median step {statistics.median(per_step):.1f} us, "
      f"mean/step {tA/198*1e6:.1f} us")

# B) drained: 198 dispatches with per-step copies, ONE final sync.
#    Reset cpu to running=1 first so these are REAL steps, not no-ops
#    (leg A halted the cpu). This makes B the honest drained cost of
#    198 actual steps.
cpu_state['running'] = 1
queue.write_buffer(bufs["cpu"], 0, cpu_state.tobytes())
t0 = time.perf_counter()
for _ in range(198):
    enc = device.create_command_encoder()
    p = enc.begin_compute_pass()
    p.set_pipeline(pipe); p.set_bind_group(0, bg); p.dispatch_workgroups(1); p.end()
    enc.copy_buffer_to_buffer(bufs["cpu"], 0, rb, 0, N)
    queue.submit([enc.finish()])
rb.map_sync(mode=wgpu.MapMode.READ)
final = np.frombuffer(bytes(rb.read_mapped()), dtype=cpu_dtype)[0].copy()
rb.unmap()
tB = time.perf_counter() - t0
print(f"B) drained (one final sync), 198 steps: total {tB*1e3:.1f} ms, "
      f"true mean/step {tB/198*1e6:.1f} us")
print(f"backlog explanation holds if B >> A per-step "
      f"(ratio {(tB/198)/(tA/198):.1f}x)")
_rb_state = final if final.ndim == 0 else final[0]
print(f"final halted={bool(_rb_state['running'] == 0)} "
      f"pc=({int(_rb_state['pc'][0])},{int(_rb_state['pc'][1])})")
