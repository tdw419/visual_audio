#!/usr/bin/env python3
"""Research tick 16 v2 (af3e, 2026-09-28): SYSRET resume-PC hijack via a
paged rewrite of SYSCALL_PC (RAM word 8201) from inside the SUPER dispatcher.

v2 CORRECTION of the on-disk probe_sysret_pc_af3e.py (uncommitted, never
landed): v1 targeted word 8205 believing it was SYSCALL_PC. Live enum read
this session pins the E-K2 block: SYSCALL_PC_ADDR = BOX_MMIO_BASE+0x24 ->
word 8201; word 8205 is SYS_A0_ADDR (0x8034>>2) — v1's own C2 fault line
(vaddr=0x8034) says so. Worse, SYS_A0 is a WRONG-write surface: the engine
overwrites it at dispatch marshal (:1178) and consumes it at SYSRET
(:1201), so v1's T1 could not have discriminated anything about the resume
PC. This v2 aims the guest rewrite at word 8201 (vaddr 0x8024) and moves
the write INTO the SUPER dispatcher (the only writer that runs after the
engine's own save at :1183-1186, which would clobber a USER-side write).

Mechanism under test (tools/glyph_isa_v2.py:1159-1208): SYSCALL saves the
USER resume PC into word 8201 (packed (row<<16)|col, :1183-1186), drops to
SUPER, jumps to the ksys dispatcher. SYSRET (:1193-1208) reads word 8201
back and turns it into the resume PC — restore regs, mode=USER,
next_pc=(col*INSTR_WIDTH, row) — with NO fence/box/tile consult on the
packed target (same unchecked-jump shape as KJMP/JMP). If a guest-chosen
dispatcher writes word 8205 (SYS_A0, :1201 delivers it to r10) and word
8201 (the resume PC) before SYSRET, the guest chooses where USER execution
resumes AFTER having executed code in SUPER — a full round trip: USER ->
SUPER (tick-15 primitive) -> back to a USER address of the guest's
choosing, no fault anywhere.

Posture (kernel-shaped, BK-41 lineage): ksys armed HOST-SIDE after spawn
(plain RAM write to word 8194 = the loader seed the E-K2 comment describes,
glyph_isa_v2.py:1171 "loader-seeded, packed pixel PC") to a dispatcher the
guest ALSO painted. The write under test is the dispatcher's PAGED ST to
word 8201 — the sanctioned translation path (vpn-32 plain-frame PTE pfn
32: vaddr 0x8024 -> paddr 8201, outside tile words {8211,8212}), exactly
the write class the 9714a363 paddr-consult posture exists to close. Note
the dispatcher's ST is a SUPER-mode access to the MMIO window (8192..8448):
:968 EXEMPTS it from the paged walk, so by source it lands raw at
memory[addr] — v2 MEASURES whether the exemption admits guest code running
in SUPER (the :971-972 exemption question tick 15 left open).

Legs:
  T1  dispatcher paged-writes word 8201 = 1966136 = (30<<16)|8 (the
      attacker gadget's packed PC, gadget = LDI r2 52; PRT r2; HALT painted
      at row 30 col 8) and word 8205 = 52 (a0 clobber), then SYSRET.
      Expected if the family holds: output [77, 52] (dispatcher PRT then
      ATTACKER PRT), mode USER, final PC (32, 30) = the gadget's HALT,
      syspc_word 8201 readback 1966136, sysa0_word 8205 readback 52 —
      resume control stolen from the kernel's saved PC, no fault.
  T2  CONTROL, dispatcher SYSRETs WITHOUT rewriting: output [77, 99]
      (dispatcher PRT 77, then post-SYSCALL LDI r3 99 ... wait: r3 marker
      is printed? No — a0 echo: :1201 sets r10 = memory[8205] AFTER the
      restore; the engine wrote r10's syscall value to 8205 at :1178, so
      r10 reads back the task's own syscall a0. Output [77] plus the
      post-SYSRET LDI r3 99 completes; final PC = the post-SYSCALL HALT;
      word 8201 readback = the engine's TRUE saved resume PC — the value
      T1's rewrite displaces. T1 vs T2 differ ONLY in the dispatcher's two
      stores, isolating their effect to the two words.
  C1  NO-TRANSLATION control: vpn-32 PTE left 0 — the dispatcher's ST to
      vaddr 0x8024 pte_invalids (byte 32808) MID-DISPATCH in SUPER,
      vectors through the live kf read to the REAL reaper trampoline
      (col 0, row 30), parked exit 1: output [77] only, no SYSRET, no
      resume. Proves the dispatcher rewrite REQUIRED translation, and that
      even a hostile dispatcher's own fault lands on the (guest-known)
      reaper — composition depth, disclosed.
  C2  ROT-GUARD: unpaged out-of-tile ST to word 8201, NO PT armed — the
      E-K1 tile fence must trap (fault_addr 8201*4 = 32804, BK-66-C2
      shape, SYSCALL_PC flavor). The fence is live for this word when
      translation is not armed.

Verdicts from exit_status + fault fields + cpu.output + final PC + RAM
readback (words 8194/8201/8205) BYTES, never stdout. Dispatcher/gadget
instruction words from the REAL GlyphAssemblerV2, never hand-encoded
colors. 3 pinned runs byte-identical, results md5 recorded.
Run: python3 .builder_queue/probe_sysret_pc_v2_af3e.py
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

PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211                     # PAGE_TABLE_WORD (word index)
TILE = (256, 19, 1, 2)                 # covers RAM words 8211/8212 only
VPN32_PTE_WORD = PT_BASE_WORD + 32     # 1568
VPN12_PTE_WORD = PT_BASE_WORD + 12     # 1548
PTE_RAM_PFN32 = 0x7 | (32 << 8)        # V|W|U, RAM frame pfn 32 -> words 8192..8447
PTE_PIX_PFN7 = 0xF | (7 << 8)          # V|W|U|PIX -> image words 1792..2047
VA_SYSPC = (32 << 8) + 0x24 - 256 + 256  # vpn-32 offset 0x24 -> paddr 8201 (word math below)
VA_SYSPC = (32 << 8) + 36              # vpn-32 frame base 8192 + offset 36 -> 8201... see assert
# NOTE: vpn-32 PTE pfn 32 maps vaddr 8192+off -> paddr 8192+off. SYSCALL_PC
# word 8201 = 8192 + 9? No: PAGE_WORDS=256, vpn 32 covers WORDS 8192..8447,
# vaddr IS the word index (addr is pre-shift word units). vaddr 8201 -> paddr 8201.
VA_SYSPC = 8201
WORD_SYSPC = 8201                      # SYSCALL_PC_ADDR >> 2 (BOX_MMIO+0x24)
WORD_SYSA0 = 8205                      # SYS_A0_ADDR >> 2 (BOX_MMIO+0x34)
WORD_KSYS = 8194
HIJACK_ROW, HIJACK_COL = 30, 8         # NOT the resume row, NOT trampoline col 0
HIJACK_PACKED = (HIJACK_ROW << 16) | HIJACK_COL   # 1966136
ATTACKER_WORD0 = HIJACK_ROW * 64 + HIJACK_COL * 4  # w=64, x=col*4 -> 1952
DISPATCH_ROW, DISPATCH_COL = 28, 8
DISPATCH_WORD0 = DISPATCH_ROW * 64 + DISPATCH_COL * 4  # 1856
assert 1792 <= ATTACKER_WORD0 < 2048, "attacker gadget in vpn-12 PIX pfn 7"
assert 1792 <= DISPATCH_WORD0 < 2048, "dispatcher in vpn-12 PIX pfn 7"
assert ATTACKER_WORD0 != DISPATCH_WORD0
assert VA_SYSPC == WORD_SYSPC == 8201, "v2 aims SYSCALL_PC (8201), not SYS_A0"
GADGET_LINES = ["LDI r2 52", "PRT r2", "HALT"]           # at (30,8)
DISPATCH_LINES_HIJACK = ["LDI r9 77", "PRT r9",
                         "LDI r6 %d" % HIJACK_PACKED,
                         "LDI r7 %d" % WORD_SYSPC,
                         "ST r7 r6",
                         "LDI r6 52",
                         "LDI r7 %d" % WORD_SYSA0,
                         "ST r7 r6",
                         "SYSRET"]                        # at (28,8)
DISPATCH_LINES_CLEAN = ["LDI r9 77", "PRT r9", "SYSRET"]  # at (28,8)
ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD,
                                                        PT_BASE_WORD)


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


def assembled_words(lines, width_instrs=16):
    """Instruction words straight from the real assembler."""
    from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
    img = GlyphAssemblerV2(OpcodeMapV2()).assemble(
        lines, width_instrs=width_instrs)
    words = []
    total = img.shape[0] * img.shape[1]
    for i in range(total):
        px = img[i // img.shape[1], i % img.shape[1]]
        words.append((int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2]))
        if len(words) >= 4 * len(lines):
            break
    assert len(words) == 4 * len(lines)
    return words


def paint_stores(lines, base_word0):
    """Paged STs painting `lines` at base_word0 via vpn 12 -> PIX pfn 7
    (frame base word 1792)."""
    words = assembled_words(lines)
    frame0 = 1792
    return "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5"
        % (words[k], (12 << 8) + (base_word0 - frame0) + k)
        for k in range(len(words)))


def run_leg(text, stamps=None, max_instructions=3000):
    from tools.glyph_process import GlyphProcessTable
    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 1570, "image must contain the PT window unwrapped"
    assert w > (HIJACK_COL * 4 + 16), "image too narrow for gadget row"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=max_instructions)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    # kernel-shaped posture: host-arms KSYS_PC to the dispatcher the task
    # painted at (28,8) — the loader seed the E-K2 comment describes.
    cpu.memory[WORD_KSYS] = (DISPATCH_ROW << 16) | DISPATCH_COL
    table._run_task(pid)
    return {
        "exit_status": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "fault_addr": (int(cpu.fault_addr)
                       if cpu.fault_addr is not None else None),
        "fault_reason": cpu.fault_reason,
        "halt_reason": (None if cpu.halt_reason is None
                        else str(cpu.halt_reason)),
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "output": [int(v) for v in cpu.output],
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "ksys_word_after": int(cpu.memory[WORD_KSYS]),
        "syspc_word_after": int(cpu.memory[WORD_SYSPC]),
        "sysa0_word_after": int(cpu.memory[WORD_SYSA0]),
        "gadget_pixels": [img_word(task["image"], ATTACKER_WORD0 + k)
                          for k in range(4 * len(GADGET_LINES))],
        "dispatch_pixels": [img_word(task["image"], DISPATCH_WORD0 + k)
                            for k in range(4 * len(DISPATCH_LINES_HIJACK))],
    }


def main():
    out = {}

    paint = (paint_stores(GADGET_LINES, ATTACKER_WORD0) + "\n"
             + paint_stores(DISPATCH_LINES_HIJACK, DISPATCH_WORD0) + "\n")
    tail = ":post_sys\nLDI r3 99\nSYSCALL r10 6\nLDI r3 99\nHALT\n"

    # T1: arm PT -> paint payloads -> SYSCALL; the HIJACKING dispatcher
    # paged-writes word 8201 (resume PC -> the gadget) + word 8205 (a0=52)
    # then SYSRETs. Discriminator = output sequence + resume PC.
    text_t1 = ":__entry\n" + ARM_SNIPPET + paint + tail
    out["T1_dispatcher_hijacks_syspc_then_sysret"] = run_leg(
        text_t1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # T2: identical minus the dispatcher's two stores (clean dispatcher).
    paint_t2 = (paint_stores(GADGET_LINES, ATTACKER_WORD0) + "\n"
                + paint_stores(DISPATCH_LINES_CLEAN, DISPATCH_WORD0) + "\n")
    text_t2 = ":__entry\n" + ARM_SNIPPET + paint_t2 + tail
    out["T2_control_clean_dispatcher_sysret"] = run_leg(
        text_t2,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # C1: no translation — vpn-32 PTE 0; the dispatcher's rewrite ST
    # pte_invalids mid-dispatch, vectors to the REAL reaper trampoline.
    text_c1 = ":__entry\n" + ARM_SNIPPET + paint + tail
    out["C1_no_translation_dispatcher_faults"] = run_leg(
        text_c1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7})

    # C2: rot-guard — unpaged out-of-tile ST to word 8201, no PT.
    text_c2 = (":__entry\nLDI r5 %d\nLDI r6 %d\nST r6 r5\nHALT\n"
               % (HIJACK_PACKED, WORD_SYSPC))
    out["C2_unpaged_out_of_tile_syspc_ST_traps"] = run_leg(text_c2, None)

    results = out
    blob = json.dumps(results, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_sysret_pc_v2_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": results, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
