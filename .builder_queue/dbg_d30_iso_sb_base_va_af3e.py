"""dbg_d30_iso_sb_base_va_af3e.py — SB/SH aliasing repro against MAIN tree
(/home/jericho/projects/zion/projects/visual_audio). cwd-independent: all
paths absolute, repo inserted at sys.path[0] so `tools.*` resolves to the
main tree, not the defect30 worktree.

RV32I probe: base in x30 (a scratch reg the old lowering used as its
address temp), two sb stores (imm 0 and 4); control with base x9.
"""
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

VA = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(VA / 'tools'))
sys.path.insert(0, str(VA))
sys.path.insert(0, str(VA / 'tests'))

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image      # noqa: E402
from test_gh23_libc_runtime import _load_posix_program           # noqa: E402

SRC_T5 = """
    .globl _start
_start:
    li   t5, 0xC00
    li   t1, 0x41
    sb   t1, 0(t5)
    li   t1, 0x42
    sb   t1, 4(t5)
    li   a0, 0
    ret
"""

SRC_CTRL = SRC_T5.replace('t5', 's1')


def build_and_run(src, tag):
    d = Path(tempfile.mkdtemp())
    c = d / f'{tag}.S'
    c.write_text(src)
    elf = d / f'{tag}.elf'
    gcc = shutil.which('riscv64-unknown-elf-gcc')
    r = subprocess.run([gcc, '-march=rv32i', '-mabi=ilp32', '-nostdlib',
                        '-nostartfiles', '-Ttext=0x200', '-o', str(elf), str(c)],
                       capture_output=True, text=True)
    print(tag, 'gcc rc', r.returncode, r.stderr[-300:] if r.returncode else '')
    if r.returncode:
        return
    out_npy = d / f'{tag}.npy'
    program = _load_posix_program(elf.read_bytes())
    libc_runtime_kernel_image(build_default_atlas(), out_path=out_npy,
                              user_program=program)
    runner = GlyphRunner(out_npy, ram_words=16384)
    receipt = runner.run(max_instructions=20000, trace=True)
    mem = receipt['memory']
    print(tag, 'halted', receipt['halted'], 'faulted', receipt['faulted'],
          '| mem[768]', hex(mem[768]), 'mem[769]', hex(mem[769]))


build_and_run(SRC_T5, 't5base')
build_and_run(SRC_CTRL, 'ctrl')
