"""BK-56 research probe (af3e, 2026-09-27): the WGSL MMIO-block READ
channel -- parity of the twin's ONLY gated memory read against the
oracle's completely ungated LD.

BK-50 measured walk_st's MMIO write door on-device but left the LD side
disclosed-not-measured: "walk_ld's MMIO branch (:361-363) is also
unmode-gated by source read -- likely a config-read channel, lower
severity, not measured here" (RESEARCH_wgsl_mmio_door_af3e.md:26).

STRUCTURAL (source read, wgsl_glyph_isa_v2.py:351-373, verified direct):
    fn walk_ld(addr: u32, is_super: bool) -> u32 {
        let pt_base = box_mmio[PAGE_TABLE_WORD - BOX_MMIO_WORD_LO];
        if (pt_base == 0u || (is_super && addr >= BOX_MMIO_WORD_LO && ...)) {
            if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
                return box_mmio[addr - BOX_MMIO_WORD_LO];
            }
    walk_ld is the twin's ONLY fence-gated read (E-K1 consults exist on
    stores only, oracle AND twin). The inner :361-363 branch carries no
    is_super/mode term; the outer condition's is_super leg is
    short-circuited when pt_base == 0 (paging disarmed -- the default on
    every probe/fleet image per BK-48/49/50). So a USER LD of a config
    word reads box_mmio. The oracle LD arm (glyph_isa_v2.py:826-933)
    consults NO fence on any path and keeps words 8192+ in plain
    self.memory, so the oracle's USER LD reads them too.
    PREDICTION: the read channel REPRODUCES on-device and is ORACLE
    PARITY (both engines leak the config block to USER reads) -- unlike
    the write side (BK-50: twin lands clean, oracle traps). Consequence
    for the BK-38..45 sequenced commit: kernel-write-only config words
    (BK-41 posture) leave the block USER-READABLE on BOTH engines; a
    read posture for the config block is a separate, explicit decision
    that landing round must make. Asymmetry with walk_st is structural:
    the twin's E-K1 write consult fires on out-of-box stores (BK-50 D2
    control, re-run here as D4), so the write door is at least
    recorded-and-vectored through the failure handler (BK-55: it is an
    escalation primitive); the read channel has no fault path AT ALL --
    it is silent on both engines.

Legs (verdicts from ram/mmio READBACK BYTES, never stdout):
  S1 (source): walk_ld's inner MMIO branch carries no mode term; the
      only mode term lives on the OUTER condition and pt_base == 0u
      short-circuits it; walk_ld is the twin's only gated read.
  D1 (on-device): seeded-USER LD of word 8196 (BOX0_HI, armed 1300),
      result STed to in-box word 310 -- conviction: ram[310] == 1300,
      mode stays USER, fault_addr_word == 0, clean halt.
  D2 (on-device, disclosure leg): seeded-USER LD of word 8193
      (KFAULT_PC, seeded 7) STed to in-box word 310 -- conviction:
      ram[310] == 7: the guest reads its own fault VECTOR, the exact
      value BK-55's hijack aims with.
  D3 (oracle-parity control): the D2 program on GlyphCPUv2 (config
      words seeded in plain self.memory, via the separate dbg harness
      with cpu.running=True set before stepping -- the probe's baked D2
      image carries a dead pixel at (28,0) after HALT rows, so the
      run()-form halts with opcode-None before the verdict reads; the
      dbg form steps past it and reads the conviction) -- conviction:
      memory[310] == 7, mode stays USER, faulted == False: PARITY, not
      divergence.
  D4 (harness control): seeded-USER ST of 4660 to out-of-box RAM word
      100 -- E-K1 must fire (fault_addr_word == 400, mode -> SUPER,
      ram[100] == 0). Proves box arming is LIVE so D1/D2's clean reads
      are the read channel, not a dead harness.

Run: python3 .builder_queue/probe_wgsl_mmio_read_af3e.py
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

MMIO_SPAN = 160
BOX0_HI_WORD = 8196                  # word 8196 -> mmio[4]
KFAULT_PC_WORD = 8193                # word 8193 -> mmio[1]
CANARY = 4660
RESULT_WORD = 310                    # in-box RAM word (box bytes [1200,1300)
                                     # = words [300,325); byte addr 1240)
BOX_LO, BOX_HI = 1200, 1300          # armed box (byte addresses)
DEST_RAM = 100                       # D4 out-of-box RAM word
KFAULT_SEED = 7


def source_legs():
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    body = src[src.index("fn walk_ld"):src.index("fn walk_st")]
    outer = body[body.index("if (pt_base == 0u"):body.index("// BK-2 fix")]
    inner = body[body.index("if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {\n            return box_mmio"):
                 body.index("// R1.4: oracle semantics")]
    # walk_ld is the twin's only fence-gated read: count consult sites in
    # the two walk fns (addr_in_box appears once, in walk_st's store path).
    walk_st_body = src[src.index("fn walk_st"):src.index("fn addr_in_box")]
    return {
        "S1_inner_mmio_branch_mentions_mode": ("mode" in inner or "is_super" in inner),
        "S1_outer_condition_has_is_super": "is_super" in outer,
        "S1_outer_condition_short_circuits_on_pt0": "pt_base == 0u ||" in outer,
        "S1_addr_in_box_calls_in_walk_ld": body.count("addr_in_box"),
        "S1_addr_in_box_calls_in_walk_st": walk_st_body.count("addr_in_box"),
    }


def run_wgsl(prog, mmio_seed, seed_mode=1, max_steps=80):
    """Real WGSL device harness (BK-50 probe shape verbatim: run_wgsl's
    real buffers + build_shader(OpcodeMapV2()), probe-only seeded
    cpu.mode + mmio)."""
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
        mmio[k] = v
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
        "ram_result_word": int(ram_out[RESULT_WORD]),
        "ram_dest": int(ram_out[DEST_RAM]),
        "mmio_box0_hi": int(mmio_out[4]),
        "mmio_kfault_pc": int(mmio_out[1]),
        "fault_addr_word": int(mmio_out[7]),
    }


def run_oracle(prog, mem_seeds, seed_mode=1, max_steps=80):
    """Oracle-parity control: same program on GlyphCPUv2.step with the
    config block seeded in plain self.memory (the oracle's storage for
    words 8192+)."""
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        img = GlyphRunner(png).image

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = np.zeros(16384, dtype=np.uint64).tolist()
    for k, v in mem_seeds.items():
        cpu.memory[k] = v
    cpu.mode = seed_mode
    steps = 0
    while cpu.running and steps < max_steps:
        cpu.step(img)
        steps += 1
    return {
        "halted": not cpu.running,
        "steps": steps,
        "mode_final": int(cpu.mode),
        "ram_result_word": int(cpu.memory[RESULT_WORD]),
        "ram_dest": int(cpu.memory[DEST_RAM]),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(cpu.fault_addr),
    }


def main():
    results = {"S1": source_legs()}

    # D1: seeded-USER LD of BOX0_HI (word 8196, armed 1300) -> in-box ST.
    prog_d1 = """
    :__entry
    LDI r6 %d
    LD r5 r6
    LDI r7 %d
    ST r7 r5
    HALT
    """ % (BOX0_HI_WORD, RESULT_WORD)
    results["D1_user_ld_mmio_box0hi"] = run_wgsl(prog_d1, {})

    # D2: seeded-USER LD of KFAULT_PC (word 8193, seeded 7) -> in-box ST.
    # The guest reads its own fault vector (BK-55's aiming value).
    prog_d2 = """
    :__entry
    LDI r6 %d
    LD r5 r6
    LDI r7 %d
    ST r7 r5
    HALT
    """ % (KFAULT_PC_WORD, RESULT_WORD)
    results["D2_user_ld_mmio_kfault_pc"] = run_wgsl(
        prog_d2, {1: KFAULT_SEED})

    # D3 oracle-parity control: same program, config words in plain RAM.
    results["D3_oracle_parity_same_program"] = run_oracle(
        prog_d2, {KFAULT_PC_WORD: KFAULT_SEED,
                  BOX0_HI_WORD - 1: BOX_LO, BOX0_HI_WORD: BOX_HI})

    # D4 harness control: USER ST to out-of-box word 100 -> E-K1 fires.
    prog_d4 = """
    :__entry
    LDI r5 %d
    LDI r6 %d
    ST r6 r5
    HALT
    """ % (CANARY, DEST_RAM)
    results["D4_user_st_oobox_ek1_control"] = run_wgsl(prog_d4, {})

    blob = json.dumps(results, indent=1, sort_keys=True)
    print(blob)
    print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
