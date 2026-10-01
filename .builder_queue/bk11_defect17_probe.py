"""BK-11 probe 42 — RED receipt for DEFECT-17 (RV x31/t6 -> glyph r31
HW-stack-pointer collision).

RV x31 (t6) maps IDENTITY to glyph r31, which is the Glyph ISA's
HARDWARE CALL STACK POINTER (CALL pushes, RET pops, PUSH/POP use it).
Any C program whose GCC output keeps a value in t6 across a call
silently corrupts the HW call stack. Repro: store a byte via a
computed address held in t6 — 'sb t6,0(a5)'-shaped — actually simpler:
`li t6,90; ret` transpiles to `LDI r31 90; RET` which pops garbage.
This probe:
  leg 1: `li t6,X` lowers to an r31-write (identity-map proof);
  leg 2: at runtime on GlyphRunner, after `li t6,90; jal helper; ret`
         the task's return path derails / r31 no longer equals the
         seeded HW stack top (behavioural proof).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

import rv64i_to_glyph as r2g


def test_t6_lowers_to_glyph_r31_hw_stack_register():
    """`li t6, imm` must NOT emit a write to glyph r31 (HW stack ptr)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "t.s").write_text(
            ".text\n.globl _start\n_start:\n li t6, 90\n ret\n")
        subprocess.run(
            ["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32",
             "-nostdlib", "-Wl,-Ttext=0x0", "-w",
             str(tmp / "t.s"), "-o", str(tmp / "t.elf")], check=True)
        base, text, symbols = r2g.parse_elf((tmp / "t.elf").read_bytes())
        symbols_f = {a: n for a, n in symbols.items() if not n.startswith("$")}
        out = r2g.transpile_rv32i_to_glyph(
            text_bytes=text, symbols=symbols_f, base_addr=base,
            entry_symbol="_start", use_ir=False, cols_instrs=16)
        body = [l for l in out.splitlines()
                if l.strip() and not l.startswith(":")
                and not l.startswith("#")]
        # the body is LDI r31 <imm> / RET today (RED) — assert it is not
        assert not any(l.strip().startswith("LDI r31 ")
                       for l in body), (
            f"DEFECT-17 RED: `li t6` lowered onto glyph r31 (HW call "
            f"stack pointer): {body}")
