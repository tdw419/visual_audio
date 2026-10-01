#!/usr/bin/env python3
"""Research tick 19 (af3e, 2026-09-28): KFAULT_PC CHAINING under E-K1/pte_invalid
traps — the LAST open tick-17 NOT-proved sibling (RESEARCH_ktick_chain_af3e.md:
"KFAULT_PC chaining under E-K1 traps ... unprobed this tick"; tick 17's receipt
carried the same bullet).

Named prior art (grep BEFORE harness build):
  - tick 13 (BK-71): the vector WORD is paged-rewriteable ONE-SHOT — V2 painted
    a payload at the redirect and the trap executed it, then the engine
    opcode-None-halted in SUPER. NO re-arm, NO chain, NO USER return.
  - tick 12 (BK-70): trampoline PIXELS paged-rewritten; same one-shot shape.
  - tick 15/16/17 (BK-72/73): the SYSCALL side chains (ksys re-arm) — measured.
  - tick 18 (BK-74): the TICK side chains and re-fires (TIMER_RELOAD) — measured.
  - No row measures the FAULT side: handler -> kf re-arm -> SECOND trap dispatch,
    nor fault-driven re-entry (persistence), nor a USER return from a fault
    handler. Net-new.

Mechanism (tools/glyph_isa_v2.py, HEAD 0a1f6a4d, source-read):
  - Vectoring arms read kf = memory[KFAULT_PC_ADDR>>2] LIVE at trap time and
    jump (tx*INSTR_WIDTH, ty) in SUPER (:890 pte_invalid, :1086 E-K1 ST; 6 sites
    total, :851/:936/:983/:1016/:1061/:1086). No provenance check, no consult.
  - kf==0 at vector time = clean stop (:890 else: running=False) — the chain's
    OFF switch, guest-writable like everything else in the window.
  - `faulted` is STICKY (set at every trap site, never reset in step()); unlike
    the tick arm (:1363 requires `not self.faulted`) the VECTORING arms do NOT
    consult it — a fault-driven foothold cannot be disarmed by the latch.
  - A fault handler has NO sanctioned return: SYSRET needs _syscall_regs (only
    the SYSCALL arm :1166 arms it), the DEFECT-18 JMPR restore needs _tick_pc
    (only the tick fire :1378 arms it). The only mode=USER transitions are
    SYSRET (:1202), the JMPR tick restore (:1258), and KJMP + MODE_LATCH
    (:1259-1270: mode=SUPER, then USER iff memory[8192]==1). MODE_LATCH (word
    8192) sits INSIDE the SUPER MMIO window (words 8192..8447) whose ST/LD the
    :968/:836 exemption serves unguarded — so a fault handler can write the
    latch and KJMP back to USER code. That is the candidate USER-return path
    this probe measures (K3).

Legs (real GlyphProcessTable.spawn(tile=(256,19,1,2)) posture — the TABLE arms
KFAULT_PC = 30<<16 and plants HALT at (0,30); PT armed by the task's lawful
in-tile ST to word 8211, tag 0x505447 at 1535, PT base 1536; vpn-12 PIX pfn 7
payload paint; vpn-32 plain RAM pfn 32; ALL instruction words from the REAL
GlyphAssemblerV2, never hand-encoded; verdicts from exit_status + fault fields
+ cpu.output + final PC + RAM readback BYTES, never stdout):

  K1  FAULT CHAIN (two distinct dispatches through one LIVE vector word):
      program rewrites kf <- HANDLER (31,8), faults (unmapped vpn 20 LD);
      handler PRT 77, re-arms kf <- G2 (29,8) via ONE plain SUPER-window ST
      (the :968 exemption), faults again (unmapped LD); G2 PRT 52, re-arms
      kf <- 0, faults a third time -> kf==0 clean stop.
      EXPECT: output [77, 52], faulted True (sticky), mode SUPER, exit 1.
      If G2 never runs, no chain.
  K2  FAULT-DRIVEN RE-ENTRY (persistence): handler re-arms kf <- ITSELF and
      faults — an infinite fault/handler/fault cycle with ZERO guest
      SYSCALLs and ZERO ticks. Budget 900: EXPECT output_len >> 1 (dozens of
      re-entries), mode SUPER, halt None, exit 1. Each re-entry is a FRESH
      trap dispatch through the LIVE kf read.
  K3  FAULT-HANDLER USER RETURN via MODE_LATCH + KJMP: handler PRT 77,
      re-arms kf <- G3 (29,8), faults; G3 PRT 52, ST MODE_LATCH (8192) <- 1
      via the :968 exemption, KJMP -> USER spin. The spin runs to budget
      exhaustion. EXPECT: output [77, 52], mode_final USER — the fault path
      RETURNED TO USER, arming a resident USER-mode continuation (every prior
      fault-side receipt ended parked in SUPER).
  C1  NO-CHAIN control: handler PRT 77, re-arms kf <- 0, faults -> clean stop,
      output [77] exactly once. Isolates K1's second dispatch on the re-arm.
  C2  NO-REWRITE control: no kf rewrite; the trigger fault vectors to the REAL
      planted trampoline (0,30), output []. Pins the kernel-armed vector.
  C3  ROT-GUARD: unpaged (no PT) out-of-tile USER ST to word 8193 -> E-K1,
      fault_addr 32772, parked at the REAL trampoline, exit 1. The fence is
      LIVE for the word when translation is unarmed.

3 pinned runs must be byte-identical (results md5 recorded). Run:
  python3 .builder_queue/probe_kfault_chain_af3e.py
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
WORD_KFAULT = 8193                     # KFAULT_PC_ADDR >> 2
WORD_LATCH = 8192                      # MODE_LATCH_ADDR >> 2
VA_KF = (32 << 8) + 1                  # vaddr encoding paddr 8193 (vpn 32, off 1)
VA_LATCH = (32 << 8) + 0               # paddr 8192
VA_UNMAPPED = 5120                     # vpn 20, no PTE -> pte_invalid
H_ROW, H_COL = 31, 8                   # handler (col<=15, in vpn-12 frame)
H_PACKED = (H_ROW << 16) | H_COL
H_WORD0 = H_ROW * 64 + H_COL * 4       # 31*64+32 = 2016
G_ROW, G_COL = 29, 8                   # gadget (K1's G2 / K3's G3)
G_PACKED = (G_ROW << 16) | G_COL
G_WORD0 = G_ROW * 64 + G_COL * 4       # 29*64+32 = 1888
REAL_TRAMPOLINE = (0, 30)
assert 1792 <= H_WORD0 < 2048, "handler in vpn-12 PIX pfn 7 frame"
assert 1792 <= G_WORD0 < 2048, "gadget in vpn-12 PIX pfn 7 frame"
assert H_WORD0 != G_WORD0

HANDLER_CHAIN = [                      # K1: PRT 77; kf <- G2; fault (chain on)
    "LDI r9 77", "PRT r9",
    "LDI r6 %d" % G_PACKED,
    "LDI r7 %d" % WORD_KFAULT,
    "ST r7 r6",                        # :968-exempt SUPER re-arm of KFAULT_PC
    "LDI r2 %d" % VA_UNMAPPED,
    "LD r3 r2",                        # pte_invalid -> vectors through LIVE kf
]
HANDLER_ZERO = [                       # C1: PRT 77; kf <- 0; fault (chain OFF)
    "LDI r9 77", "PRT r9",
    "LDI r6 0",
    "LDI r7 %d" % WORD_KFAULT,
    "ST r7 r6",
    "LDI r2 %d" % VA_UNMAPPED,
    "LD r3 r2",
]
GADGET_G2 = [                          # K1: PRT 52; kf <- 0; fault (clean stop)
    "LDI r2 52", "PRT r2",
    "LDI r6 0",
    "LDI r7 %d" % WORD_KFAULT,
    "ST r7 r6",
    "LDI r2 %d" % VA_UNMAPPED,
    "LD r3 r2",
]
GADGET_G3 = [                          # K3: PRT 52; latch <- 1; KJMP -> USER spin
    "LDI r2 52", "PRT r2",
    "LDI r6 1",
    "LDI r7 %d" % WORD_LATCH,
    "ST r7 r6",                        # :968-exempt MODE_LATCH write
    "LDI r30 %d",                      # spin packed PC filled at build time
    "KJMP r30",                        # mode SUPER -> (latch==1 -> USER)
]
SPIN_PACKED_PLACEHOLDER = (0, 30)      # computed per-leg in main() (probe
SPIN_ROW = 4                           # defect #2: the static row-4 guess was
SPIN_PACKED = (SPIN_ROW << 16) | 1     # wrong for K3's longer text)
GADGET_G3[5] = "LDI r30 %d" % SPIN_PACKED
HANDLER_SELF = [                       # K2: PRT 77; kf <- ITSELF; fault (loop)
    "LDI r9 77", "PRT r9",
    "LDI r6 %d" % H_PACKED,
    "LDI r7 %d" % WORD_KFAULT,
    "ST r7 r6",
    "LDI r2 %d" % VA_UNMAPPED,
    "LD r3 r2",
]
ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD,
                                                        PT_BASE_WORD)
TRIGGER = "LDI r2 %d\nLD r3 r2\nHALT\n" % VA_UNMAPPED


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
    """Paged STs painting `lines` at base_word0 via vpn 12 -> PIX pfn 7."""
    words = assembled_words(lines)
    frame0 = 1792
    return "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5"
        % (words[k], (12 << 8) + (base_word0 - frame0) + k)
        for k in range(len(words)))


def run_leg(text, stamps=None, max_instructions=2000):
    from tools.glyph_process import GlyphProcessTable
    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 2112, "image must contain the PT window + payload rows"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=max_instructions)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    table._run_task(pid)
    task_img = task["image"]
    out = [int(v) for v in cpu.output]
    return {
        "exit_status": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "fault_addr": (int(cpu.fault_addr)
                       if cpu.fault_addr is not None else None),
        "fault_reason": cpu.fault_reason,
        "halt_reason": (None if cpu.halt_reason is None
                        else str(cpu.halt_reason)),
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "output_head": out[:8],
        "output_len": len(out),
        "output_tail": out[-3:] if len(out) > 8 else [],
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "kf_word_after": int(cpu.memory[WORD_KFAULT]),
        "latch_word_after": int(cpu.memory[WORD_LATCH]),
        "h_pixels": [img_word(task_img, H_WORD0 + k)
                     for k in range(4 * len(HANDLER_CHAIN))],
        "g_pixels": [img_word(task_img, G_WORD0 + k)
                     for k in range(4 * len(GADGET_G2))],
    }


def main_text(payload_lines, kf_rewrite_value, extra_paint=None):
    """ARM + paint payload + (optional kf rewrite) + trigger.

    extra_paint: additional paint text placed BEFORE the trigger (probe
    defect #1: appending it after the trigger left it unexecuted — the
    trigger ends in HALT and the paint stores never ran)."""
    pre = ARM_SNIPPET + paint_stores(payload_lines, H_WORD0) + "\n"
    if extra_paint:
        pre += extra_paint + "\n"
    if kf_rewrite_value is not None:
        pre += ("LDI r5 %d\nLDI r6 %d\nST r6 r5\n"
                % (kf_rewrite_value, VA_KF))
    return ":__entry\n" + pre + TRIGGER


STAMPS = lambda: {PT_TAG_WORD: 0x505447,
                  VPN12_PTE_WORD: PTE_PIX_PFN7,
                  VPN32_PTE_WORD: PTE_RAM_PFN32}


def main():
    out = {}

    # K1: FAULT CHAIN — rewrite kf<-HANDLER, fault; handler PRT 77, kf<-G2,
    # fault; G2 PRT 52, kf<-0, fault -> clean stop.
    out["K1_fault_chain_two_dispatches"] = run_leg(
        main_text(HANDLER_CHAIN, H_PACKED,
                  extra_paint=paint_stores(GADGET_G2, G_WORD0)), STAMPS())

    # K2: FAULT-DRIVEN RE-ENTRY — handler re-arms kf<-itself: fault loop.
    out["K2_fault_loop_reentry"] = run_leg(
        main_text(HANDLER_SELF, H_PACKED), STAMPS(), max_instructions=900)

    # K3: FAULT-HANDLER USER RETURN — MODE_LATCH <- 1 + KJMP to a USER spin.
    # The spin's packed PC is computed from the ACTUAL instruction count of
    # the text before it (probe defect #2: a static row guess vectored the
    # KJMP into the middle of the paint stores; probe defect #3: patching
    # GADGET_G3 AFTER base_k3 was painted had no effect on the painted
    # pixels — the patch must precede the paint, so the count is derived
    # from a FIRST paint, then the gadget is re-painted with the right
    # packed PC; the count shifts by nothing because the gadget paint text
    # is the same length either way).
    base_k3 = main_text(HANDLER_CHAIN, H_PACKED,
                        extra_paint=paint_stores(GADGET_G3, G_WORD0))
    n_before = len([l for l in base_k3.splitlines()
                    if l.strip() and not l.strip().startswith(":")])
    spin_packed = ((n_before // 16) << 16) | ((n_before + 1) % 16)
    GADGET_G3[5] = "LDI r30 %d" % spin_packed
    base_k3 = main_text(HANDLER_CHAIN, H_PACKED,
                        extra_paint=paint_stores(GADGET_G3, G_WORD0))
    n_check = len([l for l in base_k3.splitlines()
                   if l.strip() and not l.strip().startswith(":")])
    assert n_check == n_before, "spin row shifted between paints"
    out["K3_latch_kjmp_user_return"] = run_leg(
        base_k3 + "\nLDI r31 99\nLDI r30 %d\nJMPR r30\n" % spin_packed,
        STAMPS(), max_instructions=1500)

    # C1: NO-CHAIN control — handler re-arms kf<-0: single dispatch only.
    out["C1_no_rearm_single_dispatch"] = run_leg(
        main_text(HANDLER_ZERO, H_PACKED), STAMPS())

    # C2: NO-REWRITE control — vectors to the REAL planted trampoline.
    out["C2_no_rewrite_real_trampoline"] = run_leg(
        main_text(HANDLER_ZERO, None), STAMPS())

    # C3: rot-guard — unpaged out-of-tile USER ST to word 8193: E-K1.
    text_c3 = (":__entry\nLDI r5 1\nLDI r6 %d\nST r6 r5\nHALT\n"
               % WORD_KFAULT)
    out["C3_unpaged_out_of_tile_kfault_ST_traps"] = run_leg(text_c3, None)

    blob = json.dumps(out, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_kfault_chain_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": out, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
