"""BK-11 root-cause probe 2: order-dependence + symbol-collision tests.

Trial A: compile ONLY the tool TU (no libc .o) — do the wc word counts
come out right? (Isolates whether linking the libc changes text layout.)
Trial B: rename every tool-side `out_`/`_n`/`_buf` symbol to bk11_* via
the C source only (already done) BUT with the libc also linked —
repeat twice with different fixture ORDER to see if results rotate.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.coreutils_port import (  # noqa: E402
    coreutils_tool_elf, COREUTILS_FIXTURES)
from tests.test_gh23_libc_runtime import (  # noqa: E402
    _load_posix_program, GH23_STDOUT_WORDS)


def run_tool(tool, fx_name, tmp):
    elf = coreutils_tool_elf(tool, fx_name, tmp)
    program = _load_posix_program(elf)
    out = tmp / f"{tool}_{fx_name}.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    mem = receipt["memory"]
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in GH23_STDOUT_WORDS).rstrip(b"\0")
    return got


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    print("== Trial B: fixture-order sensitivity ==")
    for order in (["one_line", "two_lines", "three_lines"],
                  ["two_lines", "one_line", "three_lines"]):
        results = []
        for fx in order:
            r = run_tool("wc", fx, tmp)
            results.append((fx, r))
        print("  order:", order)
        for fx, r in results:
            want = str(COREUTILS_FIXTURES["wc"][fx]["output"]).encode()
            print(f"    {fx}: got {r!r} want {want!r} "
                  f"{'OK' if r == want else 'MISMATCH'}")
