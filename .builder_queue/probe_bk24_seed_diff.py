#!/usr/bin/env python3
"""probe_bk24_seed_diff.py — round-7 falsifier: pointer-table seeds vs spliced cells.

Rounds 1-6 narrowed the defect to write()'s internal shape via the
transpile/load/bake pipeline. The loader's fixed-point seeding
(_load_posix_program) computes :pc_ packed PCs from a final-shape
assemble, then the bake SPLICES the task at SPLICE_OFFSET_CELLS=384. If
the two disagree for any :pc_ entry under the NEW layout, the comparator
RET pops a wrong PC — exactly the ticket's measured symptom.

This probe dumps, for GREEN (trivial) and RED (new) libc variants:
  - every :pc_ label's rv byte, spliced cell, packed value
  - the qsort symbol's rv32 address (from parse_elf symbols)
and diffs the two. Read-only; no engine run.
"""
import importlib.util
import re
import sys
import tempfile
from pathlib import Path

_REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

spec = importlib.util.spec_from_file_location(
    "t_gh23", _REPO / "tests" / "test_gh23_libc_runtime.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

spec2 = importlib.util.spec_from_file_location(
    "p_r1", _REPO / ".builder_queue" / "probe_bk24_wrapper_falsifier.py")
p1 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(p1)

import rv64i_to_glyph as r2g

CELLS_PER_ROW = 16
SPLICE_OFFSET_CELLS = 384


def collect(libc_text: str, tag: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = t._compile_elf(tmp, p1.QSORT_ONLY_C, libc_text=libc_text)
        base, text, symbols = r2g.parse_elf(elf)
        syms = {a: n for a, n in symbols.items()
                if not n.startswith("$") and n not in t.LINKER_JUNK}
        program = t._load_posix_program(elf)
        entries = {}
        for ln in program.splitlines():
            m = re.match(r"^:pc_([0-9a-f]+)\b", ln.strip())
            if m:
                entries[int(m.group(1), 16)] = ln.strip()
        qsort_addr = next((a for a, n in syms.items() if n == "qsort"), None)
        cmp_addr = next((a for a, n in syms.items()
                         if n == "cmp_ilv_unused"), None)
        print(f"== {tag}: qsort@{hex(qsort_addr) if qsort_addr else '?'} "
              f"cmp@{hex(cmp_addr) if cmp_addr else '?'} "
              f"pc_entries={len(entries)}", flush=True)
        for rv in sorted(entries):
            print(f"  :pc_{rv:02x} -> {entries[rv][:110]}")
        return {"entries": entries, "qsort": qsort_addr,
                "cmp": cmp_addr, "program": program}


def main() -> int:
    g = collect(p1.VARIANTS["V_trivial_write"], "GREEN trivial")
    b = collect(p1.VARIANTS["V_new_control"], "RED new")
    print("\n-- diff --")
    keys = sorted(set(g["entries"]) | set(b["entries"]))
    for k in keys:
        gv, bv = g["entries"].get(k), b["entries"].get(k)
        mark = "  " if gv == bv else "**"
        print(f"{mark} :pc_{k:02x}  G={gv}  R={bv}")
    print(f"\nqsort addr: green {hex(g['qsort'])} red {hex(b['qsort'])}")
    print(f"cmp addr:   green {hex(g['cmp'])} red {hex(b['cmp'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
