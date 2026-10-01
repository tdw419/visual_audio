"""dbg_d31g_lw_addr_alias_af3e.py - DEFECT-31g candidate: LW address-path
scratch aliasing (rs1==x30), measured. New op-family per the ledger's
next-tick line (31c = SB/SH else branches, 31e = store fix branches
value-side, 31f = ALU/imm; the LW/SW ADDRESS path was never probed).

Source reading (HEAD 7c0d62da, tools/rv64i_to_glyph.py LW lowering,
~:899-909): LW uses r30 as its address temp UNCONDITIONALLY:
    LDI r30 <imm>; ADD r30 r{rs1}    # LDI clobbers before ADD reads
    [LDI r29 2; SHR r30 r29]         # byte_to_word_mem
    LD r{rd} r30
When gcc allocates the BASE in x30, `LDI r30 imm` destroys the base and
`ADD r30 r30` computes 2*imm (imm=0 -> 0) - the load reads the wrong
word, silently. The sibling SW lowering got the DEFECT-31 fix
(:913-928: rs1==30 -> push r30, address in r28, shift in r26, pop r30);
LW never got the equivalent guard. Note imm=0 does NOT save it:
LDI r30 0; ADD r30 r30 = 0 -> loads word 0.

Harness: REUSES dbg_d31f's proven module (build_elf/by_pc/t2g_head/main
loop) by importing it and swapping CASES - zero harness re-typing.
Store convention: base x18 = byte 0xC00 -> word 768 (byte_to_word_mem);
every leg's result lands in mem[768]. All legs expect halted=True
faulted=False (silent misexecution) when RED.

Legs:
  L01 lw x9,  0(x30), base x30   -> predicted word 0 (golden 0xABCD) RED
  L02 lw x9,  8(x30), base x30   -> predicted word (2*8)>>2=4        RED
  L03 lw x30, 0(x30), dest=base  -> predicted word 0                 RED
  L04 control: lw x9, 0(x18), base x18                            PASS
  L05 control: sw x9, 0(x30), base x30 (DEFECT-31 fix path)       PASS
  L06 control: lw/sw roundtrip through x18                        PASS

Run: python3 .builder_queue/dbg_d31g_lw_addr_alias_af3e.py
Exit 0 = all PASS (LW address path clean). Exit 1 = at least one RED.
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

SETUP = """
    li   x18, 0xC00
    li   x19, 0xABCD
    sw   x19, 0(x18)
"""

CASES = {
    'L01_lw_base_x30_imm0': (SETUP + """
    li   x30, 0xC00
    lw   x9, 0(x30)
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xABCD),
    'L02_lw_base_x30_imm8': (SETUP + """
    li   x30, 0xC00
    lw   x9, 8(x30)
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xABCD),
    'L03_lw_dest_eq_base_x30': (SETUP + """
    li   x30, 0xC00
    lw   x30, 0(x30)
    sw   x30, 0(x18)
    li   a0, 0
    ret
""", 0xABCD),
    'L04_ctrl_lw_base_x18': (SETUP + """
    li   x18, 0xC00
    lw   x9, 0(x18)
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xABCD),
    'L05_ctrl_sw_base_x30_fixpath': (SETUP + """
    li   x30, 0xC00
    li   x9, 0xBEEF
    sw   x9, 0(x30)
    lw   x9, 0(x18)
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xBEEF),
    'L06_ctrl_lw_sw_roundtrip_x18': (SETUP + """
    li   x18, 0xC00
    li   x10, 0xC04
    lw   x9, 0(x18)
    sw   x9, 0(x10)
    lw   x9, 0(x10)
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xABCD),
}

if __name__ == '__main__':
    d31f.CASES = CASES
    sys.exit(d31f.main())
