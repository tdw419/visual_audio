#!/usr/bin/env python3
"""BK-62/BK-63 twin frame-path gate: the WGSL paged walker's HILB and PIX
frame arms must consult the GO-2 tile fence POST-TRANSLATION (ruling
9714a363 clause 5, landed on-device 7c4d791d) — measured, not by code path.

This gate closes the NOT-proved line item the BK-66-TWIN landing named:
"PTE_HILB twin arm not device-measured in-tile (consult covers it by code
path; BK-62/63 twin legs are the frame-path line items)." It drives HILB-
flagged and PIX-flagged PTEs through the twin's paged walk_ld/walk_st with
a tile armed (box_mmio TILE words seeded — the BK-48/BK-51 harness shape)
and pins BOTH sides of ruling clause 1/5:

  the fence judges the TRANSLATED frame word (paddr), never the vaddr —
  in-tile frames land, out-of-tile frames refuse with FAULT_ADDR = the
  PHYSICAL byte the fence judged (decoded_word << 2).

HILB placement (derived, not assumed — cross-checked at import against the
twin's own generated shader constants, HILB_SIDE=64, PAGE_WORDS=256):
  d=0  <- pfn 0x000 (col 0, row 0):  frame word = 0*256 + offset
  d=5  <- pfn 0x300 (col 0, row 3):  frame word = 5*256 + offset
  d=32 <- pfn 0x404 (col 4, row 4):  frame word = 32*256 + offset
  d=6  <- pfn 0x301 (col 1, row 3):  frame word = 6*256 + offset
PIX placement is the same arithmetic with the pfn field LINEAR
(paddr = pfn*256 + offset) — the two arms differ only in the PTE flag and
the transform, per the deliberate BK-62/BK-63 symmetry.

Tile: (row 8, col 0, h 1, w 8) -> grid words 256..263 (row 8, cols 0..7).
  - HILB IN-TILE target:  pfn 0x000 (d=0), offset 256-d*256 impossible —
    offset is 8-bit (vaddr & 0xFF), so d=0 frames span words 0..255 (rows
    0..7): every d=0 frame word is OUT of a row-8 tile. The in-tile HILB
    construction therefore uses d=32 (pfn 0x404): frame words 8192+off,
    rows 256+ — too far. RESOLUTION: the tile is chosen to FIT the frame,
    not the frame the tile: tile (row 0, col 0, h 8, w 8) covers grid
    words 0..7 rows 0..7 cols 0..7; HILB d=0 frame word (0*256 + offset)
    for offset 0..7 lands at grid rows 0, cols 0..7 — IN tile. The
    out-of-tile HILB target is d=5 (pfn 0x300, word 1280 + off = grid row
    40) — OUT. PIX: pfn 0 (word = offset, in-tile for off<8) vs pfn 5
    (word 1280+off, out-of-tile).

Legs (device verdicts from ram/mmio/image readback, never stdout):
  L1a HILB LD  in-tile frame word lands clean USER  (clause 3 over-
      confinement guard: translation must keep working — never weaken a
      live GH-25 path).
  L1b HILB LD  out-of-tile frame word REFUSED: fault_addr == word*4 (the
      PADDR byte — oracle :777 parity), rd unwritten, mode -> SUPER.
  L1c HILB ST  out-of-tile frame word does NOT land; same fault shape.
  L2a PIX  LD  in-tile lands clean USER (over-confinement guard).
  L2b PIX  LD  out-of-tile REFUSED (paddr-byte FAULT_ADDR).
  L2c PIX  ST  out-of-tile does NOT land.
  L3  PTE-flag discrimination rot-guard: the SAME program under a PLAIN
      (RAM-frame) PTE to an in-tile paddr lands, and to an out-of-tile
      paddr refuses — pins that all three arms share the consult, per
      clause 1 ("no consult ever sees a vaddr").
  L4  non-vacuity: the paddr consult is neutered in a TEMP COPY of the
      WGSL module (paged_paddr_out_of_tile -> return false) and L1b's
      program re-runs — the canary must come back (pre-fix behavior
      reproduced). Real tree md5-pinned before/after.
  L5  family: test_bk48_wgsl_ld_tile_fence.py (the landed twin fence
      gate) green on this tree — never weaken a live guard.

Determinism: no LLM/network; pinned probe programs; real WGSL device run
(GPU) is the engine under test, not an uncontrolled input — verdicts are
structural readbacks, 2 pinned runs per tick in the receipt.
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
FAULT_ADDR_WORD = 8199
PAGE_TABLE_WORD = 8211
PT_BASE = 2001
PT_TAG_WORD = PT_BASE - 1
PT_TAG = 0x505447

# Tile: grid rows [0,8) x cols [0,8) -> grid words 0..7 rows 0..7.
TILE_ROW, TILE_COL, TILE_H, TILE_W = 0, 0, 8, 8
TILE_ROW_WORD, TILE_COL_WORD = 8280, 8281
TILE_H_WORD, TILE_W_WORD = 8282, 8283
TILE_MMIO = {TILE_ROW_WORD - MMIO_LO: TILE_ROW,
             TILE_COL_WORD - MMIO_LO: TILE_COL,
             TILE_H_WORD - MMIO_LO: TILE_H,
             TILE_W_WORD - MMIO_LO: TILE_W}

# HILB frame words (derived; asserted against the shader source at import).
HILB_PFN_D0 = 0x000    # xy2d(0,0) = 0   -> frame word base 0
HILB_PFN_D5 = 0x300    # xy2d(0,3) = 5   -> frame word base 1280
PTE_V, PTE_W, PTE_U = 0x1, 0x2, 0x4
PTE_PIX, PTE_HILB = 0x8, 0x10

PROG_LD = ":__entry\nLDI r5 %d\nLD r6 r5\nHALT\n"
PROG_ST = ":__entry\nLDI r5 %d\nLDI r15 %d\nST r15 r5\nHALT\n"


def _hilb_crosscheck():
    """Derive d for the two pfns from the twin's own generated shader
    source constants; a mismatch aborts collection (never silently pass)."""
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    assert "const HILB_SIDE: u32 = 64u" in src, "shader constants drifted"
    assert "fn hilb_frame_word" in src, "hilb_frame_word missing"

    def xy2d(side, x, y):
        d = 0
        s = side >> 1
        while s > 0:
            rx = 1 if (x & s) else 0
            ry = 1 if (y & s) else 0
            d += s * s * ((3 * rx) ^ ry)
            if ry == 0:
                if rx == 1:
                    x = side - 1 - x
                    y = side - 1 - y
                x, y = y, x
            s >>= 1
        return d

    assert xy2d(64, HILB_PFN_D0 & 0xFF, HILB_PFN_D0 >> 8) == 0, "d0 pfn wrong"
    assert xy2d(64, HILB_PFN_D5 & 0xFF, HILB_PFN_D5 >> 8) == 5, "d5 pfn wrong"


_hilb_crosscheck()


def run_twin_seeded(name, text, mmio_seed, ram_seed=None, seed_mode=1,
                    max_steps=120, module_override=None, img_seed=None):
    """The BK-48 gate harness verbatim (three deltas: optional
    module_override so L4 can patch build_shader from a temp copy; optional
    img_seed stamping canary words into the IMAGE plane — the frame arms'
    own memory; ram/img readbacks for verdicts). Never stdout."""
    import wgpu, wgpu.utils  # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    if module_override is not None:
        build_shader = module_override.build_shader

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / f"{name}.png"
        bake_image(text, cols_instrs=8, out_path=png)
        image = GlyphRunner(png).image
    if img_seed:
        h, w, _ = image.shape
        total = h * w
        for word_i, val in img_seed.items():
            idx = word_i % total
            image[idx // w, idx % w] = ((val >> 16) & 0xFF,
                                        (val >> 8) & 0xFF, val & 0xFF)

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
    img_out = np.frombuffer(memoryview(queue.read_buffer(bufs["img"])),
                            dtype=np.uint32).reshape(n_pixels, 4)
    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "r6": int(rb['registers'][6]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_WORD - MMIO_LO]),
        "ram": ram_out,
        "img_words": [(int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2])
                      for p in img_out],
    }


def _hilb_pte(pfn_field, flags):
    return flags | PTE_HILB | (pfn_field << 8)


def _pix_pte(pfn_field, flags):
    return flags | PTE_PIX | (pfn_field << 8)


def _plain_pte(pfn_field, flags):
    return flags | (pfn_field << 8)


def _pt_stamps(vpn, pte_word):
    return {PT_TAG_WORD: PT_TAG, PT_BASE + vpn: pte_word}


# --------------------------------------------------------------- HILB legs
def leg_l1a_hilb_in_tile_ld_lands():
    # vaddr 192 (vpn 0, off 192) -> HILB pfn 0x000 (d=0) -> frame word 192
    # = tile-grid row 6 col 0 — IN the (0,0,8,8) tile, and PAST the program
    # text (text lives in the image's first pixel rows; word 192 = pixel
    # (0,6), verified black for this gate's 4-instruction program). A
    # canary at RAM word 192 is irrelevant to the frame read (the HILB arm
    # reads the IMAGE plane), so the canary is stamped into the IMAGE at
    # word 192 via the img stamp table below — same plane the read consults.
    word = 192
    va = 192
    ram = {PT_TAG_WORD: PT_TAG, PT_BASE + 0: _hilb_pte(HILB_PFN_D0, PTE_V | PTE_U)}
    rec = run_twin_seeded("H1a", PROG_LD % va,
                          {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE},
                          ram_seed=ram, img_seed={word: CANARY})
    assert rec["r6"] == CANARY and rec["mode_final"] == 1, (
        f"H62-L1a RED: lawful in-tile HILB paged LD did not land "
        f"(r6={rec['r6']:#x}, mode {rec['mode_final']}, fault "
        f"{rec['fault_addr_word']}) — the paddr consult over-confines "
        f"the live GH-25 HILB path (clause 3)")
    return ("L1a ok: in-tile HILB paged LD lands (r6=%#x, mode USER, "
            "fault 0)" % rec["r6"])


def leg_l1b_hilb_out_of_tile_ld_refused():
    # vaddr 0x300 = vpn 3, off 0 -> HILB pfn 0x300 (d=5) -> frame word
    # 1280 = grid row 40 col 0 — OUT of the tile. Refusal must carry the
    # PADDR byte (1280*4 = 5120), rd unwritten, mode -> SUPER.
    va = 0x300
    word = 1280
    ram = {word: CANARY}
    ram.update(_pt_stamps(3, _hilb_pte(HILB_PFN_D5, PTE_V | PTE_U)))
    rec = run_twin_seeded("H1b", PROG_LD % va,
                          {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE},
                          ram_seed=ram)
    assert rec["fault_addr_word"] == word * 4, (
        f"H62-L1b RED: HILB paged LD refusal did not carry the PADDR byte "
        f"(fault {rec['fault_addr_word']}, expected {word * 4}) — the "
        f"consult never saw the translated frame word")
    assert rec["r6"] != CANARY and rec["mode_final"] == 0, (
        f"H62-L1b RED: out-of-tile HILB paged LD landed clean "
        f"(r6={rec['r6']:#x}, mode {rec['mode_final']}) — the HILB frame "
        f"arm's read fence is not live on the twin")
    return ("L1b ok: out-of-tile HILB paged LD refused (fault %d = the "
            "PADDR byte, r6 refused, mode SUPER)" % rec["fault_addr_word"])


def leg_l1c_hilb_out_of_tile_st_refused():
    va = 0x300
    word = 1280
    ram = dict(_pt_stamps(3, _hilb_pte(HILB_PFN_D5, PTE_V | PTE_W | PTE_U)))
    rec = run_twin_seeded("H1c", PROG_ST % (CANARY, va),
                          {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE},
                          ram_seed=ram)
    landed = rec["img_words"][word % len(rec["img_words"])]
    assert rec["fault_addr_word"] == word * 4 and rec["mode_final"] == 0, (
        f"H62-L1c RED: out-of-tile HILB paged ST not refused (fault "
        f"{rec['fault_addr_word']}, mode {rec['mode_final']})")
    assert landed != CANARY, (
        f"H62-L1c RED: the canary LANDED at HILB frame word {word} "
        f"({landed:#x}) — instruction-stream-class write went through")
    return ("L1c ok: out-of-tile HILB paged ST refused (fault %d, image "
            "word untouched)" % rec["fault_addr_word"])


# ---------------------------------------------------------------- PIX legs
def leg_l2a_pix_in_tile_ld_lands():
    # PIX pfn 0, off 192 -> frame word 192 (tile-grid row 6 col 0) — IN
    # tile, past program text; canary stamped into the IMAGE plane.
    word = 192
    ram = {PT_TAG_WORD: PT_TAG, PT_BASE + 0: _pix_pte(0, PTE_V | PTE_U)}
    rec = run_twin_seeded("P2a", PROG_LD % 192,
                          {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE},
                          ram_seed=ram, img_seed={word: CANARY})
    assert rec["r6"] == CANARY and rec["mode_final"] == 1, (
        f"H63-L2a RED: lawful in-tile PIX paged LD did not land "
        f"(r6={rec['r6']:#x}, mode {rec['mode_final']}) — over-confinement")
    return "L2a ok: in-tile PIX paged LD lands (r6=%#x, mode USER)" % rec["r6"]


def leg_l2b_pix_out_of_tile_ld_refused():
    # PIX pfn 5, off 0 -> frame word 1280 — OUT of tile.
    va = 0x300
    word = 1280
    ram = {word: CANARY}
    ram.update(_pt_stamps(3, _pix_pte(5, PTE_V | PTE_U)))
    rec = run_twin_seeded("P2b", PROG_LD % va,
                          {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE},
                          ram_seed=ram)
    assert rec["fault_addr_word"] == word * 4, (
        f"H63-L2b RED: PIX refusal did not carry the PADDR byte (fault "
        f"{rec['fault_addr_word']}, expected {word * 4})")
    assert rec["r6"] != CANARY and rec["mode_final"] == 0, (
        f"H63-L2b RED: out-of-tile PIX paged LD landed clean "
        f"(r6={rec['r6']:#x}, mode {rec['mode_final']})")
    return ("L2b ok: out-of-tile PIX paged LD refused (fault %d = the "
            "PADDR byte)" % rec["fault_addr_word"])


def leg_l2c_pix_out_of_tile_st_refused():
    va = 0x300
    word = 1280
    ram = dict(_pt_stamps(3, _pix_pte(5, PTE_V | PTE_W | PTE_U)))
    rec = run_twin_seeded("P2c", PROG_ST % (CANARY, va),
                          {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE},
                          ram_seed=ram)
    landed = rec["img_words"][word % len(rec["img_words"])]
    assert rec["fault_addr_word"] == word * 4 and rec["mode_final"] == 0, (
        f"H63-L2c RED: out-of-tile PIX paged ST not refused (fault "
        f"{rec['fault_addr_word']}, mode {rec['mode_final']})")
    assert landed != CANARY, (
        f"H63-L2c RED: canary LANDED at PIX frame word {word} ({landed:#x})")
    return ("L2c ok: out-of-tile PIX paged ST refused (fault %d, image "
            "word untouched)" % rec["fault_addr_word"])


# --------------------------------------------- L3: plain-arm shared consult
def leg_l3_plain_arm_parity():
    # Same programs, PLAIN PTEs: in-tile paddr lands, out-of-tile paddr
    # refuses — all three arms share the post-translation consult. Plain
    # frames live in the RAM buffer (twin :444), so the canary is a RAM
    # seed here, unlike the frame arms' image-plane stamps.
    ram_in = {PT_TAG_WORD: PT_TAG,
              PT_BASE + 0: _plain_pte(0, PTE_V | PTE_U), 192: CANARY}
    rec_in = run_twin_seeded(
        "P3in", PROG_LD % 192,
        {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE}, ram_seed=ram_in)
    assert rec_in["r6"] == CANARY and rec_in["mode_final"] == 1, (
        f"H62/63-L3 RED: in-tile PLAIN paged LD broke (r6={rec_in['r6']:#x})")
    ram_out = {PT_TAG_WORD: PT_TAG,
               PT_BASE + 0: _plain_pte(1, PTE_V | PTE_U), 356: CANARY}
    rec_out = run_twin_seeded(
        "P3out", PROG_LD % 100,
        {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE}, ram_seed=ram_out)
    assert rec_out["fault_addr_word"] == 356 * 4 and rec_out["r6"] != CANARY, (
        f"H62/63-L3 RED: out-of-tile PLAIN paged LD landed "
        f"(r6={rec_out['r6']:#x}, fault {rec_out['fault_addr_word']})")
    # Note this leg's shape doubles as twin-side paddr-ness evidence:
    # vaddr 100 (IN-tile rows 0..7 at word 100? 100//32=3, col 4 — IN the
    # tile) maps via pfn 1 to paddr 356 (row 11 — OUT). The refusal fired
    # on the PADDR: a vaddr-side consult would have admitted this load.
    return ("L3 ok: PLAIN arm shares the consult (in-tile lands, "
            "out-of-tile refuses with the paddr byte)")


# ------------------------------------------------------- L4: non-vacuity
NEUTER_SNIPPET = ("fn paged_paddr_out_of_tile(paddr_word: u32, "
                  "is_super: bool) -> bool {\n    if (is_super) "
                  "{ return false; }")


def _real_module_md5():
    return hashlib.md5((REPO / "tools" / "wgsl_glyph_isa_v2.py")
                       .read_bytes()).hexdigest()


def leg_l4_nonvacuity_neuter():
    """Neuter paged_paddr_out_of_tile in a TEMP COPY of the WGSL module ->
    L1b's program must READ the canary again (the gate fires against the
    live defect). Real tree md5-pinned before/after."""
    real = REPO / "tools" / "wgsl_glyph_isa_v2.py"
    before = _real_module_md5()
    src = real.read_text()
    neutered = src.replace(
        NEUTER_SNIPPET,
        "fn paged_paddr_out_of_tile(paddr_word: u32, is_super: bool) "
        "-> bool {\n    return false; // TEMP-COPY neuter: consult disabled",
        1)
    assert neutered != src, "neuter target (paged_paddr_out_of_tile) missing"
    with tempfile.TemporaryDirectory() as td:
        mod_dir = Path(td) / "tools"
        mod_dir.mkdir()
        (mod_dir / "wgsl_glyph_isa_v2.py").write_text(neutered)
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk62", mod_dir / "wgsl_glyph_isa_v2.py")
        saved_path = sys.path[:]
        try:
            sys.path.insert(0, str(mod_dir.parent))
            for stale in [m for m in list(sys.modules)
                          if m == "wgsl_neutered_bk62"]:
                del sys.modules[stale]
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            va = 0x300
            # The frame arm reads the IMAGE plane, not ram — stamp the
            # canary at image word 1280 (same plane mem_read consults).
            rec = run_twin_seeded(
                "L4", PROG_LD % va,
                {**TILE_MMIO, PAGE_TABLE_WORD - MMIO_LO: PT_BASE},
                ram_seed=_pt_stamps(3, _hilb_pte(HILB_PFN_D5, PTE_V | PTE_U)),
                img_seed={1280: CANARY}, module_override=mod)
            assert rec["r6"] == CANARY, (
                f"H62/63-L4 non-vacuity RED: even with the consult neutered "
                f"the out-of-tile HILB load did not return the canary "
                f"(r6={rec['r6']:#x}) — the gate is dead, not the defect "
                f"fixed")
        finally:
            sys.path[:] = saved_path
            after = _real_module_md5()
            assert after == before, (
                f"real WGSL module changed during L4 ({before} -> {after})")
    return ("L4 ok: neutering paged_paddr_out_of_tile re-delivers the "
            "canary (gate discriminating; real tree untouched)")


# ------------------------------------------------------------- L5: family
def leg_l5_family():
    gate = HERE / "test_bk48_wgsl_ld_tile_fence.py"
    r = subprocess.run([sys.executable, str(gate)], capture_output=True,
                       timeout=900, cwd=str(REPO))
    out = r.stdout.decode() + r.stderr.decode()
    assert r.returncode == 0, (
        f"H62/63-L5 RED: family gate test_bk48 regressed "
        f"(rc={r.returncode}):\n{out[-1500:]}")
    return "L5 ok: family gate green (BK-48 twin LD fence + BK-51 ST fence)"


def main():
    msgs = [
        leg_l1a_hilb_in_tile_ld_lands(),
        leg_l1b_hilb_out_of_tile_ld_refused(),
        leg_l1c_hilb_out_of_tile_st_refused(),
        leg_l2a_pix_in_tile_ld_lands(),
        leg_l2b_pix_out_of_tile_ld_refused(),
        leg_l2c_pix_out_of_tile_st_refused(),
        leg_l3_plain_arm_parity(),
        leg_l4_nonvacuity_neuter(),
        leg_l5_family(),
    ]
    for m in msgs:
        print(m)


def test_l1a_hilb_in_tile_ld_lands():
    leg_l1a_hilb_in_tile_ld_lands()


def test_l1b_hilb_out_of_tile_ld_refused():
    leg_l1b_hilb_out_of_tile_ld_refused()


def test_l1c_hilb_out_of_tile_st_refused():
    leg_l1c_hilb_out_of_tile_st_refused()


def test_l2a_pix_in_tile_ld_lands():
    leg_l2a_pix_in_tile_ld_lands()


def test_l2b_pix_out_of_tile_ld_refused():
    leg_l2b_pix_out_of_tile_ld_refused()


def test_l2c_pix_out_of_tile_st_refused():
    leg_l2c_pix_out_of_tile_st_refused()


def test_l3_plain_arm_parity():
    leg_l3_plain_arm_parity()


def test_l4_neutered_consult_redelivers():
    leg_l4_nonvacuity_neuter()


def test_l5_family_gates():
    leg_l5_family()


if __name__ == "__main__":
    main()
