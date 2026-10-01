"""BK-50 research probe (af3e, 2026-09-27): the WGSL MMIO-block write
door. BK-48/BK-49 measured walk_ld/walk_st's RAM path and the stack ops
fence-blind; the remaining unmeasured surface in this family is the
box_mmio sub-range itself.

STRUCTURAL (source, wgsl_glyph_isa_v2.py): in walk_st the MMIO-range
store at :443-444 executes BEFORE the E-K1 consult at :451 and is NOT
mode-gated, while the identical byte address via the oracle's single
consult (glyph_isa_v2.py:1041) DOES fire E-K1 unless a box covers it.
Also: addr_in_box (:463-476) compares only lo0..2/hi0..2 — an MMIO word
(8192+) can never be inside a guest box unless the guest rewrites the
config itself. So the twin's USER ST into the kernel MMIO block should
land clean where the oracle traps — and the block contains BOX0_HI
(word 8196) and KFAULT_PC (word 8193), i.e. the fence configuration and
the fault vector itself (a fence-self-disarm chain candidate).

Legs (verdicts from mmio/ram READBACK BYTES, never stdout):
  S1 (source): the :443 MMIO branch in walk_st precedes the :451
      addr_in_box consult and carries no mode check.
  D1 (on-device): seeded-USER ST to word 8196 (BOX0_HI byte 0x8030,
      byte 32784) — conviction: mmio[4] takes the value, mode stays
      USER, fault_addr_word == 0. Oracle twin expectation: E-K1 fires
      (byte 32784 outside any box), value refused — divergence.
  D2 (on-device control): seeded-USER ST to out-of-box RAM word 100 —
      E-K1 must fire (fault_addr_word == 400, mode -> SUPER, value
      refused). Proves the harness box arming is LIVE so D1's clean
      landing is a genuine door, not a dead harness.
  D3 (on-device disarm chain): D1's ST re-arms BOX0_HI=65536 via mmio,
      then a second run of the SAME program shape STs to RAM word 999
      (outside the original box) — conviction: value lands clean,
      mode USER, fault_addr 0: the confined task rewrote its own
      confinement THROUGH the legitimate walk_st door (compare BK-39's
      PARALLEL_ST self-grant on the oracle).

Run: python3 .builder_queue/probe_wgsl_mmio_door_af3e.py
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
BOX0_HI_WORD = 8196                  # byte 0x8030 = 32784
CANARY = 0x0ADF00D
DEST_RAM = 100                       # out-of-box RAM word for D2
DISARM_VAL = 65536                   # D3 BOX0_HI self-grant value
BOX_LO, BOX_HI = 1200, 1300          # armed box (byte addresses)

TARGET_BYTES = BOX0_HI_WORD * 4      # 32784


def source_legs():
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    body = src[src.index("fn walk_st"):src.index("fn addr_in_box")]
    mmio_br = body[body.index("BOX_MMIO_WORD_LO && addr <"):body.index("} else if (addr < RAM_WORDS)")]
    consult = body[body.index("addr_in_box(addr << 2u)"):]
    return {
        "S1_mmio_branch_mentions_mode": ("mode" in mmio_br or "is_super" in mmio_br),
        "S1_consult_present": "addr_in_box" in consult,
        "S1_mmio_branch_before_consult": (body.index("box_mmio[addr - BOX_MMIO_WORD_LO] = value;")
                                          < body.index("addr_in_box(addr << 2u)")),
    }


def run_prog(prog, mmio_seed, seed_mode=1, max_steps=80):
    """Bake+run one program on the real WGSL device harness (BK-48/49
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
    mmio[3] = BOX_LO            # BOX0_LO
    mmio[4] = BOX_HI            # BOX0_HI
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
        "ram_dest": int(ram_out[DEST_RAM]),
        "ram_word999": int(ram_out[999]),
        "mmio_box0_hi": int(mmio_out[4]),
        "mmio_kfault_pc": int(mmio_out[1]),
        "fault_addr_word": int(mmio_out[7]),
    }


def main():
    results = {"S1": source_legs()}

    # D1: seeded-USER ST of CANARY to word 8196 (BOX0_HI). The :443 branch
    # should take it BEFORE the :451 consult — no mode gate.
    prog_d1 = """
    :__entry
    LDI r5 %d
    LDI r6 %d
    ST r6 r5
    HALT
    """ % (CANARY, BOX0_HI_WORD)
    results["D1_user_st_mmio_box0hi"] = run_prog(prog_d1, {})

    # D2 control: seeded-USER ST to out-of-box RAM word 100 -> E-K1 must
    # fire (fault_addr_word == 400 = 100*4, mode -> SUPER, value refused).
    prog_d2 = """
    :__entry
    LDI r5 4660
    LDI r6 %d
    ST r6 r5
    HALT
    """ % DEST_RAM
    results["D2_user_st_oobox_ek1_control"] = run_prog(prog_d2, {})

    # D3 disarm chain: pre-seed nothing — run a two-ST program: first ST
    # writes DISARM_VAL to BOX0_HI (through the :443 door), second ST
    # writes word 999 (outside the original box). If the first landed,
    # addr_in_box now covers everything and the second lands clean.
    prog_d3 = """
    :__entry
    LDI r4 %d
    LDI r5 %d
    LDI r6 999
    LDI r7 %d
    ST r4 r5
    ST r6 r7
    HALT
    """ % (BOX0_HI_WORD, DISARM_VAL, CANARY)
    results["D3_self_grant_then_oob_st"] = run_prog(prog_d3, {})

    blob = json.dumps(results, indent=1, sort_keys=True)
    print(blob)
    print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
