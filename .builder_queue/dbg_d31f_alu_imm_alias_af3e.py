"""dbg_d31f_alu_imm_alias_af3e.py - DEFECT-31f: ALU/immediate lowering
scratch-lifetime aliasing, measured. New op-class question per the BK-29
ledger's next-tick line (31c = SB/SH else branches, 31e = store fix
branches; the ALU/imm paths were never probed).

Store convention for EVERY leg: base = x18 (s2, far from the x26..x30
scratch class), result stored via sw, 0(x18) -> word 768
(byte_to_word_mem). No leg touches x26/x27/x30 except L12, which
deliberately uses x30 as the store base to measure sltiu's unconditional
scratch bleed into RV x30.

Predicted from source reading (HEAD 96c97619):
  L1 andi  x29,x29,imm  (LDI r29 imm; AND r29 r29) -> stores the imm
  L2 ori   x29,x29,imm                             -> stores the imm
  L3 xori  x29,x29,imm                             -> stores 0
  L4 sub   x29,x28,x29  (rd==rs2 arm: SUB r29 r29) -> stores 0
  L5 neg   x29,x29                                 -> stores 0
  L6 srli  x29,x29,4                               -> stores 0
  L7 srai  x29,x29,4    (r29/r27 scratch)          -> sign bits only
  L8 slti  x29,x29,imm  (else arm consumes rs1 into rd first) -> 0
  L9 sltiu x29,x29,imm  (rs1 -> r28 BEFORE rd)     -> PASS (defensive
     ordering control; base x18 keeps x30 out of the way)
  L10 control: andi x28,x28,imm, base x18          -> PASS
  L11 control: sub  x28,x9,x28,  base x18          -> PASS
  L12 sltiu x8,x9,imm with BASE=x30: unconditional
      scratch bleed clobbers the store base        -> RED

Method identical to dbg_d31c/dbg_d31e: riscv64-unknown-elf-gcc
-march=rv32i -mabi=ilp32 -nostdlib, transpiled through BOTH the tree
transpiler AND a git-show-HEAD snapshot (op streams must be
byte-identical per pc -> latent at HEAD, not a lane regression), baked
via libc_runtime_kernel_image, run on GlyphRunner, mem[768] vs golden.
All legs expect halted=True faulted=False (silent misexecution).

Run: python3 .builder_queue/dbg_d31f_alu_imm_alias_af3e.py
Exit 0 = all PASS (ALU/imm paths clean). Exit 1 = at least one RED.
"""
import importlib.util
import shutil
import subprocess
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
spec = importlib.util.spec_from_file_location('t2g_head_f', head_path)
t2g_head = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2g_head)

# tag -> (asm, golden). Result word is ALWAYS 768 (base 0xC00).
CASES = {
    'L01_andi_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x1234
    andi x29, x29, 0xff
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0x1234),
    'L02_ori_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x1200
    ori  x29, x29, 0x34
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0x1234),
    'L03_xori_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x1234
    xori x29, x29, 0xff
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0x12CB),
    'L04_sub_rd_eq_rs2_x29': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x28, 0x100
    li   x29, 0x40
    sub  x29, x28, x29
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xC0),
    'L05_neg_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x1234
    neg  x29, x29
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xFFFFEDCC),
    'L06_srli_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x1230
    srli x29, x29, 4
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0x123),
    'L07_srai_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x80001230
    srai x29, x29, 4
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xF8000123),
    'L08_slti_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x5
    slti x29, x29, 0x10
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'L09_sltiu_x29_self': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x29, 0x5
    sltiu x29, x29, 0x10
    mv   x9, x29
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0x1),
    'L10_andi_x28_ctrl': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x28, 0x1234
    andi x28, x28, 0x34
    mv   x9, x28
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0x34),
    'L11_sub_x28_eq_rs2_ctrl': ("""
    .globl _start
_start:
    li   x18, 0xC00
    li   x10, 0x100
    li   x28, 0x40
    sub  x28, x10, x28
    mv   x9, x28
    sw   x9, 0(x18)
    li   a0, 0
    ret
""", 0xC0),
    'L12_sltiu_base_x30_bleed': ("""
    .globl _start
_start:
    li   x30, 0xC00
    li   x9, 0x5
    sltiu x8, x9, 0x10
    mv   x11, x8
    sw   x11, 0(x30)
    li   a0, 0
    ret
""", 0x1),
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
    c = d / (tag + '.S')
    c.write_text(src)
    elf = d / (tag + '.elf')
    r = subprocess.run(
        [gcc, '-march=rv32i', '-mabi=ilp32', '-nostdlib', '-nostartfiles',
         '-Ttext=0x200', '-o', str(elf), str(c)],
        capture_output=True, text=True)
    if r.returncode:
        print(tag, 'gcc FAILED', r.stderr[-200:])
        return None
    return elf.read_bytes()


def main():
    from tools.glyph_gpt.baker import libc_runtime_kernel_image
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.runner import GlyphRunner
    from test_gh23_libc_runtime import _load_posix_program

    results = []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for tag, (src, golden) in CASES.items():
            elf_bytes = build_elf(src, tag, d)
            if elf_bytes is None:
                return 1
            program = _load_posix_program(elf_bytes)
            src_tree = transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)
            src_head = t2g_head.transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)
            same = by_pc(src_tree) == by_pc(src_head)
            npy = d / (tag + '.npy')
            libc_runtime_kernel_image(build_default_atlas(), out_path=npy,
                                      user_program=program)
            r = GlyphRunner(npy, ram_words=16384)
            rec = r.run(max_instructions=20000, trace=False)
            got = rec['memory'][768]
            ok = (got == golden)
            results.append((tag, same, rec['halted'], rec['faulted'],
                            hex(got), hex(golden), ok))
            print(f'{tag}: tree==HEAD lowering: {same} | halted={rec["halted"]} '
                  f'faulted={rec["faulted"]} | mem[768]={hex(got)} '
                  f'(golden {hex(golden)}) -> {"PASS" if ok else "RED"}')

    red = [x for x in results if not x[-1]]
    print(f'\nSUMMARY: {len(results) - len(red)}/{len(results)} PASS, '
          f'{len(red)} RED')
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main())
