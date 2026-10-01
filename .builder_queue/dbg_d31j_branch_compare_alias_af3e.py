"""dbg_d31j_branch_compare_alias_af3e.py - DEFECT-31j candidate: branch/compare
lowering aliasing (the family BK-33 named UNPROBED). Three predicted shapes,
all measured this tick:

S1 BLTU/BGEU SIGNEDNESS: tools/rv64i_to_glyph.py:1297/:1322 route BLTU/BGEU
   through the SAME lowering as BLT/BGE - r30 = rs1-rs2, SHR 31, branch on
   sign bit. That is a SIGNED compare. Any unsigned compare whose operands
   straddle 2^31 misdirects.
S2 BLT/BGE SCRATCH-CONSUMED-DURING-COMPARE: the DEFECT-16 PUSH/POP guards
   (:1303-1315, :1328-1340) protect x28/x29/x30 ACROSS the lowering, but the
   compare itself reads rs1/rs2 via `ADD r30 r{rs1}; SUB r30 r{rs2}` AFTER
   `LDI r30 0` - if rs1 or rs2 IS x28/x29/x30, the compare reads a clobbered
   or zeroed register, not the live value.
S3 BEQ/BNE ZERO-SCRATCH SELF-CMP: the rs1==0/rs2==0 paths (:1231-1241,
   :1260-1271) materialize zero in r28 then `CMP r28 r{other}` - if the other
   operand is ALSO x28, this is `CMP r28 r28`: always-equal, branch always
   (BEQ) / never (BNE) taken.

Legs (golden = value stored to mem word 768; harness convention):
  L01 bltu x9,x28  1 vs 2^31   -> unsigned branches (golden 1); signed falls
                                  through (predicted 0)   RED  [S1]
  L02 bgeu x28,x9  2^31 vs 1   -> unsigned branches (golden 1); signed no
                                  (predicted 0)           RED  [S1]
  L03 blt  x30,x9  2 vs 1      -> golden no-branch (0); lowering reads
                                  rs1=0 -> 0-1 sign1 -> branches (1) RED [S2]
  L04 blt  x9,x29  1 vs 2      -> golden branch (1); reads rs2=0 -> 1-0
                                  sign0 -> no-branch (0)  RED  [S2]
  L05 bge  x30,x9  2 vs 1      -> golden branch (1); reads rs1=0 -> sign1
                                  -> no-branch (0)        RED  [S2]
  L06 beq  x0,x28  x28=5       -> golden no-branch (0); CMP r28 r28 always
                                  equal -> branches (1)   RED  [S3]
  L07 bne  x28,x0  x28=5       -> golden branch (1); JZ skip always -> no
                                  branch (0)              RED  [S3]
  C08 blt  x9,x10  clean regs 1 vs 2 -> PASS control
  C09 bltu x9,x10  both small (signed==unsigned region) -> PASS control,
          shows S1 is boundary-specific, not a total break
  C10 beq  x9,x0   x9=0 (zero-scratch path, other operand clean) -> PASS
          control (DEFECT-16b path correct when x28 is not an operand)

Harness: REUSES dbg_d31f's proven module (build_elf/by_pc/t2g_head/main,
incl. the tree-vs-HEAD op-stream compare) by importing it and swapping
CASES - zero harness re-typing. 2^31 materialized via li+slli (no LUI
dependence).

Run: python3 .builder_queue/dbg_d31j_branch_compare_alias_af3e.py
Exit 0 = all PASS (branch family clean). Exit 1 = at least one RED.
"""
import importlib.util
import sys
from pathlib import Path

VA = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    'dbg_d31f_harness',
    VA / '.builder_queue' / 'dbg_d31f_alu_imm_alias_af3e.py')
d31f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d31f)

CASES = {
    'L01_bltu_signedness_1_vs_2p31': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x28, 1
    slli x28, x28, 31        # x28 = 0x80000000
    bltu x9, x28, taken      # unsigned: 1 < 2^31 -> branch
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'L02_bgeu_signedness_2p31_vs_1': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x28, 1
    slli x28, x28, 31        # x28 = 0x80000000
    bgeu x28, x9, taken      # unsigned: 2^31 >= 1 -> branch
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'L03_blt_rs1_x30_scratch': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x30, 2
    li   x9, 1
    blt  x30, x9, taken      # 2 < 1 false -> fall through, mem=0
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x0),
    'L04_blt_rs2_x29_scratch': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x29, 2
    blt  x9, x29, taken      # 1 < 2 true -> branch, mem=1
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'L05_bge_rs1_x30_scratch': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x30, 2
    li   x9, 1
    bge  x30, x9, taken      # 2 >= 1 true -> branch, mem=1
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'L06_beq_rs2_x28_selfcmp': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x28, 5
    beq  x0, x28, taken      # 0 != 5 -> no branch, mem=0
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x0),
    'L07_bne_rs1_x28_selfcmp': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x28, 5
    bne  x28, x0, taken      # 5 != 0 -> branch, mem=1
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'C08_ctrl_blt_clean_regs': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x10, 2
    blt  x9, x10, taken      # 1 < 2 -> branch, mem=1
    li   x11, 0
    j    store
taken:
    li   x11, 1
store:
    sw   x11, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'C09_ctrl_bltu_small_unsigned': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x10, 2
    bltu x9, x10, taken      # unsigned 1 < 2 -> branch, mem=1
    li   x11, 0
    j    store
taken:
    li   x11, 1
store:
    sw   x11, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'C10_ctrl_beq_zero_path_clean': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 0
    beq  x9, x0, taken       # 0 == 0 -> branch, mem=1
    li   x11, 0
    j    store
taken:
    li   x11, 1
store:
    sw   x11, 0(x18)
    li   a0, 0
    ret
""", 0x1),
}

if __name__ == '__main__':
    d31f.CASES = CASES
    sys.exit(d31f.main())
