#!/usr/bin/env python3
"""probe_bk24_codegen_diff.py — round-3 falsifier: qsort codegen vs layout.

Round 2 established: write() is DEAD CODE in the qsort-only fixture (the
fixture path is malloc -> qsort -> exit; out_flush/write never execute),
yet V_new is RED and V_trivial is GREEN. So the causal channel is what the
wrapper does to the TRANSLATION UNIT, not what it does at runtime:

  C1 (codegen): the wrapper changes <qsort>'s instruction stream
  C2 (layout):  <qsort> instructions are IDENTICAL; only its address /
                the surrounding symbol layout shifts.

This probe compiles HEAD's LIBC_C and the dirty LIBC_C side by side,
dumps <qsort>, <cmp_ilv>, <out_flush> etc., and diffs the instruction
streams per symbol. Read-only, disassembly only.
"""
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# HEAD's LIBC_C via git show into a temp module text
head_src = subprocess.run(
    ["git", "-C", str(_REPO), "show", "HEAD:tests/test_gh23_libc_runtime.py"],
    check=True, capture_output=True, text=True).stdout

spec = importlib.util.spec_from_file_location(
    "t_gh23", _REPO / "tests" / "test_gh23_libc_runtime.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

GCC = "riscv64-unknown-elf-gcc"
OBJDUMP = "riscv64-unknown-elf-objdump"


def _extract_libc(src: str) -> str:
    i = src.index('LIBC_C = r"""\\\n') + len('LIBC_C = r"""\\\n')
    j = src.index('"""', i)
    return src[i:j]


def symbol_ops(libc_text: str, tag: str) -> dict[str, list[str]]:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        libc = tmp / "libc.c"
        libc.write_text(libc_text)
        obj = tmp / "libc.o"
        subprocess.run([GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
                        "-nostdlib", "-fno-builtin", "-ffreestanding", "-w",
                        "-c", str(libc), "-o", str(obj)],
                       check=True, capture_output=True, timeout=60)
        out = subprocess.run([OBJDUMP, "-d", str(obj)],
                             check=True, capture_output=True,
                             text=True, timeout=60).stdout
    syms: dict[str, list[str]] = {}
    cur = None
    for ln in out.splitlines():
        m = re.match(r"^([0-9a-f]+) <([^>]+)>:$", ln)
        if m:
            cur = m.group(2)
            syms.setdefault(cur, [])
            continue
        if cur is None:
            continue
        parts = ln.split("\t")
        if len(parts) >= 3:
            op = parts[2].split("#")[0].strip()
            if re.match(r"^[0-9a-f]+:", parts[0].strip()):
                syms[cur].append(op)
    return syms


def main() -> int:
    old_libc = _extract_libc(head_src)
    new_libc = t.LIBC_C
    so = symbol_ops(old_libc, "old")
    sn = symbol_ops(new_libc, "new")
    print("old symbols:", sorted(so))
    print("new symbols:", sorted(sn))
    common = sorted(set(so) & set(sn))
    print("\n-- per-symbol instruction-stream diff (opcode only) --")
    changed = []
    for s in common:
        if s.startswith(".L"):
            continue
        if so[s] != sn[s]:
            changed.append(s)
            print(f"CHANGED {s}:")
            print(f"  old ({len(so[s])}): {'; '.join(so[s])}")
            print(f"  new ({len(sn[s])}): {'; '.join(sn[s])}")
    same = [s for s in common
            if s not in changed and not s.startswith(".L")]
    print("\nunchanged streams:", same)
    print("\nnew-only symbols:", sorted(set(sn) - set(so)))
    print("old-only symbols:", sorted(set(so) - set(sn)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
