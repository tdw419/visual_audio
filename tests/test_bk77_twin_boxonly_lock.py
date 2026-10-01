#!/usr/bin/env python3
"""BK-77 gate: the twin config lock must hold in the BOX-CONFIRMED-ONLY
(no-tile) posture — BK-55's residual escape (research receipt
.builder_queue/RESEARCH_bk55_boxonly_door_af3e.md, backlog row BK-77).

The landed BK-50-twin lock is TILE_H-gated: `bk50_config_write_refused`
bails when box_mmio[TILE_H]==0 (:661) and the ever_user latch fires only
when `was_user && TILE_H != 0` (:733). In the proven BK-49/50/51/55
box-only harness (mmio zero-seeded except BOX0 LO/HI) BOTH terms are
inert, the mode-blind MMIO branch (:604-606) takes the arming store, and
the E-K1 trap then vectors LIVE to guest pixels in SUPER — the measured
engine divergence "twin lands / oracle refuses" (oracle E-K1 USER arm
glyph_isa_v2.py:1481 needs NO _tile_confinement; box-only is a real
oracle containment posture, dbg_bk55_boxonly_oracle_af3e.py).

Fix under test: the lock's scope term widens from "tile armed" to "any
fence armed" — box_confirmed() = any of BOX0/1/2 HI != 0 — in BOTH the
refusal function AND the ever_user latch. The BK-50 tile posture is
unchanged (BOX_HI==0 there, so the widened term is strictly additive;
L5 pins BK-50's gate byte-identical green). Refusal shape stays the
landed no-vector Option A tail (BK-75 KFC-L6 restart-loop constraint:
the refusal itself must NOT vector, or the fix re-creates the
persistence it closes).

Pre-landing RED evidence (measured at HEAD e9f453c8, this session,
results md5 15a5dda21e2bf25c9c252d0383172c85 == the receipt's):
  probe_ek1_vector_hijack_wgsl_af3e.py, box-only, no tile:
    D1 HIJACK — trapped into guest payload in SUPER, canary 4660 printed
    D2 SUPER CAPABILITY — refused write LANDS via trapped-into code
    D3 VECTOR GUEST-WRITABLE via door (no fault, mode USER)
    C1 control discriminating (kf=0 loud stop); C2 fence LIVE (3996)

Legs (device verdicts from mmio/ram readback + fault words, never stdout;
harness = BK-50 gate's run_leg shape, box-only unless stated):
  L1  seeded-USER ST canary -> 8193 (KFAULT_PC) through the door, then
      out-of-box ST trigger: REFUSED before the arm — mmio[1] stays 0,
      machine stopped in SUPER, fault_addr == trigger*4, NO output canary
      (the D1 escape shape is dead).
  L2  D2's trapped-into SUPER write cannot land: door arm refused ->
      no vector exists -> payload LD/ST never executes; ram[200] keeps
      its seeded canary, 0x0ADF00D NOWHERE.
  L3  D3 door-only arm refuses: ST 7 -> 8193, mode USER: mmio[1] stays 0,
      machine stopped SUPER with fault_addr == 8193*4 = 32772
      (no fault pre-fix, mode stayed USER).
  L4  rot-guard (never weaken): plain out-of-box USER ST (word 999, no
      door use) STILL traps E-K1 fault 3996, value refused — the box
      fence itself stays live.
  L5  over-confinement: BK-50's tile-seeded gate
      (tests/test_bk50_wgsl_config_door.py) stays 6/6 GREEN on this
      tree, AND a boot-phase control in the box-only posture (never-USER
      SUPER store to 8193) LANDS — the widened latch gates on USER
      history, not on box arming alone.
  L6  non-vacuity: neuter the widened term in a TEMP-COPY module ->
      L3's program reproduces the PRE-FIX shape (kf=7 lands, mode USER,
      no fault); real tree md5-pinned before/after.
  L7  family subprocess: BK-76-twin + BK-51 twin gates green on this
      tree (never weaken a live guard; TW-L2's no-tile control exercises
      the no-box posture).

Scope: tools/wgsl_glyph_isa_v2.py ONLY (bk50_config_write_refused term
set + the ever_user latch condition). glyph_dispatch WGSL mirrors
synced post-gate (triple md5 parity, BK-50 precedent). NOT proved here:
oracle side (already refuses — dbg control in the receipt), any landed
box-only image lawfully writing locked words post-USER (source-read
found none; the design-judgment flag from the receipt stands recorded).
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
KFAULT_WORD = 8193
MMIO_LO = 8192
IDX = lambda w: w - MMIO_LO  # noqa: E731
KFAULT_IDX = IDX(KFAULT_WORD)          # 1
FAULT_ADDR_IDX = IDX(8199)             # 7
BOX_LO, BOX_HI = 1200, 1300            # the proven box-only posture
OOB_WORD = 999                          # out-of-box RAM word (byte 3996)
SEED_WORD = 200                         # out-of-box RAM word (byte 800)
PAYLOAD_PACKED = 7                      # slot (7,0) — probe's label-resolved slot

# L1/L2 shape = the probe's D1/D2 program (arm via door, trigger E-K1
# with an out-of-box ST, payload at :payload).
PROG_D1 = """
:__entry
LDI r7 %d
LDI r5 %d
ST r7 r5
LDI r6 %d
LDI r5 %d
ST r5 r6
HALT
:payload
PRT r6
HALT
""" % (KFAULT_WORD, PAYLOAD_PACKED, CANARY, OOB_WORD)

PROG_D2 = """
:__entry
LDI r7 %d
LDI r5 %d
ST r7 r5
LDI r6 %d
LDI r5 %d
ST r5 r6
HALT
:payload
LDI r2 %d
LD r6 r2
LDI r3 %d
ST r2 r3
HALT
""" % (KFAULT_WORD, PAYLOAD_PACKED, CANARY, OOB_WORD, SEED_WORD, CANARY)

# L3 shape = the probe's D3: door-only vector arm, no trigger.
PROG_D3 = """
:__entry
LDI r7 %d
LDI r5 %d
ST r7 r5
HALT
""" % (KFAULT_WORD, PAYLOAD_PACKED)

# L4 rot-guard: plain out-of-box ST, no door use.
PROG_ROT = """
:__entry
LDI r6 %d
LDI r5 %d
ST r5 r6
HALT
""" % (CANARY, OOB_WORD)

# L5 boot-phase control: never-USER SUPER store to the vector word,
# box-only (the latch must gate on USER history, not box arming).
PROG_BOOT = PROG_D3


def run_leg(name, text, mmio_seed=None, seed_mode=1, max_steps=80,
            module=None, ram_seeds=None, box=True):
    """Run one program on the real WGSL device (BK-49/50/51/76 harness
    shape: run_wgsl's real buffers + build_shader(OpcodeMapV2()), seeded
    cpu.mode + box_mmio + RAM seeds). Box-only unless box=False."""
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
    mmio[KFAULT_IDX] = 0        # kf = 0: any stray vector = loud stop
    if box:
        mmio[IDX(8195)] = BOX_LO
        mmio[IDX(8196)] = BOX_HI
    for k, v in (mmio_seed or {}).items():
        mmio[k] = v
    ram = np.zeros(16384, dtype=np.uint32)
    for addr, val in (ram_seeds or {}).items():
        ram[addr] = val
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
    out = np.frombuffer(memoryview(queue.read_buffer(bufs["out"])),
                        dtype=np.uint32)
    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "output_words": [int(v) for v in out[:8]],
        "ram_seed_word": int(ram_out[SEED_WORD]),
        "ram_oob_word": int(ram_out[OOB_WORD]),
        "mmio_kfault_pc": int(mmio_out[KFAULT_IDX]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_IDX]),
    }


def _real_module_md5():
    return hashlib.md5((REPO / "tools" / "wgsl_glyph_isa_v2.py")
                       .read_bytes()).hexdigest()


# ------------------------------------------------------------------ L1
def test_l1_boxonly_vector_hijack_dead():
    """D1's escape shape is dead: the door refuses the vector arm (no
    vector exists), the trigger E-K1 faults LOUDLY to kf==0, no payload
    canary prints."""
    r = run_leg("bk77_l1", PROG_D1)
    assert r["mmio_kfault_pc"] == 0, (
        f"BK77-L1 RED (defect live): vector arm LANDED via the door "
        f"(kf={r['mmio_kfault_pc']}) — the box-only posture is open")
    assert not any(w == 4660 for w in r["output_words"]), (
        f"BK77-L1 RED: payload canary 4660 printed in SUPER {r['output_words']} "
        f"— the trap vectored to guest pixels")
    assert r["mode_final"] == 0 and r["halted"], r   # SUPER, loud stop
    # The refusal stops the machine AT the arm ST (no vector), so the
    # recorded fault is the REFUSED window word, never the trigger's 3996.
    assert r["fault_addr_word"] == KFAULT_WORD * 4, r   # 32772


# ------------------------------------------------------------------ L2
def test_l2_trapped_into_capability_dead():
    """D2's shape is dead: refused arm -> no vector -> the payload's
    SUPER store never executes; ram[200] keeps its seeded canary."""
    r = run_leg("bk77_l2", PROG_D2, ram_seeds={SEED_WORD: 4660})
    assert r["ram_seed_word"] == 4660, (
        f"BK77-L2 RED: trapped-into-SUPER write LANDED "
        f"(ram[{SEED_WORD}]={r['ram_seed_word']:#x})")
    assert r["mmio_kfault_pc"] == 0, r
    assert r["mode_final"] == 0 and r["halted"], r
    assert r["fault_addr_word"] == KFAULT_WORD * 4, r  # stopped at the arm


# ------------------------------------------------------------------ L3
def test_l3_doors_only_arm_refused():
    """D3's shape is dead: door-only vector arm refuses — mmio[1] stays 0,
    machine stopped SUPER, fault_addr == 8193*4 (pre-fix: kf=7 landed,
    mode USER, no fault)."""
    r = run_leg("bk77_l3", PROG_D3)
    assert r["mmio_kfault_pc"] == 0, (
        f"BK77-L3 RED (defect live): kf={r['mmio_kfault_pc']} LANDED "
        f"through the door in the box-only posture")
    assert r["mode_final"] == 0 and r["halted"], r
    assert r["fault_addr_word"] == KFAULT_WORD * 4, r  # 32772


# ------------------------------------------------------------------ L4
def test_l4_box_fence_stays_live():
    """Rot-guard (never weaken): plain out-of-box USER ST still traps
    E-K1, fault 3996, value refused. (Pre-fix C2 control shape.)"""
    r = run_leg("bk77_l4", PROG_ROT)
    assert r["ram_oob_word"] == 0, (
        f"BK77-L4 ROT: plain OOB store LANDED (word999={r['ram_oob_word']:#x})"
        f" — the box fence was weakened")
    assert r["fault_addr_word"] == OOB_WORD * 4, r
    assert r["mode_final"] == 0 and r["halted"], r


# ------------------------------------------------------------------ L5
def test_l5_scope_never_widened_past_measured_amendment():
    """Over-confinement guard, two legs:
    (a) never-USER SUPER store to 8193 in the box-only posture LANDS —
        the widened latch gates on USER history, not box arming alone
        (boot/config-phase kernel config stays lawful);
    (b) BK-50's tile-seeded gate stays 6/6 GREEN on this tree — the
        widened term is strictly additive there (BOX_HI==0 in the tile
        harness's box seeds... pinned by re-running the whole gate)."""
    r = run_leg("bk77_l5_boot", PROG_BOOT, seed_mode=0)
    assert r["mmio_kfault_pc"] == PAYLOAD_PACKED, (
        f"BK77-L5 SCOPE BREACH: never-USER SUPER config store refused "
        f"(kf={r['mmio_kfault_pc']}) — the latch must gate on USER "
        f"history, not block kernel config outright")
    assert r["mode_final"] == 0 and r["halted"], r  # SUPER throughout
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         str(REPO / "tests" / "test_bk50_wgsl_config_door.py")],
        capture_output=True, text=True, timeout=1800, cwd=str(REPO))
    assert p.returncode == 0, (
        f"BK77-L5 ROT: BK-50 twin gate went RED after the scope widening:\n"
        f"{p.stdout[-2000:]}")


# ------------------------------------------------------------------ L6
def test_l6_non_vacuity_neutered_term_reproduces_prefix():
    """Neuter the widened scope in a TEMP-COPY module -> L3's program must
    reproduce the PRE-FIX shape (kf=7 lands through the door, mode USER,
    no fault). Real tree md5-pinned before/after."""
    real_src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    call_marker = "if (bk50_config_write_refused(&cpu, addr)) {"
    assert real_src.count(call_marker) == 1, "call-site marker not unique"
    latch_marker = "if (was_user && (box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO] != 0u || box_confirmed())) {"
    assert real_src.count(latch_marker) == 1, "widened latch marker not unique"
    md5_before = _real_module_md5()
    with tempfile.TemporaryDirectory() as td:
        mod_path = Path(td) / "wgsl_glyph_isa_v2_neutered.py"
        mod_path.write_text(real_src.replace(
            call_marker,
            "if (false && bk50_config_write_refused(&cpu, addr)) {"
        ).replace(
            latch_marker,
            "if (was_user && box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO] != 0u) {"
        ))
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk77", mod_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        r = run_leg("bk77_l6_neutered", PROG_D3, module=module)
    assert _real_module_md5() == md5_before, "real tree mutated by L6"
    assert r["mmio_kfault_pc"] == PAYLOAD_PACKED, (
        f"BK77-L6 NON-VACUITY FAILURE: neutered gate STILL refuses "
        f"(kf={r['mmio_kfault_pc']}); the live gate cannot fail")
    assert r["mode_final"] == 1 and r["halted"], r  # exact pre-fix shape


# ------------------------------------------------------------------ L7
def test_l7_family_gates_green():
    for gate in ("tests/test_bk76_exemption_refusal_twin.py",
                 "tests/test_bk51_wgsl_tile_fence.py"):
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=1800, cwd=str(REPO))
        assert p.returncode == 0, f"{gate} RED:\n{p.stdout[-2000:]}"


if __name__ == "__main__":
    import traceback
    failed = 0
    for fn in (test_l1_boxonly_vector_hijack_dead,
               test_l2_trapped_into_capability_dead,
               test_l3_doors_only_arm_refused,
               test_l4_box_fence_stays_live,
               test_l5_scope_never_widened_past_measured_amendment,
               test_l6_non_vacuity_neutered_term_reproduces_prefix,
               test_l7_family_gates_green):
        try:
            fn()
            print(f"{fn.__name__}: ok")
        except AssertionError:
            failed += 1
            traceback.print_exc()
    sys.exit(1 if failed else 0)
