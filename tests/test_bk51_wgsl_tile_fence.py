#!/usr/bin/env python3
"""BK-51 twin-side GO-2 tile-fence gate: the WGSL walker's addr_in_box must
carry the 2D tile predicate (bitwise mirror of glyph_isa_v2.py:734-747), so
a tile-armed USER task's LAWFUL in-tile stores LAND (oracle parity) and
out-of-tile stores still trap E-K1.

RED-first (measured at the pre-fix tree, probe_wgsl_tile_fence_af3e.py
results md5 9701e0d40eba3fd3f9ce12b6dd6c4d89): D3 in-tile ST faulted 640,
refused, mode -> SUPER on the twin while the oracle lands it clean — the
twin denied EVERY tile-confined GPU store. Post-fix: D3 lands (fault 0,
mode USER, canary at word 160), D1 out-of-tile still traps (fault 656).

Legs (device verdicts from ram readback + fault words, never stdout):
  L1a tile-armed USER in-tile ST LANDS (word 160, mode stays USER, no
      fault) — the oracle-parity leg, RED pre-fix.
  L1b tile-armed USER out-of-tile ST traps (fault_addr == 164*4, mode ->
      SUPER) — the fence-still-live leg.
  L2  D1/D2 controls: box-only arming still fences (fault 400); tile
      arming with boxes unset leaves word 100 refused.
  L3  non-vacuity: the L1a/L1b programs differ ONLY in the target word
      (160 vs 164); under the pre-fix module (tile term removed in a
      TEMP COPY of the shader source) L1a's program DENIES the store —
      the gate fires against the live defect. Real tree md5-pinned.
  L4  family subprocess leg: BK-48 twin-fence + BK-64 paged-flag gates
      green (the fence family on this tree).
  (BK-51 row's L4 — BK-50 MMIO-door posture for the TILE words — is the
  sequenced-commit posture decision (BK-41/50), NOT this gate: this fix
  adds the read-side predicate only; D4's door composition is disclosed
  in the ledger, unchanged by this landing.)
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
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * 32 + TILE_COL          # 160 (W_MEM = 32 words/row)
OUT_TILE_WORD = IN_TILE_WORD + TILE_W            # 164 (first word outside)
TILE_ROW_WORD, TILE_COL_WORD = 8280, 8281
TILE_H_WORD, TILE_W_WORD = 8282, 8283
MMIO_LO = 8192
BOX_LO, BOX_HI = 1200, 1300
BOX0_LO_WORD, BOX0_HI_WORD = 8195, 8196

PROG_ST = """:__entry
LDI r5 %d
LDI r6 %d
ST r6 r5
HALT
"""


def run_twin_seeded(name, text, mmio_seed, seed_mode=1, max_steps=80):
    """Run one program on the real WGSL device with probe-only seeds
    (BK-48/49/50/51 harness shape: run_wgsl's real buffers +
    build_shader(OpcodeMapV2()), seeded cpu.mode + mmio tile/box words).
    Verdicts come from RAM + mmio READBACK, never stdout."""
    import wgpu, wgpu.utils  # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / f"{name}.png"
        bake_image(text, cols_instrs=8, out_path=png)
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
    ram_out = np.frombuffer(memoryview(queue.read_buffer(bufs["ram"])),
                            dtype=np.uint32)
    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "ram_word160": int(ram_out[160]),
        "ram_word164": int(ram_out[164]),
        "ram_word100": int(ram_out[100]),
        "fault_addr_word": int(mmio_out[7]),
        "kfault_pc": int(mmio_out[1]),
    }


TILE_MMIO = {TILE_ROW_WORD - MMIO_LO: TILE_ROW,
             TILE_COL_WORD - MMIO_LO: TILE_COL,
             TILE_H_WORD - MMIO_LO: TILE_H,
             TILE_W_WORD - MMIO_LO: TILE_W}


def leg_l1a_in_tile_st_lands():
    rec = run_twin_seeded("L1a", PROG_ST % (CANARY, IN_TILE_WORD),
                          dict(TILE_MMIO))
    assert rec["fault_addr_word"] == 0 and rec["mode_final"] == 1, (
        f"BK51-L1a RED (defect live): tile-armed USER in-tile ST TRAPPED "
        f"(fault {rec['fault_addr_word']}, mode {rec['mode_final']}) — the "
        f"twin denies the lawful store; addr_in_box must admit the armed "
        f"tile (oracle parity, glyph_isa_v2.py:734-747)")
    assert rec["ram_word160"] == CANARY, (
        f"BK51-L1a RED: in-tile store did not land (word160="
        f"{rec['ram_word160']:#x})")
    return ("L1a ok: in-tile ST lands (word160=%#x, mode USER, no fault)"
            % rec["ram_word160"])


def leg_l1b_out_of_tile_st_traps():
    rec = run_twin_seeded("L1b", PROG_ST % (CANARY, OUT_TILE_WORD),
                          dict(TILE_MMIO))
    assert rec["fault_addr_word"] == OUT_TILE_WORD * 4, (
        f"BK51-L1b RED: out-of-tile ST did not trap E-K1 (fault_addr="
        f"{rec['fault_addr_word']}, expected {OUT_TILE_WORD * 4}) — the "
        f"tile predicate must not disarm the fence")
    assert rec["mode_final"] == 0 and rec["ram_word164"] == 0, (
        f"BK51-L1b RED: out-of-tile canary landed or mode not SUPER "
        f"(word164={rec['ram_word164']:#x}, mode {rec['mode_final']})")
    return "L1b ok: out-of-tile ST traps (fault %d, mode SUPER)" % (
        rec["fault_addr_word"],)


def leg_l2_box_controls():
    # Box-only arming (no tile): out-of-box word 100 refused, fault 400.
    rec = run_twin_seeded("L2a", PROG_ST % (CANARY, 100),
                          {BOX0_LO_WORD - MMIO_LO: BOX_LO,
                           BOX0_HI_WORD - MMIO_LO: BOX_HI})
    assert rec["fault_addr_word"] == 400 and rec["ram_word100"] == 0, (
        f"BK51-L2 RED: box-only control broke (fault "
        f"{rec['fault_addr_word']}, word100={rec['ram_word100']:#x}) — "
        f"the fix must not weaken the live box consult")
    # Tile armed, BOX0-2 unset: out-of-tile word 100 refused too (the
    # tile term ADDS admission, it does not remove the default deny).
    rec2 = run_twin_seeded("L2b", PROG_ST % (CANARY, 100), dict(TILE_MMIO))
    assert rec2["fault_addr_word"] == 400 and rec2["ram_word100"] == 0, (
        f"BK51-L2 RED: tile-armed default-deny broke (fault "
        f"{rec2['fault_addr_word']}, word100={rec2['ram_word100']:#x})")
    return "L2 ok: box consult live + tile arming keeps default deny"


def _real_module_md5():
    return hashlib.md5((REPO / "tools" / "wgsl_glyph_isa_v2.py")
                       .read_bytes()).hexdigest()


def leg_l3_nonvacuity_neuter():
    """Neuter the tile term in a TEMP COPY of the WGSL module (tile branch
    removed -> the pre-fix addr_in_box) -> L1a's program must TRAP again
    (the gate fires against the live defect). Real tree md5-pinned."""
    real = REPO / "tools" / "wgsl_glyph_isa_v2.py"
    before = _real_module_md5()
    src = real.read_text()
    neutered = src.replace(
        """    let tile_h = box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO];
    if (tile_h != 0u) {
        let tile_w = box_mmio[TILE_W_WORD - BOX_MMIO_WORD_LO];
        let trow = box_mmio[TILE_ROW_WORD - BOX_MMIO_WORD_LO];
        let tcol = box_mmio[TILE_COL_WORD - BOX_MMIO_WORD_LO];
        let word = byte_addr >> 2u;
        let row = word / W_MEM;
        let col = word % W_MEM;
        if (trow <= row && row < trow + tile_h && tcol <= col && col < tcol + tile_w) {
            return true;
        }
    }
""", "", 1)
    assert neutered != src, "neuter target (tile branch) not found"
    with tempfile.TemporaryDirectory() as td:
        mod_dir = Path(td) / "tools"
        mod_dir.mkdir()
        (mod_dir / "wgsl_glyph_isa_v2.py").write_text(neutered)
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk51", mod_dir / "wgsl_glyph_isa_v2.py")
        saved_path = sys.path[:]
        try:
            sys.path.insert(0, str(mod_dir.parent))
            for stale in [m for m in list(sys.modules)
                          if m == "wgsl_neutered_bk51"]:
                del sys.modules[stale]
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            import tools.wgsl_glyph_isa_v2 as real_wgsl
            orig_build = real_wgsl.build_shader
            real_wgsl.build_shader = mod.build_shader
            try:
                rec = run_twin_seeded(
                    "L3", PROG_ST % (CANARY, IN_TILE_WORD), dict(TILE_MMIO))
            finally:
                real_wgsl.build_shader = orig_build
            assert rec["fault_addr_word"] == IN_TILE_WORD * 4, (
                f"BK51-L3 non-vacuity RED: even with the tile term removed "
                f"the in-tile store did not trap (fault "
                f"{rec['fault_addr_word']}) — the gate is dead, not the "
                f"defect fixed")
        finally:
            sys.path[:] = saved_path
            after = _real_module_md5()
            assert after == before, (
                f"real WGSL module changed during L3 ({before} -> {after})")
    return ("L3 ok: removing the tile term re-traps the in-tile store "
            "(gate discriminating; real tree untouched)")


def leg_l4_family():
    """Family subprocess leg: the fence family's twin-side + paged gates
    must stay green on this tree (never weaken a live guard)."""
    for gate, expect in (("test_bk48_wgsl_fence.py", None),
                         ("test_bk64_pte_flag_paged.py", None)):
        path = HERE / gate
        if not path.exists():
            continue  # family gate not landed on this tree; not this row's gap
        r = subprocess.run(
            [sys.executable, str(path)], capture_output=True, timeout=900)
        out = r.stdout.decode() + r.stderr.decode()
        assert r.returncode == 0 and "Error" not in out.split("ok")[0][:200], (
            f"BK51-L4 RED: family gate {gate} failed (rc={r.returncode}):\n"
            f"{out[-1500:]}")
    return "L4 ok: family gates green"


def main():
    msgs = [
        leg_l1a_in_tile_st_lands(),
        leg_l1b_out_of_tile_st_traps(),
        leg_l2_box_controls(),
        leg_l3_nonvacuity_neuter(),
        leg_l4_family(),
    ]
    for m in msgs:
        print(m)


def test_l1a_in_tile_st_lands():
    leg_l1a_in_tile_st_lands()


def test_l1b_out_of_tile_st_traps():
    leg_l1b_out_of_tile_st_traps()


def test_l2_box_controls_stay_green():
    leg_l2_box_controls()


def test_l3_neutered_tile_term_retraps():
    leg_l3_nonvacuity_neuter()


def test_l4_family_gates():
    leg_l4_family()


if __name__ == "__main__":
    main()
