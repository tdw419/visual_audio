"""BK-51 research probe (af3e, 2026-09-27): the WGSL twin omits the GO-2
2D tile predicate entirely — spawn(tile=...) confinement does not exist
on the GPU.

STRUCTURAL (source):
  - oracle `_addr_in_box` (glyph_isa_v2.py:720-748) checks BOX0-2 AND the
    2D tile predicate (TILE_H != 0 admits [trow,trow+h) x [tcol,tcol+w),
    :734-747). item-29 arms exactly these words (arm_tile,
    glyph_containment.py:74-96 → TILE_ROW/COL/H/W byte 0x8160/0x8164/
    0x8168/0x816C = words 8280/8281/8282/8283, inside the 160-word MMIO
    block 8192..8351).
  - twin `addr_in_box` (wgsl_glyph_isa_v2.py:463-476) checks ONLY
    lo0..2/hi0..2 — zero tile references (the constant block even says
    so at :206-208: "The 2D tile predicate is not mirrored").
  So a WGSL-twin USER task with its tile armed in box_mmio[88..91] has an
  INERT fence: out-of-tile STs should land clean where the oracle traps.

Legs (verdicts from mmio/ram READBACK BYTES, never stdout):
  S1 (source): twin addr_in_box body contains zero TILE references;
      oracle's _addr_in_box contains the tile branch.
  D1 (on-device): seeded-USER ST to word 164 (out of tile (5,0,2,4),
      byte 656, BOX0-2 all unset) — conviction: value LANDS at ram[164],
      mode stays USER, fault_addr_word == 0. Oracle twin expectation:
      E-K1 fires (fault 656, mode -> SUPER, refused) — measured
      engine divergence (oracle control: dbg_wgsl_tile_oracle_af3e.py).
  D2 (on-device control): BOX0 [1200,1300) armed (no tile), seeded-USER
      ST to out-of-box word 100 — E-K1 must fire (fault_addr_word == 400,
      value refused). Proves the twin's box consult is LIVE, so D1's
      clean landing is the missing tile predicate, not a dead harness.
  D3 (on-device control): tile (5,0,2,4) armed, seeded-USER ST to
      in-tile word 160 — value lands, mode USER (in-tile stores are
      lawful; the probe cannot have broken in-tile semantics).
  D4 (on-device composition): tile armed, seeded-USER ST of 0 to word
      8282 (TILE_H) through the BK-50 unmode-gated MMIO door (:443-444)
      — conviction: mmio[90] reads 0, clean: even once a tile predicate
      is added, BK-50's door lets USER rewrite the tile words. The two
      defects compose.

Run: python3 .builder_queue/probe_wgsl_tile_fence_af3e.py
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

MMIO_LO, MMIO_SPAN = 8192, 160
TILE_ROW_WORD, TILE_COL_WORD, TILE_H_WORD, TILE_W_WORD = 8280, 8281, 8282, 8283
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * 32 + TILE_COL          # 160 (W_MEM = 32 words/row)
OUT_TILE_WORD = IN_TILE_WORD + TILE_W            # 164 (first word outside)
CANARY = 0x0ADF00D
DEST_RAM = 100                                   # D2 out-of-box RAM word
BOX_LO, BOX_HI = 1200, 1300                      # D2 armed box (bytes)

MMIO_TILE_IDX = TILE_ROW_WORD - MMIO_LO          # 88


def source_legs():
    twin = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    oracle = (REPO / "tools" / "glyph_isa_v2.py").read_text()
    aib = twin[twin.index("fn addr_in_box"):twin.index("@compute")]
    return {
        "S1_twin_tile_refs": aib.count("TILE"),
        "S1_twin_checks_boxes": "BOX0_LO_WORD" in aib and "hi0" in aib,
        "S1_oracle_has_tile_branch": ("TILE_H_ADDR >> 2" in oracle
                                      and "trow <= row < trow + h" in oracle),
    }


def run_prog(prog, mmio_seed, seed_mode=1, max_steps=80):
    """Bake+run one program on the real WGSL device harness (BK-48/49/50
    harness shape: run_wgsl's real buffers + build_shader(OpcodeMapV2()),
    probe-only seeded cpu.mode + mmio)."""
    import wgpu, wgpu.utils  # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        image = GlyphRunner(png).image

    device = wgpu.utils.get_default_device()
    queue = device.queue
    n_pixels = image.shape[0] * image.shape[1]
    rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
    rgba[:, 0:3] = image.reshape(n_pixels, 3)
    usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
             | wgpu.BufferUsage.COPY_SRC)
    cpu_state, cpu_dtype = make_cpu_state_array(1)
    cpu_state[0]["mode"] = seed_mode
    mmio = np.zeros(MMIO_SPAN, dtype=np.uint32)
    for k, v in mmio_seed.items():
        mmio[k] = v            # probe-only seeds (KFAULT_PC stays 0 here)
    ram = np.zeros(16384, dtype=np.uint32)
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
    step = 0
    for step in range(1, max_steps + 1):
        enc = device.create_command_encoder()
        p = enc.begin_compute_pass()
        p.set_pipeline(pipe)
        p.set_bind_group(0, bg)
        p.dispatch_workgroups(1)
        p.end()
        queue.submit([enc.finish()])
        rb = np.frombuffer(queue.read_buffer(bufs["cpu"]), dtype=cpu_dtype)[0]
        if rb['running'] == 0:
            break
    mmio_out = np.frombuffer(memoryview(queue.read_buffer(bufs["mmio"])),
                             dtype=np.uint32)
    ram_out = np.frombuffer(memoryview(queue.read_buffer(bufs["ram"])),
                            dtype=np.uint32)
    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "ram_word100": int(ram_out[100]),
        "ram_word160": int(ram_out[160]),
        "ram_word164": int(ram_out[164]),
        "mmio_tile_h": int(mmio_out[TILE_H_WORD - MMIO_LO]),
        "mmio_kfault_pc": int(mmio_out[1]),
        "fault_addr_word": int(mmio_out[7]),
    }


def main():
    results = {"S1": source_legs()}
    tile_mmio = {MMIO_TILE_IDX + 0: TILE_ROW,
                 MMIO_TILE_IDX + 1: TILE_COL,
                 MMIO_TILE_IDX + 2: TILE_H,
                 MMIO_TILE_IDX + 3: TILE_W}

    # D1: seeded-USER ST of CANARY to word 164 — outside tile (5,0,2,4),
    # BOX0-2 unset. The twin's tile-less addr_in_box should admit it.
    prog_d1 = """
    :__entry
    LDI r5 %d
    LDI r6 %d
    ST r6 r5
    HALT
    """ % (CANARY, OUT_TILE_WORD)
    results["D1_user_st_out_of_tile"] = run_prog(prog_d1, dict(tile_mmio))

    # D2 control: BOX0 [1200,1300) armed (no tile), ST to word 100 ->
    # E-K1 must fire (fault_addr_word == 400 = 100*4, value refused).
    prog_d2 = """
    :__entry
    LDI r5 4660
    LDI r6 %d
    ST r6 r5
    HALT
    """ % DEST_RAM
    results["D2_user_st_oobox_ek1_control"] = run_prog(
        prog_d2, {3: BOX_LO, 4: BOX_HI})

    # D3 control: tile armed, ST to in-tile word 160 -> lands, mode USER.
    prog_d3 = """
    :__entry
    LDI r5 4660
    LDI r6 %d
    ST r6 r5
    HALT
    """ % IN_TILE_WORD
    results["D3_user_st_in_tile_control"] = run_prog(prog_d3, dict(tile_mmio))

    # D4 composition: tile armed, ST 0 -> word 8282 (TILE_H) through the
    # BK-50 unmode-gated MMIO door. Conviction: mmio_tile_h reads 0.
    prog_d4 = """
    :__entry
    LDI r5 0
    LDI r6 %d
    ST r6 r5
    HALT
    """ % TILE_H_WORD
    results["D4_user_clears_tile_h_mmio_door"] = run_prog(
        prog_d4, dict(tile_mmio))

    blob = json.dumps(results, indent=1, sort_keys=True)
    print(blob)
    print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
