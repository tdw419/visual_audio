"""dbg_d30_iso_sh_base_af3e.py — SH aliasing probe (DEFECT-31c twin).

RV32I: base in x30, two sh stores; control with non-scratch base.
"""
import sys, subprocess, tempfile, shutil
from pathlib import Path
VA = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(VA / 'tools'))
sys.path.insert(0, str(VA))
sys.path.insert(0, str(VA / 'tests'))

from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.baker import libc_runtime_kernel_image
from test_gh23_libc_runtime import _load_posix_program

SRC_T5 = """
    .globl _start
_start:
    li   t5, 0xC00
    li   t1, 0x1141
    sh   t1, 0(t5)
    li   t1, 0x2242
    sh   t1, 4(t5)
    li   a0, 0
    ret
"""

def build_and_run(src, tag):
    d = Path(tempfile.mkdtemp())
    c = d / f'{tag}.S'
    c.write_text(src)
    elf = d / f'{tag}.elf'
    gcc = shutil.which('riscv64-unknown-elf-gcc')
    r = subprocess.run([gcc, '-march=rv32i', '-mabi=ilp32', '-nostdlib',
                        '-nostartfiles', '-Ttext=0x200', '-o', str(elf), str(c)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out_npy = d / f'{tag}.npy'
    program = _load_posix_program(elf.read_bytes())
    libc_runtime_kernel_image(build_default_atlas(), out_path=out_npy,
                              user_program=program)
    runner = GlyphRunner(out_npy, ram_words=16384)
    receipt = runner.run(max_instructions=20000, trace=True)
    mem = receipt['memory']
    print(tag, 'halted', receipt['halted'], 'faulted', receipt['faulted'],
          '| mem[768]', hex(mem[768]), 'mem[769]', hex(mem[769]),
          '(expect 0x1141 / 0x2242)')

build_and_run(SRC_T5, 'sh_t5base')
