#!/usr/bin/env python3
"""Research tick 11 (af3e, 2026-09-28): PAGED FETCH — does arming GH-17
paging change which pixels the FETCH executes, on EITHER engine? The
composition no prior row measured.

Scope lineage (prior-art grep, rule-5, done BEFORE harness build):
  - BK-60/62/63/64/65: paged LD/ST arms (plain/HILB/PIX frames, flags).
    ALL data-side. Fetch never enters their scope.
  - BK-67 (oracle) / BK-68 (twin): fetch + jump arms have NO confinement
    consult — but both probes are explicitly UNPAGED (tick 9: "NO paging
    this tick — fetch never translates on the oracle BY SOURCE READ
    (:753), the paged-fetch sibling is a source-read note, not probed";
    tick 10 NOT-proved bullet 1: "paged fetch on the twin (walk_ld's
    PTE-fetch fallback :384-394 ...)"). No probe on either engine has
    ever armed a page table and then measured fetch/jump behavior.
  - Ticks 5/8: paged PIX ST LANDS image words fence-blind (data side).
    The EXECUTE half of a paged write has never been composed.

Source prediction at HEAD 7f572095:
  - Oracle: step() fetches image[y,x..x+3] directly (glyph_isa_v2.py
    :753-764) — no pt_base read, no _addr_in_box, no walk_ld. Jump arms
    (JMPR :1245 etc.) set next_pc from the register raw. Prediction:
    arming paging changes NOTHING about fetch; a program that arms paging
    and whose vpn-0 PTE maps vaddr 0 to an all-zero frame still executes
    its own row-0 text (if fetch translated, the FIRST fetch — vaddr 0 —
    would hit the zero frame and opcode-None halt at step 0 with r10=0,
    before the program could even arm the table).
  - Twin: main() fetches load_pixel(x..x+3, y) (wgsl_glyph_isa_v2.py
    :506-509) — same raw shape; walk_ld/walk_st translate DATA only.
  - Composition prediction: a paged USER ST through a PIX PTE (tick 5/8's
    measured fence-blind image-word landing) can write INSTRUCTION pixels
    out-of-tile; a raw JMPR then executes them — arbitrary code
    injection + execution WITH paging armed (the strongest containment
    posture the stack offers), no fault anywhere.

Legs (verdicts from exit_status + cpu fault fields + register/image
readback BYTES, never stdout; oracle harness = the real
GlyphProcessTable.spawn(tile=(256,19,1,2)) posture, same tile as ticks
8/9; twin harness = the proven BK-49/50/51/55/68 device buffers +
build_shader(OpcodeMapV2()), box [1200,1300) bytes armed via mmio[3/4],
probe-only seeded cpu.mode=1):

  ORACLE:
  P1  fetch-translation discriminator: arm paging via the task's own
      in-tile ST (PT base 1536, tag 1535), vpn-0 PTE maps vaddr 0 ->
      pfn 5 (image word 1280, all zeros). Program: LDI r10 canary; HALT.
      Prediction (raw fetch): r10 == canary, clean.
      If fetch translated: opcode-None halt at step 0, r10 == 0.
  P2  composition: arm paging, then four paged STs (vaddrs 3072..3075,
      vpn 12 PIX PTE pfn 5) write the 4 pixels of `LDI r10 canary` to
      image words 1280..1283 = row 40 col 0..3 (OUT of tile rows
      256..257), then JMPR to (0,40). Prediction: pixels land via the
      paged path, injected LDI executes, r10 == canary, USER end-to-end
      (loud opcode-None halt on the zero pixel after the payload,
      disclosed — same shape as tick 9 F2).
  C1  unpaged out-of-tile ST word 164 -> E-K1 (fault 656): data fence
      LIVE when unpaged (tick 8 C2 verbatim).
  C2  unpaged out-of-tile ST word 1280 -> E-K1 (fault 5120): the SAME
      physical word P2 writes via translation is fence-protected when
      unpaged — proves P2's landing went through the paged path
      (discriminating, not a dead harness).
  C3  paging armed + in-program JMP control: jump machinery coexists
      with an armed PT (control for P2's JMPR).

  TWIN (on-device, RTX 5090):
  T-P1 twin fetch-translation discriminator: same shape as P1 — arms
      PT via ST to word 8211 (lands in box_mmio[19], the BK-50 door),
      stamps tag 1535 + vpn-0 PTE -> pfn 5 in the image. Prediction:
      r10 == canary (raw fetch).
  T-P2 twin composition: arm PT, four paged STs (vaddr 3072..3075)
      write the instruction pixels, JMPR to row 40. Prediction: r10 ==
      canary AND image word 1280 readback == the REAL LDI color
      (resolved at runtime from OpcodeMapV2, never hand-encoded).
  T-C1 twin unpaged control: NO PT arm, ST to word 3072 -> E-K1
      fault_addr_word 12288, mode -> SUPER: the paged path in T-P2 is
      real (unpaged access to the same vaddr traps).

Run: python3 .builder_queue/probe_paged_fetch_af3e.py
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

CANARY = 0x0ADF00D                     # 11399181, same canary as ticks 9/10
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211                     # PAGE_TABLE_WORD (word index)
TILE = (256, 19, 1, 2)                 # covers RAM words 8211/8212 only
VPN0_PTE_WORD = 1536                   # pt_base + vpn 0
VPN12_PTE_WORD = PT_BASE_WORD + 12     # 1548
PTE_PIX_FULL = 0xF | (5 << 8)          # V|W|U|PIX, pfn 5 -> image word 1280
PTE_TAG = 0x505447
VA_VPN12 = 12 << 8                     # vaddr word 3072 (offsets 0..3 follow)
FRAME_BASE_WORD = 5 * 256              # 1280 = image row 40 (w=32)
INJECTED_ROW = 40
OUT_TILE_ST_WORD_C1 = 164              # tick 8 C2 verbatim
ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD,
                                                        PT_BASE_WORD)


def bake(text):
    from tools.glyph_gpt.baker import bake_image
    return bake_image(text, cols_instrs=8, min_rows=64, out_path=None)


def stamp_image(img, stamps):
    h, w, _ = img.shape
    total = h * w
    for word, val in stamps.items():
        idx = int(word) % total
        img[idx // w, idx % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def img_word(img, word):
    h, w, _ = img.shape
    idx = word % (h * w)
    px = img[idx // w, idx % w]
    return (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])


def ldi_r10_pixel_words():
    """The 4 pixel-words of `LDI r10 <canary>`; opcode color from
    OpcodeMapV2 at runtime, never hand-encoded."""
    from tools.glyph_isa_v2 import OpcodeMapV2
    r, g, b = (int(v) for v in OpcodeMapV2().opcode_to_rgb("LDI"))
    opcode_word = (r << 16) | (g << 8) | b
    return [opcode_word, 10, CANARY, 0]


def run_oracle_leg(text, stamps=None):
    from tools.glyph_process import GlyphProcessTable

    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 1549, "image must contain the PT window unwrapped"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=500)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    table._run_task(pid)
    task_img = task["image"]
    return {
        "program": text,
        "exit_status": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "fault_addr": (int(cpu.fault_addr)
                       if cpu.fault_addr is not None else None),
        "fault_reason": cpu.fault_reason,
        "halt_reason": cpu.halt_reason,
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "r10": int(cpu.registers[10]) & 0xFFFFFFFF,
        "injected_opcode_px": img_word(task_img, FRAME_BASE_WORD),
        "img_dims": [int(w), int(h)],
    }


def oracle_legs():
    out = {}
    px_words = ldi_r10_pixel_words()

    # P1: fetch-translation discriminator.
    out["P1_fetch_translation_discriminator"] = run_oracle_leg(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r10 %d\nHALT\n" % CANARY,
        {PT_TAG_WORD: PTE_TAG, VPN0_PTE_WORD: PTE_PIX_FULL})

    # P2: paged write of instruction pixels + raw JMPR execute.
    store_seq = "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5" % (px_words[k], VA_VPN12 + k)
        for k in range(4))
    tgt = (INJECTED_ROW << 16) | 0
    out["P2_paged_inject_then_execute"] = run_oracle_leg(
        ":__entry\n" + ARM_SNIPPET + store_seq
        + "\nLDI r15 %d\nJMPR r15\nHALT\n" % tgt,
        {PT_TAG_WORD: PTE_TAG, VPN12_PTE_WORD: PTE_PIX_FULL})

    # C1: unpaged out-of-tile ST (word 164) — E-K1 live.
    out["C1_unpaged_out_of_tile_ST"] = run_oracle_leg(
        ":__entry\nLDI r5 4660\nLDI r15 %d\nST r15 r5\nHALT\n"
        % OUT_TILE_ST_WORD_C1, {})

    # C2: unpaged ST to the SAME physical word P2 writes (1280) — E-K1.
    out["C2_unpaged_ST_word1280"] = run_oracle_leg(
        ":__entry\nLDI r5 4660\nLDI r15 %d\nST r15 r5\nHALT\n"
        % FRAME_BASE_WORD, {})

    # C3: paging armed + in-program JMP control.
    out["C3_armed_PT_JMP_control"] = run_oracle_leg(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r5 1\nJMP 6,0\nPRT r5\n:nop\n:nop\n:nop\n:nop\n:nop\nHALT\n",
        {PT_TAG_WORD: PTE_TAG, VPN0_PTE_WORD: 0x7})
    return out


# ---------------- twin (on-device WGSL) ----------------

BOX_LO, BOX_HI = 1200, 1300


def run_twin(image, seed_mode=1, max_steps=120):
    import wgpu, wgpu.utils                                    # noqa: F401
    from tools.wgsl_glyph_isa_v2 import (build_shader,
                                         make_cpu_state_array)
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
        "fault_addr_word": int(mmio_out[7]),   # FAULT_ADDR
    }, img_out, (h, w)


def twin_img_word(img_out, addr, dims):
    h, w = dims
    a = addr % (h * w)
    p = img_out[a]
    return (int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2])


def twin_stamp(image, stamps):
    h, w, _ = image.shape
    total = h * w
    for word, val in stamps.items():
        idx = int(word) % total
        image[idx // w, idx % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return image


def twin_legs():
    import tempfile
    from pathlib import Path as _P
    from tools.glyph_gpt.baker import bake_image

    def bake_png(text):
        with tempfile.TemporaryDirectory() as td:
            png = _P(td) / "p.png"
            bake_image(text, cols_instrs=8, min_rows=64, out_path=png)
            from tools.glyph_gpt.runner import GlyphRunner
            return GlyphRunner(png)

    out = {}
    px_words = ldi_r10_pixel_words()
    real_ldi = px_words[0]

    # T-P1: twin fetch-translation discriminator.
    r1 = bake_png(":__entry\n" + ARM_SNIPPET
                  + "LDI r10 %d\nHALT\n" % CANARY)
    twin_stamp(r1.image, {PT_TAG_WORD: PTE_TAG,
                          VPN0_PTE_WORD: PTE_PIX_FULL})
    res, _img, _dims = run_twin(r1.image, 1)
    res["r10_is_canary"] = res["r10"] == CANARY
    out["T_P1_fetch_translation_discriminator"] = res

    # T-P2: twin composition — paged STs write instruction pixels, JMPR.
    store_seq = "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5" % (px_words[k], VA_VPN12 + k)
        for k in range(4))
    tgt = (INJECTED_ROW << 16) | 0
    r2 = bake_png(":__entry\n" + ARM_SNIPPET + store_seq
                  + "\nLDI r15 %d\nJMPR r15\nHALT\n" % tgt)
    twin_stamp(r2.image, {PT_TAG_WORD: PTE_TAG,
                          VPN12_PTE_WORD: PTE_PIX_FULL})
    res, img_out, dims = run_twin(r2.image, 1)
    res["injected_opcode_px"] = twin_img_word(img_out, FRAME_BASE_WORD,
                                              dims)
    res["injected_px_matches_ldi"] = res["injected_opcode_px"] == real_ldi
    res["real_ldi_color"] = real_ldi
    res["r10_is_canary"] = res["r10"] == CANARY
    out["T_P2_paged_inject_then_execute"] = res

    # T-C1: unpaged ST to the same vaddr P2 stores — must E-K1.
    r3 = bake_png(":__entry\nLDI r5 4660\nLDI r6 %d\nST r6 r5\nHALT\n"
                  % VA_VPN12)
    res, _img3, _dims3 = run_twin(r3.image, 1)
    res["fired"] = (res["fault_addr_word"] == VA_VPN12 * 4
                    and res["mode_final"] == 0)
    out["T_C1_unpaged_ST_vpn12_control"] = res
    return out


def main():
    results = {}
    print("== ORACLE legs (spawn(tile=...) posture) ==")
    o = oracle_legs()
    results["oracle"] = o
    print(json.dumps(o, indent=1, sort_keys=True, default=str))
    print("== TWIN legs (on-device WGSL, RTX 5090) ==")
    try:
        t = twin_legs()
        results["twin"] = t
        print(json.dumps(t, indent=1, sort_keys=True, default=str))
    except Exception as e:  # noqa: BLE001
        results["twin_error"] = f"{type(e).__name__}: {e}"
        print(f"DEVICE-LEG-ERROR: {type(e).__name__}: {e}")
    blob = json.dumps(results, indent=1, sort_keys=True, default=str)
    print("results_md5 %s" % hashlib.md5(blob.encode()).hexdigest())
    out_path = HERE / "probe_paged_fetch_af3e_results.json"
    out_path.write_text(blob)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
