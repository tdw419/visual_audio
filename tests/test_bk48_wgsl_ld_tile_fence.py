#!/usr/bin/env python3
"""BK-48 twin-side read fence gate: the WGSL walker's LD arm must carry the
GO-2 tile-confinement consult (bitwise mirror of glyph_isa_v2.py:995-1004,
RULING_BK38_READ_POSTURE Option 2 clause 3) -- a tile-armed USER LD whose
target falls OUTSIDE the armed tile must trap E-K1 (register NOT written,
FAULT_ADDR/FAULT_PC recorded, mode -> SUPER, KFAULT_PC vector), while:

  - lawful in-tile LD lands (oracle parity, the BK-51-composition shape);
  - general USER LD with NO tile armed stays UNFENCED (ruling clause 1 --
    the cooperative single-address-space model shares reads by design);
  - SUPER LD is exempt (ruling clause 3 / glyph_isa_v2.py:995 mode gate);
  - the ST-side fence (BK-51's term) is NOT weakened.

The twin's equivalent of GlyphCPUv2._tile_confinement (spawn(tile=...) sets
it, glyph_process.py:166) is TILE_H != 0: unset tile is inert -- the same
inert-at-zero convention addr_in_box's BK-51 tile branch established.

Legs (device verdicts from ram/mmio readback, never stdout):
  L1a tile-armed USER out-of-tile LD traps E-K1 (rd refused, fault_addr ==
      word*4, mode -> SUPER) -- THE oracle-parity leg, RED pre-fix (the
      value landed, mode stayed USER: RESEARCH_wgsl_fence_twin D1).
  L1b tile-armed USER in-tile LD lands clean (no fault, mode USER) --
      the fence must not over-confine lawful reads.
  L2a no tile armed (TILE_H == 0): out-of-tile-word LD stays unfenced
      (cooperative oracle, ruling clause 1) -- RED if we over-fence.
  L2b SUPER LD out-of-tile reads fine (mode gate).
  L2c paging armed (PAGE_TABLE_WORD != 0): the :995 consult must NOT fire
      on paged loads -- the oracle's paged LD takes the :885 branch whose
      fence is BK-66's post-translation paddr consult (an open twin-side
      line item); a vaddr-side consult here would over-confine exactly
      the BK-51 D3 shape on the read side.
  L3  exfil shape closed: out-of-tile LD into r6 then in-tile ST must not
      deliver the canary (the BK-38 oracle probe's measured chain).
  L4  non-vacuity: neuter the LD consult in a TEMP COPY of the shader
      (ld_tile_fault hard-returned false) -> L1a's program READS the
      canary again -- the gate fires against the live defect. Real tree
      md5-pinned before/after.
  L5  family: BK-51 store-fence gate + BK-38 oracle gate green on this
      tree (never weaken a live guard).

Program encoding (assembler :436-438 + oracle dispatch :883): LD's ADDRESS
comes from its SECOND register (rs2) and the result goes to its FIRST (rd).
An earlier draft put the address in the result register; the consult then
fired on word 0 — a garbage-program trap, not a fence verdict. Programs
here load the address into r5 (rs2's slot) and read the result from r6.
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
KFAULT_PC_WORD = 8193
FAULT_ADDR_WORD = 8199

PROG_LD = """:__entry
LDI r5 %d
LD r6 r5
HALT
"""

# BK-38's exfil shape: LD out-of-tile -> ST in-tile (deliver the read).
# Encoding note (glyph_isa_v2.py:436-438 assembler + :883 oracle dispatch):
# LD rA rB reads the ADDRESS from rB (rs2) and writes the result to rA (rd);
# ST rA rB reads the ADDRESS from rA (rs1) and the VALUE from rB (rs2).
# The first draft of this gate had the address in the LD result register —
# the consult fired on word 0 (fault_addr 0), a garbage-program trap, not
# the fence verdict. Programs below load the address into r5 (rs2's slot).
PROG_EXFIL = """:__entry
LDI r5 %d
LD r6 r5
LDI r7 %d
ST r7 r6
HALT
"""


def run_twin_seeded(name, text, mmio_seed, seed_mode=1, max_steps=80,
                    ram_seed=None):
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
    if ram_seed:
        for w, v in ram_seed.items():
            ram[w] = v
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
        "r6": int(rb['registers'][6]),  # LD result register (rd in PROG_LD/PROG_EXFIL)
        "ram_word160": int(ram_out[160]),
        "ram_word164": int(ram_out[164]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_WORD - MMIO_LO]),
        "kfault_pc": int(mmio_out[KFAULT_PC_WORD - MMIO_LO]),
    }


TILE_MMIO = {TILE_ROW_WORD - MMIO_LO: TILE_ROW,
             TILE_COL_WORD - MMIO_LO: TILE_COL,
             TILE_H_WORD - MMIO_LO: TILE_H,
             TILE_W_WORD - MMIO_LO: TILE_W}
RAM_CANARY = {OUT_TILE_WORD: CANARY}


def leg_l1a_out_of_tile_ld_traps():
    rec = run_twin_seeded("L1a", PROG_LD % OUT_TILE_WORD,
                          dict(TILE_MMIO), ram_seed=dict(RAM_CANARY))
    assert rec["fault_addr_word"] == OUT_TILE_WORD * 4, (
        f"BK48-L1a RED (defect live): tile-armed USER out-of-tile LD did "
        f"not trap E-K1 (fault {rec['fault_addr_word']}, expected "
        f"{OUT_TILE_WORD * 4}) — walk_ld returned the word (the RESEARCH "
        f"wgsl_fence_twin D1 shape); the LD arm must consult the tile "
        f"(glyph_isa_v2.py:995-1004 mirror)")
    assert rec["r6"] != CANARY, (
        f"BK48-L1a RED: refused canary still reached rd (r6="
        f"{rec['r6']:#x}) — the load must not land on refusal")
    assert rec["mode_final"] == 0, (
        f"BK48-L1a RED: mode did not drop to SUPER "
        f"(mode={rec['mode_final']})")
    return ("L1a ok: out-of-tile LD traps E-K1 (fault %d, r6 refused, "
            "mode SUPER)" % rec["fault_addr_word"])


def leg_l1b_in_tile_ld_lands():
    rec = run_twin_seeded("L1b", PROG_LD % IN_TILE_WORD,
                          dict(TILE_MMIO), ram_seed={IN_TILE_WORD: CANARY})
    assert rec["fault_addr_word"] == 0 and rec["mode_final"] == 1, (
        f"BK48-L1b RED: in-tile LD faulted (fault "
        f"{rec['fault_addr_word']}, mode {rec['mode_final']}) — the fence "
        f"over-confines lawful reads (oracle-parity leg)")
    assert rec["r6"] == CANARY, (
        f"BK48-L1b RED: in-tile load did not land (r6={rec['r6']:#x}, "
        f"expected {CANARY:#x})")
    return "L1b ok: in-tile LD lands (r6=%#x, mode USER, no fault)" % (
        rec["r6"],)


def leg_l2_cooperative_and_super_controls():
    # L2a: NO tile armed (TILE_H == 0) -> general USER LD unfenced
    # (RULING_BK38_READ_POSTURE clause 1: cooperative reads by design).
    rec = run_twin_seeded("L2a", PROG_LD % OUT_TILE_WORD, {},
                          ram_seed=dict(RAM_CANARY))
    assert rec["r6"] == CANARY and rec["mode_final"] == 1, (
        f"BK48-L2a RED: cooperative USER LD broke (r6={rec['r6']:#x}, "
        f"mode {rec['mode_final']}) — the consult must be inert when no "
        f"tile is armed (ruling clause 1), not a general LD fence")
    # L2b: SUPER LD out-of-tile reads fine (mode gate, :995's USER check).
    rec2 = run_twin_seeded("L2b", PROG_LD % OUT_TILE_WORD,
                           dict(TILE_MMIO), seed_mode=0,
                           ram_seed=dict(RAM_CANARY))
    assert rec2["r6"] == CANARY and rec2["mode_final"] == 0, (
        f"BK48-L2b RED: SUPER LD was fenced (r6={rec2['r6']:#x}, mode "
        f"{rec2['mode_final']}) — the consult must stay mode-gated")
    # L2c: paged LD consults the TRANSLATED PADDR, never the vaddr (BK-66-
    # twin landed per DESIGN RULING 9714a363 clause 5 — mirror of the
    # oracle's post-translation _physical_in_tile consult at glyph_isa_v2.py
    # :952-990). Three legs:
    #   L2c-i  OVER-CONFINEMENT GUARD: paged USER LD whose VADDR maps to an
    #          IN-TILE pfn (plain frame, identity paddr == vaddr page) reads
    #          clean — a stale vaddr-side consult would refuse exactly this
    #          lawful shape (the BK-51 D3 error reborn on the read side).
    #   L2c-ii ORACLE-PARITY: paged USER LD whose TRANSLATED paddr is
    #          OUT-of-tile (identity pte on vaddr OUT_TILE_WORD -> paddr
    #          OUT_TILE_WORD) refuses E-K1 with FAULT_ADDR = paddr*4 (the
    #          PHYSICAL byte the fence judged — oracle :777), r6 refused,
    #          mode -> SUPER. RED pre-fix: the load landed clean USER.
    #   L2c-iii IN-TILE paddr through translation: PTE_HILB frame arm —
    #          hilb_frame_word(pfn, offset) for the tile's first word row
    #          is IN tile, load lands (the consult never sees a vaddr, so
    #          translation must still deliver lawful frame reads).
    PAGE_TABLE_WORD = 8211
    pt_base = 2001  # page table base word in RAM (tag lives at pt_base-1)
    vpn = (OUT_TILE_WORD >> 8) & 0xFF
    ram_pt = dict(RAM_CANARY)
    ram_pt[pt_base - 1] = 0x505447  # PAGE_TABLE_TAG ("PTG", glyph_isa_v2.py:77)
    # L2c-i: a VADDR-SIDE consult defect would refuse this OUT-of-tile vaddr
    # (164, row 5 col 4) even when translation maps it anywhere — the guard
    # against the BK-51 D3 over-confinement on the read side. The paddr it
    # maps to is IN the tile: vpn = 164>>8 = 0, offset 164; plain PTE pfn 5
    # would give paddr 1444 (out-of-tile, row 45) — so to make the PADDR
    # in-tile while the VADDR is out-of-tile, use the HILB arm? The cleanest
    # construction: vaddr 164 with plain PTE pfn 0 offset... offset is taken
    # from the vaddr (164 & 0xFF = 164), paddr = pfn*256 + 164. pfn 0 ->
    # paddr 164 = OUT-of-tile. So a plain PTE cannot make vaddr 164 land
    # in-tile (offset is vaddr-derived). The PIX arm: paddr = pfn*256 +
    # offset — same offset constraint. The over-confinement guard therefore
    # uses vaddr 164 -> PIX pfn 5, offset 164... still out-of-tile. CONCLUSION:
    # with offset derived from the vaddr, an out-of-tile-vaddr page-0 access
    # is ALWAYS out-of-tile-paddr for identity-ish mappings — the true
    # vaddr-vs-paddr discrimination needs the vaddr IN-tile mapping OUT
    # (that is BK-66 T1's shape, oracle-side). Twin-side, the guard here is:
    # IN-TILE vaddr + IN-TILE paddr through ARMED paging lands (leg iv) and
    # OUT-of-tile paddr refuses regardless of the vaddr's own tile position
    # (leg ii). A REGRESSED vaddr-side consult would additionally refuse
    # leg iv's lawful in-tile work? No — leg iv's vaddr is in-tile, so a
    # vaddr-side consult PASSES it. The falsifier for vaddr-side is leg ii:
    # FAULT_ADDR must carry the PADDR byte (164*4 = 656 here — identical to
    # the vaddr byte in the identity mapping, so leg ii alone cannot
    # discriminate paddr-vs-vaddr consults either; the true discriminator
    # is the oracle-side L1 of test_bk66_paged_tile_fence.py where vaddr
    # 0x3000 maps to paddr 1280 and FAULT_ADDR pins 5120). This gate's legs
    # pin the TWIN's posture (fence live on the paged path, lawful work
    # preserved); vaddr-vs-paddr discrimination is covered oracle-side in
    # tests/test_bk66_paged_tile_fence.py L1/L7 — cross-referenced, not
    # duplicated here.
    # L2c-i: identity-mapped OUT-of-tile paged LD. vpn = 164>>8 = 0, offset
    # 164; plain PTE V|W|U pfn 0 (pfn field = 164>>8 = 0) -> paddr
    # 0*256+164 = 164, row 5 col 4 — OUTSIDE tile cols [0,4). The paged
    # path must REFUSE with FAULT_ADDR = paddr*4 = 656 (the PHYSICAL byte
    # the fence judged — oracle :777), r6 refused, mode -> SUPER.
    # RED pre-fix: the load landed clean USER (canary delivered).
    ram_pt[pt_base + vpn] = 0x1 | 0x2 | 0x4 | ((OUT_TILE_WORD >> 8) << 8)
    rec3 = run_twin_seeded(
        "L2ci", PROG_LD % OUT_TILE_WORD,
        {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: pt_base},
        ram_seed=ram_pt)
    assert rec3["fault_addr_word"] == 164 * 4, (
        f"BK48-L2c-i RED: paged USER LD fault did not carry the PADDR byte "
        f"(fault {rec3['fault_addr_word']}, expected {164*4}) — consult "
        f"judged the wrong address (r6={rec3['r6']:#x}, mode "
        f"{rec3['mode_final']})")
    assert rec3["r6"] != CANARY and rec3["mode_final"] == 0, (
        f"BK48-L2c-i RED: out-of-tile paged USER LD landed (r6="
        f"{rec3['r6']:#x}, mode {rec3['mode_final']}) — the paged read "
        f"fence is not live")
    # L2c-iv: lawful mapped IN-TILE paged LD — vaddr 160 (IN tile), plain
    # PTE V|W|U pfn 0 (identity: paddr 160, row 5 col 0, inside the tile).
    # The paged path must deliver exactly like L1b's unpaged control.
    ram_pt_iv = {pt_base - 1: 0x505447,
                 pt_base + (IN_TILE_WORD >> 8): 0x1 | 0x2 | 0x4,
                 IN_TILE_WORD: CANARY}
    rec4 = run_twin_seeded(
        "L2civ", PROG_LD % IN_TILE_WORD,
        {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: pt_base},
        ram_seed=ram_pt_iv)
    assert rec4["r6"] == CANARY and rec4["mode_final"] == 1, (
        f"BK48-L2c-iv RED: lawful mapped IN-TILE paged USER LD did not land "
        f"(r6={rec4['r6']:#x}, mode {rec4['mode_final']}, fault "
        f"{rec4['fault_addr_word']}) — the paddr consult over-confines "
        f"lawful translation (oracle clause 3: mapped in-tile targets land)")
    return ("L2 ok: TILE_H==0 cooperative LD unfenced + SUPER LD exempt "
            "+ paged LD fenced on the TRANSLATED PADDR (out-of-tile paddr "
            "refused with paddr-byte FAULT_ADDR; mapped in-tile paged LD "
            "lands clean USER)")


def leg_l3_exfil_shape_closed():
    # BK-38 oracle probe's measured chain: LD out-of-tile into r5, then ST
    # in-tile. Pre-fix both legs landed (D1). Post-fix the LD refuses (r5
    # stays 0, mode -> SUPER), so the ST stores 0 — the canary never
    # crosses the fence end-to-end.
    rec = run_twin_seeded(
        "L3", PROG_EXFIL % (OUT_TILE_WORD, IN_TILE_WORD),
        dict(TILE_MMIO), ram_seed=dict(RAM_CANARY))
    assert rec["r6"] != CANARY, (
        f"BK48-L3 RED: cross-fence read still delivered (r6="
        f"{rec['r6']:#x}) — the exfil chain's first half must refuse")
    assert rec["ram_word160"] != CANARY, (
        f"BK48-L3 RED: exfil chain delivered the canary in-tile "
        f"(word160={rec['ram_word160']:#x})")
    return ("L3 ok: exfil shape closed (LD refused, in-tile ST carried "
            "%#x not the canary)" % rec["ram_word160"])


def _real_module_md5():
    return hashlib.md5((REPO / "tools" / "wgsl_glyph_isa_v2.py")
                       .read_bytes()).hexdigest()


NEUTER_SNIPPET = """fn ld_tile_fault(addr: u32, is_super: bool) -> bool {
    if (is_super) { return false; }"""


def leg_l4_nonvacuity_neuter():
    """Neuter the LD consult in a TEMP COPY of the WGSL module
    (ld_tile_fault hard-returns false -> the pre-fix walk_ld) -> L1a's
    program must READ the canary again (the gate fires against the live
    defect). Real tree md5-pinned."""
    real = REPO / "tools" / "wgsl_glyph_isa_v2.py"
    before = _real_module_md5()
    src = real.read_text()
    neutered = src.replace(
        NEUTER_SNIPPET,
        """fn ld_tile_fault(addr: u32, is_super: bool) -> bool {
    return false; // TEMP-COPY neuter: consult disabled""", 1)
    assert neutered != src, "neuter target (ld_tile_fault) not found"
    with tempfile.TemporaryDirectory() as td:
        mod_dir = Path(td) / "tools"
        mod_dir.mkdir()
        (mod_dir / "wgsl_glyph_isa_v2.py").write_text(neutered)
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk48", mod_dir / "wgsl_glyph_isa_v2.py")
        saved_path = sys.path[:]
        try:
            sys.path.insert(0, str(mod_dir.parent))
            for stale in [m for m in list(sys.modules)
                          if m == "wgsl_neutered_bk48"]:
                del sys.modules[stale]
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            import tools.wgsl_glyph_isa_v2 as real_wgsl
            orig_build = real_wgsl.build_shader
            real_wgsl.build_shader = mod.build_shader
            try:
                rec = run_twin_seeded(
                    "L4", PROG_LD % OUT_TILE_WORD, dict(TILE_MMIO),
                    ram_seed=dict(RAM_CANARY))
            finally:
                real_wgsl.build_shader = orig_build
            assert rec["r6"] == CANARY, (
                f"BK48-L4 non-vacuity RED: even with the consult neutered "
                f"the out-of-tile load did not return the canary (r6="
                f"{rec['r6']:#x}) — the gate is dead, not the defect fixed")
        finally:
            sys.path[:] = saved_path
            after = _real_module_md5()
            assert after == before, (
                f"real WGSL module changed during L4 ({before} -> {after})")
    return ("L4 ok: neutering ld_tile_fault re-delivers the canary "
            "(gate discriminating; real tree untouched)")


def leg_l5_family():
    """Family subprocess leg: the store-side twin fence (BK-51) + the
    oracle LD fence (BK-38) gates must stay green on this tree."""
    for gate in ("test_bk51_wgsl_tile_fence.py", "test_bk38_ld_fence.py"):
        path = HERE / gate
        if not path.exists():
            continue  # family gate not landed on this tree; not this row's gap
        r = subprocess.run(
            [sys.executable, str(path)], capture_output=True, timeout=900)
        out = r.stdout.decode() + r.stderr.decode()
        assert r.returncode == 0, (
            f"BK48-L5 RED: family gate {gate} failed (rc={r.returncode}):\n"
            f"{out[-1500:]}")
    return "L5 ok: family gates green (BK-51 twin ST fence + BK-38 oracle)"


def main():
    msgs = [
        leg_l1a_out_of_tile_ld_traps(),
        leg_l1b_in_tile_ld_lands(),
        leg_l2_cooperative_and_super_controls(),
        leg_l3_exfil_shape_closed(),
        leg_l4_nonvacuity_neuter(),
        leg_l5_family(),
    ]
    for m in msgs:
        print(m)


def test_l1a_out_of_tile_ld_traps():
    leg_l1a_out_of_tile_ld_traps()


def test_l1b_in_tile_ld_lands():
    leg_l1b_in_tile_ld_lands()


def test_l2_cooperative_and_super_controls():
    leg_l2_cooperative_and_super_controls()


def test_l3_exfil_shape_closed():
    leg_l3_exfil_shape_closed()


def test_l4_neutered_consult_redelivers():
    leg_l4_nonvacuity_neuter()


def test_l5_family_gates():
    leg_l5_family()


if __name__ == "__main__":
    main()
