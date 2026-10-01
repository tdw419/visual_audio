"""BK-11 probe 43 — find the enforcement layer that catches
r31-as-target (the IR verifier's callstack_reg rule) and confirm the
raw-transpile path (use_ir=False) never consults it, i.e. the ADDI
lowering writes r31 with no gate. Then write the fix plan: map RV
x31 (t6) to a SHADOW glyph register so glyph r31 stays reserved for
the HW call stack, same for any other colliding RV register.

Also: which OTHER RV registers collide? RV x0..x31 map identity to
glyph r0..r31. Glyph r0 = CMP flag (not zero!), r31 = HW stack. So
RV x0 and x31 are BOTH semantically different in glyph-land. The
transpiler already special-cases x0 (see _emit_add_reg docstring).
x31 is the one never handled — DEFECT-17.
"""
import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

import rv64i_to_glyph as r2g

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
    print(out)
