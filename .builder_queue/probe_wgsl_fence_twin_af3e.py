"""BK-48 research probe: does the WGSL twin reproduce the fence family's
shared root cause (ST-anchored tile consult), or does it diverge?

Legs:
  S1: walk_ld body contains ZERO addr_in_box references (source read).
  S2: walk_st body — locate its addr_in_box reference arm (source read).
  D1 (on-device): USER-mode LD from an out-of-box word through run_wgsl.
      Box0 = [300,500) words armed via box_mmio; canary 0x0BADF00D seeded
      at word 200 (outside); program LDs it and STs it to word 100 (in
      box). Fence-blind LD => 0x0BADF00D lands at 100. Box-fenced LD =>
      0 lands (walk_ld has no fault channel, so a fence-blind read is
      indistinguishable from a silent cross-fence read UNLESS the value
      propagates — the value propagating IS the conviction).
  D2 (on-device): USER-mode ST to an out-of-box word (word 200) — the
      E-K1 control: walk_st must return true, value must NOT land.

Run: python3 .builder_queue/probe_wgsl_fence_twin_af3e.py
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.glyph_gpt.baker import bake_image                    # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                  # noqa: E402


def source_legs():
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    out = {}
    ld_start = src.index("fn walk_ld(")
    st_start = src.index("fn walk_st(")
    ld_body = src[ld_start:st_start]
    out["S1_walk_ld_addr_in_box_refs"] = ld_body.count("addr_in_box")
    next_fn = src.find("fn ", st_start + 10)
    st_body = src[st_start:next_fn]
    out["S2_walk_st_addr_in_box_refs"] = st_body.count("addr_in_box")
    out["S2_walk_st_is_super_or_in_box"] = (
        "is_super || addr_in_box" in st_body)
    return out


def _run(prog, mmio_writes, ram_seed, max_steps=60):
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "probe.glyph.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        r = GlyphRunner(png)
        # patch the mmio buffer the way run_wgsl builds it: easiest is to
        # re-implement the seed step by writing through runner internals —
        # instead we pre-seed via a monkey-free path: run_wgsl has no mmio
        # param, so we replicate its setup here (same buffers, same shader).
        return r.run_wgsl(max_steps=max_steps, ram_seed=ram_seed), mmio_writes


def device_legs():
    import numpy as np
    import wgpu, wgpu.utils                                    # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    BOX0_LO_WORD, BOX0_HI_WORD = 8195, 8196
    CANARY, DEST = 200, 100
    CANARY_VAL = 0x0BADF00D

    def bake(prog):
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "p.png"
            bake_image(prog, cols_instrs=8, out_path=png)
            return GlyphRunner(png)

    # D1: seeded-USER LD out-of-box canary -> ST in-box dest. Mode is seeded
    # directly in the state array (probe-only posture; documented). No KJMP
    # entry block: KJMP's target is a packed PIXEL PC, unreachable from raw
    # asm labels, and an earlier draft's KJMP-to-word-32 bug jumped past the
    # program — legs measured a jump to empty space, now removed.
    prog_d1 = """
    :__entry
    LDI r6 200
    LD r5 r6
    LDI r6 100
    ST r6 r5
    HALT
    """
    def run_seeded(image, seed_mmio, seed_mode, max_steps=60):
        device = wgpu.utils.get_default_device()
        queue = device.queue
        n_pixels = image.shape[0] * image.shape[1]
        rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
        rgba[:, 0:3] = image.reshape(n_pixels, 3)
        usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
                 | wgpu.BufferUsage.COPY_SRC)
        cpu_state, cpu_dtype = make_cpu_state_array(1)
        cpu_state[0]["mode"] = seed_mode
        mmio = np.zeros(160, dtype=np.uint32)
        for a, v in seed_mmio.items():
            mmio[a] = v
        ram = np.zeros(16384, dtype=np.uint32)
        ram[CANARY] = CANARY_VAL
        dt = np.dtype([('image_width', np.uint32),
                       ('image_height', np.uint32),
                       ('output_buffer_size', np.uint32)])
        bufs = {}
        for name, arr, extra in (
                ("img", rgba, 0), ("cpu", cpu_state, 0),
                ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
                ("u", np.array([(image.shape[1], image.shape[0], 64)], dt),
                 wgpu.BufferUsage.UNIFORM), ("ram", ram, 0)):
            b = device.create_buffer(size=arr.nbytes, usage=usage | extra)
            queue.write_buffer(b, 0, arr.tobytes())
            bufs[name] = b
        bgl = device.create_bind_group_layout(entries=[
            {'binding': i, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'storage' if i != 3 else 'uniform'}}
            for i in range(6)])
        bg = device.create_bind_group(layout=bgl, entries=[
            {'binding': 0, 'resource': {'buffer': bufs["img"], 'offset': 0,
                                        'size': rgba.nbytes}},
            {'binding': 1, 'resource': {'buffer': bufs["cpu"], 'offset': 0,
                                        'size': cpu_state.nbytes}},
            {'binding': 2, 'resource': {'buffer': bufs["out"], 'offset': 0,
                                        'size': 256}},
            {'binding': 3, 'resource': {'buffer': bufs["u"], 'offset': 0,
                                        'size': 12}},
            {'binding': 4, 'resource': {'buffer': bufs["mmio"], 'offset': 0,
                                        'size': mmio.nbytes}},
            {'binding': 5, 'resource': {'buffer': bufs["ram"], 'offset': 0,
                                        'size': ram.nbytes}}])
        sh = device.create_shader_module(code=build_shader(OpcodeMapV2()))
        pipe = device.create_compute_pipeline(
            layout=device.create_pipeline_layout(bind_group_layouts=[bgl]),
            compute={'module': sh, 'entry_point': 'main'})
        rb = None
        for step in range(1, max_steps + 1):
            enc = device.create_command_encoder()
            p = enc.begin_compute_pass()
            p.set_pipeline(pipe)
            p.set_bind_group(0, bg)
            p.dispatch_workgroups(1)
            p.end()
            queue.submit([enc.finish()])
            rb = np.frombuffer(queue.read_buffer(bufs["cpu"]),
                               dtype=cpu_dtype)[0]
            if rb['running'] == 0:
                break
        ram_out = np.frombuffer(queue.read_buffer(bufs["ram"]),
                                dtype=np.uint32)
        return {
            "halted": bool(rb['running'] == 0),
            "steps": step,
            "mode_final": int(rb['mode']),
            "r5": int(rb['registers'][5]),
            "ram_dest": int(ram_out[DEST]),
            "ram_canary": int(ram_out[CANARY]),
        }

    box = {BOX0_LO_WORD - 8192: 300, BOX0_HI_WORD - 8192: 500}
    results = {}

    # D1: seeded-USER LD out-of-box canary -> ST in-box dest (mode seeded
    # directly in the state array; probe-only posture, documented).
    r = GlyphRunner(bake(prog_d1).image)
    results["D1_user_ld_oob"] = run_seeded(r.image, box, 1)

    # D2: seeded-USER ST to out-of-box canary (E-K1 control)
    prog_d2 = """
    :__entry
    LDI r6 200
    LDI r5 4660
    ST r6 r5
    HALT
    """
    r2 = GlyphRunner(bake(prog_d2).image)
    results["D2_user_st_oob_control"] = run_seeded(r2.image, box, 1)

    # D3: SUPER LD out-of-box (should read fine — walk_ld is_super arm)
    results["D3_super_ld_oob"] = run_seeded(r.image, box, 0)

    return results


if __name__ == "__main__":
    print("== S legs (source reads) ==")
    for k, v in sorted(source_legs().items()):
        print(f"{k} = {v}")
    print("== D legs (on-device WGSL) ==")
    try:
        for k, v in sorted(device_legs().items()):
            print(k, v)
    except Exception as e:
        print(f"DEVICE-LEG-ERROR: {type(e).__name__}: {e}")
