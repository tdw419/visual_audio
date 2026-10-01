#!/usr/bin/env python3
"""probe_bk24_auipc_isolate.py — round-5 falsifier: ONE auipc call site.

Rounds 1-4: wrapper body (not tile, not BSS, not codegen of other fns,
not size) is causal even though write() is dead code at runtime. The new
unit's distinguishing compile-time feature is write()'s auipc+jalr call
sites. This probe runs ONE engine leg: a write() whose body is a single
_call_pad() invocation compiled to auipc+jalr (dead code at runtime).

If RED -> the transpiler mishandles auipc-bearing units (defect site =
rv64i_to_glyph.py, fix worktree-isolated, next tick).
If GREEN -> auipc is not sufficient; escalate to two call sites / the
exact wrapper stream.
"""
import importlib.util
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

from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner

# write() with exactly ONE indirect-through-pad call site, never executed
ONE_SITE_WRITE = """\
extern int _write_frame(int fd, const void *src);

static int (* volatile sink)(int, const void *) = 0;

int write(int fd, const void *buf, unsigned len) {
    (void)buf; (void)len;
    return sink(fd, buf);   /* volatile fn-ptr call: gcc emits auipc+jalr */
}
"""

# also verify the compiled shape BEFORE spending an engine run
import re
import subprocess


def write_ops(libc_text: str) -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        libc = tmp / "libc.c"
        libc.write_text(libc_text)
        obj = tmp / "libc.o"
        subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                        "-mabi=ilp32", "-O1", "-nostdlib", "-fno-builtin",
                        "-ffreestanding", "-w", "-c", str(libc),
                        "-o", str(obj)], check=True, capture_output=True)
        out = subprocess.run(["riscv64-unknown-elf-objdump", "-d", str(obj)],
                             check=True, capture_output=True, text=True).stdout
    lines = out.splitlines()
    start = next(i for i, ln in enumerate(lines)
                 if re.match(r"^[0-9a-f]+ <write>:", ln))
    body = []
    for ln in lines[start + 1:]:
        if re.match(r"^[0-9a-f]+ <[^.][^>]*>:$", ln):
            break
        body.append(ln)
    ops = []
    for l in body:
        parts = l.split("\t")
        if len(parts) >= 3:
            ops.append(parts[2].split("#")[0].strip())
    return ops


def main() -> int:
    ops = write_ops(p1.VARIANTS["V_trivial_write"].replace(
        "    return _write_frame(fd, buf);",
        "    return sink(fd, buf);"))
    # build the one-site variant by text surgery on the trivial write
    trivial = p1.VARIANTS["V_trivial_write"]
    variant = trivial.replace(
        "int write(int fd, const void *buf, unsigned len) {",
        "int (*volatile sinkp)(int, const void *) = 0;\n\n"
        "int write(int fd, const void *buf, unsigned len) {").replace(
        "return _write_frame(fd, buf);",
        "return sinkp(fd, buf);")
    ops = write_ops(variant)
    n_auipc = sum(1 for o in ops if o == "auipc")
    n_jalr = sum(1 for o in ops if o.startswith("jalr"))
    print(f"write() ops={len(ops)} auipc={n_auipc} jalr={n_jalr}",
          flush=True)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = t._compile_elf(tmp, p1.QSORT_ONLY_C, libc_text=variant)
        program = t._load_posix_program(elf)
        out = tmp / "qsort_only.npy"
        import tools.glyph_gpt.libc_runtime as lr
        lr.libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                     user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        r = runner.run(max_instructions=200000, trace=True)
        mem = r["memory"]
        info = {
            "variant": "V_one_auipc_site",
            "halted": r["halted"], "faulted": r["faulted"],
            "steps": r.get("steps") or r.get("n_instructions"),
            "exit_word": mem[722], "brk": mem[723],
            "heap": [mem[2560 + i] for i in range(4)],
            "fault_addr": r.get("fault_addr"), "error": r.get("error"),
        }
        print(info, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
