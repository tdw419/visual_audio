#!/usr/bin/env python3
"""DEFECT-17 evidence probe, leg 2 (builder cron af3e62239ce2, read-only).

Leg 1 (probe_defect17_gcc_x31_scan.py) measured 0 x31 (t6) references across the
16 gate-resting programs at the gate contract's own flags (-O1). This leg asks
the follow-up question that decides severity for Jericho's ruling:

  Is x31 reachable from *compiler output* at other optimization levels?

Corpus, again taken from the tree rather than re-typed:
  * tests/test_gh23_libc_runtime.py: LIBC_C + SHIM_S -- the freestanding libc /
    shim the GH-23 and BK-11 gates link against every run
  * tests/test_bk1_argv.py: the gate's C main + rt0
Sweep: -O0 / -O1 / -O2 / -O3 / -Os.
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
# NOTE: re.M is REQUIRED on all three -- without it these patterns match only the
# first line and every count comes back 0 (a vacuous "no x31 found", measured and
# self-caught by the author before this receipt was written).
_WRITE_T6 = re.compile(r"^\s*[0-9a-f]+:\s+[0-9a-f ]+\s+\S+\s+t6\s*,", re.M)
_ANY_T6 = re.compile(r"\bt6\b")
_N_INS = re.compile(r"^\s*[0-9a-f]+:", re.M)


def count(asm: str):
    return (len(_N_INS.findall(asm)),
            len(_WRITE_T6.findall(asm)),
            len([l for l in asm.splitlines() if _ANY_T6.search(l)]))


def main() -> int:
    if shutil.which(OBJDUMP) is None or shutil.which(GCC) is None:
        print("SKIP: riscv toolchain not installed")
        return 2

    from tests.test_gh23_libc_runtime import LIBC_C, SHIM_S
    from tests.test_bk1_argv import C_MAIN_SOURCE, START_ASM_SOURCE

    units = {"gh23_libc.c": LIBC_C, "bk1_main.c": C_MAIN_SOURCE}
    opts = ["-O0", "-O1", "-O2", "-O3", "-Os"]
    print(f"{'unit':14s} {'opt':4s} {'#ins':>5s} {'t6w':>4s} {'t6*':>4s}")
    any_hit = 0
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for name, text in units.items():
            src = tmp / name
            src.write_text(text)
            for opt in opts:
                obj = tmp / f"{name}.{opt}.o"
                p = subprocess.run(
                    [GCC, "-march=rv32i", "-mabi=ilp32", opt, "-nostdlib",
                     "-fno-builtin", "-ffreestanding", "-w", "-c", str(src),
                     "-o", str(obj)], capture_output=True, timeout=120)
                if p.returncode != 0:
                    print(f"{name:14s} {opt:4s} COMPILE-FAIL "
                          f"{p.stderr.decode()[:80]!r}")
                    continue
                asm = subprocess.run([OBJDUMP, "-d", str(obj)],
                                     capture_output=True, text=True,
                                     check=True).stdout
                n, nw, na = count(asm)
                any_hit += nw
                print(f"{name:14s} {opt:4s} {n:5d} {nw:4d} {na:4d}")

        # rt0 shim is hand-written asm: does the *gate's own* asm touch x31?
        s = tmp / "shim.S"
        s.write_text(SHIM_S)
        p = subprocess.run([GCC, "-march=rv32i", "-mabi=ilp32", "-nostdlib", "-w",
                            "-c", str(s), "-o", str(tmp / "shim.o")],
                           capture_output=True, timeout=120)
        if p.returncode == 0:
            asm = subprocess.run([OBJDUMP, "-d", str(tmp / "shim.o")],
                                 capture_output=True, text=True, check=True).stdout
            n, nw, na = count(asm)
            any_hit += nw
            print(f"{'gh23 shim.S':14s} {'asm':4s} {n:5d} {nw:4d} {na:4d}")
        b = tmp / "bk1_start.S"
        b.write_text(START_ASM_SOURCE)
        p = subprocess.run([GCC, "-march=rv32i", "-mabi=ilp32", "-nostdlib", "-w",
                            "-c", str(b), "-o", str(tmp / "bk1_start.o")],
                           capture_output=True, timeout=120)
        if p.returncode == 0:
            asm = subprocess.run([OBJDUMP, "-d", str(tmp / "bk1_start.o")],
                                 capture_output=True, text=True, check=True).stdout
            n, nw, na = count(asm)
            any_hit += nw
            print(f"{'bk1 start.S':14s} {'asm':4s} {n:5d} {nw:4d} {na:4d}")

    print()
    print(f"TOTAL x31 (t6) writes over the -O sweep: {any_hit}")
    print("VERDICT:", "x31 reachable from compiler output" if any_hit else
          "no x31 write at -O0..-O3/-Os on this corpus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
