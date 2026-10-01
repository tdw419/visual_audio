"""dbg_d31c_dump_sb_x29_af3e.py — dump the glyph op stream for the sb base-x29
case so the RED legs in dbg_d31c_latent_alias_af3e.py can be root-caused.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VA = Path('/home/jericho/projects/zion/projects/visual_audio')
for p in (str(VA / 'tools'), str(VA), str(VA / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402

SRC = """.globl _start
_start:
    li   t4, 0xC00
    li   t1, 0x41
    sb   t1, 0(t4)
    li   a0, 0
    ret
"""

d = Path(tempfile.mkdtemp())
c = d / 'x.S'
c.write_text(SRC)
elf = d / 'x.elf'
gcc = shutil.which('riscv64-unknown-elf-gcc')
r = subprocess.run([gcc, '-march=rv32i', '-mabi=ilp32', '-nostdlib',
                    '-nostartfiles', '-Ttext=0x200', '-o', str(elf), str(c)],
                   capture_output=True, text=True)
assert r.returncode == 0, r.stderr
src = transpile_elf_to_glyph(elf.read_bytes(), entry_symbol='_start',
                             byte_to_word_mem=True)
print('\n'.join(src.splitlines()))
