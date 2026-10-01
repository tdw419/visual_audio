#!/usr/bin/env python3
"""Research tick 9 (af3e, 2026-09-28): PC/fetch confinement under the
item-29 tile posture — the fence family's UNMEASURED third surface.

Scope lineage (prior-art grep, rule-5):
  - BK-38..45/60..66: every consult-site row governs DATA arms (LD/ST/
    PARALLEL/stack/syscall-dest/frame paths). Tick 8 closed paged x tile
    for data. NO row probes the FETCH side: glyph_isa_v2.py step() reads
    image pixels at :753-764 with zero _addr_in_box consults, and every
    jump arm (JMP :1208, JZ/JNZ/JLT/JGT, JMPR :1245, CALL :1130, RET
    :1145, CALLR :1275) sets next_pc with no fence consult.
  - BK-39 leg 4 MEASURED PUSH landing an out-of-tile IMAGE-plane pixel
    and labeled the blast radius "instruction-stream corruption class,
    RAM-grid blast radius unproven" — the EXECUTE half of that class has
    never been measured.
  - Consequence visible but never pinned: tile (256,19,1,2) covers grid
    rows 256..257 while every spawned program executes at image rows
    0..63 — i.e. every prior tile-confined leg ran its ENTIRE program
    text outside its own tile, and no receipt records the observation.

Source prediction at HEAD 2626466d (tools/glyph_isa_v2.py):
  fetch has no mode/box/tile consult; JMP/JMPR targets are unchecked
  (only _check_alignment guards col alignment, raising a LOUD
  SpatialMisalignmentFault). Prediction: a USER tile-confined task
  executes pixels at ANY row, and composed with BK-39's fence-blind
  PUSH image write it can inject + execute code OUTSIDE its tile.

Legs (harness = GlyphProcessTable.spawn(tile=(256,19,1,2)) — the real
item-29 posture, same as tick 8; NO paging this tick — fetch never
translates on the oracle BY SOURCE READ (:753 reads image directly),
the paged-fetch sibling is a source-read note, not probed; verdicts
from exit_status + cpu fault fields + registers, never stdout):
  F0: in-program JMP control — jump machinery live in this harness
      (jump to :next, continue, HALT clean).
  F1: fetch-confinement census — manual step-loop over a 3-instruction
      program, recording cpu.pc per step. Prediction: every PC row in
      0..63 (OUT of tile rows 256..257), program runs clean — the task
      never executes a single instruction inside its own tile.
  F2: execute pre-stamped out-of-tile code — probe stamps the 4 pixels
      of `LDI r10 0x0ADF00D` at image word 40*32 (row 40, OUT of tile),
      program does LDI r15 (40<<16); JMPR r15. Prediction: injected-row
      code executes, r10 == canary, clean exit.
  F3: full injection composition — the task ITSELF writes the same 4
      instruction pixels to row 50 via four fence-blind PUSHes (BK-39
      leg-4 primitive, pre-decrement, descending r31), then JMPRs there.
      Prediction: pixels land (no trap), injected LDI executes,
      r10 == canary — arbitrary code injection + execution outside the
      confined rectangle, composed from two fence-blind surfaces.
  C1: data-side fence control — unpaged out-of-tile ST word 164 traps
      (fault_addr 656): the fence is LIVE for data in the SAME posture
      where F2/F3 execute out-of-tile — the probe is discriminating.

Run: python3 .builder_queue/probe_fetch_confinement_af3e.py
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

CANARY = 0x0ADF00D
TILE = (256, 19, 1, 2)   # grid rows 256..257, cols 19..20 — words 8211/8212
INJECTED_ROW_F2 = 40     # image row 40 — OUT of tile (any row < 256 is)
INJECTED_ROW_F3 = 50     # avoid row 30 (the reaper trampoline row)
CANARY_LDI_WORDS = [     # `LDI r10 0x0ADF00D` = 4 pixels
    ("opcode", None),    # opcode color resolved at runtime from OpcodeMapV2
    ("reg", (0, 0, 10)),  # rs1=0 rs2=0 rd=10
    ("low", (0xAD, 0xF0, 0x0D)),   # low24 of the immediate (0x0ADF00D < 2^24)
    ("high", (0, 0, 0)),  # high24 = 0
]


def bake(text):
    from tools.glyph_gpt.baker import bake_image
    return bake_image(text, cols_instrs=8, min_rows=64, out_path=None)


def stamp_image(img, stamps):
    h, w, _ = img.shape
    for word, val in stamps.items():
        idx = int(word) % (h * w)
        img[idx // w, idx % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def stamp_pixels(img, row, col, pixels):
    for k, rgb in enumerate(pixels):
        img[row, col + k] = rgb
    return img


def img_word(img, word):
    h, w, _ = img.shape
    idx = word % (h * w)
    px = img[idx // w, idx % w]
    return (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])


def ldi_r10_pixels():
    from tools.glyph_isa_v2 import OpcodeMapV2
    rgb = OpcodeMapV2().opcode_to_rgb("LDI")
    return [tuple(int(v) for v in rgb),
            CANARY_LDI_WORDS[1][1], CANARY_LDI_WORDS[2][1],
            CANARY_LDI_WORDS[3][1]]


def run_leg(name, text, stamps=None, inject_pixels=None, inject_row=None,
            pc_trace=False, max_steps=200):
    from tools.glyph_process import GlyphProcessTable

    img = bake(text)
    h, w, _ = img.shape
    if stamps:
        stamp_image(img, stamps)
    if inject_pixels:
        stamp_pixels(img, inject_row, 0, inject_pixels)
    table = GlyphProcessTable(memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=500)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    if pc_trace:
        trace = []
        cpu.running = True
        for _ in range(max_steps):
            if not cpu.running:
                break
            trace.append([int(cpu.pc[0]), int(cpu.pc[1])])
            cpu.step(task["image"])
            if cpu.halt_reason is not None:
                break
        pc_rows = sorted({r for _, r in trace})
        table.tasks[pid]["exit_status"] = 0 if not cpu.faulted else 1
        task["state"] = "exited"
        return {
            "program": text,
            "exit_status": table.tasks[pid]["exit_status"],
            "faulted": bool(cpu.faulted),
            "fault_addr": (int(cpu.fault_addr)
                           if cpu.fault_addr is not None else None),
            "fault_reason": cpu.fault_reason,
            "halt_reason": cpu.halt_reason,
            "mode_final": "USER" if cpu.mode == 1 else "SUPER",
            "r10": int(cpu.registers[10]) & 0xFFFFFFFF,
            "pc_rows_visited": pc_rows,
            "pc_trace_first12": trace[:12],
            "tile": list(TILE),
            "img_dims": [int(w), int(h)],
        }
    table._run_task(pid)
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
        "injected_word0": (img_word(task["image"], inject_row * 32)
                           if inject_row is not None else None),
        "tile": list(TILE),
        "img_dims": [int(w), int(h)],
    }


def legs():
    from tools.glyph_isa_v2 import INSTR_WIDTH
    out = {}

    # F0: in-program JMP control.
    out["F0_in_program_JMP_control"] = run_leg(
        "F0",
        ":__entry\nLDI r5 1\nJMP 2,0\nPRT r5\nHALT\n:nop\n:nop\n:nop\n:nop\n")

    # F1: fetch-confinement census (PC trace).
    out["F1_fetch_pc_census"] = run_leg(
        "F1",
        ":__entry\nLDI r10 %d\nLDI r5 1\nHALT\n" % CANARY,
        pc_trace=True)

    # F2: execute pre-stamped out-of-tile code via JMPR.
    tgt = (INJECTED_ROW_F2 << 16) | 0
    out["F2_jmpr_execute_out_of_tile"] = run_leg(
        "F2",
        ":__entry\nLDI r15 %d\nJMPR r15\nHALT\n" % tgt,
        inject_pixels=ldi_r10_pixels(), inject_row=INJECTED_ROW_F2)

    # F3: full injection composition — PUSH-written pixels, then execute.
    # PUSH pre-decrements r31 and writes ONE image pixel at r31-1
    # (row-major, width 32 px). Inject at row 50 cols 0..3:
    #   r31=1601 -> pixel 1600 (opcode px); 1602 -> 1601 (reg px);
    #   1603 -> 1602 (low px); 1604 -> 1603 (high px).
    px = ldi_r10_pixels()
    base = INJECTED_ROW_F3 * 32
    push_seq = "\n".join(
        "LDI r31 %d\nLDI r5 %d\nPUSH r5" % (base + 1 + k,
                                            (px[k][0] << 16) | (px[k][1] << 8) | px[k][2])
        for k in range(4))
    tgt3 = (INJECTED_ROW_F3 << 16) | 0
    out["F3_push_inject_then_execute"] = run_leg(
        "F3",
        ":__entry\n" + push_seq + "\nLDI r15 %d\nJMPR r15\nHALT\n" % tgt3,
        inject_row=INJECTED_ROW_F3)

    # C1: data-side fence control — the SAME posture traps an out-of-tile ST.
    out["C1_unpaged_out_of_tile_ST_control"] = run_leg(
        "C1",
        ":__entry\nLDI r5 4660\nLDI r15 164\nST r15 r5\nHALT\n")

    # Liveness note: confirm INSTR_WIDTH sanity (4 px per instruction).
    out["_meta"] = {"instr_width": INSTR_WIDTH, "tile": list(TILE)}
    return out


def main():
    results = legs()
    payload = json.dumps(results, sort_keys=True, indent=1)
    digest = hashlib.md5(payload.encode()).hexdigest()
    print(payload)
    print("results_md5 %s" % digest)
    out_path = HERE / ("probe_fetch_confinement_af3e_results.json")
    out_path.write_text(payload)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
