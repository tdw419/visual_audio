"""dbg_d31j3_bltu_discriminating_af3e.py - DEFECT-31j S1 CORRECTED legs.

dbg_d31j's L01/L02 (operands {1, 0x80000000}) landed in a coincidence
region where the signed (rs1-rs2)>>31 lowering MATCHES unsigned semantics:
  1 - 0x80000000 = 0x80000001 (negative) -> BLT taken; unsigned 1 < 2^31
  also taken. Non-discriminating.
The true divergence class is where the SIGNED difference sign differs from
the UNSIGNED ordering: {small positive, 0xFFFFFFFF}:
  bltu 1, 0xFFFFFFFF: unsigned TAKEN (1 < max).   Signed: 1-(-1)=+2 -> NOT.
  bgeu 0xFFFFFFFF, 1: unsigned TAKEN (max >= 1).  Signed: -1-1=-2 -> NOT.
These legs use addi x28, x0, -1 to materialize 0xFFFFFFFF (no LUI needed).

L01 bltu x9(1), x28(0xFFFFFFFF)  -> golden 1, predicted RED (0)
L02 bgeu x28(0xFFFFFFFF), x9(1)  -> golden 1, predicted RED (0)
C03 bltu x9(1), x10(2)           -> PASS control (both unsigned-safe)
Run: python3 .builder_queue/dbg_d31j3_bltu_discriminating_af3e.py
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
    'L01_bltu_1_vs_0xffffffff': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    addi x28, x0, -1        # x28 = 0xFFFFFFFF
    bltu x9, x28, taken     # unsigned: 1 < max -> branch (golden 1)
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'L02_bgeu_0xffffffff_vs_1': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    addi x28, x0, -1        # x28 = 0xFFFFFFFF
    bgeu x28, x9, taken     # unsigned: max >= 1 -> branch (golden 1)
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'C03_ctrl_bltu_both_small': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x10, 2
    bltu x9, x10, taken     # unsigned 1 < 2 -> branch (golden 1)
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
