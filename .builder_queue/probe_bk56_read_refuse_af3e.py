"""BK-56 RED-leg probe (af3e, 2026-10-01): the CURRENT shape vs the
DIRECTIVE_BK56_MMIO_READ_POSTURE.md refusal semantics.

Post-69a53298 both engines return 0 SILENTLY on a USER config read
(BK-38 gate F1 asserts silent-0). The directive DECIDES the loud posture:
faulted=True, fault_reason mmio_config_read_refused, running=False,
destination UNWRITTEN, NO vector (BK-75 KFC-L6). This probe measures the
gap so the landing's RED-first is honest at today's HEAD (f1588fbe).

Legs (verdicts from register/memory readback, never stdout):
  T1 (twin, on-device): seeded-USER LD of KFAULT_PC (8193, seeded 7) --
      conviction: machine REFUSES (mode SUPER, stopped, fault_addr ==
      8193*4) AND ram[310] == 0 (result word never written).
      TODAY: silent-0 (halted clean, mode USER, fault 0, r5->ram[310]==0).
  T2 (twin, on-device): seeded-USER LD of BOX0_HI (8196, armed 1300) --
      same conviction. TODAY: silent-0 with the value 0 (block reads 0).
  T3 (twin boundary control): USER LD of SYS_A0 (8205, seeded 31337)
      STILL LANDS in r5 (data words stay guest-readable, BK-76 §0).
  O1 (oracle): seeded-USER LD of 8193 -- conviction: faulted=True,
      fault_reason startswith mmio_config_read_refused, running=False,
      registers[rd] unchanged (0), NO vectoring (kf stays 0 -> loud halt).
      TODAY: silent-0, faulted False, clean halt.
  O2 (oracle boundary control): USER LD of SYS_A0 8205 lands.

Run: python3 .builder_queue/probe_bk56_read_refuse_af3e.py
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
IDX = lambda w: w - 8192  # noqa: E731
KFAULT_PC_WORD = 8193
BOX0_HI_WORD = 8196
SYS_A0_WORD = 8205
RESULT_WORD = 310
KFAULT_SEED = 7
BOX_LO, BOX_HI = 1200, 1300
SYS_A0_SEED = 31337

PROG_LD_ST = (
    ":__entry\n"
    "LDI r6 %d\n"      # config word
    "LD r5 r6\n"
    "LDI r7 %d\n"      # result word
    "ST r7 r5\n"
    "HALT\n")

PROG_LD_ONLY = (
    ":__entry\n"
    "LDI r6 %d\n"
    "LD r5 r6\n"
    "HALT\n")


def run_wgsl(prog, mmio_seed, seed_mode=1, max_steps=80):
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
    mmio[IDX(BOX0_HI_WORD - 1)] = BOX_LO
    mmio[IDX(BOX0_HI_WORD)] = BOX_HI
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
        "mmio_kfault_pc": int(mmio_out[IDX(KFAULT_PC_WORD)]),
        "fault_addr_word": int(mmio_out[7]),
    }


def run_oracle(prog, mem_seeds, seed_mode=1, max_steps=80):
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
    cpu.pc = (0, 0)
    cpu.running = True   # ctor default False; step() runs only while True
    steps = 0
    while cpu.running and steps < max_steps:
        cpu.step(img)
        steps += 1
    return {
        "halted": not cpu.running,
        "steps": steps,
        "mode_final": int(cpu.mode),
        "ram_result_word": int(cpu.memory[RESULT_WORD]),
        "r5_final": int(cpu.registers[5]),
        "faulted": bool(cpu.faulted),
        "fault_addr": int(cpu.fault_addr),
        "fault_reason": str(cpu.fault_reason),
        "halt_reason": str(cpu.halt_reason),
    }


def main():
    results = {}
    # T1: twin USER LD of KFAULT_PC + result ST.
    results["T1_twin_user_ld_kfault"] = run_wgsl(
        PROG_LD_ST % (KFAULT_PC_WORD, RESULT_WORD), {IDX(KFAULT_PC_WORD): KFAULT_SEED})
    # T2: twin USER LD of BOX0_HI + result ST.
    results["T2_twin_user_ld_box0hi"] = run_wgsl(
        PROG_LD_ST % (BOX0_HI_WORD, RESULT_WORD), {})
    # T3: twin boundary control -- SYS_A0 must still land.
    results["T3_twin_boundary_sysA0"] = run_wgsl(
        PROG_LD_ST % (SYS_A0_WORD, RESULT_WORD), {IDX(SYS_A0_WORD): SYS_A0_SEED})
    # O1: oracle USER LD of KFAULT_PC (LD-only: rd stays observable).
    results["O1_oracle_user_ld_kfault"] = run_oracle(
        PROG_LD_ONLY % KFAULT_PC_WORD, {KFAULT_PC_WORD: KFAULT_SEED})
    # O2: oracle boundary control.
    results["O2_oracle_boundary_sysA0"] = run_oracle(
        PROG_LD_ONLY % SYS_A0_WORD,
        {SYS_A0_WORD: SYS_A0_SEED, BOX0_HI_WORD - 1: BOX_LO, BOX0_HI_WORD: BOX_HI})
    blob = json.dumps(results, indent=1, sort_keys=True)
    print(blob)
    print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
