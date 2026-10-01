#!/usr/bin/env python3
"""probe_bk24_size_isolation.py — round-4 falsifier: SIZE alone vs content.

Rounds 1-3 established: qsort codegen identical old vs new; write() dead
code in the qsort-only fixture; trivial (small) write GREEN, real (large)
write RED. If SIZE ALONE is causal, appending a dead 20-instruction
function after the trivial write() (never called) must turn it RED.
If it stays GREEN, the causal channel is something specific to the new
wrapper's code shape (e.g. which cells the extra text occupies).

Read-only on tracked files; full engine runs like round 1.
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

DEAD_FUNCTION = """

/* DEAD padding function — never called; exists only to shift layout. */
int dead_pad_0(int x) {
    int a = x + 1; a ^= 0x5A5A; a += x;
    a ^= a >> 3; a *= 7; a += 12345; a ^= a << 5;
    a -= x; a ^= 0xA5A5; a += a >> 7; a *= 3;
    return a - 1;
}
"""


def run_variant(name: str, libc_text: str) -> dict:
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.runner import GlyphRunner
    import tools.glyph_gpt.libc_runtime as lr
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = t._compile_elf(tmp, p1.QSORT_ONLY_C, libc_text=libc_text)
        program = t._load_posix_program(elf)
        out = tmp / "qsort_only.npy"
        lr.libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                     user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        r = runner.run(max_instructions=200000, trace=True)
        mem = r["memory"]
        return {
            "variant": name,
            "halted": r["halted"],
            "faulted": r["faulted"],
            "steps": r.get("steps") or r.get("n_instructions"),
            "exit_word": mem[722],
            "brk": mem[723],
            "heap": [mem[2560 + i] for i in range(4)],
            "fault_addr": r.get("fault_addr"),
            "error": r.get("error"),
        }


def main() -> int:
    from tools.glyph_gpt.atlas import build_default_atlas  # noqa: F401
    variants = {
        # trivial write + dead pad function appended at unit end
        "V_trivial_plus_dead": p1.VARIANTS["V_trivial_write"] + DEAD_FUNCTION,
    }
    for name, txt in variants.items():
        info = run_variant(name, txt)
        print(info, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
