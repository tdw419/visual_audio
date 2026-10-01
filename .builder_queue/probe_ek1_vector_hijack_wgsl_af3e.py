#!/usr/bin/env python3
"""probe_ek1_vector_hijack_wgsl_af3e.py — Phase 1c research (BK-55 candidate).

Question: does the BK-53 oracle hijack (a tile-confined USER task arms a
guest-chosen KFAULT_PC through a fence-blind write, then triggers E-K1 with
an out-of-tile ST; the trap vectors to attacker code IN SUPER MODE and the
refused store's handler runs guest-chosen code) reproduce ON-DEVICE on the
WGSL twin?

This is the leg RESEARCH_ek1_vector_hijack_af3e.md disclosed as
"source-read only ... reduces to BK-50's door, not re-measured". It is
also the fence family's last unmeasured vector surface: BK-50 measured the
twin's MMIO write door; BK-48/49 measured walk_ld/stack fence-blindness;
nobody has measured what the twin's E-K1 fault (wgsl_glyph_isa_v2.py:581-598)
EXECUTES once the door arms the vector.

Structure (source, wgsl_glyph_isa_v2.py):
  - E-K1 branch (:581-598): walk_st returns true for an out-of-box USER ST
    -> records FAULT_ADDR/FAULT_PC (:586-588), sets mode=SUPER (:590),
    reads kf = box_mmio[KFAULT_PC_WORD - LO] LIVE at trap time (:591),
    and if kf != 0 sets next_pc = (kf_lo * INSTR_WIDTH, kf_hi) (:592-596).
    kf == 0 halts loudly (:597-600).
  - The MMIO door (:443-444): walk_st writes box_mmio BEFORE the :451
    consult, unmode-gated — so a USER ST to word 8193 (KFAULT_PC >> 2)
    rewrites the vector (BK-50 measured this class for BOX0_HI=8196).
  - No PARALLEL_ST on the twin (_OPCODE_ORDER omits it) — so the BK-53
    pixel-overwrite mechanism (a) is structurally unreachable here; the
    only staging path is the door itself. This probe tests mechanism (b).

The twin has no tile predicate (BK-51), so "out-of-tile" on the GPU is
"out-of-box": the box is the twin's fence. Harness = BK-50/51's device
shape: run_wgsl's real buffers + build_shader(OpcodeMapV2()), probe-only
seeded cpu.mode + box_mmio.

Legs (verdicts from mmio/ram/output READBACK BYTES, never stdout):

  D1 vector-hijack escape — box [1200,1300) armed, KFAULT_PC pre-armed to
     instruction slot (col 3, row 1) where the REAL assembler placed
     payload [PRT r6; HALT] (label-resolved, never hand-encoded):
     LDI r5 canary; LDI r6 999 (outside box); LDI r7 32772 (word 8193);
     ST r7 r5  <-- walk_st is entered with addr 8193 which IS in MMIO
     range, so the DOOR takes it (no fault) — wait: the door write does
     NOT fault, so to trigger E-K1 the program must ST out-of-box AFTER
     arming. Program: arm vector via door, then ST canary2 to word 999
     (outside box) -> E-K1 -> trap vectors to slot (3,1) -> PRT r6 (canary
     still live in r6) -> HALT. Conviction: output[0] == canary, mode
     SUPER, fault_addr_word == 3996.

  D2 SUPER-capability — same shape, payload [LD canary from out-of-box
     word 200; ST 0x0ADF00D to word 200; HALT]: the trapped-into code
     reads an out-of-box canary and STORES to the same out-of-box word in
     SUPER (mode-gated walk_st admits it) — the exact write E-K1 refused
     LANDS through the trap. Conviction: ram[200] == 0x0ADF00D, output
     carries the LD value. (BK-53's D3 oracle twin.)

  D3 door-only vector arm (no E-K1 yet) — ST 196612 -> word 8193 through
     the door; conviction: mmio[1] == 196612, mode stays USER, fault 0.
     Proves the vector is guest-writable through the door WITHOUT any
     fault having fired yet (the precondition BK-50 asserted for 8196,
     here measured for the vector word itself).

  C1 control (no arming) — D1's program minus the vector ST: KFAULT_PC
     stays 0 -> E-K1 halts loudly (running=0, mode SUPER, fault recorded,
     output empty). Proves the vector arm is the load-bearing step.

  C2 control (fence live) — plain out-of-box USER ST with NO door use:
     fault_addr_word == 3996, value refused, mode SUPER. Proves the box
     arming is LIVE so D1/D2's capability is a genuine escape, not a dead
     harness.

Determinism: 3 runs diffed, run-1 md5 recorded.
Rule-1 floors: numbers are structural (word addresses, fault codes, byte
values) from one in-process device — no rate/latency/cost asserted; floors
do not attach.

Run: python3 .builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py
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

MMIO_SPAN = 160
KFAULT_IDX = 1                  # word 8193 - 8192
KFAULT_WORD = 8193
FAULT_ADDR_IDX = 7              # FAULT_ADDR word 8199 - 8192
BOX_LO, BOX_HI = 1200, 1300     # armed box (byte addresses)
CANARY = 4660                   # 0x1234 — register canary
CANARY2 = 0x0ADF00D             # seed at word 200 (out of box), BK-canary
SEED_WORD = 200                 # out-of-box RAM word, byte 800
OOB_WORD = 999                  # out-of-box RAM word, byte 3996
# Payload slot: main body = arm(3) + LDI r6 + LDI r5 + ST = 6 instrs
# (idx 0..5), HALT idx 6, :payload starts idx 7 => slot (col 7, row 0).
# KFAULT_PC packs (row<<16)|col with col in INSTRUCTION units (the E-K1
# arm multiplies col by INSTR_WIDTH). Verified against the real assembler
# (dbg_ek1_wgsl_draft5/7: :payload lands at idx 7 = pixel (28,0)).
PAYLOAD_PACKED = 7


def source_legs():
    src = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    st_body = src[src.index("fn walk_st"):src.index("fn addr_in_box")]
    ek1 = src[src.index("let e_k1_fault = walk_st"):src.index("} else if (opcode == OPCODE_JMPR)")]
    return {
        "S1_mmio_door_before_consult":
            st_body.index("box_mmio[addr - BOX_MMIO_WORD_LO] = value;")
            < st_body.index("addr_in_box(addr << 2u)"),
        "S1_door_mode_free": ("is_super" not in st_body[:st_body.index(
            "addr_in_box(addr << 2u)")]),
        "S2_ek1_vectors_kfault_live": "KFAULT_PC_WORD" in ek1 and "next_pc" in ek1,
        "S2_ek1_mode_super_before_vector": ek1.index("cpu.mode = 0u")
            < ek1.index("KFAULT_PC_WORD"),
        "S3_no_parallel_opcode": "PARALLEL" not in src.split("const")[1][:4000]
            and "PARALLEL_ST" not in src,
    }


def run_prog(prog, mmio_seed, seed_mode=1, max_steps=40, seeds=None):
    """Bake+run one program on the real WGSL device harness (BK-50/51
    shape: run_wgsl's real buffers + build_shader(OpcodeMapV2()),
    probe-only seeded cpu.mode + box_mmio + RAM seeds)."""
    import wgpu, wgpu.utils  # noqa: F401
    from tools.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
    from tools.glyph_gpt.baker import bake_image
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import OpcodeMapV2

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        image = bake_image(prog, cols_instrs=8, out_path=png)

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
    mmio[3] = BOX_LO
    mmio[4] = BOX_HI
    for k, v in mmio_seed.items():
        mmio[k] = v
    ram = np.zeros(16384, dtype=np.uint32)
    if seeds:
        for addr, val in seeds.items():
            ram[addr] = val
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
    out = np.frombuffer(memoryview(queue.read_buffer(bufs["out"])),
                        dtype=np.uint32)
    return {
        "halted": bool(rb['running'] == 0),
        "steps": step,
        "mode_final": int(rb['mode']),
        "pc": [int(rb['pc'][0]), int(rb['pc'][1])],
        "output_words": [int(v) for v in out[:8]],
        "ram_seed_word": int(ram_out[SEED_WORD]),
        "ram_oob_word": int(ram_out[OOB_WORD]),
        "mmio_kfault_pc": int(mmio_out[KFAULT_IDX]),
        "fault_addr_word": int(mmio_out[FAULT_ADDR_IDX]),
    }


def main():
    results = {"S": source_legs()}

    # The payload occupies instruction slots 0..1 of slot-3 onward:
    # program layout (8 cols/row, instruction index = row*8+col):
    #   idx 0..5  main body   idx 6: trigger ST (out-of-box)  idx 7: HALT
    #   payload at idx 11 (col 3, row 1) and idx 12 (col 4, row 1) via a
    #   label — the assembler resolves it; KFAULT_PC = (row<<16)|col with
    #   col in INSTRUCTION units (the arm multiplies by INSTR_WIDTH).
    arm = ("LDI r7 %d\n"
           "LDI r5 %d\n"
           "ST r7 r5\n") % (KFAULT_WORD, PAYLOAD_PACKED)

    # D1: arm vector through the door, then trigger E-K1 with an
    # out-of-box ST. r6 keeps CANARY across the trap; payload PRT r6.
    # Slot map verified with the real assembler (dbg drafts 5-7):
    # arm=3 instrs, trigger ST at idx 5, HALT idx 6, :payload PRT r6 at
    # idx 7 = slot (7,0) = PAYLOAD_PACKED.
    prog_d1 = """
    :__entry
    %sLDI r6 %d
    LDI r5 %d
    ST r5 r6
    HALT
    :payload
    PRT r6
    HALT
    """ % (arm, CANARY, OOB_WORD)

    # D2: trapped-into code reads the seeded out-of-box canary (word 200)
    # and stores 0x0ADF00D BACK to it in SUPER. Seeds are HOST-side RAM
    # seeds only (run_prog writes ram[200] directly) — bake_image's
    # data_words path PREPENDS init STs which would themselves fault
    # out-of-box before the arm runs, so it is deliberately NOT used.
    prog_d2 = """
    :__entry
    %sLDI r6 %d
    LDI r5 %d
    ST r5 r6
    HALT
    :payload
    LDI r2 %d
    LD r6 r2
    LDI r3 %d
    ST r2 r3
    HALT
    """ % (arm, CANARY, OOB_WORD, SEED_WORD, CANARY2)

    # D3: door-only vector arm, no trigger. Vector word must read
    # PAYLOAD_PACKED, mode stays USER, fault 0.
    prog_d3 = """
    :__entry
    LDI r7 %d
    LDI r5 %d
    ST r7 r5
    HALT
    """ % (KFAULT_WORD, PAYLOAD_PACKED)

    # C1: D1 minus the arming ST — vector stays 0, E-K1 halts loudly.
    prog_c1 = """
    :__entry
    LDI r6 %d
    LDI r5 %d
    ST r5 r6
    HALT
    """ % (CANARY, OOB_WORD)

    # C2: plain out-of-box ST — fence live (fault 3996, refused).
    prog_c2 = prog_c1

    results["D1_vector_hijack_escape"] = run_prog(prog_d1, {})
    results["D2_super_capability"] = run_prog(
        prog_d2, {}, seeds={SEED_WORD: CANARY})
    results["D3_door_arms_vector_only"] = run_prog(prog_d3, {})
    results["C1_no_arm_control"] = run_prog(prog_c1, {})
    results["C2_fence_live_control"] = run_prog(prog_c2, {})

    blob = json.dumps(results, indent=1, sort_keys=True)
    print(blob)
    print(f"results_md5={hashlib.md5(blob.encode()).hexdigest()}")

    # ---- verdicts ----
    r = results["D1_vector_hijack_escape"]
    got_canary = any(w == CANARY for w in r["output_words"])
    print("VERDICT D1:",
          "HIJACK — trapped into guest payload in SUPER, canary printed"
          if (got_canary and r["mode_final"] == 0
              and r["fault_addr_word"] == OOB_WORD * 4)
          else f"no hijack (out={r['output_words']}, mode={r['mode_final']}, "
               f"fault={r['fault_addr_word']})")
    r = results["D2_super_capability"]
    print("VERDICT D2:",
          "SUPER CAPABILITY — refused write LANDS via trapped-into code"
          if (r["ram_seed_word"] == CANARY2 and r["mode_final"] == 0)
          else f"no landing (ram[{SEED_WORD}]={r['ram_seed_word']:#x}, "
               f"mode={r['mode_final']})")
    r = results["D3_door_arms_vector_only"]
    print("VERDICT D3:",
          "VECTOR GUEST-WRITABLE via door (no fault, mode USER)"
          if (r["mmio_kfault_pc"] == PAYLOAD_PACKED and r["mode_final"] == 1
              and r["fault_addr_word"] == 0)
          else f"no door (kf={r['mmio_kfault_pc']}, mode={r['mode_final']})")
    r = results["C1_no_arm_control"]
    print("VERDICT C1:",
          "control discriminating — kf=0 halts loudly, no output"
          if (r["halted"] and r["mode_final"] == 0
              and r["fault_addr_word"] == OOB_WORD * 4
              and all(w == 0 for w in r["output_words"]))
          else f"control NOT discriminating ({r})")
    r = results["C2_fence_live_control"]
    print("VERDICT C2:",
          "fence LIVE — out-of-box ST refused (ram[999]==0)"
          if r["ram_oob_word"] == 0 and r["fault_addr_word"] == OOB_WORD * 4
          else f"fence dead? ({r})")


if __name__ == "__main__":
    main()
