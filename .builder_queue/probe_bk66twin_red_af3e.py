#!/usr/bin/env python3
"""BK-66-twin RED-baseline probe: does the WGSL twin's PAGED path consult the
paddr fence? Expected pre-fix (the live gap): a tile-armed USER paged LD/ST
whose TRANSLATED paddr falls OUT of the tile lands clean (oracle: faults
paged_paddr_fence, glyph_isa_v2.py:952-990 LD / :1114-1146 ST post-9714a363).

Harness = the landed BK-48 gate's run_twin_seeded (real run_wgsl buffers +
build_shader(OpcodeMapV2()), probe-only seeded cpu.mode, tile words seeded in
mmio, PT armed via ram). Verdicts from ram/mmio readback, never stdout.
"""
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import numpy as np

CANARY = 0x0ADF00D
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
TILE_ROW_WORD, TILE_COL_WORD = 8280, 8281
TILE_H_WORD, TILE_W_WORD = 8282, 8283
MMIO_LO = 8192
KFAULT_PC_WORD = 8193
FAULT_ADDR_WORD = 8199
PAGE_TABLE_WORD = 8211
PT_BASE = 2001
PT_TAG_WORD = PT_BASE - 1
PT_TAG = 0x505447

# vaddr picked INSIDE the tile at the vaddr level? No — the BK-66 T1 shape:
# the VADDR may be anything; the fence must judge the TRANSLATED paddr.
# Use vaddr 100 (out of tile rows 5-6 in grid coords at word granularity:
# word 100 -> row 3, col 4 -> outside tile) mapped via a PLAIN PTE to
# pfn 0 -> paddr 0*256 + 100 = word 100... plain frames: paddr = pfn*256+offset.
# offset = vaddr & 0xFF = 100, vpn = 0 -> paddr = 100 (identity, out-of-tile).
VADDR = 100
VPN = (VADDR >> 8) & 0xFF          # 0
OFFSET = VADDR & 0xFF              # 100
PFN = 0
PADDR = PFN * 256 + OFFSET         # 100 -- out-of-tile physical word

PROG_LD_ST = (":__entry\nLDI r5 %d\nLD r6 r5\nLDI r7 %d\nLDI r8 %d\nST r7 r8\nHALT\n"
              % (VADDR, VADDR, CANARY))


def run_twin(name, text, mmio_seed, seed_mode=1, max_steps=80, ram_seed=None):
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
        "r6": int(rb['registers'][6]),
        "ram_vaddr": int(ram_out[VADDR]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_WORD - MMIO_LO]),
        "kfault_pc": int(mmio_out[KFAULT_PC_WORD - MMIO_LO]),
    }


TILE_MMIO = {TILE_ROW_WORD - MMIO_LO: TILE_ROW,
             TILE_COL_WORD - MMIO_LO: TILE_COL,
             TILE_H_WORD - MMIO_LO: TILE_H,
             TILE_W_WORD - MMIO_LO: TILE_W}

# PT: tag + vpn-0 PTE V|W|U pfn 0 (plain RAM frame) -> vaddr 100 == paddr 100
# NOTE: the PT-ARM word (PAGE_TABLE_WORD 8211) lives in box_mmio (the walker
# reads box_mmio[8211-8192]); the tag + PTEs live in the ram buffer (RAM-first
# fetch, image fallback). v2: v1 seeded 8211 into ram — the walker never saw
# an armed PT, the LD took the unpaged fallback and the ST E-K1'd (fault 400)
# — a dead-harness shape, not a paged verdict. Caught pre-evidence.
RAM_PT = {PT_TAG_WORD: PT_TAG,
          PT_BASE + VPN: 0x1 | 0x2 | 0x4 | (PFN << 8)}
MMIO_PT = dict(TILE_MMIO)
MMIO_PT[PAGE_TABLE_WORD - MMIO_LO] = PT_BASE

print("=== BK-66-twin RED baseline: tile-armed USER paged LD+ST, translated")
print("=== paddr %d is OUT of tile rows [%d,%d) — oracle REFUSES this" % (
    PADDR, TILE_ROW, TILE_ROW + TILE_H))
rec = run_twin("red", PROG_LD_ST, dict(MMIO_PT), ram_seed=dict(RAM_PT))
print("rec:", rec)
gap = []
if rec["ram_vaddr"] == CANARY and rec["mode_final"] == 1 and rec["fault_addr_word"] == 0:
    gap.append("ST: paged store to translated out-of-tile paddr %d LANDED clean "
               "USER (ram[%d]=%#x, fault 0) — oracle refuses (paged_paddr_fence op=ST paddr=%d)"
               % (PADDR, VADDR, CANARY, PADDR))
if rec["r6"] != CANARY:
    print("LD leg note: r6=%#x (canary not pre-seeded at paddr %d in this probe; "
          "the LD-side consult gets its own canary-seeded legs in the gate)"
          % (rec["r6"], PADDR))
if gap:
    for g in gap:
        print("RED CONFIRMED:", g)
else:
    print("NOT RED — investigate before landing")
