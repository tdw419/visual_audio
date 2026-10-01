#!/usr/bin/env python3
"""Research tick 12 (af3e, 2026-09-28): the item-29 REAPER TRAMPOLINE x
BK-66's paged fence-disarm — does the containment mechanism's own catcher
hold when the task can write through translation? The composition no prior
row measured.

Scope lineage (prior-art grep, rule-5, done BEFORE harness build):
  - BK-53 / BK-55: the E-K1 ST trap VECTOR hijack (rewrite KFAULT_PC /
    trampoline pixels via PARALLEL_ST or the twin's box_mmio door) — both
    UNPAGED postures; D5 used BK-39's fence-blind PARALLEL_ST, not paging.
  - BK-66: arming paging DISARMS the tile fence (paged branch is the first
    arm) — measured for LD/ST of DATA words; the trap path never fires in
    its legs, so the trampoline never enters scope.
  - BK-69 (tick 11): paged DATA-write x raw fetch composes into code
    injection with paging armed — but its legs NEVER TRAP (JMPR, no E-K1);
    KFAULT_PC / the reaper are not in scope.
  - BK-52: KFAULT_PC==0 semantics (replay-and-land), unpaged, no reaper.
  - Item-29 landing: a TILED spawn ALWAYS arms a reaper vector (KFAULT_PC
    nonzero, HALT planted at (0, DEFAULT_REAPER_ROW=30)) — so every
    BK-66-class paged out-of-tile store in a real spawn posture is a
    potential trap INTO a trampoline the task may be able to rewrite.
  - No RESEARCH_*/backlog row arms paging AND lets the paged fault path
    (tag gate or pte_invalid) vector into the reaper. Net-new.

The composition this probe measures (oracle only this tick — the twin has
no tile predicate at all, BK-51, so a reaper-composition leg is not
expressible until BK-51 lands; disclosed in the receipt):
  In the REAL spawn(tile=(256,19,1,2)) posture the table arms the reaper
  (KFAULT_PC = 30<<16) and wraps the image with wrap_with_reaper (HALT at
  pixel (0,30), word 960). The task lawfully arms paging via its own
  in-tile ST to word 8211 (BK-66). From then on translation replaces the
  fence — so:
  R1  paged-fault vector control: a paged LD through an UNMAPPED vpn
      faults pte_invalid and vectors KFAULT_PC -> the reaper trampoline
      HALT at (0,30) (mode SUPER, parked). Pins the honest reaper behavior
      under paging (rot-guard for the composition).
  R2  PAGED REWRITE of the trampoline pixels: four paged USER STs (vpn 12
      PIX PTE 0x50F pfn 5 -> image words 1280..1283 = row 40) — NO, row 40
      is NOT the reaper. The reaper is word 960 = row 30 col 0..3 (w=32).
      Same PTE class (PIX pfn 3 -> word 768..1023 covers 960): vpn 12 PTE
      pfn 3, vaddrs 3072..3075 -> words 768..771. WRONG — 960 = pfn 3
      offset 192. PAGE_WORDS=256, so pfn 3 covers 768..1023, offset 192
      = vaddr (12<<8)+192..195. Single PTE, four STs at vaddrs
      3072+192..3072+195. The rewrite lands fence-blind (BK-66 T2 class);
      the pixels at (0..3, 30) are now PRT r6 / canary / 0 / 0.
  R3  DELIVER: task then does a paged LD through an UNMAPPED vpn — the
      pte_invalid fault vectors KFAULT_PC to (0,30) and SUPER-executes
      the REWRITTEN trampoline: PRT prints the attacker canary. The
      containment mechanism's own catcher is the injection target —
      no trampoline overwrite via the trap door (BK-53) needed; the task
      rewrote it THROUGH TRANSLATION, lawfully, before any fault.
  C1  no-paging control: same R2 store shape unpaged -> E-K1 traps 5120
      (word 1280-class word; here use 771's physical word 771, fault
      3084), trampoline pixels untouched, task parked at the REAL HALT.
  C2  no-rewrite control: arm paging, rewrite NOTHING, paged unmapped LD
      -> vectors to (0,30), executes the REAL HALT (clean stop). Pins
      that R3's canary needs BOTH halves (paging + rewrite).

Run: python3 .builder_queue/probe_reaper_paged_af3e.py
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

CANARY = 0x0ADF00D                     # 11399181, same canary as ticks 9-11
PRT_CANARY = 0x34                      # attacker PRT payload prints this
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211                     # PAGE_TABLE_WORD (word index)
TILE = (256, 19, 1, 2)                 # covers RAM words 8211/8212 only
VPN12_PTE_WORD = PT_BASE_WORD + 12     # 1548
PTE_PIX_FULL = 0xF | (3 << 8)          # V|W|U|PIX, pfn 3 -> words 768..1023
REAPER_WORD0 = 30 * 32                 # 960: reaper row col 0 (w=32)
REAPER_FIRST_OFFSET = REAPER_WORD0 - 3 * 256   # 192 inside pfn-3 frame
VA_REWRITE0 = (12 << 8) + REAPER_FIRST_OFFSET  # 3264..3267 -> words 960..963
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


def rewrite_pixel_words():
    """The 4 pixel-words of `PRT r6` + canary + 2 zero pixels; opcode
    color from OpcodeMapV2 at runtime, never hand-encoded."""
    from tools.glyph_isa_v2 import OpcodeMapV2
    r, g, b = (int(v) for v in OpcodeMapV2().opcode_to_rgb("PRT"))
    return [(r << 16) | (g << 8) | b, 6, PRT_CANARY, 0]


def run_leg(text, stamps=None):
    """Real spawn(tile=...) posture: the table itself arms the reaper
    (KFAULT_PC = 30<<16) and wraps the image (HALT at pixel (0,30))."""
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
        "output": [int(v) for v in cpu.output],
        "trampoline_words": [img_word(task_img, REAPER_WORD0 + k)
                             for k in range(4)],
        "kf_word": int(cpu.memory[8193]),
        "img_dims": [int(w), int(h)],
    }


def legs():
    out = {}
    rw = rewrite_pixel_words()

    # R1: paged-fault vector control — paged LD via UNMAPPED vpn 20
    # (pte_idx 1556, PTE 0) -> pte_invalid -> vector to reaper HALT.
    out["R1_paged_fault_vectors_to_reaper"] = run_leg(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r2 5120\nLD r3 r2\nHALT\n",          # vaddr 5120 = vpn 20
        {PT_TAG_WORD: 0x505447})

    # R2+R3: paged rewrite of the trampoline pixels, then a paged
    # unmapped LD whose fault vectors into the rewritten trampoline.
    store_seq = "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5" % (rw[k], VA_REWRITE0 + k)
        for k in range(4))
    out["R3_paged_reaper_rewrite_then_fault_execute"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + store_seq
        + "\nLDI r2 5120\nLD r3 r2\nHALT\n",
        {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: PTE_PIX_FULL})

    # C1: no paging — the same rewrite stores are E-K1 traps; trampoline
    # pixels must be untouched (real HALT at word 960).
    out["C1_unpaged_rewrite_traps"] = run_leg(
        ":__entry\n" + store_seq + "\nLDI r2 5120\nLD r3 r2\nHALT\n", {})

    # C2: paging armed, NO rewrite — fault vectors to the REAL HALT.
    out["C2_paged_fault_real_trampoline"] = run_leg(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r2 5120\nLD r3 r2\nHALT\n",
        {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: 0})

    return out


def main():
    results = legs()
    blob = json.dumps(results, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_reaper_paged_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": results, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
