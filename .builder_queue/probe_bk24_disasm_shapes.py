#!/usr/bin/env python3
"""probe_bk24_disasm_shapes.py — round-2 falsifier: the call-frame shape.

Round 1 (RECEIPT_BK24_wrapper_falsifier_round1.md): trivial pass-through
write() GREEN; any wrapper with a body around _write_frame RED.
This probe dumps FULL disassembly of <write> for both variants and counts
call instructions. Read-only; disassembly only, no engine runs.
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

spec = importlib.util.spec_from_file_location(
    "t_gh23", _REPO / "tests" / "test_gh23_libc_runtime.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

spec2 = importlib.util.spec_from_file_location(
    "p_r1", _REPO / ".builder_queue" / "probe_bk24_wrapper_falsifier.py")
p1 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(p1)

GCC = "riscv64-unknown-elf-gcc"
OBJDUMP = "riscv64-unknown-elf-objdump"


def write_body(tag: str, libc_text: str) -> list[str]:
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
    # slice between "<write>:" and the next GLOBAL symbol label
    # (local labels like <.L20> appear inline and must NOT cut the slice)
    lines = out.splitlines()
    start = next(i for i, ln in enumerate(lines)
                 if re.match(r"^[0-9a-f]+ <write>:", ln))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if re.match(r"^[0-9a-f]+ <[^.][^>]*>:$", ln):
            end = i
            break
    body = lines[start + 1:end]
    print(f"== {tag} :: <write> ({len(body)} instrs) ==")
    for ln in body:
        print(ln)
    return body


def stats(body: list[str]) -> dict:
    ops = []
    for l in body:
        parts = l.split("\t")
        if len(parts) >= 3:
            ops.append(parts[2].split("#")[0].strip())
    return {
        "n": len(ops),
        "calls": [o for o in ops if re.match(r"(jal|jalr|call)", o)],
        "rets": [o for o in ops if o == "ret"],
        "sp_ops": [o for o in ops if "sp" in o],
        "ra_ops": [o for o in ops if "ra" in o.split()[-1][:3] or re.search(r"\bra\b", o)],
    }


def main() -> int:
    b_triv = write_body("V_trivial_write", p1.VARIANTS["V_trivial_write"])
    b_new = write_body("V_new_control", p1.VARIANTS["V_new_control"])
    s_triv, s_new = stats(b_triv), stats(b_new)
    print("trivial stats:", s_triv)
    print("new     stats:", s_new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
