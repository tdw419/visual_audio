#!/usr/bin/env python3
"""dbg_d31k_ecall_rewrite_af3e.py - DEFECT-31k: the GH-23 loader's ECALL
rewrite contract is adjacency-keyed on a lowered `LDI r17`, and any a7 load
that does not lower to ONE bare `LDI r17` immediately before the ecall leaves
a bare HALT - the machine stops SILENTLY mid-program.

Source reading (HEAD eb4dc784):
  - tools/rv64i_to_glyph.py:1438-1440: ecall (0x73, funct12=0 -> OP_ECALL)
    lowers to bare "HALT".
  - tests/test_gh23_libc_runtime.py:435 (the loader): "HALT" -> "SYSCALL r10"
    ONLY when the immediately-preceding emitted line starts "LDI r17 ".
  - tests/test_gh23_libc_runtime.py:795-804: a landing gate ASSERTS that
    adjacency - load-bearing for the fixture's `li a7,N; ecall` thunks only.
  - tools/glyph_isa_v2.py:1320-1322 + :616: HALT sets running=False with
    halt_reason=None - a mid-program stop is indistinguishable from clean halt.

Legs (buf word0 = word 900 / byte 0xE10; marker = word 901; both clear of the
GH-23 ring [768,832), window 718-721, brk 723, cursor 724):
  C01 control: li a7,64; ecall adjacent -> window=0x1234, marker=0x1234  PASS
  L02 RED:    one intervening op        -> window/marker dead (silent)   RED
  L03 RED:    mv a7,x5 runtime sysnum   -> window/marker dead (silent)   RED

Run: python3 .builder_queue/dbg_d31k_ecall_rewrite_af3e.py
Exit 0 = all PASS (rewrite contract holds). Exit 1 = at least one RED.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

VA = Path(__file__).resolve().parent.parent
for p in (str(VA / 'tools'), str(VA), str(VA / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

_spec = importlib.util.spec_from_file_location(
    'dbg_d31f_harness',
    VA / '.builder_queue' / 'dbg_d31f_alu_imm_alias_af3e.py')
assert _spec is not None
d31f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d31f)

WINDOW = 718   # GH-23 legacy stdout mirror (word0)
MARKER = 902   # post-ecall continuation marker (byte 0xE18; word 901 holds
               # the PRE-ecall sw x10,4(x18) store on purpose)

CASES = {
    'C01_ecall_adjacent_li': ("""
    .globl _start
_start:
    li   x18, 0xE10
    li   x9, 0x1234
    sw   x9, 0(x18)
    li   x10, 0x4567
    sw   x10, 4(x18)
    li   x11, 0xE10
    li   a0, 0
    li   a7, 64
    ecall
    sw   x9, 8(x18)
    li   a0, 0
    ret
""", 0x1234),
    'L02_ecall_intervening_op': ("""
    .globl _start
_start:
    li   x18, 0xE10
    li   x9, 0x1234
    sw   x9, 0(x18)
    li   x11, 0xE10
    li   a0, 0
    li   a7, 64
    li   x10, 0
    ecall
    sw   x9, 8(x18)
    li   a0, 0
    ret
""", 0x1234),
    'L03_ecall_runtime_sysnum': ("""
    .globl _start
_start:
    li   x18, 0xE10
    li   x9, 0x1234
    sw   x9, 0(x18)
    li   x11, 0xE10
    li   a0, 0
    li   x5, 64
    mv   a7, x5
    ecall
    sw   x9, 8(x18)
    li   a0, 0
    ret
""", 0x1234),
}


def main():
    from tools.glyph_gpt.baker import libc_runtime_kernel_image
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.runner import GlyphRunner
    from test_gh23_libc_runtime import _load_posix_program

    results = []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for tag, (src, golden) in CASES.items():
            elf_bytes = d31f.build_elf(src, tag, d)
            if elf_bytes is None:
                return 1
            program = _load_posix_program(elf_bytes)
            n_sys = sum(1 for ln in program.splitlines()
                        if ln.split(';')[0].strip() == 'SYSCALL r10')
            src_tree = d31f.transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)
            src_head = d31f.t2g_head.transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)
            same = d31f.by_pc(src_tree) == d31f.by_pc(src_head)
            npy = d / (tag + '.npy')
            libc_runtime_kernel_image(build_default_atlas(), out_path=npy,
                                      user_program=program)
            r = GlyphRunner(npy, ram_words=16384)
            rec = r.run(max_instructions=20000, trace=False)
            win = rec['memory'][WINDOW]
            mark = rec['memory'][MARKER]
            ok = (win == golden) and (mark == golden)
            results.append((tag, same, rec['halted'], rec['faulted'],
                            n_sys, win, mark, ok))
            print(f'{tag}: tree==HEAD: {same} | rewritten_ecalls: {n_sys} | '
                  f'halted={rec["halted"]} faulted={rec["faulted"]} '
                  f'| window[718]={hex(win)} marker[902]={hex(mark)} '
                  f'(golden {hex(golden)}) -> {"PASS" if ok else "RED"}',
                  flush=True)

    red = [x for x in results if not x[-1]]
    print(f'\nSUMMARY: {len(results) - len(red)}/{len(results)} PASS, '
          f'{len(red)} RED', flush=True)
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main())
