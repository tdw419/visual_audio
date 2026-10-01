"""BK-56: the CONFIG-block READ posture (DIRECTIVE_BK56_MMIO_READ_POSTURE.md,
seat-lane provisional 2026-10-01, Option A decided).

The posture: USER-mode reads of the BK-41 locked config words refuse at
every guest-reachable read arm, on BOTH engines. Refusal semantics (family
Option A, read variant): the load delivers NO value, fault_reason
mmio_config_read_refused, fault_addr = word<<2, mode -> SUPER, stop,
NO vector (BK-75 KFC-L6 -- a read-refusal vector would itself leak the
fault PC; RESEARCH_wgsl_mmio_read_af3e.md finding 6: the read channel has
no fault path to ride, this consult IS new code on both engines).

Scope: the SAME 11-word set as BK-41/50/77's write lock (MODE_LATCH 8192
and TILE 8280..8283 stay OUT by BK-41's measured scope amendment).
Explicitly OUT (stays guest-readable / silent-0): SYS_A0/A1 (8205/8206),
the INPUT ring, all plain RAM. SUPER reads stay green (mode-scoped).

What the PASS does NOT prove: the syscall DATA-handler copy paths (0x02
READ etc.) as config-read arms are not exercised here (their dest consult
is BK-40's; no measured config-read shape exists on that path -- research
S1 found the leak on the LD arm only); the paged walk_ld arms are not
BK-56 legs (the config window is not paged on any landed image); the
oracle PARALLEL_LD leg is device-free (oracle is CPU-side); L6's family
run is a subprocess whose GREEN depends on the same device as this gate.

RED-first evidence (measured pre-fix at HEAD f1588fbe, probe
.builder_queue/probe_bk56_read_refuse_af3e.py, results md5
b9848e6f4202004521598c092b513c6f): T1/T2 silent-0 clean USER halt (fault
0, mode_final 1, steps 5) -- the whole window read as unset words; O1
clean USER halt, faulted False. Post-fix probe md5
b7b26ecef1bbb6f3d8305b735e731396: T1 fault 32772 mode 0 no vector, T2
fault 32784, T3 boundary clean, O1 faulted mmio_config_read_refused.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402

MMIO_SPAN = 160
IDX = lambda w: w - 8192  # noqa: E731
KFAULT_PC_WORD = 8193
BOX0_HI_WORD = 8196
SYS_A0_WORD = 8205
MODE_LATCH_WORD = 8192
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


# ---------------------------------------------------------------- oracle


def run_oracle(prog, mem_seeds, seed_mode=1, max_steps=80):
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
        "kf_after": int(cpu.memory[KFAULT_PC_WORD]),
    }


# ---------------------------------------------------------------- twin


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
        "kf_after": int(mmio_out[IDX(KFAULT_PC_WORD)]),
        "fault_addr_word": int(mmio_out[7]),
    }


# ------------------------------------------------------------- twin legs
# (RTX 5090, wgpu default adapter -- the BK-48/49/50/51/77 harness shape.)


def test_l1_twin_user_ld_kfault_refused():
    """USER LD of KFAULT_PC refuses on-device: fault 32772 = 8193*4, mode
    -> SUPER, result word NEVER written, NO vector (kf keeps its seed 7).
    RED pre-fix: silent-0 clean USER halt, steps 5, fault 0."""
    r = run_wgsl(PROG_LD_ST % (KFAULT_PC_WORD, RESULT_WORD),
                 {IDX(KFAULT_PC_WORD): KFAULT_SEED})
    assert r["halted"] and r["mode_final"] == 0, r
    assert r["fault_addr_word"] == KFAULT_PC_WORD * 4 == 32772, r
    assert r["ram_result_word"] == 0, r        # rd/ST path never delivered
    assert r["kf_after"] == KFAULT_SEED, r     # NO vector: kf untouched


def test_l2_twin_user_ld_box0hi_refused():
    """USER LD of BOX0_HI (the BK-55 aim target) same posture: fault
    32784 = 8196*4. RED pre-fix: ram[310] == 0 silent (block read as 0)."""
    r = run_wgsl(PROG_LD_ST % (BOX0_HI_WORD, RESULT_WORD), {})
    assert r["halted"] and r["mode_final"] == 0, r
    assert r["fault_addr_word"] == BOX0_HI_WORD * 4 == 32784, r
    assert r["ram_result_word"] == 0, r
    assert r["kf_after"] == 0, r


def test_l3_twin_super_ld_config_green():
    """SUPER LD of the config block stays green (mode-scoped, not a
    blanket block): the seeded value lands in the result word."""
    r = run_wgsl(PROG_LD_ST % (KFAULT_PC_WORD, RESULT_WORD),
                 {IDX(KFAULT_PC_WORD): KFAULT_SEED}, seed_mode=0)
    assert r["halted"] and r["mode_final"] == 0, r
    assert r["fault_addr_word"] == 0, r
    assert r["ram_result_word"] == KFAULT_SEED, r


def test_boundary_twin_sysA0_still_lands():
    """Boundary (BK-76 section 0): USER LD of SYS_A0 (8205) is NOT a config
    word -- the silent-0 landed-window semantics are unchanged (no fault,
    clean USER halt). We do not widen the lock to the data words."""
    r = run_wgsl(PROG_LD_ST % (SYS_A0_WORD, RESULT_WORD),
                 {IDX(SYS_A0_WORD): SYS_A0_SEED})
    assert r["halted"] and r["mode_final"] == 1, r
    assert r["fault_addr_word"] == 0, r
    # 69a53298 posture: non-config window words read silent-0 to USER.
    assert r["ram_result_word"] == 0, r


# ------------------------------------------------------------ oracle legs


def test_l4a_oracle_user_ld_kfault_refused():
    """L4 (decided: the gated posture): the ORACLE gains the symmetric read
    gate. USER LD of 8193: faulted, mmio_config_read_refused, fault_addr
    32772, mode -> SUPER, rd unchanged, NO vector. RED pre-fix: faulted
    False, clean USER halt (research D3 parity-on-the-leak)."""
    r = run_oracle(PROG_LD_ONLY % KFAULT_PC_WORD,
                   {KFAULT_PC_WORD: KFAULT_SEED})
    assert r["faulted"], r
    assert r["fault_reason"].startswith("mmio_config_read_refused"), r
    assert r["fault_addr"] == 32772, r
    assert r["mode_final"] == 0 and r["halted"], r
    assert r["r5_final"] == 0, r               # rd never written
    assert r["kf_after"] == KFAULT_SEED, r     # NO vector


def test_l4b_oracle_user_ld_box0hi_refused():
    """Oracle BOX0_HI: same shape, fault 32784 (research D1's word)."""
    r = run_oracle(PROG_LD_ONLY % BOX0_HI_WORD, {})
    assert r["faulted"], r
    assert r["fault_reason"].startswith("mmio_config_read_refused"), r
    assert r["fault_addr"] == 32784, r
    assert r["r5_final"] == 0, r


def test_l4c_oracle_super_ld_config_green():
    """Oracle SUPER LD of the config block stays green -- the seeded value
    lands in rd (kernel reads are the lawful path)."""
    r = run_oracle(PROG_LD_ONLY % KFAULT_PC_WORD,
                   {KFAULT_PC_WORD: KFAULT_SEED}, seed_mode=0)
    assert not r["faulted"], r
    assert r["r5_final"] == KFAULT_SEED, r
    assert r["halted"], r


def test_boundary_oracle_sysA0_scope():
    """Oracle boundary: SYS_A0 is outside the lock -- USER LD keeps the
    pre-BK-56 posture (no refusal; the un-configured window word reads 0
    silently, fault-free). Rot-guard: the lock must never silently widen
    to the data words."""
    r = run_oracle(PROG_LD_ONLY % SYS_A0_WORD,
                   {SYS_A0_WORD: SYS_A0_SEED,
                    BOX0_HI_WORD - 1: BOX_LO, BOX0_HI_WORD: BOX_HI})
    assert not r["faulted"], r
    assert r["mode_final"] == 1 and r["halted"], r
    assert r["r5_final"] == 0, r  # silent-0, NOT the seeded data value


def test_boundary_oracle_mode_latch_scope():
    """Scope amendment rot-guard: MODE_LATCH (8192) is EXCLUDED from the
    lock by BK-41's measured amendment (xv6-nano S6/S11 re-arm it
    post-USER) -- a USER LD of 8192 must NOT refuse."""
    r = run_oracle(PROG_LD_ONLY % MODE_LATCH_WORD,
                   {MODE_LATCH_WORD: 0x5A5A})
    assert not r["faulted"], r


def test_oracle_parallel_ld_config_refused():
    """The parallel arm refuses too (directive section 2 'every read
    arm'): USER PARALLEL_LD whose window covers a locked word refuses the
    WHOLE op -- no register in the window is written, no vector."""
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    prog = (
        ":__entry\n"
        "PARALLEL_LD r2 8193 4\n"
        "HALT\n")
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        bake_image(prog, cols_instrs=8, out_path=png)
        img = GlyphRunner(png).image
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = np.zeros(16384, dtype=np.uint64).tolist()
    cpu.memory[KFAULT_PC_WORD] = KFAULT_SEED
    cpu.memory[8194] = 11
    cpu.mode = 1
    cpu.pc = (0, 0)
    cpu.running = True
    steps = 0
    while cpu.running and steps < 40:
        cpu.step(img)
        steps += 1
    assert cpu.faulted, "PARALLEL_LD across KFAULT_PC must refuse"
    assert cpu.fault_reason.startswith("mmio_config_read_refused"), \
        cpu.fault_reason
    assert cpu.fault_addr == 32772, cpu.fault_addr
    assert cpu.registers[2] == 0 and cpu.registers[3] == 0, "no value lands"
    assert cpu.memory[KFAULT_PC_WORD] == KFAULT_SEED, "no vector"
    assert not cpu.running and cpu.mode == 0


def test_l5_nonvacuity_twin_neuter():
    """Non-vacuity (BK-41 L5 pattern): neuter bk56_config_read_refused in
    a TEMP-COPY module -> L1's shape reverts to the pre-fix silent USER
    halt; the real tree keeps the consult (md5-pinned before/after)."""
    real = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    marker = "fn bk56_config_read_refused(addr: u32, is_super: bool) -> bool {"
    assert marker in real, "consult missing from the real module"
    neutered = real.replace(
        marker,
        marker + "\n    if (true) { return false; }  // NEUTERED")
    assert neutered != real
    tmpmod = REPO / "tools" / "wgsl_glyph_isa_v2_bk56neuter_tmp.py"
    import hashlib
    real_md5 = hashlib.md5(real.encode()).hexdigest()
    try:
        tmpmod.write_text(neutered)
        import importlib
        import tools.wgsl_glyph_isa_v2_bk56neuter_tmp as neut
        importlib.reload(neut)
        # The neutered module must compile AND lose the refusal: run the
        # L1 program through its build_shader and confirm the value path.
        import wgpu, wgpu.utils  # noqa: F401
        from tools.glyph_gpt.baker import bake_image
        from tools.glyph_gpt.runner import GlyphRunner
        from tools.glyph_isa_v2 import OpcodeMapV2
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "p.png"
            bake_image(PROG_LD_ST % (KFAULT_PC_WORD, RESULT_WORD),
                       cols_instrs=8, out_path=png)
            image = GlyphRunner(png).image
        device = wgpu.utils.get_default_device()
        queue = device.queue
        n_pixels = image.shape[0] * image.shape[1]
        rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
        rgba[:, 0:3] = image.reshape(n_pixels, 3)
        usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
                 | wgpu.BufferUsage.COPY_SRC)
        cpu_state, cpu_dtype = neut.make_cpu_state_array(1)
        cpu_state[0]["mode"] = 1
        mmio = np.zeros(MMIO_SPAN, dtype=np.uint32)
        mmio[IDX(BOX0_HI_WORD - 1)] = BOX_LO
        mmio[IDX(BOX0_HI_WORD)] = BOX_HI
        mmio[IDX(KFAULT_PC_WORD)] = KFAULT_SEED
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
        sh = device.create_shader_module(code=neut.build_shader(OpcodeMapV2()))
        pipe = device.create_compute_pipeline(
            layout=device.create_pipeline_layout(
                bind_group_layouts=[bgl]),
            compute={'module': sh, 'entry_point': 'main'})
        rb = None
        for step in range(1, 40):
            enc = device.create_command_encoder()
            p = enc.begin_compute_pass()
            p.set_pipeline(pipe)
            p.set_bind_group(0, bg)
            p.dispatch_workgroups(1)
            p.end()
            queue.submit([enc.finish()])
            rb = np.frombuffer(queue.read_buffer(bufs["cpu"]),
                               dtype=cpu_dtype)[0]
            if rb['running'] == 0:
                break
        mmio_out = np.frombuffer(
            memoryview(queue.read_buffer(bufs["mmio"])), dtype=np.uint32)
        # Neutered shape == pre-fix: NO refusal, fault word stays 0.
        assert int(mmio_out[7]) == 0, "neutered tree must NOT refuse"
    finally:
        tmpmod.unlink(missing_ok=True)
        after = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
        assert hashlib.md5(after.encode()).hexdigest() == real_md5, \
            "real tree mutated by the neuter leg"


def test_l6_family():
    """Family: the twin fence gates (BK-48 + BK-50 + BK-77) stay green on
    the landed tree -- the read consult must not have disturbed the write
    lock or the tile/stack fences. Subprocess, real device."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         str(REPO / "tests" / "test_bk48_wgsl_ld_tile_fence.py"),
         str(REPO / "tests" / "test_bk50_wgsl_config_door.py"),
         str(REPO / "tests" / "test_bk77_twin_boxonly_lock.py")],
        cwd=REPO, capture_output=True, text=True, timeout=900)
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    assert r.returncode == 0, f"family RED:\n{r.stdout[-3000:]}\n{tail}"
    assert " passed" in tail, tail


# --------------------------------------------------- oracle regression


def test_oracle_plain_ram_ld_unaffected():
    """Plain-RAM USER LD is byte-identical posture: a non-window address
    reads its value with no fault (the consult is window+lock scoped)."""
    r = run_oracle(PROG_LD_ONLY % 500, {500: 0xC0FFEE})
    assert not r["faulted"], r
    assert r["r5_final"] == 0xC0FFEE, r
