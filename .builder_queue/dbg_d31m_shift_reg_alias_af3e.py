"""dbg_d31m_shift_reg_alias_af3e.py - DEFECT-31m candidate: REGISTER-register
shift lowerings (SLL/SRA) aliasing, measured. New op-family members per the
31i/31j ledger next-tick lines: BK-30 covered SRLI/SRAI (immediates only);
the register-register SLL (:769-776) and SRA (:779-813) lowerings were never
probed. SRL stages its count through PUSH/POP'd r26 (DEFECT-30 fix) - safe.

Source reading (HEAD fb06b690, tools/rv64i_to_glyph.py):

SLL (:769-776):
    if rd == rs1: SHL r{rd} r{rs2}          # safe: no scratch
    else: LDI r{rd} 0; ADD r{rd} r{rs1}; SHL r{rd} r{rs2}
    ^ rd!=rs1 AND rs2==rd: `LDI r{rd} 0` destroys the COUNT before
    `SHL r{rd} r{rs2}` reads it -> shifts by 0, silently.

SRA (:779-813, DEFECT-30 guard covers r26 only):
    PUSH r26; LDI r26 31; AND r26 r{rs2}    # count staged, safe
    [LDI r{rd} 0; ADD r{rd} r{rs1}]
    LDI r29 0x80000000; XOR r{rd} r29       # rd==x29: XOR r29 r29 -> 0
    SHR r{rd} r26
    LDI r27 0x80000000; SHR r27 r26         # r27 = sign fill
    SUB r{rd} r27                           # rd==x27: SUB r27 r27 -> 0
    POP r26
    ^ rd==x29: sign-extend XOR destroys rd in place (silent);
    rd==x27: fill scratch clobbered by rd's own LDI 0x80000000? No -
    r27 IS rd, so `LDI r27 0x80000000` overwrites rd, then
    `SHR r27 r26`, then `SUB r{rd} r27` = SUB rd rd = 0 (silent).

Harness: REUSES dbg_d31f's proven module verbatim (build_elf/by_pc/
tree-vs-HEAD/main loop) by importing it and swapping CASES - zero harness
re-typing. Store convention: base = x18 = byte 0xC00 -> mem[768]; every
leg stores via `sw x9, 0(x18)` after mv'ing the result into x9 (the
d31f convention - keeps the store path itself off the probed registers).
All legs expect halted=True faulted=False (silent misexecution) when RED.

Legs:
  L01 sll  x9,x18,x9   (rd!=rs1, count lives in rd)   predicted shift-by-0 RED
  L02 sra  x29,x18,x8  (rd==x29, sign scratch)        predicted 0-shape  RED
  L03 sra  x27,x18,x8  (rd==x27, fill scratch)        predicted 0-shape  RED
  L04 ctrl: sll  x9,x18,x8   (no alias)                PASS
  L05 ctrl: sra  x9,x18,x8   (rd clean, DEFECT-30 path) PASS
  L06 ctrl: srl  x9,x18,x8   (staged r26, rd clean)    PASS

Run: python3 .builder_queue/dbg_d31m_shift_reg_alias_af3e.py
Exit 0 = all PASS (register-shift paths clean). Exit 1 = at least one RED.
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
    # rd=x9, rs1=x18, rs2=x9: lowering = LDI r9 0; ADD r9 r18; SHL r9 r9.
    # Count 12 destroyed -> 0xABCD << 0. Golden: << 12.
    'L01_sll_count_in_rd': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x19, 0xABCD
    li   x9,  12
    sll  x9, x19, x9
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", (0xABCD << 12) & 0xFFFFFFFF),

    # rd=x29 (the sign-extend XOR scratch): XOR r29 r29 -> 0; SHR 0 by 8
    # = 0; LDI r27..; SUB r29 r27 = 0 - 0x80000000>>8. Golden: (0x87654000
    # >>a 8) sign-extended.
    'L02_sra_rd_eq_x29': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x8,  8
    li   x29, 0x87654000
    sra  x29, x29, x8
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", (0x87654000 >> 8) | 0xFF000000),

    # rd=x27 (the sign-fill scratch): LDI r27 0x80000000 overwrites rd,
    # SHR r27 r26, SUB r27 r27 = 0. Golden: (0x87654000 >>a 12).
    'L03_sra_rd_eq_x27': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x8,  12
    li   x27, 0x87654000
    sra  x27, x27, x8
    mv   x9, x27
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", (0x87654000 >> 12) | 0xFFF00000),

    # Control: no aliasing, SLL rd!=rs1 clean path.
    'L04_ctrl_sll_clean': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x19, 0xABCD
    li   x8,  8
    sll  x9, x19, x8
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", (0xABCD << 8) & 0xFFFFFFFF),

    # Control: SRA rd clean (x9), rd!=rs1 - the DEFECT-30 guarded path.
    'L05_ctrl_sra_clean': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x19, 0x87654000
    li   x8,  8
    sra  x9, x19, x8
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", (0x87654000 >> 8) | 0xFF000000),

    # Control: SRL rd clean - the staged-r26 DEFECT-30 fix path.
    'L06_ctrl_srl_clean': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x19, 0xABCD
    li   x8,  4
    srl  x9, x19, x8
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xABCD >> 4),
}

if __name__ == '__main__':
    d31f.CASES = CASES
    sys.exit(d31f.main())
