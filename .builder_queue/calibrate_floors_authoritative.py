"""Authoritative floor calibration — measures the REAL methods, not proxies.

Landed 2026-09-21 by the seat lane, on Jericho's direction, after the R0
rereceipt (396bc8ed) was shown to police claims with a units-mismatched
floor: .builder_queue/calibrate_floors.py measures one dispatch + one
readback of a trivial constant-write shader, while the code the probe
times (SpatialRV32ICore.step / get_state) performs FOUR blocking
readbacks per step() (two get_state calls x two read_buffer each) plus a
write_buffer and a full pipeline dispatch against real buffers.

This calibrator imports the real classes and times the real methods in
this dedicated process, per policy rule 1: a floor must come from a
process other than the one making the claim, and must measure the code
path being judged.

Window policy: 12h (Jericho's call 2026-09-21) — this host's floors are
non-stationary (same calibrator moved 2.5x between 10:02 and 10:40; the
Qoder observer watched 2-15x swings under GPU contention while mins held
within 17%). Consumers treat floors older than 12h as stale.

Output: .builder_queue/floors_authoritative.json
This file is THE floors authority for the zion repo. The two prior
floors files are superseded:
  - .builder_queue/floors.json (proxy shader, wrong quantity) — kept
    only as a dead artifact; check_regime.py no longer reads it.
  - Qoder builder_watch/floors.json (real methods, right quantity, but
    lives in ANOTHER repo and is re-measured on its own cadence) — its
    protocol was the model for this calibrator, but cross-repo floors
    are not citable in zion receipts.
"""
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent.parent))  # repo root's parent chain for 'tools.' package imports

import numpy as np

from spatial_rv32i_cpu import SpatialRV32ICore
from pyshader_fde import FIB_PROGRAM
from pyshader_wgsl import _cached_device

REPS = 30
WARMUP = 5


def pct(sorted_vals, q):
    return sorted_vals[min(int(q * len(sorted_vals)), len(sorted_vals) - 1)]


def main():
    device = _cached_device()
    # SpatialRV32ICore creates its own default device; use the same one.
    core = SpatialRV32ICore()
    device = core.device

    # FIB_PROGRAM is a list of u32 instruction words; load_program takes bytes.
    prog_words = [int(w) & 0xFFFFFFFF for w in FIB_PROGRAM]
    prog_bytes = b"".join(w.to_bytes(4, "little") for w in prog_words)

    # ---- floor(step): the REAL SpatialRV32ICore.step(1) ----
    # Warm the pipeline, caches, and first-submission costs.
    core.load_program(prog_bytes)
    for _ in range(WARMUP):
        core.step(1)
        time.sleep(0.01)

    step_floor = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        core.step(1)
        step_floor.append((time.perf_counter() - t0) * 1e6)
        time.sleep(0.005)  # decouple reps from queue depth effects

    # ---- floor(get_state): the REAL get_state() ----
    gs_floor = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        core.get_state()
        gs_floor.append((time.perf_counter() - t0) * 1e6)
        time.sleep(0.002)

    # ---- floor(gen dispatch+map): real GEN-path shader, batch=256 ----
    # Mirrors probe_ps009b_paired.py's GEN leg construction.
    import wgpu
    from pyshader_fde_gpu import _build_shader, ARRAY_WORDS
    batch = 256
    shader = device.create_shader_module(code=_build_shader(batch),
                                         label="floor-gen-probe")
    gpu_buf = device.create_buffer(
        size=ARRAY_WORDS * 4,
        usage=wgpu.BufferUsage.STORAGE
        | wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.COPY_SRC)
    readback = device.create_buffer(
        size=ARRAY_WORDS * 4,
        usage=wgpu.BufferUsage.MAP_READ
        | wgpu.BufferUsage.COPY_DST)
    arr_words = (prog_words * ((ARRAY_WORDS // len(prog_words)) + 1))[:ARRAY_WORDS]
    prog = np.array(arr_words, dtype=np.uint32)
    device.queue.write_buffer(gpu_buf, 0, prog.tobytes())
    # Build pipeline + bind group ONCE (creating the pipeline inside the
    # timed loop was both wrong-shape and a validation error: layout=auto
    # requires the bind group to be set before dispatch).
    pipe = device.create_compute_pipeline(
        layout="auto", compute={"module": shader, "entry_point": "main"})
    bg = device.create_bind_group(
        layout=pipe.get_bind_group_layout(0),
        entries=[{"binding": 0,
                  "resource": {"buffer": gpu_buf, "offset": 0,
                               "size": ARRAY_WORDS * 4}}])

    gen_floor = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        enc = device.create_command_encoder()
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(1, 1, 1)
        cp.end()
        enc.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, ARRAY_WORDS * 4)
        device.queue.submit([enc.finish()])
        readback.map("read")
        readback.read_mapped()
        readback.unmap()
        gen_floor.append((time.perf_counter() - t0) * 1e6)
        time.sleep(0.005)

    # ---- floor(glyphrunner_wgsl_step): the REAL GlyphRunner WGSL protocol ----
    # Landed 2026-09-21 (pre-registered unblock in RECEIPT_R11_task_queue.md):
    # the receipts' WGSL legs time GlyphRunner.run_wgsl's per-step protocol —
    # 1 dispatch + 1 blocking cpu-state readback per step — which is a
    # DIFFERENT quantity than SpatialRV32ICore.step() (4 readbacks). Without
    # this floor, check_regime.py correctly rejects those legs as 0.02x
    # "below floor" and every verdict is UNDETERMINABLE. This times exactly
    # the probe_r11_task_queue.py leg-B loop body against the real
    # wgsl_glyph_isa_v2 shader in THIS dedicated process.
    from tools.wgsl_glyph_isa_v2 import build_shader as _gr_build_shader
    from tools.wgsl_glyph_isa_v2 import make_cpu_state_array as _gr_mkstate
    from tools.glyph_isa_v2 import OpcodeMapV2

    gr_cpu_state, gr_cpu_dtype = _gr_mkstate(1)
    gr_mmio = np.zeros(160, dtype=np.uint32)
    gr_ram = np.zeros(16384, dtype=np.uint32)
    gr_rgba = np.zeros((64, 4), dtype=np.uint32)
    gr_dt = np.dtype([('image_width', np.uint32), ('image_height', np.uint32),
                      ('output_buffer_size', np.uint32)])
    gr_bufs = {}
    for _name, _arr, _extra in (
            ("img", gr_rgba, 0), ("cpu", gr_cpu_state, 0),
            ("out", np.zeros(256, np.uint32), 0), ("mmio", gr_mmio, 0),
            ("u", np.array([(1, 1, 64)], gr_dt), wgpu.BufferUsage.UNIFORM),
            ("ram", gr_ram, 0)):
        _b = device.create_buffer(size=_arr.nbytes,
                                  usage=wgpu.BufferUsage.STORAGE
                                  | wgpu.BufferUsage.COPY_DST
                                  | wgpu.BufferUsage.COPY_SRC | _extra)
        queue = device.queue
        queue.write_buffer(_b, 0, _arr.tobytes())
        gr_bufs[_name] = _b
    gr_bgl = device.create_bind_group_layout(entries=[
        {'binding': _i, 'visibility': wgpu.ShaderStage.COMPUTE,
         'buffer': {'type': 'storage' if _i != 3 else 'uniform'}}
        for _i in range(6)])
    gr_pipe = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[gr_bgl]),
        compute={'module': device.create_shader_module(
            code=_gr_build_shader(OpcodeMapV2())), 'entry_point': 'main'})
    gr_bg = device.create_bind_group(layout=gr_bgl, entries=[
        {'binding': 0, 'resource': {'buffer': gr_bufs["img"], 'offset': 0, 'size': gr_rgba.nbytes}},
        {'binding': 1, 'resource': {'buffer': gr_bufs["cpu"], 'offset': 0, 'size': gr_cpu_state.nbytes}},
        {'binding': 2, 'resource': {'buffer': gr_bufs["out"], 'offset': 0, 'size': 256}},
        {'binding': 3, 'resource': {'buffer': gr_bufs["u"], 'offset': 0, 'size': gr_bufs["u"].size}},
        {'binding': 4, 'resource': {'buffer': gr_bufs["mmio"], 'offset': 0, 'size': gr_mmio.nbytes}},
        {'binding': 5, 'resource': {'buffer': gr_bufs["ram"], 'offset': 0, 'size': gr_ram.nbytes}}])
    gr_rb = device.create_buffer(
        size=gr_cpu_state.nbytes,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ)
    gr_n = gr_cpu_state.nbytes

    def _gr_step_once():
        enc = device.create_command_encoder()
        p = enc.begin_compute_pass()
        p.set_pipeline(gr_pipe)
        p.set_bind_group(0, gr_bg)
        p.dispatch_workgroups(1)
        p.end()
        enc.copy_buffer_to_buffer(gr_bufs["cpu"], 0, gr_rb, 0, gr_n)
        queue.submit([enc.finish()])
        gr_rb.map_sync(mode=wgpu.MapMode.READ)
        _last_rb[0] = np.frombuffer(
            bytes(gr_rb.read_mapped()), dtype=gr_cpu_dtype)[0]
        gr_rb.unmap()

    _last_rb = [None]
    for _ in range(WARMUP):
        _gr_step_once()
        time.sleep(0.005)
    gr_floor = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        _gr_step_once()
        gr_floor.append((time.perf_counter() - t0) * 1e6)
        time.sleep(0.002)
    gr_floor.sort()

    # ---- floor(glyphrunner_wgsl_step_tput): pipelined THROUGHPUT floor ----
    # The receipts' WGSL legs run a TIGHT loop (dispatch+map per step, no
    # sleep): the GPU stays busy and each map only waits for its own copy,
    # so per-step wall time lands ~100us — 5x below the spaced round-trip
    # latency above. Both are real; they are DIFFERENT quantities (latency
    # vs throughput). orch_grfloor_falsifier + orch_grbacklog (2026-09-21)
    # measured the gap: spaced ~480-690us, tight ~72-111us, empty-dispatch
    # ~34us. A tight-loop leg adjudicated against a latency floor is a
    # category error; this leg times the SAME tight-loop protocol on the
    # REAL resident program so check_regime can adjudicate apples-to-apples.
    import tempfile as _tempfile
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.agent_resident import resident_image as _resident_image

    with _tempfile.TemporaryDirectory() as _td:
        _img_path = Path(_td) / "resident_floor.npy"
        _resident_image(build_default_atlas(), mode="resident",
                        out_path=_img_path)
        gr2_img = np.load(_img_path)
    gr2_h, gr2_w, _ = gr2_img.shape
    gr2_n_px = gr2_h * gr2_w
    # gr_bufs["img"] was sized for a 64-px placeholder; recreate it at the
    # real resident-image size (the bind group references the buffer object,
    # so replace BOTH and rebuild the bind group entry for img).
    gr2_rgba = np.zeros((gr2_n_px, 4), dtype=np.uint32)
    gr2_rgba[:, 0:3] = gr2_img.reshape(gr2_n_px, 3)
    gr_bufs["img"] = device.create_buffer(
        size=gr2_rgba.nbytes,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        | wgpu.BufferUsage.COPY_SRC)
    queue.write_buffer(gr_bufs["img"], 0, gr2_rgba.tobytes())
    queue.write_buffer(gr_bufs["u"], 0, np.array(
        [(gr2_w, gr2_h, 64)], gr_dt).tobytes())
    gr_bg = device.create_bind_group(layout=gr_bgl, entries=[
        {'binding': 0, 'resource': {'buffer': gr_bufs["img"], 'offset': 0, 'size': gr2_rgba.nbytes}},
        {'binding': 1, 'resource': {'buffer': gr_bufs["cpu"], 'offset': 0, 'size': gr_cpu_state.nbytes}},
        {'binding': 2, 'resource': {'buffer': gr_bufs["out"], 'offset': 0, 'size': 256}},
        {'binding': 3, 'resource': {'buffer': gr_bufs["u"], 'offset': 0, 'size': gr_bufs["u"].size}},
        {'binding': 4, 'resource': {'buffer': gr_bufs["mmio"], 'offset': 0, 'size': gr_mmio.nbytes}},
        {'binding': 5, 'resource': {'buffer': gr_bufs["ram"], 'offset': 0, 'size': gr_ram.nbytes}}])

    gr_tput_reps = []
    for _rep in range(REPS):
        gr_cpu_state["running"] = 1  # reset; pc stays (0,0) = program entry
        queue.write_buffer(gr_bufs["cpu"], 0, gr_cpu_state.tobytes())
        rep_steps, rep_us = 0, []
        for _step in range(1, 401):  # same cap shape as the probe leg
            t0 = time.perf_counter()
            _gr_step_once()
            rep_us.append((time.perf_counter() - t0) * 1e6)
            rep_steps = _step
            if _last_rb[0] is not None and _last_rb[0]["running"] == 0:
                break
        if rep_steps >= 50:  # a real run, not an instant halt
            gr_tput_reps.append(statistics.median(rep_us))

    gr_tput = statistics.median(gr_tput_reps) if gr_tput_reps else None

    step_floor.sort()
    gs_floor.sort()
    gen_floor.sort()
    result = {
        "authority": "floors_authoritative.json (zion repo; supersedes "
                     ".builder_queue/floors.json and any cross-repo floors)",
        "measures": "REAL SpatialRV32ICore.step(1)/get_state() — 4 blocking "
                    "readbacks per step(), not a proxy shader; plus "
                    "glyphrunner_wgsl_step = the GlyphRunner.run_wgsl "
                    "per-step protocol (1 dispatch + 1 blocking cpu-state "
                    "readback) against the real wgsl_glyph_isa_v2 shader",
        "floor_us": {
            "step": round(statistics.median(step_floor), 1),
            "step_min": round(step_floor[0], 1),
            "step_p10": round(pct(step_floor, 0.10), 1),
            "step_p90": round(pct(step_floor, 0.90), 1),
            "get_state": round(statistics.median(gs_floor), 1),
            "get_state_min": round(gs_floor[0], 1),
            "gen_dispatch_plus_map": round(statistics.median(gen_floor), 1),
            "glyphrunner_wgsl_step": round(statistics.median(gr_floor), 1),
            "glyphrunner_wgsl_step_min": round(gr_floor[0], 1),
            **({"glyphrunner_wgsl_step_tput": round(gr_tput, 1)}
               if gr_tput is not None else {}),
        },
        "readbacks_per_step_call": 4,
        "reps": REPS,
        "freshness_window_h": 12,
        "adapter_summary": str(device.adapter.summary),
        "measured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    out = REPO / ".builder_queue" / "floors_authoritative.json"
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
