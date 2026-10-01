"""BK-49 research probe (af3e, 2026-09-27): the previous WGSL fence tick
(BK-48, HEAD 9e8b1bc0) measured the LD/ST core on-device and left three
caveats "not probed". This probe closes the push/stack-class one:

  Is the WGSL PUSH/POP/CALL stack path (mem_write via addr_to_xy onto the
  IMAGE plane, wgsl_glyph_isa_v2.py:635-659) fence-blind on the GPU the
  way the oracle's PUSH was measured (BK-39 leg 4: out-of-tile image-plane
  write, clean exit)?

Key structural fact: PUSH/POP/CALL in the WGSL shader use mem_write/
mem_read (addr_to_xy -> image pixels), NOT the ram[] plane and NOT
walk_st/walk_ld — so the E-K1 consult at :451 cannot see them BY
CONSTRUCTION. The question the device must answer is whether a USER-mode
PUSH actually lands an out-of-box pixel on real hardware (i.e. the
image-plane stack write is a live cross-fence write channel, not just a
source-read inference), and whether POP reads it back (the exfil twin:
out-of-box image bytes -> register -> in-box ram store).

Legs:
  S1 (source read): the PUSH/POP/CALL dispatch arms reference ZERO
      addr_in_box sites and go through mem_write/mem_read.
  D1 (on-device): seeded-USER PUSH with r31 landed OUTSIDE box [1200,1300)
      — prologue r31=500 (out), PUSH canary 0x0BADF00D, HALT. Conviction =
      the word READ BACK from image pixel address 500 equals the canary
      while mode stays USER, halted clean, no fault channel exists.
  D2 (on-device control): same program, r31=1250 (INSIDE the box) —
      stack write lands, value identical: proves the harness sees the
      in-box case work and the two legs differ only in box membership.
  D3 (on-device exfil twin): out-of-box image pixel pre-seeded with
      canary (via initial image bake pixels), seeded-USER POP from
      out-of-box r31 -> register r5 gets the canary -> ST it in-box
      (word 100). Conviction = ram[100] == 0x0BADF00D.

Verdicts from READBACK BYTES (ram buffer + image buffer), never handler
stdout. Run: python3 .builder_queue/probe_wgsl_stack_fence_af3e.py
"""
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
OUT_WORD = 500                        # out-of-box stack word
IN_WORD = 1250                        # in-box stack word (byte addr)
CANARY = 0x0BADF00D
DEST = 100                            # in-box ram dest for exfil ST


def source_legs():
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    out = {}
    for name in ("PUSH", "POP", "CALL"):
        start = src.index(f"opcode == OPCODE_{name}")
        end = src.find("} else if", start + 10)
        body = src[start:end]
        out[f"S1_{name}_addr_in_box_refs"] = body.count("addr_in_box")
        out[f"S1_{name}_uses_mem_rw"] = (
            "mem_write" in body or "mem_read" in body)
    return out


def device_legs():
    import wgpu, wgpu.utils                                    # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    def bake(prog):
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "p.png"
            bake_image(prog, cols_instrs=8, out_path=png)
            return GlyphRunner(png)

    def run_seeded(image, seed_mode, max_steps=60):
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
        mmio[3] = BOX_LO   # BOX0_LO (byte address)
        mmio[4] = BOX_HI   # BOX0_HI
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
        ram_out = np.frombuffer(queue.read_buffer(bufs["ram"]),
                                dtype=np.uint32)
        img_out = np.frombuffer(queue.read_buffer(bufs["img"]),
                                dtype=np.uint32).reshape(n_pixels, 4)
        mmio_out = np.frombuffer(queue.read_buffer(bufs["mmio"]),
                                 dtype=np.uint32)
        return {
            "halted": bool(rb['running'] == 0),
            "steps": step,
            "mode_final": int(rb['mode']),
            "r31": int(rb['registers'][31]),
            "r5": int(rb['registers'][5]),
            "ram_dest": int(ram_out[DEST]),
            "fault_addr_word": int(mmio_out[7]),   # FAULT_ADDR word 8199
        }, img_out

    def img_word(img_out, addr):
        """Read image-plane word exactly the way mem_read/addr_to_xy does:
        scanline wrap over the FULL image (x = addr % w, y = addr // w,
        modulo total pixels). PUSH decrements r31 in these raw address
        units; value is packed (r,g,b) channels back into a u32."""
        h, w, _c = img_out_shape
        total = h * w
        a = addr % total
        p = img_out[a]  # run_seeded returns the image as (n_pixels, 4)
        return (int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2]), (a % w, a // w)

    results = {}

    # D1: USER PUSH canary with out-of-box r31=500
    prog_d1 = """
    :__entry
    LDI r31 500
    LDI r4 %d
    PUSH r4
    HALT
    """ % CANARY
    r1 = GlyphRunner(bake(prog_d1).image)
    img_out_shape = r1.image.shape
    res, img_out = run_seeded(r1.image, 1)
    res["img_word_500"], _ = img_word(img_out, 500)
    res["img_word_499"], xy499 = img_word(img_out, 499)
    res["push_landed_xy"] = list(xy499)
    results["D1_user_push_oob"] = res

    # D2 control: same program, r31=1250 (inside box)
    prog_d2 = prog_d1.replace("500", "1250")
    r2 = GlyphRunner(bake(prog_d2).image)
    res, img_out2 = run_seeded(r2.image, 1)
    res["img_word_1250"], _ = img_word(img_out2, 1250)
    res["img_word_1249"], xy1249 = img_word(img_out2, 1249)
    res["push_landed_xy"] = list(xy1249)
    results["D2_user_push_inbox_control"] = res

    # D3: exfil twin — POP from out-of-box r31 reads the canary, ST in-box
    # Pre-seed: set r31=500 via LDI, POP into r5 (image pixel at 500 holds
    # 0 — so also run a second variant where the canary is PRE-BAKED into
    # the image at address 500 by painting it into the baked image array
    # before dispatch), then ST r5 -> word 100.
    r3img = bake("""
    :__entry
    LDI r31 500
    POP r5
    LDI r6 100
    ST r6 r5
    HALT
    """)
    # pre-paint image ADDRESS 500 (addr_to_xy units: x=500%w, y=500//w)
    # with the canary payload, exactly as mem_write would pack it
    h3, w3, _c = r3img.image.shape
    a = 500 % (h3 * w3)
    px = (a % w3, a // w3)
    v = CANARY & 0xFFFFFF
    r3img.image[px[1], px[0]] = ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
    res, img_out3 = run_seeded(r3img.image, 1)
    res["ram_dest"] = int(res["ram_dest"])
    res["preseed_pixel"] = list(px)
    results["D3_user_pop_oob_exfil"] = res

    # D4 E-K1 control: seeded-USER ST to in-RAM word 100 OUTSIDE the box
    # [1200,1300) byte — the fence MUST fire (fault_addr=400, mode→SUPER,
    # value refused). Proves the harness arms the box correctly and that
    # D1/D2's clean image-plane writes are a real bypass class, not a
    # dead harness.
    prog_d4 = """
    :__entry
    LDI r5 4660
    LDI r6 100
    ST r6 r5
    HALT
    """
    r4 = GlyphRunner(bake(prog_d4).image)
    res, _img4 = run_seeded(r4.image, 1)
    results["D4_user_st_oobox_ek1_control"] = res

    return results


if __name__ == "__main__":
    import hashlib
    import json
    print("== S legs (source reads) ==")
    s = source_legs()
    for k, v in sorted(s.items()):
        print(f"{k} = {v}")
    print("== D legs (on-device WGSL, RTX 5090) ==")
    try:
        d = device_legs()
        blob = json.dumps(d, indent=1, sort_keys=True)
        print(blob)
        print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")
    except Exception as e:  # noqa: BLE001
        print(f"DEVICE-LEG-ERROR: {type(e).__name__}: {e}")
