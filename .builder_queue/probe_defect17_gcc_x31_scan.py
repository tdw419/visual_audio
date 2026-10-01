#!/usr/bin/env python3
"""DEFECT-17 evidence probe (builder cron af3e62239ce2, read-only).

Question: the DEFECT-17 note says RV x31 (t6) lowers IDENTITY onto glyph r31,
which is the Glyph ISA hardware call-stack pointer, so any write to x31 destroys
the HW stack -> the next CALL/RET pops garbage. The note also says the gap is
"latent: no landed gate exercises this today (the coreutils/xv6/GH programs
happen not to keep a live t6 across a call)".

That last clause is the decision-relevant one for Jericho's ruling: is the
"stranger's C program runs provably unmodified" claim broken by *compiler output*
(GCC emits x31), or only by hand-written asm / non-GCC producers?

This probe asks the narrow measured question: over the exact corpus the landed
gates rest on, how many times does GCC emit a WRITE to x31 (t6)?

Sources of truth (no copies, no hardcoding):
  * BK-11 gate tools -> tools/glyph_gpt/coreutils_port.py: coreutils_tool_elf()
    (the gate's own ELF builder, same flags as the gate)
  * BK-1 gate program -> the C + rt0 source embedded in tests/test_bk1_argv.py
    (imported, not re-typed)
Everything else is objdump output parsing.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OBJDUMP = "riscv64-unknown-elf-objdump"
GCC = "riscv64-unknown-elf-gcc"

# A write to t6 is any instruction whose FIRST operand is t6.
_WRITE_T6 = re.compile(r"^\s*[0-9a-f]+:\s+[0-9a-f ]+\s+\S+\s+t6\s*,", re.M)
# Any mention at all (read or write).
_ANY_T6 = re.compile(r"\bt6\b")


def scan_asm(asm: str):
    writes = [m.group(0).strip() for m in _WRITE_T6.finditer(asm)]
    reads = [l.strip() for l in asm.splitlines()
             if _ANY_T6.search(l) and l.strip() not in writes]
    return writes, reads


def disasm(elf_bytes: bytes, tmp: Path, tag: str):
    p = tmp / f"{tag}.elf"
    p.write_bytes(elf_bytes)
    out = subprocess.run([OBJDUMP, "-d", str(p)],
                         capture_output=True, text=True, check=True)
    return out.stdout


def main() -> int:
    if shutil.which(OBJDUMP) is None or shutil.which(GCC) is None:
        print("SKIP: riscv toolchain not installed")
        return 2

    from tools.glyph_gpt.coreutils_port import coreutils_tool_elf, COREUTILS_FIXTURES
    from tests.test_bk1_argv import C_MAIN_SOURCE, START_ASM_SOURCE

    total_writes = 0
    rows = []

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        # 1) BK-11 corpus: the gate's own per-tool ELFs (3 fixtures each).
        for tool in ("cat", "echo", "wc", "cmp", "head"):
            for fx in sorted(COREUTILS_FIXTURES[tool]):
                elf = coreutils_tool_elf(tool, fx, tmp)
                asm = disasm(elf, tmp, f"bk11_{tool}_{fx}")
                w, r = scan_asm(asm)
                n_ins = len(re.findall(r"^\s*[0-9a-f]+:", asm, re.M))
                total_writes += len(w)
                rows.append((f"BK-11 {tool}/{fx}", n_ins, len(w), len(r), w[:3]))

        # 2) BK-1 corpus: the gate's own C main + rt0, compiled with the gate's flags.
        (tmp / "main.c").write_text(C_MAIN_SOURCE)
        (tmp / "start.S").write_text(START_ASM_SOURCE)
        elf_path = tmp / "bk1.elf"
        subprocess.run([GCC, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
                        "-Wl,-Ttext=0x0",
                        "-Wl,--section-start=.data=0x200",
                        "-Wl,--section-start=.sdata=0x208",
                        "-Wl,--section-start=.sbss=0x210",
                        "-Wl,--section-start=.bss=0x218",
                        str(tmp / "start.S"), str(tmp / "main.c"),
                        "-o", str(elf_path)], check=True)
        asm = disasm(elf_path.read_bytes(), tmp, "bk1")
        w, r = scan_asm(asm)
        n_ins = len(re.findall(r"^\s*[0-9a-f]+:", asm, re.M))
        total_writes += len(w)
        rows.append(("BK-1 argv (gate C + rt0)", n_ins, len(w), len(r), w[:3]))

    print(f"{'corpus':32s} {'#ins':>5s} {'t6-writes':>9s} {'t6-reads':>8s}  first")
    for name, n, nw, nr, sample in rows:
        print(f"{name:32s} {n:5d} {nw:9d} {nr:8d}  {sample}")
    print()
    print(f"TOTAL t6 WRITES over the landed gates' own corpus: {total_writes}")
    print("VERDICT:", "GCC EMITS x31 -> claim is reachable from compiler output"
          if total_writes else
          "no GCC-emitted x31 write in this corpus -> DEFECT-17 is latent for "
          "compiler output here (hand-written asm / other producers still at risk)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
