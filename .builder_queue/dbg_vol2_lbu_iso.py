#!/usr/bin/env python3
"""Fix verification plan for the LBU stack leak: craft a minimal RV32I
program with an LBU whose rd is x28/x29/x30, transpile, count PUSH vs
POP. Also check the current landing shape: does the leak reproduce in
ISOLATION?"""
import sys, tempfile, subprocess
from pathlib import Path
REPO = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / 'tools'))
import rv64i_to_glyph as r2g

# minimal: lbu t4, 0(a0)  -> rd = x29 = t4
C = r"""
.global _start
_start:
    lbu t4, 0(a0)
    lbu t4, 1(a0)
    ret
"""
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    src = tmp / 'm.c'
    asm = tmp / 'm.S'
    elf = tmp / 'm.elf'
    src.write_text('void _start(void);\n')
    asm.write_text(C)
    subprocess.run(['riscv64-unknown-elf-gcc', '-march=rv32i', '-mabi=ilp32',
                    '-nostdlib', '-Wl,-Ttext=0x0', '-Wl,--entry=_start',
                    '-w', str(asm), '-o', str(elf)], check=True)
    b = elf.read_bytes()
    base, text, symbols = r2g.parse_elf(b)
    out = r2g.transpile_rv32i_to_glyph(
        text_bytes=text, symbols={}, base_addr=base,
        entry_symbol='_start', use_ir=True, cols_instrs=32)
    pushes = sum(1 for ln in out.splitlines() if ln.strip().startswith('PUSH'))
    pops = sum(1 for ln in out.splitlines() if ln.strip().startswith('POP'))
    print('PUSH:', pushes, 'POP:', pops, '-> leak per lbu(t4):', pushes - pops)
    print(out)
