"""dbg_d31j2_bltu_bitexact_af3e.py - DEFECT-31j S1 follow-up: WHY did the
bltu/bgeu signedness legs pass when the lowering is the signed (rs1-rs2)>>31
trick? Hypothesis H-shift: gcc -march=rv32i can't materialize 0x80000000 in
one li, and the lowered glyph stream is correct-but-different from what I
assumed. Dump the raw glyph op-stream for L01's branch region + print the
actual operands the runner saw.
"""
import subprocess, tempfile, sys
from pathlib import Path

VA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VA))
from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402

SRC = """
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x28, 1
    slli x28, x28, 31
    bltu x9, x28, taken
    li   x10, 0
    j    store
taken:
    li   x10, 1
store:
    sw   x10, 0(x18)
    li   a0, 0
    ret
"""

with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    c = d / 'l01.S'
    c.write_text(SRC)
    elf = d / 'l01.elf'
    gcc = 'riscv64-unknown-elf-gcc'
    r = subprocess.run([gcc, '-march=rv32i', '-mabi=ilp32', '-nostdlib',
                        '-nostartfiles', '-Ttext=0x200', '-o', str(elf),
                        str(c)], capture_output=True, text=True)
    if r.returncode:
        print('gcc FAILED', r.stderr)
        sys.exit(1)
    # 1) what instructions did gcc actually emit?
    objdump = subprocess.run(
        ['riscv64-unknown-elf-objdump', '-d', str(elf)],
        capture_output=True, text=True)
    print('=== objdump ===')
    print(objdump.stdout)
    ops = transpile_elf_to_glyph(elf.read_bytes(), entry_symbol='_start',
                                 byte_to_word_mem=True)
    print('=== glyph op stream (branch region) ===')
    show = False
    for line in ops.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(':'):
            print(s)
            show = True
            continue
        if show:
            print(' ', s)
