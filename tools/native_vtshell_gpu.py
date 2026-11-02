#!/usr/bin/env python3
"""tools/native_vtshell_gpu.py — GPU-Native vtshell executor (BK-82 Rung 2).

Executes the xv6-nano shell (SCENARIO 9) on the live WGSL Twin (NVIDIA RTX 5090
via wgpu/Vulkan) and renders terminal output through GlyphVT (VT100 screen buffer).

Directive: .builder_queue/DIRECTIVE_BK82_NATIVE_UI_LADDER.md (RUNG 2)
Gate: tests/test_bk82_rung2_native_vtshell.py
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

REPO = Path(__file__).resolve().parent.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tools.glyph_vt as VT
import tools.wgsl_glyph_isa_v2 as wgsl_twin
from tools.build_map_bridge import _vtshell_image
from tools.glyph_isa_v2 import OpcodeMapV2

_VTSHELL_MAX_LINE = 64
_VTSHELL_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SESSION_DIR = Path("/tmp/geos_vtshell_sessions")


def _serialize_vt(vt: VT.GlyphVT) -> Dict[str, Any]:
    return {
        "rows": vt.screen.rows,
        "cols": vt.screen.cols,
        "grid": vt.screen.grid,
        "r": vt.screen.r,
        "c": vt.screen.c,
        "wrap_pending": vt.screen._wrap_pending,
    }


def _deserialize_vt(data: Dict[str, Any]) -> VT.GlyphVT:
    vt = VT.GlyphVT(rows=data.get("rows", 24), cols=data.get("cols", 80))
    vt.screen.grid = data["grid"]
    vt.screen.r = data["r"]
    vt.screen.c = data["c"]
    vt.screen._wrap_pending = data.get("wrap_pending", False)
    return vt


def _save_session(sid: str, sess: Dict[str, Any]) -> None:
    try:
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        data = _serialize_vt(sess["vt"])
        (_SESSION_DIR / f"{sid}.json").write_text(json.dumps(data))
    except Exception:
        pass


def _load_session(sid: str) -> Optional[Dict[str, Any]]:
    if sid in _VTSHELL_SESSIONS:
        return _VTSHELL_SESSIONS[sid]
    f = _SESSION_DIR / f"{sid}.json"
    if f.exists():
        try:
            data = json.loads(f.read_text())
            vt = _deserialize_vt(data)
            sess = {"vt": vt}
            _VTSHELL_SESSIONS[sid] = sess
            return sess
        except Exception:
            return None
    return None


def run_vtshell_gpu(session_id: Optional[str] = None,
                    line: Optional[str] = None,
                    new_session: bool = False,
                    neuter_seed: bool = False,
                    max_steps: int = 4000) -> Dict[str, Any]:
    """Execute one command batch on the live WGSL Twin via wgpu."""
    if new_session:
        sid = uuid.uuid4().hex
        sess = {"vt": VT.GlyphVT(cols=80, rows=24)}
        _VTSHELL_SESSIONS[sid] = sess
        _save_session(sid, sess)
        if line is None:
            vt = sess["vt"]
            return {
                "ok": True,
                "session_id": sid,
                "screen": vt.text(),
                "bytes_out": 0,
                "steps": 0,
                "lines": vt.text().splitlines(),
            }
    else:
        if session_id:
            sess = _load_session(session_id)
            if sess is None:
                return {
                    "ok": False,
                    "error": f"unknown session_id '{session_id}' — open a session first (new_session=true)"
                }
            sid = session_id
        else:
            sid = uuid.uuid4().hex
            sess = {"vt": VT.GlyphVT(cols=80, rows=24)}
            _VTSHELL_SESSIONS[sid] = sess
            _save_session(sid, sess)

    if line is None:
        return {"ok": False, "error": "missing command line"}

    n_bytes = len(line.encode("utf-8"))
    if n_bytes > _VTSHELL_MAX_LINE:
        return {
            "ok": False,
            "error": f"line is {n_bytes}B utf-8; per-batch input cap is "
                     f"{_VTSHELL_MAX_LINE}B (INPUT_DATA_CAP) — refused, no silent truncation"
        }

    vt = sess["vt"]

    # Feed characters into VT line discipline
    for ch in line + "\r":
        vt.feed_key(ch)

    c = _vtshell_image()

    # Seed input into RAM/MMIO
    # We create a pristine memory array
    mem = list(c["memory"])
    seeded = vt.seed_bytes_into_mem(mem) if hasattr(vt, "seed_bytes_into_mem") else None
    if seeded is None:
        # Fallback to standard seed_bytes using a dummy CPU object
        from tools.build_map_bridge import _vtshell_fresh_cpu
        dummy_cpu = _vtshell_fresh_cpu()
        seeded = vt.seed_bytes(dummy_cpu)
        mem = list(dummy_cpu.memory)

    if not neuter_seed:
        # LBU little-endian adapter for xv6-nano
        ring_start = 8288
        for i in range(seeded):
            w = ring_start + i
            b = mem[w] & 0xFF
            sh = (i & 3) * 8
            target_w = ring_start + (i >> 2)
            if (i & 3) == 0:
                mem[target_w] = b
            else:
                mem[target_w] |= (b << sh)
    else:
        # Neutered seed: clear input length to simulate empty/corrupted buffer
        INPUT_LEN_WORD = 8284
        mem[INPUT_LEN_WORD] = 0

    # Execute on GPU via wgpu
    import wgpu
    import wgpu.utils

    device = wgpu.utils.get_default_device()
    queue = device.queue
    image = c["img"]
    n_pixels = image.shape[0] * image.shape[1]
    rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
    rgba[:, 0:3] = image.reshape(n_pixels, 3)
    usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC)

    cpu_state, cpu_dtype = wgsl_twin.make_cpu_state_array(1)
    cpu_state['mode'][0] = 0

    ram = np.array(mem[:16384], dtype=np.uint32)
    mmio = np.zeros(256, dtype=np.uint32)
    for i in range(256):
        if 8192 + i < len(mem):
            mmio[i] = mem[8192 + i]

    dt = np.dtype([('image_width', np.uint32),
                   ('image_height', np.uint32),
                   ('output_buffer_size', np.uint32)])
    bufs = {}
    for name_b, arr, extra in (
            ("img", rgba, 0), ("cpu", cpu_state, 0),
            ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
            ("u", np.array([(image.shape[1], image.shape[0], 64)], dt),
             wgpu.BufferUsage.UNIFORM), ("ram", ram, 0)):
        b = device.create_buffer(size=arr.nbytes, usage=usage | extra)
        queue.write_buffer(b, 0, arr.tobytes())
        bufs[name_b] = b

    bgl = device.create_bind_group_layout(entries=[
        {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
         'buffer': {'type': 'storage' if i != 3 else 'uniform'}}
        for i in range(6)])
    bg = device.create_bind_group(layout=bgl, entries=[
        {'binding': 0, 'resource': {'buffer': bufs["img"], 'offset': 0, 'size': rgba.nbytes}},
        {'binding': 1, 'resource': {'buffer': bufs["cpu"], 'offset': 0, 'size': cpu_state.nbytes}},
        {'binding': 2, 'resource': {'buffer': bufs["out"], 'offset': 0, 'size': 256}},
        {'binding': 3, 'resource': {'buffer': bufs["u"], 'offset': 0, 'size': bufs["u"].size}},
        {'binding': 4, 'resource': {'buffer': bufs["mmio"], 'offset': 0, 'size': mmio.nbytes}},
        {'binding': 5, 'resource': {'buffer': bufs["ram"], 'offset': 0, 'size': ram.nbytes}}])

    sh = device.create_shader_module(code=wgsl_twin.build_shader(OpcodeMapV2()))
    pipe = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[bgl]),
        compute={'module': sh, 'entry_point': 'main'})

    steps = 0
    for _ in range(max_steps):
        enc = device.create_command_encoder()
        cpass = enc.begin_compute_pass()
        cpass.set_pipeline(pipe)
        cpass.set_bind_group(0, bg)
        cpass.dispatch_workgroups(1, 1, 1)
        cpass.end()
        queue.submit([enc.finish()])
        steps += 1
        st = np.frombuffer(queue.read_buffer(bufs["cpu"]), dtype=cpu_dtype)
        if st['running'][0] == 0:
            break

    ram_gpu = np.frombuffer(queue.read_buffer(bufs["ram"]), dtype=np.uint32)
    clen_gpu = int(ram_gpu[c["g_clen_word"]] & 0xFFFFFFFF)
    g_console = c["g_console"]
    out_gpu = bytes((ram_gpu[(g_console + i) >> 2] >> (((g_console + i) & 3) * 8)) & 0xFF
                    for i in range(clen_gpu))

    vt.feed_output(out_gpu)
    _save_session(sid, sess)

    return {
        "ok": True,
        "session_id": sid,
        "screen": vt.text(),
        "bytes_out": clen_gpu,
        "steps": steps,
        "lines": vt.text().splitlines(),
    }


def main():
    parser = argparse.ArgumentParser(description="GPU-Native vtshell executor")
    parser.add_argument("--session-id", help="Session ID for state persistence")
    parser.add_argument("--line", help="Input command line")
    parser.add_argument("--new-session", action="store_true", help="Start fresh session")
    parser.add_argument("--neuter-seed", action="store_true", help="Neuter ring seed for RED test")
    args = parser.parse_args()

    res = run_vtshell_gpu(
        session_id=args.session_id,
        line=args.line,
        new_session=args.new_session,
        neuter_seed=args.neuter_seed,
    )
    print(json.dumps(res))


if __name__ == "__main__":
    main()
