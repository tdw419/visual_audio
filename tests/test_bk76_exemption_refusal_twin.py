#!/usr/bin/env python3
"""BK-76-twin gate — the WGSL twin's SUPER MMIO-window exemption refusal
(clause-4 parity with RULING_BK76_EXEMPTION_POSTURE.md, which the ORACLE
side landed at ab758f1c / tests/test_bk76_exemption_refusal.py 8/8).

The twin's walk_st SUPER window exemption (`wgsl_glyph_isa_v2.py` walk_st
`is_super` mmio branch) had the SAME hole the oracle's :968 exemption had:
a tile-confined task's own text can SYSCALL into SUPER (E-K2, KSYS armed)
and ST a sentinel straight into a DISPATCH VECTOR word (KFAULT_PC 8193 /
KSYS_PC 8194 / KTICK_PC 8207) — the store lands, mode stays SUPER, no
consult fires. The oracle side of this exact shape was MEASURED (ticks
19-21; restart loop 162 fires at KFAULT under fault-path refusal, clean
[7,7,52,0]->[7] collapse under no-vector refusal at KSYS).

Fix mirrored from the oracle (glyph_isa_v2.py:817-833/:1098-1103):
  - `bk76_ever_user` one-way latch in the SpatialCPU struct, set at
    dispatch top when the instruction started USER and a tile is armed
    (the twin's documented _tile_confinement equivalent is TILE_H != 0 —
    walk_ld/walk_st comments :452/:493). Boot/config-phase vector writes
    happen pre-first-USER and stay lawful (GH-25 fault image, GH-16/GH-6
    kernels, loader seeding).
  - ST-arm refusal: ever_user ∧ SUPER ∧ tile-armed ∧ window word ∧ locked
    vector word -> store DROPPED, FAULT_ADDR = word<<2, FAULT_PC packed,
    mode -> SUPER (post-mortem), running = 0, NO vector (tick-19
    restart-loop immunity). Scope is the three vector words ONLY —
    xv6-nano ISO_SYS_A0 (8205), MODE_LATCH (8192), ISO_INPUT_CURSOR
    (8237) stay lawful (ruling invariant 2).

Twin-side disclosures (struct limits, not behavior gaps): the WGSL
SpatialCPU struct has no `faulted`/`fault_reason` fields — the refusal's
verdict surface is the readback words (FAULT_ADDR/FAULT_PC/KSYS_PC),
running=0, mode=SUPER, and the store NOT landing. Device verdicts from
RAM + mmio + cpu READBACK, never stdout (family rule).

Legs:
  TW-L1  KSYS site: tile-armed USER task SYSCALLs to an armed handler in
         SUPER; handler ST of sentinel to 8194 is REFUSED (word unchanged,
         running=0, mode SUPER, FAULT_ADDR == 8194*4, no PRT after the
         refused store). RED pre-fix: sentinel lands, PRT fires.
  TW-L1b KTICK site: same shape against 8207 — refused, machine stops
         (ruling §0: each site exercised, not extrapolated).
  TW-L2  no-tile control: same KSYS program with NO tile armed — the lock
         is containment-scoped, never legacy: sentinel LANDS, PRT fires,
         SYSRET returns to USER (oracle EX-L2 parity).
  TW-L3  non-vector window word: handler ST to SYS_A0 (8205, the
         xv6-nano ISO_SYS_A0 site) LANDS clean, run continues — vector-
         words-only scope pinned (ruling invariant 2).
  TW-L4  boot-phase posture: tile armed but cpu starts SUPER and never
         executes USER — store to 8194 LANDS (latch never sets; GH-16/GH-6
         kernel config untouched).
  TW-L5  non-vacuity: neutering the ST-arm refusal in a TEMP-COPY module
         reproduces the PRE-FIX shape in TW-L1's program (sentinel lands,
         PRT fires). Real tree md5-pinned before/after.
  TW-L6  family subprocess: BK-49 twin stack-fence gate + BK-76 ORACLE
         gate green on this tree (never weaken a live guard).

RED-first at landing time: this gate run against the UNFIXED tree failed
TW-L1/TW-L1b with the measured pre-fix shapes (pasted in the landing
commit). 2 pinned GREEN runs byte-identical (results-line md5).
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
SENTINEL = 65537
MMIO_LO = 8192
WORD_KFAULT = 8193
WORD_KSYS = 8194
WORD_SYS_A0 = 8205
WORD_KTICK = 8207
IDX = lambda w: w - MMIO_LO  # noqa: E731
PACKED_HANDLER = (0 << 16) | 3  # pixel (12, 0) = instr 3 of an 8-col bake
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 8, 8  # item-29 spawn posture
TILE_SEED = {
    IDX(8280): TILE_ROW, IDX(8281): TILE_COL,
    IDX(8282): TILE_H, IDX(8283): TILE_W,
}
FAULT_ADDR_MMIO_IDX = IDX(8199)  # 7

DISPATCHER_TEXT = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # 0: dispatch to ksys in SUPER
    "LDI r3 99\n"          # 1 (resume target after SYSRET)
    "HALT\n"               # 2
    "LDI r6 %d\n"          # 3: handler start (SUPER) — sentinel value
    "LDI r7 %d\n"          # 4: target vector word
    "ST r7 r6\n"           # 5: THE SUPER-window store
    "LDI r5 52\n"          # 6
    "PRT r5\n"             # 7
    "SYSRET\n"             # 8
)

BOOT_TEXT = (
    ":__entry\n"
    "LDI r6 %d\n"          # 0: sentinel
    "LDI r7 %d\n"          # 1: target vector word
    "ST r7 r6\n"           # 2: SUPER store from a never-USER engine
    "HALT\n"               # 3
)


def run_leg(name, text, target_word, tile=True, seed_mode=1, max_steps=80,
            ksys_armed=True, module=None):
    """Run one program on the real WGSL device (BK-48/49/50/51 harness
    shape: run_wgsl's real buffers + build_shader(OpcodeMapV2()), seeded
    cpu.mode + mmio words). Device verdicts from readback, no stdout."""
    import wgpu, wgpu.utils  # noqa: F401
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
        bake_image(text % (SENTINEL, target_word), cols_instrs=8,
                   out_path=png)
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
    mmio[IDX(WORD_KFAULT)] = 0  # kf = 0: any stray vector = loud stop
    if ksys_armed:
        mmio[IDX(WORD_KSYS)] = PACKED_HANDLER
    if tile:
        for k, v in TILE_SEED.items():
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
    out_words = [int(w) for w in np.frombuffer(
        queue.read_buffer(bufs["out"]), dtype=np.uint32) if w]
    return {
        "name": name,
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "target_word_val": int(mmio_out[IDX(target_word)]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_MMIO_IDX]),
        "output": out_words,
    }


def _results_line(results):
    return hashlib.md5(
        repr(sorted(r.items() for r in results)).encode()).hexdigest()


# ---------------------------------------------------------------- TW-L1

def test_tw_l1_ksys_site_store_refused():
    r = run_leg("tw_l1_ksys", DISPATCHER_TEXT, WORD_KSYS,
                tile=True, seed_mode=1)
    assert r["target_word_val"] == PACKED_HANDLER, (
        f"TW-L1 REFUSAL FAILED — sentinel {r['target_word_val']} LANDED at "
        f"KSYS_PC through the SUPER window exemption (pre-fix shape)")
    assert r["halted"] and r["steps"] <= 6, r
    assert r["mode_final"] == 0, r  # dropped to SUPER, post-mortem posture
    assert r["fault_addr_word"] == WORD_KSYS * 4, r  # 32776
    assert 52 not in r["output"], r  # no PRT after the refused store


def test_tw_l1b_ktick_site_store_refused():
    r = run_leg("tw_l1b_ktick", DISPATCHER_TEXT, WORD_KTICK,
                tile=True, seed_mode=1)
    assert r["target_word_val"] == 0, (
        f"TW-L1b REFUSAL FAILED — sentinel LANDED at KTICK_PC "
        f"({r['target_word_val']}) through the SUPER window exemption")
    assert r["halted"] and r["steps"] <= 6, r
    assert r["mode_final"] == 0, r
    assert r["fault_addr_word"] == WORD_KTICK * 4, r  # 32828
    assert 52 not in r["output"], r


# ---------------------------------------------------------------- TW-L2

def test_tw_l2_no_tile_control_store_lands():
    r = run_leg("tw_l2_notile", DISPATCHER_TEXT, WORD_KSYS,
                tile=False, seed_mode=1)
    assert r["target_word_val"] == SENTINEL, r  # lock is containment-scoped
    assert 52 in r["output"], r  # handler ran through PRT
    assert r["halted"], r


# ---------------------------------------------------------------- TW-L3

def test_tw_l3_nonvector_window_word_lands():
    r = run_leg("tw_l3_sys_a0", DISPATCHER_TEXT, WORD_SYS_A0,
                tile=True, seed_mode=1)
    assert r["target_word_val"] == SENTINEL, (
        f"TW-L3 SCOPE BREACH — lawful ISO_SYS_A0 store refused "
        f"(word={r['target_word_val']})")  # vector-words-ONLY scope
    assert 52 in r["output"], r
    assert r["halted"], r


# ---------------------------------------------------------------- TW-L4

def test_tw_l4_boot_phase_super_store_lands():
    r = run_leg("tw_l4_boot", BOOT_TEXT, WORD_KSYS,
                tile=True, seed_mode=0)  # SUPER from step 0, never USER
    assert r["target_word_val"] == SENTINEL, (
        f"TW-L4 BOOT-PHASE BROKEN — never-USER SUPER config store refused "
        f"(word={r['target_word_val']})")  # latch must gate on USER history
    assert r["halted"], r


# ---------------------------------------------------------------- TW-L5

def _real_module_md5():
    return hashlib.md5((REPO / "tools" / "wgsl_glyph_isa_v2.py")
                       .read_bytes()).hexdigest()


def test_tw_l5_non_vacuity_neutered_refusal_reproduces_prefix():
    """Neuter the ST-arm refusal in a TEMP-COPY module -> TW-L1's program
    must reproduce the PRE-FIX shape (sentinel lands, PRT fires).

    BK-50-twin amendment: KSYS_PC (8194) is ALSO in the BK-50 locked set,
    so neutering the BK-76 clause alone no longer lets the sentinel land —
    the additive BK-50 clause refuses the same word through the same door
    (that overlap is the POINT of BK-50: the vector trio is inside the
    locked config set). Non-vacuity therefore neuters BOTH refusal sites;
    the real tree is md5-pinned before/after either way."""
    real_src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    marker = "cpu.bk76_ever_user == 1u"
    assert real_src.count(marker) == 1, "refusal check marker not unique"
    call_marker = "if (bk50_config_write_refused(&cpu, addr)) {"
    assert real_src.count(call_marker) == 1, "BK-50 clause marker not unique"
    md5_before = _real_module_md5()
    with tempfile.TemporaryDirectory() as td:
        mod_path = Path(td) / "wgsl_glyph_isa_v2_neutered.py"
        mod_path.write_text(real_src.replace(
            marker, "0u == 1u /* neutered */").replace(
            call_marker, "if (false && bk50_config_write_refused(&cpu, addr)) {"))
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk76", mod_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        r = run_leg("tw_l5_neutered", DISPATCHER_TEXT, WORD_KSYS,
                    tile=True, seed_mode=1, module=module)
    assert _real_module_md5() == md5_before, "real tree mutated by TW-L5"
    assert r["target_word_val"] == SENTINEL, (
        f"TW-L5 NON-VACUITY FAILURE — neutered gate STILL refuses "
        f"(word={r['target_word_val']}); the live gate cannot fail")
    assert 52 in r["output"], r  # the exact pre-fix landing shape


# ---------------------------------------------------------------- TW-L6

def test_tw_l6_family_gates_green():
    """BK-49 twin stack-fence + BK-76 ORACLE gates green on this tree."""
    for gate in ("tests/test_bk49_stack_fence.py",
                 "tests/test_bk76_exemption_refusal.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        assert p.returncode == 0, f"{gate} RED:\n{p.stdout[-2000:]}"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-line", action="store_true")
    a = ap.parse_args()
    summary = [
        run_leg("tw_l1_ksys", DISPATCHER_TEXT, WORD_KSYS, True, 1),
        run_leg("tw_l1b_ktick", DISPATCHER_TEXT, WORD_KTICK, True, 1),
        run_leg("tw_l2_notile", DISPATCHER_TEXT, WORD_KSYS, False, 1),
        run_leg("tw_l3_sys_a0", DISPATCHER_TEXT, WORD_SYS_A0, True, 1),
        run_leg("tw_l4_boot", BOOT_TEXT, WORD_KSYS, True, 0),
    ]
    for r in summary:
        print(r)
    if a.results_line:
        print("RESULTS_MD5", _results_line(summary))
