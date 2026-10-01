#!/usr/bin/env python3
"""Research tick 8 (af3e, 2026-09-28): the ORACLE side of the paged x tile
composition — the surface every prior receipt left open ("paged x tile
composition still unprobed"; tick 2's twin D3 measured the twin's paged
branch only, with 0 tile refs BY SOURCE READ, tile NOT armed).

Scope lineage (prior-art grep, rule-5):
  - Tick 2 (RESEARCH_wgsl_paged_fence_af3e.md): twin paged LD measured (D3),
    tile NOT armed; oracle paged legs (D2/D4) tile NOT armed.
  - Ticks 3-7: tile probes are all UNPAGED (spawn(tile=...) + plain LD/ST);
    paged probes (ticks 2/4/5/6/7) never arm a tile. No probe sets
    PAGE_TABLE_WORD != 0 on a tile-armed task. BK-60..65 rows: frame/flag
    fences, no tile composition.

Source prediction at HEAD cd5e0233 (tools/glyph_isa_v2.py):
  LD: the paged branch is the FIRST arm (:832 `if pt_base != 0 and ...`);
  the GO-2 tile LD fence (:917) is an `elif` reached only when pt_base == 0
  (the BK-38-landing fence). ST: identical shape — paged first (:972), the
  E-K1 box+tile arm (:1075) only when pt_base == 0. Therefore ANY task with
  a page table armed loses the tile fence on EVERY access, in-tile or not,
  and a valid PTE admits out-of-tile physical targets on both engines' oracle.

Legs (harness = GlyphProcessTable.spawn(tile=...) — the real item-29
posture; tile (256,19,1,2) covers RAM words 8211/8212 so the task can
lawfully arm paging through its own in-tile ST (PAGE_TABLE_WORD = 8211);
min_rows=64 image; PT tag @1535 + PTEs image-stamped (RAM-first, image
fallback per GH-25); verdicts from exit_status + cpu fault fields +
register/memory/image readbacks, never stdout):
  T1: tile-armed, PT armed, paged USER LD vaddr 3072 (vpn 12 — vaddr is
      ALSO out-of-tile on the fence's own predicate) through a full-flag
      PIX PTE (0x50F, pfn 5 -> image word 1280, out-of-tile physical).
      Prediction: r10 == canary 0x0ADF00D, clean — out-of-tile READ.
  T2: same posture, paged USER ST of the canary to vaddr 3072.
      Prediction: clean, canary LANDS at image word 1280 — out-of-tile
      WRITE (the unpaged arm traps this exact shape at fault_addr 5120).
  T3: tile-armed, PT armed, access to the task's OWN in-tile word 164
      (vaddr 164, PTE 0x7 -> plain RAM frame paddr 164). Prediction: lands
      clean — the fence failure direction is ADMIT-ALL, not deny-all:
      paging disarms the fence for the task's whole lifetime.
  C1: tile-armed, NO PT: unpaged out-of-tile LD word 4000 -> the landed
      BK-38 fence must trap (fault_addr 16000): fence LIVE when unpaged.
  C2: tile-armed, NO PT: unpaged out-of-tile ST word 164 -> E-K1
      (fault_addr 656): the item-29 baseline, LIVE when unpaged.
  C3: tile-armed, NO PT: in-tile LD + ST of word 164 land clean —
      harness liveness on the admitted side.

Run: python3 .builder_queue/probe_paged_tile_oracle_af3e.py
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
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211            # PAGE_TABLE_WORD (0x8000+0x4C bytes -> word 8211)
TILE = (256, 19, 1, 2)        # covers RAM words 8211, 8212 only
VA_OUT = (12 << 8) | 0        # vaddr word 3072: vpn 12, offset 0 (out-of-tile vaddr)
VPN12_PTE_WORD = PT_BASE_WORD + 12   # 1548
VPN0_PTE_WORD = PT_BASE_WORD         # 1536
PTE_PIX_FULL = 0xF | (5 << 8)        # V|W|U|PIX, pfn 5 -> image word 1280
PTE_PLAIN_VPN0 = 0x7                 # V|W|U, pfn 0 -> RAM paddr 0*256+off
FRAME_OUT_WORD = 1280
CANARY_IMG_WORD = 1280
IN_TILE_WORD = 8212           # row 256, col 20 — INSIDE tile (256,19,1,2)
OUT_TILE_LD_WORD = 4000


def bake(text):
    from tools.glyph_gpt.baker import bake_image
    return bake_image(text, cols_instrs=8, min_rows=64, out_path=None)


def stamp_image(img, stamps):
    h, w, _ = img.shape
    total = h * w
    for word, val in stamps.items():
        idx = word % total
        img[idx // w, idx % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def img_word(img, word):
    h, w, _ = img.shape
    idx = word % (h * w)
    px = img[idx // w, idx % w]
    return (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])


ARM_SNIPPET = ("LDI r15 %d\nLDI r14 %d\nST r15 r14\n"
               % (PT_ARM_WORD, PT_BASE_WORD))


def run_leg(name, text, stamps):
    from tools.glyph_process import GlyphProcessTable

    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 1549, "image must contain the PT window unwrapped"
    stamp_image(img, stamps)
    table = GlyphProcessTable(memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=500)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    table._run_task(pid)
    task_img = task["image"]
    mem = cpu.memory

    def mword(i):
        return int(mem[i]) & 0xFFFFFFFF if i < len(mem) else None

    return {
        "program": text,
        "stamps": {str(k): v for k, v in stamps.items()},
        "exit_status": task["exit_status"],
        "state": task["state"],
        "faulted": bool(cpu.faulted),
        "fault_addr": (int(cpu.fault_addr)
                       if cpu.fault_addr is not None else None),
        "fault_reason": cpu.fault_reason,
        "halt_reason": cpu.halt_reason,
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "r10": int(cpu.registers[10]) & 0xFFFFFFFF,
        "steps": int(getattr(cpu, "steps", -1)),
        "ram_pt_arm": mword(PT_ARM_WORD),
        "ram_164": mword(IN_TILE_WORD),
        "img_canary_word": img_word(task_img, CANARY_IMG_WORD),
        "img_dims": [int(w), int(h)],
    }


def legs():
    out = {}
    # T1: paged out-of-tile READ through a full-flag PIX PTE.
    out["T1_paged_out_of_tile_LD"] = run_leg(
        "T1",
        ":__entry\n" + ARM_SNIPPET
        + "LDI r15 %d\nLD r10 r15\nHALT\n" % VA_OUT,
        {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: PTE_PIX_FULL,
         CANARY_IMG_WORD: CANARY})
    # T2: paged out-of-tile WRITE through the same PTE.
    out["T2_paged_out_of_tile_ST"] = run_leg(
        "T2",
        ":__entry\n" + ARM_SNIPPET
        + "LDI r5 %d\nLDI r15 %d\nST r15 r5\nHALT\n" % (CANARY, VA_OUT),
        {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: PTE_PIX_FULL})
    # T3: paged IN-tile access — fence direction is admit-all, not deny-all.
    out["T3_paged_in_tile_ST"] = run_leg(
        "T3",
        ":__entry\n" + ARM_SNIPPET
        + "LDI r5 4660\nLDI r15 %d\nST r15 r5\nHALT\n" % IN_TILE_WORD,
        {PT_TAG_WORD: 0x505447, VPN0_PTE_WORD: PTE_PLAIN_VPN0})
    # C1: unpaged out-of-tile LD — the BK-38 fence, LIVE when pt_base == 0.
    out["C1_unpaged_out_of_tile_LD"] = run_leg(
        "C1",
        ":__entry\nLDI r15 %d\nLD r10 r15\nHALT\n" % OUT_TILE_LD_WORD,
        {})
    # C2: unpaged out-of-tile ST — the item-29 E-K1 baseline, LIVE.
    out["C2_unpaged_out_of_tile_ST"] = run_leg(
        "C2",
        ":__entry\nLDI r5 4660\nLDI r15 164\nST r15 r5\nHALT\n",
        {})
    # C3: unpaged in-tile LD+ST of word 8212 (row 256, col 20 — inside the
    # tile) — admitted side of the live fence. (Probe defect #1, fixed
    # pre-evidence: v1 used word 164 = row 5 col 4, which is OUT of tile
    # (256,19,1,2) — C3 v1 was a mis-aimed leg, both legs E-K1'd.)
    out["C3_unpaged_in_tile_LD_ST"] = run_leg(
        "C3",
        ":__entry\nLDI r15 %d\nLD r10 r15\nLDI r5 4660\nST r15 r5\nHALT\n"
        % IN_TILE_WORD,
        {})
    return out


def main():
    out = legs()
    blob = json.dumps(out, indent=1, sort_keys=True, default=str)
    print(blob)
    print("results_md5", hashlib.md5(blob.encode()).hexdigest())


if __name__ == "__main__":
    main()
