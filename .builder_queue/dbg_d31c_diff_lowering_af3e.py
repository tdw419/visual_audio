"""dbg_d31c_diff_lowering_af3e.py — falsifier 1b: transpile the same xv6-nano
scenario ELF with (a) the dirty tree lowering and (b) clean HEAD lowering
(git show HEAD:tools/rv64i_to_glyph.py loaded as a standalone module), and
diff the glyph op streams per RV pc label around the faulting address.

Run: .venv/bin/python .builder_queue/dbg_d31c_diff_lowering_af3e.py <scenario>
"""
import importlib.util, sys, tempfile, subprocess
from pathlib import Path

VA = Path('/home/jericho/projects/zion/projects/visual_audio')
for p in (str(VA / 'tools'), str(VA), str(VA / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_rv64i_to_glyph_xv6_nano as T  # noqa: E402
from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402

SCENARIO = int(sys.argv[1]) if len(sys.argv) > 1 else 6
FOCUS = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x6a0  # RV pc of interest

# load clean HEAD transpiler as module 't2g_head'
head_src = subprocess.check_output(
    ['git', '-C', str(VA), 'show', 'HEAD:tools/rv64i_to_glyph.py']).decode()
head_path = VA / '.builder_queue' / '_rv64i_to_glyph_HEAD_snapshot.py'
head_path.write_text(head_src)
spec = importlib.util.spec_from_file_location('t2g_head', head_path)
t2g_head = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2g_head)


def by_pc(src):
    """rv pc -> list of glyph ops (labels skipped)."""
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


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, objdump = T._build(SCENARIO, tmp)
        src_dirty = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start", byte_to_word_mem=True)
        src_head = t2g_head.transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start", byte_to_word_mem=True)
        d, h = by_pc(src_dirty), by_pc(src_head)
        pcs = sorted((p for p in set(d) | set(h) if p is not None))
        diffs = 0
        for pc in pcs:
            if d.get(pc) != h.get(pc):
                diffs += 1
                mark = ' <<< FOCUS' if pc == FOCUS else ''
                print(f"--- RV pc {pc:#010x}{mark}")
                print(f"  HEAD : {h.get(pc)}")
                print(f"  DIRTY: {d.get(pc)}")
        print(f"\ntotal differing RV instructions: {diffs}")
        if FOCUS in d:
            print(f"\nDIRTY lowering at focus pc {FOCUS:#x}:")
            for ln in d[FOCUS]:
                print("   ", ln)


if __name__ == '__main__':
    main()
