#!/usr/bin/env python3
"""BK-49 twin-side stack-path fence gate: PUSH/POP/CALL/RET/CALLR must
consult the E-K1 fence (addr_in_box — boxes + the GO-2 tile) on the stack
address they touch, bitwise-twin of walk_st's consult shape. Previously the
stack arms routed through mem_write/mem_read (image plane) with ZERO
consults, USER-clean (measured: .builder_queue/probe_wgsl_stack_fence_af3e.py
at HEAD 8f5f2e47 — out-of-box PUSH lands, POP reads, mode stays USER).

Landing posture (the row's option 1, decided at this gate): per-op consult,
NOT a consult inside mem_write/mem_read — a shared-site consult would
double-fence the paged frame arms (BK-66-twin's post-translation consult
already owns the paged path) and would change every non-stack caller.
Kernel KJMP/entry stacks are SUPER-exempt (same `is_super ||` shape as
walk_st), so the cooperative kernel is unaffected; a USER task's lawful
stack lives inside its kernel-programmed box (BOX2 = its stack page per
glyph_isa_v2.py:53-54) or its armed tile (addr_in_box's BK-51 tile branch).

Legs (device verdicts from RAM + image + mmio READBACK, never stdout):
  L1  seeded-USER PUSH to an out-of-box stack address -> refused: nothing
      lands at the image word, r31 UNCHANGED (consult runs BEFORE the
      pre-decrement), FAULT_ADDR == sp*4, mode -> SUPER. RED pre-fix
      (canary landed at 499, r31 decremented, fault 0).
  L2  seeded-USER POP from an out-of-box address -> refused: the pre-painted
      image canary does NOT enter rd, r31 unchanged, FAULT_ADDR == sp*4.
      RED pre-fix (r5 == canary).
  L3  in-box controls: armed box [1200,1300) — in-box PUSH lands (image
      word 323 == canary, r31 == 323, mode USER, fault 0); in-box POP
      returns the pre-painted canary (r5 == canary, r31 == 325).
  L4  E-K1 ST control (rot-guard): plain USER ST to out-of-box word 100
      still traps (fault 400, refused) — the fix must not touch walk_st.
  L5  CALL posture (same class): out-of-box CALL's return-address push is
      refused (E-K1, r31 unchanged, no jump — the fault vector owns next_pc);
      in-box CALL/RET control runs a real subroutine roundtrip green.
  L6  non-vacuity: stack_fence_fault neutered to `return false` in a
      TEMP-COPY module -> L1's program reproduces the PRE-FIX shape
      (canary lands out-of-box). Real tree md5-pinned before/after.
  L7  family subprocess leg: BK-48 twin gates + BK-38 oracle gate green
      (never weaken a live guard).

RED-first at landing time: this gate run against the UNFIXED tree failed
L1/L2/L5 with the measured pre-fix shapes (pasted in the landing commit).
2 pinned GREEN runs byte-identical.
"""
import hashlib
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

CANARY = 0x0ADF00D
MMIO_LO = 8192
BOX_LO, BOX_HI = 1200, 1300           # byte range -> words 300..324
BOX0_LO_WORD, BOX0_HI_WORD = 8195, 8196
OUT_SP_WORD = 500                     # byte 2000: outside the box
IN_SP_WORD = 324                      # byte 1296: inside [1200,1300)
IN_PUSH_WORD = 323                    # in-box PUSH landing (sp-1)
OUT_PUSH_WORD = 499                   # out-of-box PUSH landing
FAULT_ADDR_MMIO_IDX = 7               # FAULT_ADDR_WORD 8199 - 8192

BOX_SEED = {BOX0_LO_WORD - MMIO_LO: BOX_LO, BOX0_HI_WORD - MMIO_LO: BOX_HI}

PROG_PUSH = """:__entry
LDI r5 %d
LDI r31 %d
PUSH r5
HALT
"""

PROG_POP = """:__entry
LDI r31 %d
POP r5
HALT
"""

PROG_ST = """:__entry
LDI r5 %d
LDI r15 100
ST r15 r5
HALT
"""

PROG_CALL_OUT = """:__entry
LDI r31 %d
CALL 2,0
HALT
"""  # CALL target = instruction 2 of the baked stream; the PUSH (return-addr
     # store) must refuse BEFORE the jump takes effect on any verdict word.

PROG_CALLRET_IN = """:__entry
LDI r31 %d
LDI r10 7
CALL 5,0
PRT r10
HALT
LDI r10 9
RET
"""  # CALL 5,0 -> instruction index 5 (LDI r10 9 / RET subroutine)


def run_stack_leg(name, text, mmio_seed, seed_mode=1, max_steps=80,
                  ram_seed=None, img_prepaint=None):
    """Run one program on the real WGSL device (BK-48/49/50/51 harness
    shape: run_wgsl's real buffers + build_shader(OpcodeMapV2()), seeded
    cpu.mode + mmio words). Stack ops land on the IMAGE plane, so verdicts
    read the img buffer too. No stdout verdicts."""
    import wgpu, wgpu.utils  # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / f"{name}.png"
        bake_image(text, cols_instrs=8, out_path=png)
        image = GlyphRunner(png).image

    if img_prepaint:
        for word, val in img_prepaint.items():
            h, w, _ = image.shape
            idx = word % (h * w)
            image[idx // w, idx % w] = (
                (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)

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
        for w_, v in ram_seed.items():
            ram[w_] = v
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
        {'binding': 0, 'resource': {'buffer': bufs["img"], 'offset': 0,
                                    'size': rgba.nbytes}},
        {'binding': 1, 'resource': {'buffer': bufs["cpu"], 'offset': 0,
                                    'size': cpu_state.nbytes}},
        {'binding': 2, 'resource': {'buffer': bufs["out"], 'offset': 0,
                                    'size': 256}},
        {'binding': 3, 'resource': {'buffer': bufs["u"], 'offset': 0,
                                    'size': bufs["u"].size}},
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
    img_out = np.frombuffer(queue.read_buffer(bufs["img"]),
                            dtype=np.uint32).reshape(n_pixels, 4)

    def img_word(word):
        h, w, _ = image.shape
        idx = word % (h * w)
        p = img_out[idx]
        return int((int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2]))

    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "r31": int(rb['registers'][31]),
        "r5": int(rb['registers'][5]),
        "r10": int(rb['registers'][10]),
        "output": [int(w) for w in np.frombuffer(
            queue.read_buffer(bufs["out"]), dtype=np.uint32) if w],
        "img_word499": img_word(499),
        "img_word323": img_word(323),
        "img_word324": img_word(324),
        "ram_word100": int(np.frombuffer(
            memoryview(queue.read_buffer(bufs["ram"])),
            dtype=np.uint32)[100]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_MMIO_IDX]),
    }


def _real_module_md5():
    return hashlib.md5((REPO / "tools" / "wgsl_glyph_isa_v2.py")
                       .read_bytes()).hexdigest()


# ---------------------------------------------------------------- L1
def leg_l1_push_out_of_box_refused():
    rec = run_stack_leg("L1push", PROG_PUSH % (CANARY, OUT_SP_WORD),
                        dict(BOX_SEED))
    assert rec["img_word499"] != CANARY, (
        f"BK49-L1 RED (defect live): out-of-box PUSH LANDED at image word "
        f"499 ({rec['img_word499']:#x}) — the stack path is fence-blind; "
        f"PUSH must consult addr_in_box on its landing word")
    assert rec["r31"] == OUT_SP_WORD, (
        f"BK49-L1 RED: r31 moved on a refused PUSH "
        f"(r31={rec['r31']}) — the consult must run BEFORE the "
        f"pre-decrement so a refused op mutates nothing")
    assert rec["fault_addr_word"] == OUT_PUSH_WORD * 4, (
        f"BK49-L1 RED: E-K1 did not judge the stack landing word "
        f"(fault {rec['fault_addr_word']}, expected {OUT_PUSH_WORD * 4})")
    assert rec["mode_final"] == 0, (
        f"BK49-L1 RED: mode not SUPER after refusal "
        f"(mode {rec['mode_final']})")
    return ("L1 ok: out-of-box PUSH refused (nothing at 499, r31 untouched, "
            "fault %d, SUPER)" % rec["fault_addr_word"])


# ---------------------------------------------------------------- L2
def leg_l2_pop_out_of_box_refused():
    rec = run_stack_leg("L2pop", PROG_POP % (OUT_SP_WORD,), dict(BOX_SEED),
                        img_prepaint={500: CANARY})
    assert rec["r5"] != CANARY, (
        f"BK49-L2 RED (defect live): out-of-box POP delivered the "
        f"pre-painted canary into r5 ({rec['r5']:#x}) — cross-fence stack "
        f"READ; POP must consult the fence before mem_read")
    assert rec["r31"] == OUT_SP_WORD, (
        f"BK49-L2 RED: r31 incremented on a refused POP (r31={rec['r31']})")
    assert rec["fault_addr_word"] == OUT_SP_WORD * 4, (
        f"BK49-L2 RED: fault judged the wrong word "
        f"({rec['fault_addr_word']}, expected {OUT_SP_WORD * 4})")
    assert rec["mode_final"] == 0, (
        f"BK49-L2 RED: mode not SUPER (mode {rec['mode_final']})")
    return ("L2 ok: out-of-box POP refused (canary not delivered, r31 "
            "untouched, fault %d)" % rec["fault_addr_word"])


# ---------------------------------------------------------------- L3
def leg_l3_in_box_controls():
    rec_push = run_stack_leg("L3push", PROG_PUSH % (CANARY, IN_SP_WORD),
                             dict(BOX_SEED))
    assert rec_push["fault_addr_word"] == 0 and rec_push["mode_final"] == 1, (
        f"BK49-L3 RED: lawful in-box PUSH was fenced "
        f"(fault {rec_push['fault_addr_word']}, mode "
        f"{rec_push['mode_final']}) — over-confinement")
    assert rec_push["img_word323"] == CANARY and rec_push["r31"] == IN_PUSH_WORD, (
        f"BK49-L3 RED: in-box PUSH did not land "
        f"(word323={rec_push['img_word323']:#x}, r31={rec_push['r31']})")
    rec_pop = run_stack_leg("L3pop", PROG_POP % (IN_SP_WORD,), dict(BOX_SEED),
                            img_prepaint={IN_SP_WORD: CANARY})
    assert rec_pop["fault_addr_word"] == 0 and rec_pop["mode_final"] == 1, (
        f"BK49-L3 RED: lawful in-box POP was fenced "
        f"(fault {rec_pop['fault_addr_word']}, mode {rec_pop['mode_final']})")
    assert rec_pop["r5"] == CANARY and rec_pop["r31"] == IN_SP_WORD + 1, (
        f"BK49-L3 RED: in-box POP wrong (r5={rec_pop['r5']:#x}, "
        f"r31={rec_pop['r31']})")
    return ("L3 ok: in-box PUSH lands + in-box POP returns (lawful stack "
            "work preserved, both clean USER)")


# ---------------------------------------------------------------- L4
def leg_l4_ek1_st_rotguard():
    rec = run_stack_leg("L4st", PROG_ST % CANARY, dict(BOX_SEED))
    assert rec["fault_addr_word"] == 400 and rec["ram_word100"] == 0, (
        f"BK49-L4 RED: walk_st's live E-K1 control broke "
        f"(fault {rec['fault_addr_word']}, word100={rec['ram_word100']:#x}) "
        f"— never weaken a live guard")
    return "L4 ok: plain out-of-box ST still traps (fault 400, refused)"


# ---------------------------------------------------------------- L5
def leg_l5_call_posture():
    rec = run_stack_leg("L5call", PROG_CALL_OUT % (OUT_SP_WORD,),
                        dict(BOX_SEED))
    assert rec["fault_addr_word"] == OUT_PUSH_WORD * 4, (
        f"BK49-L5 RED: out-of-box CALL's return-address push was not "
        f"refused at the stack word (fault {rec['fault_addr_word']}, "
        f"expected {OUT_PUSH_WORD * 4})")
    assert rec["r31"] == OUT_SP_WORD, (
        f"BK49-L5 RED: CALL pushed anyway (r31={rec['r31']})")
    rec_rt = run_stack_leg("L5callret", PROG_CALLRET_IN % (IN_SP_WORD,),
                           dict(BOX_SEED))
    assert rec_rt["fault_addr_word"] == 0 and rec_rt["mode_final"] == 1, (
        f"BK49-L5 RED: lawful in-box CALL/RET roundtrip fenced "
        f"(fault {rec_rt['fault_addr_word']}, mode {rec_rt['mode_final']})")
    assert rec_rt["output"] == [9], (
        f"BK49-L5 RED: in-box CALL/RET roundtrip wrong "
        f"(output {rec_rt['output']}, expected [9] — subroutine overwrote "
        f"r10 then returned)")
    return ("L5 ok: out-of-box CALL push refused at the stack word; in-box "
            "CALL/RET roundtrip green (output [9])")


# ---------------------------------------------------------------- L6
def leg_l6_nonvacuity_neuter():
    """Neuter stack_fence_fault in a TEMP COPY -> L1's program must
    reproduce the PRE-FIX shape (canary lands out-of-box). Real tree
    md5-pinned."""
    real = REPO / "tools" / "wgsl_glyph_isa_v2.py"
    before = _real_module_md5()
    src = real.read_text()
    needle = "    return !addr_in_box(sp_word << 2u);"
    assert needle in src, "consult helper not found — gate must pin its target"
    neutered = src.replace(needle,
                           "    return false;  // NEUTERED for non-vacuity",
                           1)
    assert neutered != src
    with tempfile.TemporaryDirectory() as td:
        mod_dir = Path(td) / "tools"
        mod_dir.mkdir()
        (mod_dir / "wgsl_glyph_isa_v2.py").write_text(neutered)
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk49", mod_dir / "wgsl_glyph_isa_v2.py")
        saved_path = sys.path[:]
        try:
            sys.path.insert(0, str(mod_dir.parent))
            for stale in [m for m in list(sys.modules)
                          if m == "wgsl_neutered_bk49"]:
                del sys.modules[stale]
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            import tools.wgsl_glyph_isa_v2 as real_wgsl
            orig_build = real_wgsl.build_shader
            real_wgsl.build_shader = mod.build_shader
            try:
                rec = run_stack_leg(
                    "L6", PROG_PUSH % (CANARY, OUT_SP_WORD), dict(BOX_SEED))
            finally:
                real_wgsl.build_shader = orig_build
            assert rec["img_word499"] == CANARY, (
                f"BK49-L6 non-vacuity RED: even with the stack consult "
                f"neutered the out-of-box PUSH did not land "
                f"(word499={rec['img_word499']:#x}) — the gate is dead, "
                f"not the defect fixed")
        finally:
            sys.path[:] = saved_path
            after = _real_module_md5()
            assert after == before, (
                f"real WGSL module changed during L6 ({before} -> {after})")
    return ("L6 ok: neutering the consult re-delivers the canary "
            "(gate discriminating; real tree untouched)")


# ---------------------------------------------------------------- L7
def leg_l7_family():
    for gate in ("test_bk48_wgsl_fence.py",
                 "test_bk48_wgsl_ld_tile_fence.py",
                 "test_bk51_wgsl_tile_fence.py",
                 "test_bk38_ld_fence.py"):
        path = HERE / gate
        if not path.exists():
            continue  # family gate not landed on this tree; not this row's gap
        r = subprocess.run([sys.executable, str(path)],
                           capture_output=True, timeout=900)
        out = r.stdout.decode() + r.stderr.decode()
        assert r.returncode == 0, (
            f"BK49-L7 RED: family gate {gate} failed (rc={r.returncode}):\n"
            f"{out[-1500:]}")
    return "L7 ok: family gates green"


def main():
    msgs = [
        leg_l1_push_out_of_box_refused(),
        leg_l2_pop_out_of_box_refused(),
        leg_l3_in_box_controls(),
        leg_l4_ek1_st_rotguard(),
        leg_l5_call_posture(),
        leg_l6_nonvacuity_neuter(),
        leg_l7_family(),
    ]
    for m in msgs:
        print(m)


def test_l1_push_out_of_box_refused():
    leg_l1_push_out_of_box_refused()


def test_l2_pop_out_of_box_refused():
    leg_l2_pop_out_of_box_refused()


def test_l3_in_box_controls():
    leg_l3_in_box_controls()


def test_l4_ek1_st_rotguard():
    leg_l4_ek1_st_rotguard()


def test_l5_call_posture():
    leg_l5_call_posture()


def test_l6_nonvacuity_neuter():
    leg_l6_nonvacuity_neuter()


def test_l7_family_gates():
    leg_l7_family()


if __name__ == "__main__":
    main()
