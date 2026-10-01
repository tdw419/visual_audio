"""BK-51 post-landing research probe (af3e, 2026-09-27): the WGSL twin's
LD side under an ARMED GO-2 tile — the leg BK-51's receipt explicitly
left unprobed ("walk_ld under a tile — unprobed") and the leg the
69a53298 landing made load-bearing on the ORACLE (spawn(tile=...) now
arms _tile_confinement -> out-of-tile USER LD traps, in-tile LD lands).

Question: after 69a53298, does the twin DIVERGE from the oracle on the
tile-LD read side the same way it denies lawful in-tile STs (BK-51 D3)?

Legs (verdicts from mmio/ram READBACK + cpu register readback, never
stdout):
  L1 (twin, on-device): tile (5,0,2,4) armed in mmio[88..91], seeded-USER
      LD from OUT-of-tile word 164 (canary 0x0ADF00D) -> ST r3 to in-tile
      word 160 -> readback. Conviction per source (walk_ld has NO tile
      consult): the LD SUCCEEDS, r3 == canary. Whether the exfil ST then
      lands or traps is the D3 parallel measured separately (L2).
  L2 (twin, on-device): same tile, in-tile ST to word 160 -> BK-51's
      standing D3: twin TRAPS (fault 640, mode->SUPER, refused).
  L3 (twin, on-device control): same tile, in-tile LD from word 160 ->
      value must reach r3 (in-tile reads lawful on both engines).
  L4 (oracle, host): SAME L1 program via the landed spawn(tile=...)
      path at HEAD -> EXIT_FAULT, fault_addr == 656, the landed BK-38
      fence fires; the twin's L1 success is therefore a measured
      ENGINE DIVERGENCE, not just a fence gap.
  L5 (source): walk_ld body contains zero TILE references; the oracle
      LD arm carries the _tile_confinement branch.

Run: python3 .builder_queue/probe_bk51_twin_tile_ld_af3e.py
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

MMIO_LO = 8192
TILE_ROW_WORD, TILE_COL_WORD, TILE_H_WORD, TILE_W_WORD = 8280, 8281, 8282, 8283
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * 32 + TILE_COL          # 160 (W_MEM = 32 words/row)
OUT_TILE_WORD = IN_TILE_WORD + TILE_W            # 164 (first word outside)
CANARY = 0x0ADF00D
MMIO_TILE_IDX = TILE_ROW_WORD - MMIO_LO          # 88

TILE_MMIO_SEED = {MMIO_TILE_IDX + 0: TILE_ROW,
                  MMIO_TILE_IDX + 1: TILE_COL,
                  MMIO_TILE_IDX + 2: TILE_H,
                  MMIO_TILE_IDX + 3: TILE_W}


def run_prog(prog, mmio_seed, ram_seed=None, seed_mode=1, max_steps=80):
    import wgpu  # noqa: F401
    import wgpu.utils
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
    mmio = np.zeros(160, dtype=np.uint32)
    for k, v in mmio_seed.items():
        mmio[k] = v
    ram = np.zeros(16384, dtype=np.uint32)
    if ram_seed:
        for k, v in ram_seed.items():
            ram[k] = v
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
    out_words = np.frombuffer(memoryview(queue.read_buffer(bufs["out"])),
                              dtype=np.uint32)
    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "r3": int(rb['registers'][3]) if hasattr(rb['registers'], '__len__') else None,
        "ram_word160": int(ram_out[160]),
        "ram_word164": int(ram_out[164]),
        "mmio_tile_h": int(mmio_out[TILE_H_WORD - MMIO_LO]),
        "fault_addr_word": int(mmio_out[7]),
        "out0": int(out_words[0]),
    }


def source_legs():
    twin = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    oracle = (REPO / "tools" / "glyph_isa_v2.py").read_text()
    wl = twin[twin.index("fn walk_ld"):twin.index("fn walk_st")]
    return {
        "L5_twin_walk_ld_tile_refs": wl.count("TILE"),
        "L5_oracle_ld_tile_confinement": "_tile_confinement" in oracle,
    }


def main():
    results = {"S_L5": source_legs()}

    # L1: tile armed, USER LD from out-of-tile word 164, exfil ST to
    # in-tile word 160. walk_ld has no tile consult -> LD succeeds;
    # the exfil ST then hits the ST-side E-K1 (BK-51 D3 shape).
    prog_l1 = """
    :__entry
    LDI r2 %d
    LD r3 r2
    LDI r2 %d
    ST r2 r3
    HALT
    """ % (OUT_TILE_WORD, IN_TILE_WORD)
    results["L1_twin_ld_out_of_tile"] = run_prog(
        prog_l1, dict(TILE_MMIO_SEED), ram_seed={OUT_TILE_WORD: CANARY})

    # L2: BK-51 standing D3 — in-tile ST still traps on the twin.
    prog_l2 = """
    :__entry
    LDI r5 4660
    LDI r6 %d
    ST r6 r5
    HALT
    """ % IN_TILE_WORD
    results["L2_twin_in_tile_st_traps"] = run_prog(
        prog_l2, dict(TILE_MMIO_SEED))

    # L3: in-tile LD control — value must reach r3 (PRT via out buffer
    # is not needed; we read the register straight from cpu state).
    prog_l3 = """
    :__entry
    LDI r2 %d
    LD r3 r2
    HALT
    """ % IN_TILE_WORD
    results["L3_twin_in_tile_ld_control"] = run_prog(
        prog_l3, dict(TILE_MMIO_SEED), ram_seed={IN_TILE_WORD: CANARY})

    # L4: oracle — the SAME L1 program through the landed spawn(tile=)
    # path at HEAD. 69a53298's fence must fire: EXIT_FAULT, fault 656.
    from tools.glyph_isa_v2 import (GlyphAssemblerV2, OpcodeMapV2)
    from tools.glyph_process import EXIT_FAULT, GlyphProcessTable
    asm = GlyphAssemblerV2(OpcodeMapV2())
    lines = ["LDI r2 %d" % OUT_TILE_WORD, "LD r3 r2",
             "LDI r2 %d" % IN_TILE_WORD, "ST r2 r3", "HALT"]
    img = asm.assemble(lines, width_instrs=8)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk51ld", tile=(TILE_ROW, TILE_COL,
                                                TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    cpu.memory[OUT_TILE_WORD] = CANARY
    rc = table.wait(pid)
    results["L4_oracle_same_program"] = {
        "rc": int(rc),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(cpu.fault_addr),
        "mode_final": int(cpu.mode),
        "expected_rc_EXIT_FAULT": int(EXIT_FAULT),
    }

    blob = json.dumps(results, indent=1, sort_keys=True)
    print(blob)
    print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
