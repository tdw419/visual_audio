"""dbg_d31h_sw_value_side_alias_af3e.py - DEFECT-31h candidate: SW VALUE-side
scratch aliasing (rs2==x30 / rs2==x29 on the unguarded path), measured.
The clean follow-on leg BK-31's receipt named (its L03 was confounded by the
LW address defect; this probe never loads through x30).

Source reading (HEAD f4fe2946, tools/rv64i_to_glyph.py SW lowering ~:913-962):
on the UNGUARDED path (rs1 not in {29,30}) the address temp is glyph r30 and
the byte_to_word shift scratch is glyph r29:
    LDI r30 <imm>; ADD r30 r{rs1}    # r30 == RV x30 under the identity map
    LDI r29 2; SHR r30 r29           # r29 == RV x29
    ST r30 r{rs2}                    # value read HERE, after both scratches
Identity register map => rs2==x30 lowers to `ST r30 r30` (stores the ADDRESS,
not the value) and rs2==x29 lowers to `ST r30 r29` (stores the shift
amount 2). The guarded fix paths (rs1==30 -> ST r28 r30; rs1==29 -> ST r28
r29) read the value register untouched, so only the unguarded path aliases.

Harness: REUSES dbg_d31f's proven module (build_elf/by_pc/t2g_head/main
loop) by importing it and swapping CASES - zero harness re-typing.
Store convention: results land in mem[768] (byte base 0xC00 >>
byte_to_word_mem). All legs expect halted=True faulted=False (silent
misexecution) when RED.

Legs:
  L01 sw x30, 0(x18), x30=0xBEEF  -> predicted 0x300 (address)  RED
  L02 sw x30, 4(x18), x30=0xBEEF  -> predicted 0x301 (addr>>2)  RED
  L03 sw x30, 0(x0),  x30=0xBEEF  -> predicted 0x0              RED
  L04 sw x29, 0(x18), x29=0xBEEF  -> predicted 0x2 (shift amt)  RED
  C05 control: sw x9, 0(x18) normal path                          PASS
  C06 control: sw x9, 0(x30) base-x30 DEFECT-31 fix path          PASS
  C07 control: sw x30, 0(x30) value==base via fix path (decomposes
      BK-31's confounded L03: THIS leg alone must PASS 0xC00)     PASS

Run: python3 .builder_queue/dbg_d31h_sw_value_side_alias_af3e.py
Exit 0 = all PASS (SW value path clean). Exit 1 = at least one RED.
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

SETUP = "    li   x18, 0xC00\n"

CASES = {
    'L01_sw_val_x30_imm0': (SETUP + """
    li   x30, 0xBEEF
    sw   x30, 0(x18)
    li   a0, 0
    ret
""", 0xBEEF),
    'L02_sw_val_x30_imm4': (SETUP + """
    li   x30, 0xBEEF
    sw   x30, 4(x18)
    li   a0, 0
    ret
""", 0xBEEF),
    'L03_sw_val_x30_base_x0': (SETUP + """
    li   x30, 0xBEEF
    sw   x30, 0(x0)
    li   a0, 0
    ret
""", 0xBEEF),
    'L04_sw_val_x29_imm0': (SETUP + """
    li   x29, 0xBEEF
    sw   x29, 0(x18)
    li   a0, 0
    ret
""", 0xBEEF),
    'C05_ctrl_sw_val_x9': (SETUP + """
    li   x9, 0xBEEF
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xBEEF),
    'C06_ctrl_sw_val_x9_base_x30': (SETUP + """
    li   x30, 0xC00
    li   x9, 0xBEEF
    sw   x9, 0(x30)
    li   a0, 0
    ret
""", 0xBEEF),
    'C07_ctrl_sw_val_x30_base_x30': (SETUP + """
    li   x30, 0xC00
    sw   x30, 0(x30)
    li   a0, 0
    ret
""", 0xC00),
}

if __name__ == '__main__':
    d31f.CASES = CASES
    sys.exit(d31f.main())
