"""dbg_d31i_jalr_alias_af3e.py - DEFECT-31i candidate: JALR lowering
fixed-scratch aliasing (rs1==x30 target self-alias; rd==x30 return-address
clobber), measured. New op-class per the 31h ledger's next-tick line
(branch/compare lowerings = the named unprobed family; JALR is its
computed-jump member).

Source reading (HEAD d6169173, tools/rv64i_to_glyph.py JALR lowering
~:1366-1436): the dynamic-target path lowers to
    LDI r30 <tbl_base>; ADD r30 r{rs1}   # rs1==x30: ADD r30 r30 reads the
                                         #   CLOBBERED x30 -> index = tbl+tbl
    [LDI r29 imm; ADD r30 r29]           # imm != 0 only
    LDI r29 2; SHR r30 r29; LD r30 r30
    LDI r{rd} <pc+4>; CALLR r30          # rd != 0 return addr as DATA;
                                         #   rd==x30: LDI r30 <ret> overwrites
                                         #   the loaded target BEFORE CALLR
Structural probes this tick (byte-level transpile dumps at HEAD):
  - `jalr x0,0(x30)` -> `LDI r30 0x2000; ADD r30 r30; ...; JMPR r30`
  - `jalr x30,0(x5)` -> `... LD r30 r30; LDI r30 0x214; CALLR r30`

Legs (golden = 0xBEEF stored to mem[768] by fn; caller never stores):
  L01 jalr x0,0(x30)  rs1==x30 target self-alias -> predicted RED
  L02 jalr x30,0(x5)  rd==x30  ret-addr clobber  -> predicted RED
  C03 jalr x0,0(x5)   rs1 clean, rd==x0          -> PASS control
  C04 jalr x1,0(x5)   plain fn-pointer call      -> PASS control

Harness: REUSES dbg_d31f's proven module (build_elf/by_pc/t2g_head/main
loop, incl. the tree-vs-HEAD op-stream compare) by importing it and
swapping CASES - zero harness re-typing.

Run: python3 .builder_queue/dbg_d31i_jalr_alias_af3e.py
Exit 0 = all PASS (JALR path clean). Exit 1 = at least one RED.
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
    'L01_jalr_rs1_x30': ("""
    .globl _start
_start:
    li   x18, 0xC00
    la   x30, fn
    jalr x0, 0(x30)
    li   x10, 0
    j    done
fn:
    li   x9, 0xBEEF
    sw   x9, 0(x18)
    ret
done:
    ret
""", 0xBEEF),
    'L02_jalr_rd_x30': ("""
    .globl _start
_start:
    li   x18, 0xC00
    la   x5, fn
    jalr x30, 0(x5)
    li   x10, 0
    j    done
fn:
    li   x9, 0xBEEF
    sw   x9, 0(x18)
    ret
done:
    ret
""", 0xBEEF),
    'C03_ctrl_jalr_rs1_x5_rd_x0': ("""
    .globl _start
_start:
    li   x18, 0xC00
    la   x5, fn
    jalr x0, 0(x5)
    li   x10, 0
    j    done
fn:
    li   x9, 0xBEEF
    sw   x9, 0(x18)
    ret
done:
    ret
""", 0xBEEF),
    'C04_ctrl_jalr_call_x1': ("""
    .globl _start
_start:
    li   x18, 0xC00
    la   x5, fn
    jalr x1, 0(x5)
    j    done
fn:
    li   x9, 0xBEEF
    sw   x9, 0(x18)
    ret
done:
    ret
""", 0xBEEF),
}

if __name__ == '__main__':
    d31f.CASES = CASES
    sys.exit(d31f.main())
