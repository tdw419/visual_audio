#!/usr/bin/env python3
"""Research tick 13 (af3e, 2026-09-28): paged rewrite of the KFAULT_PC
VECTOR WORD itself (RAM word 8193 = 0x8004, BOX_MMIO_BASE+4) — the open
NOT-proved sibling from tick 12. Tick 12 rewrote the reaper TRAMPOLINE
PIXELS (image words 960..963); the vector word 8193 lived in RAM, left
unmapped, and every verdict read cpu.memory[8193] == 1966080 == (30<<16).
This tick asks: can a tile-confined USER task REWRITE the vector word
through translation, so that the NEXT fault vectors wherever the task
chooses — including a row the reaper never planted?

Source posture (read, not assumed):
  - LD  paged arm glyph_isa_v2.py:836 and ST paged arm :968: translation
    applies UNLESS `mode == SUPER and BOX_MMIO window` — a USER task's
    access to a vaddr that TRANSLATES to word 8193 goes through the paged
    branch (tick 12's receipt predicted exactly this: the SUPER MMIO
    exemption is USER-scoped).
  - The E-K1 trap vectoring arm :1086 reads `kf = self.memory[8193]`
    LIVE from RAM — no image involvement, no re-check. If the task's
    paged ST lands at RAM word 8193, the next trap vectors to the task's
    own packed PC.
  - The tick-12 finding still holds underneath: arming paging DISARMS
    the tile fence (paged branch first in both LD/ST), so the rewrite
    itself is lawful-from-the-task's-view (BK-66).
  - BK-56's read posture (69a53298) blinds USER LD of the MMIO window to
    AIMING (the task cannot READ 8193 to learn the reaper row), but the
    task does not need to read it to WRITE a vaddr that translates there
    — the blind-write variant the postfix recheck receipt called "not
    dead". This probe is that blind-write, THROUGH TRANSLATION.

Prior-art grep (rule-5, before harness build):
  - BK-53/55: vector rewrite via UNPAGED primitives (PARALLEL_ST / twin
    box_mmio door) — never through a pte_translated USER ST.
  - Tick 12 (BK-70): trampoline PIXELS paged-rewritten; vector WORD
    explicitly left unmapped/UNMEASURED.
  - BK-56/postfix recheck: USER MMIO READ returns 0 (aim de-fang);
    blind WRITE via the translation path never probed.
  - No row composes paging x vector-word rewrite. Net-new.

Legs (oracle only — twin has no tile predicate, BK-51; spawn(tile=...)
posture, same as tick 12; PT armed by the task's own lawful in-tile ST
to word 8211, tag 0x505447 at word 1535, PT base word 1536):
  V1  vector-word rewrite: vpn 33 PTE (V|W|U, NO PIX flag — RAM frame,
      pfn 32) at PT word 1569 maps vaddr 8449 (=(33<<8)|1) -> paddr =
      32*256+1 = 8193 = the KFAULT_PC word IN RAM (plain-page arm,
      glyph_isa_v2.py:1038-1074). One ST: LDI r5 <packed (30<<16)|8>
      (reaper row, col 8, NOT the planted trampoline col 0) then
      ST r6 r5 with r6=8449. Then a paged LD via UNMAPPED vpn 20 ->
      pte_invalid fault -> the pte_invalid vectoring arm reads kf LIVE
      from RAM (:890) -> vectors to (8*4, 30) = (32,30) pixel. The
      pixels at (8..11, 30) are ZERO, so the engine opcode-None-halts
      AT the redirected site: observable = kf_word_after == 1966344
      (redirect, not the planted 1966080), final PC on row 30 col 32,
      vs tick-12 R1/C2 which land on the REAL HALT at col 0. The
      redirect itself is the finding; execution of task-chosen code at
      the redirect is V2.
  V2  full compose: same V1 rewrite, plus PIX-frame stores painting the
      attacker PRT payload at words 1952..1955 = pixel (32..35, 30) —
      exactly where the redirected kf col 8 vectors (x = 8*4) — then the
      unmapped-vpn LD faults: expected cpu.output == [3235] (the PRT
      prints r6 = the last store address), attacker code EXECUTED at the
      task-chosen vector in SUPER; loud opcode-None tail at (36,30)
      disclosed.
  C1  control: same V1 but the vpn-33 PTE left 0 (no mapping): the
      rewrite ST itself pte_invalid-faults (vpn 33 unmapped), vectors to
      the REAL trampoline (col 0, kf still 1966080), parked exit 1 —
      proves the rewrite went through TRANSLATION, not some fence hole.
  C2  rot-guard: tick-12 R1 verbatim (no rewrite at all) — kf word reads
      back 1966080 in every leg as the arm-value pin.

Verdicts from exit_status + fault fields + cpu.output + kf readback +
final PC BYTES, never stdout. Opcode colors resolved at runtime from
OpcodeMapV2, never hand-encoded. 3 pinned runs, results md5 recorded.
Run: python3 .builder_queue/probe_kf_paged_af3e.py
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

CANARY = 0x0ADF00D                     # same canary as ticks 9-12
PRT_CANARY = 0x34                      # attacker PRT payload prints this
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211                     # PAGE_TABLE_WORD (word index)
TILE = (256, 19, 1, 2)                 # covers RAM words 8211/8212 only
VPN33_PTE_WORD = PT_BASE_WORD + 33     # 1569
VPN12_PTE_WORD = PT_BASE_WORD + 12     # 1548 (tick-12 trampoline PTE)
PTE_RAM_PFN32 = 0x7 | (32 << 8)        # V|W|U, RAM frame pfn 32 -> words 8192..8447
PTE_PIX_PFN3 = 0xF | (3 << 8)          # tick-12: pfn 3 -> words 768..1023
VA_KF = (33 << 8) | 1                  # 8449 -> paddr 8193 = KFAULT_PC word
VA_REWRITE0 = (12 << 8) + 192          # 3264..3267 -> words 960..963
REDIRECT_ROW = 30
REDIRECT_COL = 8                       # NOT the planted trampoline col 0
REDIRECT_PC = (REDIRECT_ROW << 16) | REDIRECT_COL   # 1966344
ATTACKER_WORD0 = REDIRECT_ROW * 64 + REDIRECT_COL * 4  # 1952 (w=64, x=8*4)
KF_WORD = 8193
ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD,
                                                        PT_BASE_WORD)
UNMAPPED_LD = "LDI r2 5120\nLD r3 r2\n"             # vaddr 5120 = vpn 20


def bake(text):
    from tools.glyph_gpt.baker import bake_image
    return bake_image(text, cols_instrs=16, min_rows=64, out_path=None)


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


def attacker_pixel_words():
    """4 pixel-words at the redirect site: `PRT r6` + canary + zeros."""
    from tools.glyph_isa_v2 import OpcodeMapV2
    r, g, b = (int(v) for v in OpcodeMapV2().opcode_to_rgb("PRT"))
    return [(r << 16) | (g << 8) | b, 6, PRT_CANARY, 0]


def run_leg(text, stamps=None):
    """Real spawn(tile=...) posture: the TABLE arms the reaper
    (KFAULT_PC = 30<<16 = 1966080) and wraps the image (HALT at (0,30))."""
    from tools.glyph_process import GlyphProcessTable

    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 1570, "image must contain the PT window unwrapped"
    # The redirect target (8*INSTR_WIDTH, 30) must be INSIDE the image or
    # the engine walk-offs before executing the payload (measured run-1
    # defect: 32x64 image -> walk-off at (32,30), payload never ran).
    assert w > REDIRECT_COL * 4 + 4, (
        f"image width {w} too narrow for redirect col {REDIRECT_COL}")
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=500)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
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
        "output": [int(v) for v in cpu.output],
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "kf_word_after": int(cpu.memory[KF_WORD]),
        "redirect_pixels": [img_word(task["image"], ATTACKER_WORD0 + k)
                            for k in range(4)],
    }


def legs():
    out = {}
    rw = attacker_pixel_words()

    # V1: paged rewrite of the VECTOR WORD (vaddr 8449 -> word 8193),
    # value = redirect PC (row 30, col 8). Then unmapped-vpn LD faults ->
    # pte_invalid vectoring reads kf LIVE -> redirected to (8*4, 30) on
    # zero pixels. Observable: kf_word_after == 1966344, final PC on
    # row 30 col >= 32, opcode-None halt (zero pixel), output [].
    rewrite = ("LDI r5 %d\nLDI r6 %d\nST r6 r5\n"
               % (REDIRECT_PC, VA_KF))
    out["V1_vector_word_paged_rewrite_redirect"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + rewrite + UNMAPPED_LD + "HALT\n",
        {PT_TAG_WORD: 0x505447, VPN33_PTE_WORD: PTE_RAM_PFN32})

    # V2: full compose — ALSO rewrite the trampoline pixels AT the redirect
    # site. w=64, engine cols_instrs=16 (row_width 64 px): kf col 8 vectors
    # to pixel x = 8*INSTR_WIDTH = 32, row 30 -> image word 30*64+32 = 1952.
    # PIX PTE pfn 7 covers words 1792..2047; offset 160 -> vaddrs 3232..3235.
    VPN12B_PTE_WORD = PT_BASE_WORD + 12  # same vpn 12, PTE now pfn 7
    PTE_PIX_PFN7 = 0xF | (7 << 8)        # V|W|U|PIX -> words 1792..2047
    attacker_word0 = REDIRECT_ROW * 64 + REDIRECT_COL * 4  # 1952 (x=32)
    assert 1792 <= attacker_word0 < 2048, "redirect pixels outside pfn-7 frame"
    attacker_stores = "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5"
        % (rw[k], (12 << 8) + (attacker_word0 - 1792) + k)
        for k in range(4))
    out["V2_vector_word_plus_trampoline_compose"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + rewrite + attacker_stores
        + "\n" + UNMAPPED_LD + "HALT\n",
        {PT_TAG_WORD: 0x505447,
         VPN12B_PTE_WORD: PTE_PIX_PFN7,
         VPN33_PTE_WORD: PTE_RAM_PFN32})

    # C1: vpn-33 PTE left 0 — the rewrite ST itself faults pte_invalid
    # (no translation available), vectors to the REAL trampoline; kf word
    # must still read 1966080 (never rewritten).
    out["C1_no_translation_rewrite_faults"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + rewrite + UNMAPPED_LD + "HALT\n",
        {PT_TAG_WORD: 0x505447})

    # C2 rot-guard: tick-12 R1 verbatim — arm paging, no rewrite, unmapped
    # LD vectors to the REAL HALT, kf untouched.
    out["C2_tick12_R1_rotguard"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + UNMAPPED_LD + "HALT\n",
        {PT_TAG_WORD: 0x505447})

    return out


def main():
    results = legs()
    blob = json.dumps(results, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_kf_paged_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": results, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
