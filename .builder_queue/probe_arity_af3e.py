#!/usr/bin/env python3
"""Research probe: assembler arity handling (BK-36 folded candidate).

Question: does GlyphAssemblerV2 silently drop extra operands, and does an
unknown mnemonic fail loud? Deterministic structural probe, no engine edits.
"""
import sys

sys.path.insert(0, "tools")
sys.path.insert(0, ".")

from glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2  # noqa: E402

am = GlyphAssemblerV2(OpcodeMapV2())

cases = [
    "ADD r1 r2 r3",      # 3-operand RISC-V-style form (ISA is 2-operand)
    "ADD r1 r2 bogus",   # non-register trailing token
    "LDI r1 5 r3",       # extra operand on LDI
    "SUB r4 r5",         # well-formed control
    "MOV r1 r2",         # unknown mnemonic control
]

for src in cases:
    try:
        img = am.assemble([src], width_instrs=1)
        print(f"{src!r:24} -> assembled OK  rs1/rs2/rd word px: {img[0,1]} {img[0,2]} {img[0,3]}")
    except Exception as e:
        print(f"{src!r:24} -> raised: {type(e).__name__}: {e}")
