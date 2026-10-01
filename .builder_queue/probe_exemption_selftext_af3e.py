#!/usr/bin/env python3
"""Self-text dispatcher probe v2 — CORRECTED (v1 defect: I assumed packed
(row<<16)|col targeted (row, col) in INSTRUCTION units and that the baker
kept my label rows; in fact instructions pack contiguously, 8 per 32-px
image row, and dispatch targets are (x=col*INSTR_WIDTH, y=row) PIXEL
coordinates. v1's ksys=(1,0) pointed at pixel (0,1) = scanline word 10 —
past the 9-instruction program: the 'dispatcher' fetched a ZERO pixel,
opcode-None halted... then the trace showed resume — actually the engine's
opcode-None silent-halt class; ksys readback 65536 was my own host arm,
NOT a landed store. v1 measured nothing. Disclosed in the receipt.

v2: handler = the task's own text at the CORRECT packed coordinates.
Layout (8 instrs/row, INSTR_WIDTH=4):
  row0: SYSCALL(0) LDI r3(post) HALT LDI r6 LDI r7 ST LDI r5 PRT   [0..7]
  row1: SYSRET (0,1)
BUT: ksys dispatch to handler start = instr 3 = pixel (12, 0) = packed
(row 0, col 3) = 3. The dispatcher then runs instr 3..7 and SYSRET at
(0,1) — reachable because after PRT (instr 7, pixel x=28) next_pc wraps
to (0,1) which IS the SYSRET. No jumps needed.

Store: ST r7 r6 with r7=8194 (word), r6 = the VALUE stored (52? no—
value in rs2=r6, address rs1=r7; LDI r6 <value>). Set value=65537 (junk
sentinel ≠ host arm 3) to prove the store LANDED (word 8194 becomes
65537, not 3).
"""
import json
import sys
from pathlib import Path

HERE = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

from tools.glyph_process import GlyphProcessTable  # noqa: E402
from tools.glyph_gpt.baker import bake_image  # noqa: E402

TILE = (256, 19, 1, 2)
WORD_KSYS = 8194
PACKED_HANDLER = (0 << 16) | 3       # pixel (12, 0) = instr 3
SENTINEL = 65537                      # stored value, != host arm

text = (
    ":__entry\n"
    "SYSCALL r10 6\n"      # 0: dispatch to ksys=(0,3) in SUPER
    "LDI r3 99\n"          # 1: post (resume point)
    "HALT\n"               # 2
    "LDI r6 %d\n"          # 3: handler start (SUPER) — value
    "LDI r7 %d\n"          # 4: address = KSYS word
    "ST r7 r6\n"           # 5: THE :968 SUPER-window store
    "LDI r5 52\n"          # 6
    "PRT r5\n"             # 7: output [52] proves handler ran to the end
    "SYSRET\n"             # 8: at (0,1) — resumes USER at syspc
    % (SENTINEL, WORD_KSYS)
)

table = GlyphProcessTable(cols_instrs=8, memory_words=16384)
img = bake_image(text, cols_instrs=8, min_rows=64, out_path=None)
pid = table.spawn(image=img, tile=TILE, max_instructions=500)
cpu = table.tasks[pid]["cpu"]
task = table.tasks[pid]
cpu.memory[WORD_KSYS] = PACKED_HANDLER   # host-arm (loader-seed posture)
table._run_task(pid)
out = {
    "exit_status": task["exit_status"],
    "faulted": bool(cpu.faulted),
    "fault_reason": cpu.fault_reason,
    "mode_final": "USER" if cpu.mode == 1 else "SUPER",
    "output": [int(v) for v in cpu.output],
    "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
    "ksys_word_after": int(cpu.memory[WORD_KSYS]),
    "host_arm": PACKED_HANDLER,
    "sentinel": SENTINEL,
    "exemption_store_landed": int(cpu.memory[WORD_KSYS]) == SENTINEL,
}
print(json.dumps(out, indent=1))
