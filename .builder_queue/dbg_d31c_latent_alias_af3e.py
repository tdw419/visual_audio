"""dbg_d31c_latent_alias_af3e.py — DEFECT-31c receipt follow-up: measure the
latent aliasing classes the minimal fix (rs1==30-only guard) did NOT cover.

Classes (tools/rv64i_to_glyph.py, OP_SB :1038-1111 / OP_SH :1157-1215):
  A. rs1 == x29 (t4): the non-aliased else-branch uses r29 as its lane/shift
     scratch and re-reads rs1 (`LDI r30 imm; ADD r30 r29` a second time).
     If the shift/r29 write happens between the two reads of the base, the
     second ADD consumes a CORRUPTED base.
  B. rs2 == x27 (s11... actually x27 = t2/scratch under the identity map):
     value is loaded late via `LDI r26 0; ADD r26 r27` in SB — but the SH
     else-branch uses r27 as its MASK scratch (`LDI r27 0xffff; SHL r27 r28`)
     BEFORE `_emit_add_reg(r26, rs2)` re-reads rs2==x27. Mask write may
     clobber the value register before the value is read.
  C. control (no aliasing) — must stay byte-identical to HEAD.

Method: transpile minimal RV32I programs with HEAD's transpiler (git show
HEAD:tools/rv64i_to_glyph.py, standalone module) AND the tree's, diff the
glyph op stream per RV pc; then RUN both images on GlyphRunner and compare
stored memory bytes against the golden expectation.

Run: python3 .builder_queue/dbg_d31c_latent_alias_af3e.py
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

# --- load HEAD transpiler as an isolated module -------------------------
head_src = subprocess.check_output(
    ['git', '-C', str(VA), 'show', 'HEAD:tools/rv64i_to_glyph.py']).decode()
head_path = VA / '.builder_queue' / '_rv64i_to_glyph_HEAD_snapshot.py'
head_path.write_text(head_src)
spec = importlib.util.spec_from_file_location('t2g_head', head_path)
t2g_head = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2g_head)

CASES = {
    # A: base x29 — exercises the second ADD re-read + r29 scratch
    'A_sb_base_x29': """
    .globl _start
_start:
    li   t4, 0xC00
    li   t1, 0x41
    sb   t1, 0(t4)
    li   a0, 0
    ret
""",
    # B: value x27 (EXPLICIT numeric reg — x26/x27 are unnamed in RV32I,
    # gcc will never allocate them from a C-level temp name)
    'B_sb_val_x27': """
    .globl _start
_start:
    li   s1, 0xC00
    li   x27, 0x42
    sb   x27, 0(s1)
    li   a0, 0
    ret
""",
    # B2: value x27 through SH (mask scratch is r27 in the else branch)
    'B2_sh_val_x27': """
    .globl _start
_start:
    li   s1, 0xC00
    li   x27, 0x4243
    sh   x27, 0(s1)
    li   a0, 0
    ret
""",
    # D: value x26 (value scratch r26 in the else branch)
    'D_sb_val_x26': """
    .globl _start
_start:
    li   s1, 0xC00
    li   x26, 0x44
    sb   x26, 0(s1)
    li   a0, 0
    ret
""",
    # A2: base x29 through SH (r29 is the shift scratch)
    'A2_sh_base_x29': """
    .globl _start
_start:
    li   t4, 0xC00
    li   t1, 0x4243
    sh   t1, 0(t4)
    li   a0, 0
    ret
""",
    # C: control — no scratch aliasing, base s1, value t1
    'C_ctrl_sb': """
    .globl _start
_start:
    li   s1, 0xC00
    li   t1, 0x41
    sb   t1, 0(s1)
    li   a0, 0
    ret
""",
}

GOLDEN_MEM768 = {
    'A_sb_base_x29': 0x41,
    'B_sb_val_x27': 0x42,
    'B2_sh_val_x27': 0x4243,
    'D_sb_val_x26': 0x44,
    'A2_sh_base_x29': 0x4243,
    'C_ctrl_sb': 0x41,
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


def run_image(npy, runner_factory):
    from tools.glyph_gpt.runner import GlyphRunner  # noqa
    r = GlyphRunner(npy, ram_words=16384)
    receipt = r.run(max_instructions=20000, trace=False)
    return receipt


def main():
    from tools.glyph_gpt.baker import libc_runtime_kernel_image
    from tools.glyph_gpt.atlas import build_default_atlas
    try:
        from test_gh23_libc_runtime import _load_posix_program
    except ImportError:
        _load_posix_program = None

    results = []
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for tag, src in CASES.items():
            elf_bytes = build_elf(src, tag, d)
            if elf_bytes is None:
                return 1
            program = _load_posix_program(elf_bytes)
            src_tree = transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)
            src_head = t2g_head.transpile_elf_to_glyph(
                elf_bytes, entry_symbol='_start', byte_to_word_mem=True)

            same = by_pc(src_tree) == by_pc(src_head)
            # bake + run TREE image
            npy = d / f'{tag}.npy'
            libc_runtime_kernel_image(build_default_atlas(), out_path=npy,
                                      user_program=program)
            rec = run_image(npy, None)
            mem768 = rec['memory'][768]
            ok = (mem768 == GOLDEN_MEM768[tag])
            results.append((tag, same, rec['halted'], rec['faulted'],
                            hex(mem768), hex(GOLDEN_MEM768[tag]), ok))
            print(f'{tag}: tree==HEAD lowering: {same} | halted={rec["halted"]} '
                  f'faulted={rec["faulted"]} | mem[768]={hex(mem768)} '
                  f'(golden {hex(GOLDEN_MEM768[tag])}) -> {"PASS" if ok else "RED"}')

    red = [r for r in results if not r[-1]]
    print(f'\nSUMMARY: {len(results) - len(red)}/{len(results)} PASS, '
          f'{len(red)} RED')
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main())
