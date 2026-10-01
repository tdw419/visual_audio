"""Probe: do multiple BNE lowerings produce colliding skip labels?
(bne_counter declared at :490, referenced at :1253 - check uniqueness.)"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

VA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VA))
from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402

SRC = """
    .globl _start
_start:
    li   x18, 0xC00
    li   x9, 1
    li   x10, 2
    li   x28, 7
b1: bne  x9, x10, t1
    li   x11, 9
    j    nxt
t1: li   x11, 8
nxt: mv   x12, x11
b2: bne  x28, x0, t2
    li   x13, 1
    j    fin
t2: li   x13, 2
fin: sw   x13, 0(x18)
    li   a0, 0
    ret
"""

with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    c = d / 't.S'
    c.write_text(SRC)
    elf = d / 't.elf'
    subprocess.run(['riscv64-unknown-elf-gcc', '-march=rv32i', '-mabi=ilp32',
                    '-nostdlib', '-nostartfiles', '-Ttext=0x200',
                    '-o', str(elf), str(c)], check=True, capture_output=True)
    ops = transpile_elf_to_glyph(elf.read_bytes(), entry_symbol='_start',
                                 byte_to_word_mem=True)
    labels = re.findall(r':__skip_bne_\d+', ops)
    print('skip labels found:', labels)
    if len(set(labels)) == len(labels):
        print('UNIQUE - no collision')
    else:
        print('COLLISION detected!')
