#!/usr/bin/env python3
"""probe_bk24_auipc_ra_isolate.py — round-6 falsifier: the auipc+JALR ra pattern.

Round 5: one *indirect* call site via `lui+lw+jalr a5` (fn-ptr through a
data symbol) in dead code = GREEN. But write()'s real call sites compile
to `auipc ra, 0` + `jalr ra` — a PC-relative sequence that OVERWRITES ra
(the return address register) mid-function. In the transpiled image,
JALR-through-ra is exactly the CALLR machinery the pointer-table seeds.
Hypothesis: the presence of `auipc ra` (a two-instruction sequence whose
second half writes ra) breaks the transpiler/loader's return-PC
accounting even in dead code.

This variant puts an `extern`-reached call (gcc emits auipc ra + jalr ra
for externs at -O1 small model) in dead code. Disasm check first, then
one engine run.
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


def main() -> int:
    # the trivial write's extern call ALREADY compiles to auipc+jalr ra
    # (verified: round-2 disasm of V_trivial showed auipc ra,0 / jalr ra).
    # So re-run V_trivial unchanged but instrument the transpiled text:
    # does the glyph assembly contain the auipc's two LDI-shaped lines,
    # and where do the :pc_ labels land?
    variant = p1.VARIANTS["V_trivial_write"]
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = t._compile_elf(tmp, p1.QSORT_ONLY_C, libc_text=variant)
        program = t._load_posix_program(elf)
        # inspect the transpiled text for auipc artifacts
        import rv64i_to_glyph as r2g
        base, text, symbols = r2g.parse_elf(elf)
        syms = {a: n for a, n in symbols.items()
                if not n.startswith("$") and n not in t.LINKER_JUNK}
        lines = program.splitlines()
        n_auipc_shape = sum(1 for ln in lines
                            if "auipc" in ln.lower())
        # auipc lowers through the IR — count nothing; instead check
        # write()'s address span in RV32 bytes
        waddr = next((a for a, n in syms.items() if n == "write"), None)
        print(f"write rv32 addr: {hex(waddr) if waddr else None}",
              flush=True)
        print(f"literal 'auipc' occurrences in glyph text: "
              f"{n_auipc_shape}", flush=True)
        out = tmp / "qsort_only.npy"
        import tools.glyph_gpt.libc_runtime as lr
        lr.libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                     user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        r = runner.run(max_instructions=200000, trace=True)
        mem = r["memory"]
        info = {
            "variant": "V_trivial_recheck",
            "halted": r["halted"], "faulted": r["faulted"],
            "steps": r.get("steps") or r.get("n_instructions"),
            "exit_word": mem[722],
            "fault_addr": r.get("fault_addr"),
        }
        print(info, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
