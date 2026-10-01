#!/usr/bin/env python3
"""BK-50-twin gate: kernel-write-only CONFIG words at the WGSL walk_st
MMIO door (twin parity for the landed BK-41 oracle posture).

Oracle precedent (landed 65c1c46b, tests/test_bk41_ksys_fence.py 10/10):
the :968 SUPER MMIO-window exemption ST arm and the SUPER post-USER
PARALLEL_ST arm refuse stores to _BK41_LOCKED_WORDS = {8193 KFAULT_PC,
8194 KSYS_PC, 8195/8196 BOX0_LO/HI, 8197/8198 BOX1_LO/HI, 8202/8203
BOX2_LO/HI, 8207 KTICK_PC, 8208 TIMER_COUNT, 8209 TIMER_RELOAD}, gated
on the BK-76 ever_user latch + _tile_confinement. MODE_LATCH (8192) and
the TILE words (8280..8283) are EXCLUDED by the measured scope amendment
(xv6-nano S6/S11 lawfully re-arm them post-USER every context switch).

The twin's walk_st carries the BK-76-twin refusal (AB gate, 7/7) for the
three VECTOR words only (8193/8194/8207), leaving the BK-50 measured
door OPEN for the remaining BK-41 locked words — the D1/D3 probe shapes
(measured again this session, probe_wgsl_mmio_door_af3e.py results md5
f9349631f7610092ef583759d81cf319):
  D1  seeded-USER ST 0x0ADF00D -> word 8196 (BOX0_HI) LANDS clean
      (mmio[4]=11399181, mode USER, fault 0, 4 steps);
  D3  pure-USER disarm chain ST 65536->8196 then CANARY->word 999 BOTH
      land (the task rewrote its own confinement through the door);
while the oracle traps the same program (E-K1, fault 0x8010).

Legs (device verdicts from mmio/ram readback + fault words, never stdout):
  L1  seeded-USER ST canary -> 8196 REFUSED: mmio[4] unchanged (BOX0_HI
      stays at its seeded 1300), fault_addr == 8196*4 = 32784, mode ->
      SUPER, stopped with no vector (kf=0). RED today (D1 lands).
  L2  disarm chain dead: ST 65536->8196 then canary->999: word 8196
      unchanged, word 999 unchanged (nothing landed), machine stopped.
      RED today (both land).
  L3  scope boundary: TILE_H (word 8282, mmio idx 90) USER store LANDS
      clean post-USER — the BK-41 measured scope amendment is preserved
      (S6/S11 lawful re-arm must survive; never widen the lock).
  L4  boot-phase control: never-USER SUPER store to 8196 LANDS (latch
      gate: boot/config-phase kernel config untouched).
  L5  non-vacuity: neutering the new refusal clause in a TEMP-COPY
      module reproduces L1's pre-fix shape (canary lands at 8196); real
      tree md5-pinned before/after.
  L6  family subprocess: BK-51 twin gate + BK-41 oracle gate green on
      this tree (never weaken a live guard).

Scope: tools/wgsl_glyph_isa_v2.py ST dispatch arm ONLY (the clause
extends the landed BK-76-twin refusal from the three vector words to
the BK-41 locked set; the existing clause text/semantics for the vector
words is byte-identical in behavior). glyph_dispatch WGSL mirrors
synced post-gate (triple md5 parity).
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
DISARM = 65536
MMIO_LO = 8192
IDX = lambda w: w - MMIO_LO  # noqa: E731

WORD_BOX0_HI = 8196          # BK-41 locked, NOT in BK-76's vector trio
WORD_TILE_H = 8282           # BK-41 EXCLUDED (S6/S11 lawful re-arm)
WORD_OOB_RAM = 999           # outside any box after the D3 self-grant
FAULT_ADDR_IDX = 7           # mmio[7] = FAULT_ADDR word
BOX0_LO_WORD, BOX0_HI_WORD = 8195, 8196
BOX_LO, BOX_HI = 1200, 1300

TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
TILE_SEED = {IDX(8280): TILE_ROW, IDX(8281): TILE_COL,
             IDX(8282): TILE_H, IDX(8283): TILE_W}

# USER ST canary -> BOX0_HI (the D1 door shape)
PROG_ST_WORD = (
    ":__entry\n"
    "LDI r5 %d\n"          # value
    "LDI r6 %d\n"          # target word
    "ST r6 r5\n"
    "HALT\n")

# the D3 disarm chain: ST 65536 -> BOX0_HI, then canary -> OOB word 999
PROG_DISARM = (
    ":__entry\n"
    "LDI r4 %d\n"
    "LDI r5 %d\n"
    "LDI r6 %d\n"
    "LDI r7 %d\n"
    "ST r4 r5\n"
    "ST r6 r7\n"
    "HALT\n") % (WORD_BOX0_HI, DISARM, WORD_OOB_RAM, CANARY)


def run_leg(name, text, mmio_seed, seed_mode=1, max_steps=80, module=None,
            kfault_zero=True):
    """Run one program on the real WGSL device (BK-48/49/50/51/76 harness
    shape: run_wgsl's real buffers + build_shader(OpcodeMapV2()), seeded
    cpu.mode + mmio words)."""
    import wgpu, wgpu.utils  # noqa: E401
    if module is None:
        from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    else:
        build_shader = module.build_shader
        make_cpu_state_array = module.make_cpu_state_array
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
    if kfault_zero:
        mmio[IDX(8193)] = 0        # kf = 0: any stray vector = loud stop
    mmio[IDX(BOX0_LO_WORD)] = BOX_LO
    mmio[IDX(BOX0_HI_WORD)] = BOX_HI
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
        "box0_hi": int(mmio_out[IDX(WORD_BOX0_HI)]),
        "tile_h": int(mmio_out[IDX(WORD_TILE_H)]),
        "ram_word999": int(ram_out[WORD_OOB_RAM]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_IDX]),
    }


def _real_module_md5():
    return hashlib.md5((REPO / "tools" / "wgsl_glyph_isa_v2.py")
                       .read_bytes()).hexdigest()


# ------------------------------------------------------------------ L1
def test_l1_user_st_box0_hi_refused():
    r = run_leg("l1_st_box0hi", PROG_ST_WORD % (CANARY, WORD_BOX0_HI),
                dict(TILE_SEED), seed_mode=1)
    assert r["box0_hi"] == BOX_HI, (
        f"BK50T-L1 RED (defect live): USER canary {r['box0_hi']:#x} LANDED "
        f"at BOX0_HI through the walk_st MMIO door — the BK-50 door is open")
    assert r["fault_addr_word"] == WORD_BOX0_HI * 4, r   # 32784
    assert r["mode_final"] == 0 and r["halted"], r       # SUPER, no vector


# ------------------------------------------------------------------ L2
def test_l2_disarm_chain_dead():
    r = run_leg("l2_disarm", PROG_DISARM, dict(TILE_SEED), seed_mode=1)
    assert r["box0_hi"] == BOX_HI, (
        f"BK50T-L2 RED: self-grant LANDED (BOX0_HI={r['box0_hi']}) — the "
        f"confinement rewrite went through the door")
    assert r["ram_word999"] == 0, (
        f"BK50T-L2 RED: OOB canary landed after self-grant "
        f"(word999={r['ram_word999']:#x})")
    assert r["halted"], r


# ------------------------------------------------------------------ L3
def test_l3_tile_h_stays_guest_writable():
    """BK-41's measured scope amendment: TILE words excluded from the lock
    (xv6-nano S6/S11 re-arm them post-USER). Never widen the lock."""
    r = run_leg("l3_tile_h_lands",
                PROG_ST_WORD % (777, WORD_TILE_H), dict(TILE_SEED),
                seed_mode=1)
    assert r["tile_h"] == 777, (
        f"BK50T-L3 SCOPE BREACH: lawful TILE_H store refused "
        f"(tile_h={r['tile_h']}) — the lock was widened past BK-41's "
        f"measured scope amendment")
    assert r["halted"], r


# ------------------------------------------------------------------ L4
def test_l4_boot_phase_super_store_lands():
    r = run_leg("l4_boot", PROG_ST_WORD % (CANARY, WORD_BOX0_HI),
                dict(TILE_SEED), seed_mode=0)   # SUPER from step 0
    assert r["box0_hi"] == CANARY, (
        f"BK50T-L4 BOOT-PHASE BROKEN: never-USER SUPER config store "
        f"refused (BOX0_HI={r['box0_hi']:#x}) — the latch must gate on "
        f"USER history, not block kernel config outright")
    assert r["halted"], r


# ------------------------------------------------------------------ L5
def test_l5_non_vacuity_neutered_clause_reproduces_prefix():
    """Neuter the new refusal clause in a TEMP-COPY module -> L1's program
    must reproduce the PRE-FIX shape (canary lands at BOX0_HI)."""
    real_src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    marker = "bk50_config_write_refused"
    assert real_src.count(marker) >= 1, "gate clause marker not found"
    md5_before = _real_module_md5()
    # Neuter = make the clause's condition constant-false at its call site.
    call_marker = "if (bk50_config_write_refused(&cpu, addr)) {"
    assert real_src.count(call_marker) == 1, "call-site marker not unique"
    with tempfile.TemporaryDirectory() as td:
        mod_path = Path(td) / "wgsl_glyph_isa_v2_neutered.py"
        mod_path.write_text(real_src.replace(
            call_marker, "if (false && bk50_config_write_refused(&cpu, addr)) {"))
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk50", mod_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        r = run_leg("l5_neutered", PROG_ST_WORD % (CANARY, WORD_BOX0_HI),
                    dict(TILE_SEED), seed_mode=1, module=module)
    assert _real_module_md5() == md5_before, "real tree mutated by L5"
    assert r["box0_hi"] == CANARY, (
        f"BK50T-L5 NON-VACUITY FAILURE: neutered gate STILL refuses "
        f"(BOX0_HI={r['box0_hi']:#x}); the live gate cannot fail")


# ------------------------------------------------------------------ L6
def test_l6_family_gates_green():
    for gate in ("tests/test_bk51_wgsl_tile_fence.py",
                 "tests/test_bk41_ksys_fence.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=900, cwd=str(REPO))
        assert p.returncode == 0, f"{gate} RED:\n{p.stdout[-2000:]}"


if __name__ == "__main__":
    import traceback
    failed = 0
    for fn in (test_l1_user_st_box0_hi_refused,
               test_l2_disarm_chain_dead,
               test_l3_tile_h_stays_guest_writable,
               test_l4_boot_phase_super_store_lands,
               test_l5_non_vacuity_neutered_clause_reproduces_prefix,
               test_l6_family_gates_green):
        try:
            fn()
            print(f"{fn.__name__}: ok")
        except AssertionError:
            failed += 1
            traceback.print_exc()
    sys.exit(1 if failed else 0)
