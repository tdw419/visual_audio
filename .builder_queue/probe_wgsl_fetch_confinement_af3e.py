#!/usr/bin/env python3
"""Research tick 10 (af3e, 2026-09-28): the WGSL TWIN side of BK-67 fetch
confinement — tick 9 measured the oracle (spawn(tile=...) posture, HEAD
2626466d) and left "WGSL twin (no tile harness, BK-51)" in NOT-proved.
This probe closes the twin half on-device (RTX 5090, wgpu compute),
using the proven BK-49/50/51/55 device harness (run real buffers +
build_shader(OpcodeMapV2()), probe-only seeded cpu.mode, box armed via
mmio[3]/mmio[4] = BOX0 byte LO/HI).

The twin has NO tile predicate at all (BK-51, measured: addr_in_box
contains zero tile references), so the twin-side question is the BOX
one: does the shader (a) fetch+execute pixels anywhere in the image
regardless of the armed box, and (b) execute pixels a USER task itself
wrote through BK-49's measured fence-blind PUSH (image-plane mem_write,
no consult) — i.e. arbitrary code injection + execution on the GPU,
USER end-to-end, no fault channel.

Source prediction at HEAD 89f0444a (tools/wgsl_glyph_isa_v2.py):
  main() fetches load_pixel(x..x+3, y) at :506-509 with ZERO
  addr_in_box terms (the only consults live in walk_ld/walk_st :451);
  every jump arm (JMPR :605, JMP :686, CALLR, CALL, RET, KJMP) sets
  next_pc with alignment-free raw pixel arithmetic; PUSH :636-638 is
  mem_write unguarded. Prediction: both D-legs land the canary in USER
  with fault_addr_word == 0.

Legs (verdicts from image/ram/mmio READBACK BYTES, never stdout):
  S1 (source): fetch block + each jump arm reference ZERO addr_in_box
      terms (count == 0); PUSH goes through mem_write.
  D1 (on-device): seeded-USER JMPR to a PRE-BAKED out-of-box code row
      carrying `LDI r10 <canary>` — twin executes it: r10 == canary,
      mode stays USER, fault_addr_word 0. (Oracle F2's twin.)
  D2 (on-device): full injection composition — seeded-USER program
      PUSHes the 4 canary-LDI pixels to an out-of-box image row via
      BK-49's fence-blind PUSH, then JMPRs there. Conviction =
      r10 == canary AND the injected opcode pixel readback equals the
      REAL LDI color (resolved at runtime from OpcodeMapV2, never
      hand-encoded). (Oracle F3's twin.)
  C1 (on-device control): plain seeded-USER ST to an out-of-box RAM
      word — E-K1 must fire (fault_addr_word == BOX-relative 400,
      mode -> SUPER): proves the box arming is LIVE in the exact
      harness where D1/D2 execute out-of-box (probe discriminating).
  C2 (on-device control): in-box program runs clean — the harness
      itself is not the cause of any D-leg oddity.

Run: python3 .builder_queue/probe_wgsl_fetch_confinement_af3e.py
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

BOX_LO, BOX_HI = 1200, 1300          # byte addresses of the armed box
INJECTED_ROW = 40                    # image row 40 (bake rows allow it)
CANARY = 0x0ADF00D                   # same canary as tick 9
OUT_ST_WORD = 100                    # in-RAM byte addr OUTSIDE the box


def source_legs():
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    out = {}
    # S1a: the fetch block in main() — from the load_pixel of the opcode
    # pixel through the next_pc default — contains no consult.
    start = src.index("let opcode_px = load_pixel(x, y);")
    end = src.index("if (opcode == OPCODE_LDI)", start)
    fetch = src[start:end]
    out["S1a_fetch_addr_in_box_refs"] = fetch.count("addr_in_box")
    # S1b: each control-transfer arm — zero consults, raw pixel target.
    for name in ("JMPR", "JMP", "CALL", "RET", "CALLR"):
        a = src.index(f"opcode == OPCODE_{name}")
        b = src.find("} else if", a + 10)
        body = src[a:b]
        out[f"S1b_{name}_addr_in_box_refs"] = body.count("addr_in_box")
        out[f"S1b_{name}_sets_next_pc"] = "next_pc = vec2<u32>" in body
    # S1c: PUSH through mem_write, unguarded (BK-49's measured primitive).
    a = src.index("opcode == OPCODE_PUSH")
    b = src.find("} else if", a + 10)
    push_body = src[a:b]
    out["S1c_PUSH_uses_mem_write"] = "mem_write" in push_body
    out["S1c_PUSH_addr_in_box_refs"] = push_body.count("addr_in_box")
    return out


def bake(text):
    from tools.glyph_gpt.baker import bake_image
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        bake_image(text, cols_instrs=8, min_rows=64, out_path=png)
        from tools.glyph_gpt.runner import GlyphRunner
        return GlyphRunner(png)


def ldi_r10_pixels():
    """The 4 pixels of `LDI r10 <canary>`; opcode color from OpcodeMapV2."""
    from tools.glyph_isa_v2 import OpcodeMapV2
    rgb = OpcodeMapV2().opcode_to_rgb("LDI")
    return [tuple(int(v) for v in rgb),
            (0, 0, 10),                                  # rd = r10
            ((CANARY >> 16) & 0xFF, (CANARY >> 8) & 0xFF, CANARY & 0xFF),
            (0, 0, 0)]


def run_seeded(image, seed_mode=1, max_steps=120):
    import wgpu, wgpu.utils                                    # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_isa_v2 import OpcodeMapV2

    device = wgpu.utils.get_default_device()
    queue = device.queue
    h, w, _c = image.shape
    n_pixels = h * w
    rgba = np.zeros((n_pixels, 4), dtype=np.uint32)
    rgba[:, 0:3] = image.reshape(n_pixels, 3)
    usage = (wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
             | wgpu.BufferUsage.COPY_SRC)
    cpu_state, cpu_dtype = make_cpu_state_array(1)
    cpu_state[0]["mode"] = seed_mode
    mmio = np.zeros(160, dtype=np.uint32)
    mmio[3] = BOX_LO
    mmio[4] = BOX_HI
    ram = np.zeros(16384, dtype=np.uint32)
    dt = np.dtype([('image_width', np.uint32),
                   ('image_height', np.uint32),
                   ('output_buffer_size', np.uint32)])
    bufs = {}
    for name, arr, extra in (
            ("img", rgba, 0), ("cpu", cpu_state, 0),
            ("out", np.zeros(256, np.uint32), 0), ("mmio", mmio, 0),
            ("u", np.array([(w, h, 64)], dt), wgpu.BufferUsage.UNIFORM),
            ("ram", ram, 0)):
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
    for step in range(1, max_steps + 1):
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
    ram_out = np.frombuffer(queue.read_buffer(bufs["ram"]), dtype=np.uint32)
    img_out = np.frombuffer(queue.read_buffer(bufs["img"]),
                            dtype=np.uint32).reshape(n_pixels, 4)
    mmio_out = np.frombuffer(queue.read_buffer(bufs["mmio"]), dtype=np.uint32)
    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "r10": int(rb['registers'][10]) & 0xFFFFFFFF,
        "r31": int(rb['registers'][31]) & 0xFFFFFFFF,
        "fault_addr_word": int(mmio_out[7]),   # FAULT_ADDR (word 8199)
    }, img_out, (h, w)


def img_word(img_out, addr, dims):
    """Image-plane word in BK-49's scanline address units (x=addr%w,
    y=addr//w over the FULL bake), packed (r,g,b) -> u32."""
    h, w = dims
    total = h * w
    a = addr % total
    p = img_out[a]
    return (int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2])


def paint_pixels(image, row, col, pixels):
    for k, rgb in enumerate(pixels):
        image[row, col + k] = tuple(int(v) for v in rgb)
    return image


def device_legs():
    results = {}

    # D1: seeded-USER JMPR to pre-baked out-of-box code row.
    tgt = (INJECTED_ROW << 16) | 0
    r1 = bake(":__entry\nLDI r15 %d\nJMPR r15\nHALT\n" % tgt)
    # Pre-paint the canary-LDI at row 40 col 0 of the BAKED image (before
    # dispatch) — the twin of tick 9 F2's pre-stamped pixels.
    px = ldi_r10_pixels()
    paint_pixels(r1.image, INJECTED_ROW, 0, px)
    res, img_out, dims = run_seeded(r1.image, 1)
    word0 = INJECTED_ROW * (dims[1]) + 0   # scanline addr of (row40,col0)
    res["injected_opcode_px"] = img_word(img_out, word0, dims)
    res["injected_opcode_px_is_ldi_color"] = (
        res["injected_opcode_px"] == ldi_r10_pixels()[0][0] << 16
        | ldi_r10_pixels()[0][1] << 8 | ldi_r10_pixels()[0][2])
    res["r10_is_canary"] = res["r10"] == CANARY
    results["D1_user_jmpr_exec_oobox_code"] = res

    # D2: full injection — PUSH writes the 4 pixels to row 50, then JMPR.
    # PUSH pre-decrements; descending r31 = base+1..base+4 lands pixels at
    # base..base+3 (row 50 cols 0..3, scanline units — the bake is
    # cols_instrs=8 x 4 px/instr = 32 px/row, same as tick 9).
    INJ_ROW2 = 50
    w1 = dims[1]
    base = INJ_ROW2 * w1
    push_seq = "\n".join(
        "LDI r31 %d\nLDI r5 %d\nPUSH r5"
        % (base + 1 + k, (px[k][0] << 16) | (px[k][1] << 8) | px[k][2])
        for k in range(4))
    tgt2 = (INJ_ROW2 << 16) | 0
    r2 = bake(":__entry\n" + push_seq
              + "\nLDI r15 %d\nJMPR r15\nHALT\n" % tgt2)
    res, img_out2, dims2 = run_seeded(r2.image, 1)
    res["injected_opcode_px"] = img_word(img_out2, base, dims2)
    real_ldi = (px[0][0] << 16) | (px[0][1] << 8) | px[0][2]
    res["real_ldi_color"] = real_ldi
    res["injected_px_matches_ldi"] = res["injected_opcode_px"] == real_ldi
    res["r10_is_canary"] = res["r10"] == CANARY
    results["D2_push_inject_then_execute"] = res

    # C1: E-K1 control — seeded-USER ST to out-of-box RAM word.
    r3 = bake(":__entry\nLDI r5 4660\nLDI r6 %d\nST r6 r5\nHALT\n"
              % OUT_ST_WORD)
    res, _img, _d = run_seeded(r3.image, 1)
    # FAULT_ADDR carries the raw byte address (400), the same shape BK-49
    # D4 measured — NOT box-relative.
    res["fired"] = (res["fault_addr_word"] == OUT_ST_WORD * 4
                    and res["mode_final"] == 0)
    results["C1_user_st_oobox_ek1_control"] = res

    # C2: in-box control — ST inside [1200,1300) lands clean (byte addr
    # 300 = word 75, inside the box). Exit/fault-shaped leg: no fault,
    # mode stays USER. (The D1/D2 legs do NOT trip this path.)
    r4 = bake(":__entry\nLDI r5 4660\nLDI r6 300\nST r6 r5\nHALT\n")
    res, _img4, _dims4 = run_seeded(r4.image, 1)
    res["clean"] = res["fault_addr_word"] == 0 and res["mode_final"] == 1
    results["C2_user_st_inbox_control"] = res

    return results


if __name__ == "__main__":
    print("== S legs (source reads, tools/wgsl_glyph_isa_v2.py) ==")
    s = source_legs()
    print(json.dumps(s, indent=1, sort_keys=True))
    print("== D legs (on-device WGSL, RTX 5090) ==")
    try:
        d = device_legs()
        blob = json.dumps(d, indent=1, sort_keys=True)
        print(blob)
        print("results_md5=%s" % hashlib.md5(blob.encode()).hexdigest())
    except Exception as e:  # noqa: BLE001
        print(f"DEVICE-LEG-ERROR: {type(e).__name__}: {e}")
