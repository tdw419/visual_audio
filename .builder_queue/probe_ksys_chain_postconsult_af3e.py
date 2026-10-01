#!/usr/bin/env python3
"""KSYS-side chain + persistence post-consult — the last UNMEASURED sibling.

Tick 20 (RESEARCH_exemption_survivor_af3e.md) proved the :968 SUPER
MMIO-window exemption still lands via the self-text dispatcher (E1, no
paging, no paint) but named persistence/chain UNMEASURED. Tick 19 (BK-75)
measured KFAULT-side chain/persistence; ticks 15/16 measured the SYSCALL
side only PRE-consult (paged paint, now refused). This probe closes the
gap with the E1 vehicle: real GlyphProcessTable.spawn(tile=(256,19,1,2))
posture, real assembler + baker, NO paging, NO paint.

Layout discipline (the tick-20 v1 defect class — recomputed, not assumed):
baker packs 8 instrs/row, INSTR_WIDTH=4, labels do NOT hold rows.
Packed dispatch targets are (row<<16)|col in INSTRUCTION units; the
engine multiplies col by INSTR_WIDTH. A text whose n_instr exceeds one
row SHIFTS every later row — so each leg's text is laid out on its own
with an assert that instr counts match the layout comment.

  K1  KSYS CHAIN: H (instrs 3..7 row0) PRTs 7, re-arms ksys<-G2 (one
      :968-exempt SUPER-window ST), falls into a second SYSCALL which
      vectors through the RE-ARMED ksys -> G2; G2 PRTs 52, unarms
      ksys<-0, third SYSCALL takes the no-handler fallback
      (_handle_syscall 0x06 DEBUG -> r10=0), PRT 0. Output [7,52,0]
      proves chain AND unarm. Disarmed word readback 0 != host arm 3.
  K2  KSYS PERSISTENCE: H PRTs 7, re-arms ksys<-ITSELF, SYSRET; main
      loops SYSCALL;JMP forever — N handler fires inside the budget
      (N measured, budget-pinned), zero guest-visible state advance.
  C1  NO-REARM control: H unarms ksys<-0; second SYSCALL -> fallback;
      output [7,0] — isolates the re-arm as the chain mechanism and
      shows the unarm IS effective (SYSRET still returns cleanly).
  C2  NO-REWRITE control: ksys never re-armed; a second SYSCALL re-enters
      the SAME handler ([7,7]) — pins the loader-seed posture.
  C3  rot-guard: unpaged USER out-of-tile ST to 8194 -> E-K1 refused
      (fence live when translation unarmed).

Verdicts from exit_status + fault fields + cpu.output + RAM readback,
never stdout. Structural numbers only — rule-1 floors do not attach.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

WORD_KSYS = 8194          # KSYS_PC_ADDR >> 2 (BOX_MMIO_BASE 0x8000 + 0x08)
TILE = (256, 19, 1, 2)
H_PACKED = (0 << 16) | 3  # handler entry = instr 3 (row0 col3) in ALL legs


def bake(text):
    from tools.glyph_gpt.baker import bake_image
    return bake_image(text, cols_instrs=8, min_rows=64, out_path=None)


def n_code(text):
    return len([l for l in text.splitlines()
                if l.strip() and not l.strip().startswith(":")])


def run_leg(text, host_ksys, max_instructions=500):
    from tools.glyph_process import GlyphProcessTable
    img = bake(text)
    table = GlyphProcessTable(cols_instrs=8, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=max_instructions)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    cpu.memory[WORD_KSYS] = host_ksys          # loader-seed posture (host arm)
    table._run_task(pid)
    return {
        "exit_status": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "fault_reason": cpu.fault_reason,
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "output": [int(v) for v in cpu.output],
        "ksys_word_after": int(cpu.memory[WORD_KSYS]),
        "host_arm": host_ksys,
    }


def main():
    out = {}

    # ---- K1: chain. Layout (8 instrs/row): G2 = instr 12 = (row1, col4);
    # unarm ST = instr 18; 3rd SYSCALL = instr 19 (fallback).
    assert n_code(K1_TEXT) == 22, n_code(K1_TEXT)
    g2 = (1 << 16) | 4
    out["K1_ksys_chain_two_dispatches_plus_unarm"] = run_leg(
        K1_TEXT % (g2, WORD_KSYS, WORD_KSYS), H_PACKED)

    # ---- K2: persistence. H PRT 7, ksys<-ITSELF, SYSRET; main loops
    # SYSCALL;JMP — SYSRET restores regs each round, loop unbounded.
    assert n_code(K2_TEXT) == 9, n_code(K2_TEXT)
    r = run_leg(K2_TEXT % (H_PACKED, WORD_KSYS), H_PACKED,
                max_instructions=600)
    r["handler_fires"] = sum(1 for v in r["output"] if v == 7)
    out["K2_ksys_self_rearm_persistence"] = r

    # ---- C1: no-rearm. H PRT 7, ksys<-0, SYSRET; second SYSCALL in main?
    # C1 main has ONE syscall; the unarm is proven by ksys_word_after==0
    # and (unlike C2) a second dispatch would take the fallback.
    assert n_code(C1_TEXT % WORD_KSYS) == 9, n_code(C1_TEXT % WORD_KSYS)
    out["C1_no_rearm_single_dispatch"] = run_leg(C1_TEXT % WORD_KSYS,
                                                 H_PACKED)

    # ---- C2: no-rewrite. H PRT 7, SYSRET. Two SYSCALLs in main.
    assert n_code(C2_TEXT) == 6, n_code(C2_TEXT)
    c2 = run_leg(C2_TEXT, H_PACKED)
    c2["fires_of_7"] = sum(1 for v in c2["output"] if v == 7)
    out["C2_no_rewrite_same_handler_each_dispatch"] = c2

    # ---- C3: rot-guard.
    c3_text = ":__entry\nLDI r5 1\nLDI r6 %d\nST r6 r5\nHALT\n" % WORD_KSYS
    out["C3_unpaged_out_of_tile_ksys_ST_traps"] = run_leg(c3_text, 0)

    blob = json.dumps(out, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    (HERE / ".builder_queue" / "probe_ksys_chain_postconsult_af3e_results.json").write_text(
        json.dumps({"results": out, "results_md5": md5},
                   indent=1, sort_keys=True))
    return 0


K1_TEXT = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # 0  USER: dispatch -> H (instr 3)
    "LDI r3 99\n"          # 1  post-SYSCALL resume marker
    "HALT\n"               # 2
    "LDI r9 7\n"           # 3  H entry (SUPER)
    "PRT r9\n"             # 4  prints 7
    "LDI r6 %d\n"          # 5  G2 packed
    "LDI r7 %d\n"          # 6  8194
    "ST r7 r6\n"           # 7  THE re-arm (SUPER :968 exemption)
    "SYSCALL r10 6\n"      # 8  dispatch #2 -> RE-ARMED ksys = G2 (12)
    "PRT r9\n"             # 9  prints 7 — proof of resumed-in-H
    "LDI r4 41\n"          # 10
    "HALT\n"               # 11
    "LDI r9 7\n"           # 12 G2 entry
    "PRT r9\n"             # 13 prints 7
    "LDI r9 52\n"          # 14
    "PRT r9\n"             # 15 prints 52
    "LDI r6 0\n"           # 16
    "LDI r7 %d\n"          # 17 8194
    "ST r7 r6\n"           # 18 unarm ksys<-0
    "SYSCALL r10 6\n"      # 19 dispatch #3 -> ksys==0 -> fallback
    "PRT r10\n"            # 20 prints fallback result 0
    "HALT\n"               # 21
)

K2_TEXT = (
    ":__entry\n"
    "LDI r5 5\n"           # 0
    "SYSCALL r10 6\n"      # 1 -> H (3); SYSRET resumes at 2
    "JMP 1,0\n"            # 2 jump back to instr 1
    "LDI r9 7\n"           # 3  H entry
    "PRT r9\n"             # 4  prints 7 per fire
    "LDI r6 %d\n"          # 5  H packed (self re-arm)
    "LDI r7 %d\n"          # 6  8194
    "ST r7 r6\n"           # 7  self re-arm (SUPER exemption)
    "SYSRET\n"             # 8
)

C1_TEXT = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # 0 -> H
    "LDI r3 99\n"          # 1
    "HALT\n"               # 2
    "LDI r9 7\n"           # 3
    "PRT r9\n"             # 4 prints 7
    "LDI r6 0\n"           # 5
    "LDI r7 %d\n"          # 6 8194
    "ST r7 r6\n"           # 7 unarm
    "SYSRET\n"             # 8
)

C2_TEXT = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # 0 -> H
    "SYSCALL r10 6\n"      # 1 -> H again (ksys never rewritten)
    "HALT\n"               # 2
    "LDI r9 7\n"           # 3
    "PRT r9\n"             # 4
    "SYSRET\n"             # 5
)

if __name__ == "__main__":
    sys.exit(main())
