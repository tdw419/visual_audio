"""dbg_d31e_fixbranch_alias_af3e.py — DEFECT-31c/31 SW fix-branch residual
aliasing: measure whether the LANDED rs1==30/rs1==29 guard branches are
themselves alias-free for the VALUE register rs2.

Prior art: .builder_queue/dbg_d31c_latent_alias_af3e.py measured the
ELSE branches (rs1 != 30) of SB/SH. This probe measures the FIX branches:

  A. SB/SH rs1==x30 fix branch (tools/rv64i_to_glyph.py:1058-1083 SB,
     :1163-1187 SH): value read is `LDI r26 0; ADD r26 r{rs2}` — AFTER
     r27/r28/r29 have been used as lane/shift/word_addr/cur_word scratch.
     Predicted RED for rs2 in {x26 (LDI r26 0 destroys it in-place),
     x27 (shift), x28 (word_addr), x29 (cur_word)}.
  B. SW rs1==x30 fix branch (:930-950): address temp is r28, shift temp
     r26; value path `LDI r28 0; ST r28 r28` when rs2==x0 — r28 IS the
     address temp on this path, so sw x0 should store to word 0 instead
     of the target. rs2==x26 predicted clobbered by `LDI r26 2`.
  C. SW rs1==x29 elif branch (:935-937): same r26 shift-temp clobber.
  D. control legs (non-aliased) must PASS.

Method identical to dbg_d31c_latent_alias_af3e.py: gcc rv32i -nostdlib,
transpile with tree AND HEAD transpiler (op streams must be byte-identical
per pc — latent-at-HEAD, not a lane regression), bake via
libc_runtime_kernel_image, run on GlyphRunner, compare mem[768]/mem[769]
against golden.

Run: python3 .builder_queue/dbg_d31e_fixbranch_alias_af3e.py
Exit 0 = all PASS (fix branches clean). Exit 1 = at least one RED.
"""
import importlib.util
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

VA = Path(__file__).resolve().parent.parent
for p in (str(VA / 'tools'), str(VA), str(VA / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402

head_src = subprocess.check_output(
    ['git', '-C', str(VA), 'show', 'HEAD:tools/rv64i_to_glyph.py']).decode()
head_path = VA / '.builder_queue' / '_rv64i_to_glyph_HEAD_snapshot.py'
head_path.write_text(head_src)
spec = importlib.util.spec_from_file_location('t2g_head_e', head_path)
t2g_head = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2g_head)

# base 0xC00 -> word 768 (byte_to_word_mem), 0xC04 -> word 769
CASES = {
    # --- A: SB fix branch (rs1 == x30), value register varying ---
    'A1_sb_fix_val_x26': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x26, 0x42
    sb   x26, 0(x30)
    li   a0, 0
    ret
""", 768, 0x42),
    'A2_sb_fix_val_x27': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x27, 0x43
    sb   x27, 0(x30)
    li   a0, 0
    ret
""", 768, 0x43),
    'A3_sb_fix_val_x28': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x28, 0x44
    sb   x28, 0(x30)
    li   a0, 0
    ret
""", 768, 0x44),
    'A4_sb_fix_val_x29': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x29, 0x45
    sb   x29, 0(x30)
    li   a0, 0
    ret
""", 768, 0x45),
    'A5_sb_fix_ctrl_t1': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   t1, 0x41
    sb   t1, 0(x30)
    li   a0, 0
    ret
""", 768, 0x41),
    # --- A-SH: SH fix branch, value x27 ---
    'A6_sh_fix_val_x27': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x27, 0x4243
    sh   x27, 0(x30)
    li   a0, 0
    ret
""", 768, 0x4243),
    # --- B: SW fix branch (rs1 == x30) ---
    # B1: sw x0 must zero word 769 (pre-poisoned with 0x1111).
    'B1_sw_fix_val_x0': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   t1, 0x1111
    sw   t1, 0(x30)
    sw   x0, 4(x30)
    li   a0, 0
    ret
""", 769, 0x0),
    'B2_sw_fix_val_x26': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x26, 0x2222
    sw   x26, 0(x30)
    li   a0, 0
    ret
""", 768, 0x2222),
    'B3_sw_fix_val_x28': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x28, 0x3333
    sw   x28, 0(x30)
    li   a0, 0
    ret
""", 768, 0x3333),
    'B4_sw_fix_val_x29_predpass': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x29, 0x4444
    sw   x29, 0(x30)
    li   a0, 0
    ret
""", 768, 0x4444),
    # --- C: SW rs1==x29 elif branch, value x26 (r26 = shift temp there) ---
    'C1_sw_x29base_val_x26': ("""
    .globl _start
_start:
    li   x29, 0xC00
    li   x26, 0x5555
    sw   x26, 0(x29)
    li   a0, 0
    ret
""", 768, 0x5555),
    # --- D: SW control, non-aliased ---
    'D1_sw_fix_ctrl_t1': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   t1, 0x6666
    sw   t1, 0(x30)
    li   a0, 0
    ret
""", 768, 0x6666),
}


def by_pc(src):
    out = {}
    cur = None
    for line in src.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith(':'):
            cur = int(s[4:], 16) if s[1:].startswith('pc_') else None
            continue
        out.setdefault(cur, []).append(s)
    return out


def build_elf(src, tag, d):
    gcc = shutil.which('riscv64-unknown-elf-gcc')
    if not gcc:
        print('SKIP: no riscv64-unknown-elf-gcc on PATH')
        return None
    c = d / f'{tag}.S'
    c.write_text(src)
    elf = d / f'{tag}.elf'
    r = subprocess.run(
        [gcc, '-march=rv32i', '-mabi=ilp32', '-nostdlib', '-nostartfiles',
         '-Ttext=0x200', '-o', str(elf), str(c)],
        capture_output=True, text=True)
    if r.returncode:
        print(tag, 'gcc FAILED', r.stderr[-200:])
        return None
    return elf.read_bytes()


def main():
    from tools.glyph_gpt.libc_runtime import libc_runtime_kernel_image
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.runner import GlyphRunner
    from test_gh23_libc_runtime import _load_posix_program

    results = []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for tag, (src, widx, golden) in CASES.items():
            elf_bytes = build_elf(src, tag, d)
            if elf_bytes is None:
                return 1
            program = _load_posix_program(elf_bytes)
            src_tree = transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)
            src_head = t2g_head.transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)
            same = by_pc(src_tree) == by_pc(src_head)
            npy = d / f'{tag}.npy'
            libc_runtime_kernel_image(build_default_atlas(), out_path=npy,
                                      user_program=program)
            r = GlyphRunner(npy, ram_words=16384)
            rec = r.run(max_instructions=20000, trace=False)
            got = rec['memory'][widx]
            ok = (got == golden)
            results.append((tag, same, rec['halted'], rec['faulted'],
                            hex(got), hex(golden), ok))
            print(f'{tag}: tree==HEAD lowering: {same} | halted={rec["halted"]} '
                  f'faulted={rec["faulted"]} | mem[{widx}]={hex(got)} '
                  f'(golden {hex(golden)}) -> {"PASS" if ok else "RED"}')

    red = [r for r in results if not r[-1]]
    print(f'\nSUMMARY: {len(results) - len(red)}/{len(results)} PASS, '
          f'{len(red)} RED')
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main())
