"""dbg_d31e_recheck_a2_af3e.py — independent single-leg recheck of probe
dbg_d31e_fixbranch_alias_af3e.py leg A2 (SB fix branch, rs1=x30, value=x27).
Written because the probe's echoed output showed harness-text drift; this
re-derives the load-bearing number with fresh code, fresh tempdir.

Golden: mem[768] == 0x43. Probe said RED (0x0).
Run: python3 .builder_queue/dbg_d31e_recheck_a2_af3e.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

VA = Path(__file__).resolve().parent.parent
for p in (str(VA), str(VA / 'tools'), str(VA / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402

SRC = """    .globl _start
_start:
    li   x30, 0xC00
    li   x27, 0x43
    sb   x27, 0(x30)
    li   a0, 0
    ret
"""


def main():
    from tools.glyph_gpt.libc_runtime import libc_runtime_kernel_image
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.runner import GlyphRunner
    from test_gh23_libc_runtime import _load_posix_program

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / 'a.S').write_text(SRC)
        subprocess.run(
            ['riscv64-unknown-elf-gcc', '-march=rv32i', '-mabi=ilp32',
             '-nostdlib', '-nostartfiles', '-Ttext=0x200',
             '-o', str(d / 'a.elf'), str(d / 'a.S')],
            check=True, capture_output=True, timeout=60)
        elf = (d / 'a.elf').read_bytes()
        prog = _load_posix_program(elf)
        glyph_text = transpile_elf_to_glyph(
            elf, entry_symbol='_start', byte_to_word_mem=True)
        # show the transpiled fix-branch lines so the corruption is visible
        # in the artifact itself, not just the engine result
        lines = [l for l in glyph_text.splitlines()
                 if 'r26' in l or 'r27' in l or 'r28' in l or 'r29' in l
                 or 'r30' in l]
        print('--- transpiled scratch lines (first 24) ---')
        for l in lines[:24]:
            print(l)
        npy = d / 'a.npy'
        libc_runtime_kernel_image(build_default_atlas(), out_path=npy,
                                  user_program=prog)
        r = GlyphRunner(npy, ram_words=16384)
        rec = r.run(max_instructions=20000, trace=False)
        got = rec['memory'][768]
        verdict = 'PASS (probe contradicted!)' if got == 0x43 else \
                  f'RED (probe confirmed: mem[768]={hex(got)}, golden 0x43)'
        print(f'A2 recheck: halted={rec["halted"]} faulted={rec["faulted"]}'
              f' mem[768]={hex(got)} -> {verdict}')
        return 0 if got != 0x43 else 2


if __name__ == '__main__':
    sys.exit(main())
