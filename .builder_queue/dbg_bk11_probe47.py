"""BK-11 probe 47: run real wc/two_lines with trace and reconstruct
 glyph-register history around the word-increment region. The glyph
 program text is available (program string); we run GlyphRunner with
 trace=True and inspect the receipt trace frames for the loop pcs.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.coreutils_port import coreutils_tool_elf  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tests.test_gh23_libc_runtime import _load_posix_program  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    program = _load_posix_program(elf)
    Path("output/bk11_wc_prog.txt").write_text(program)
    out = tmp / "wc.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    print("halted:", receipt.get("halted"), "faulted:", receipt.get("faulted"))
    trace = receipt.get("trace") or []
    print("trace frames:", len(trace))
    if trace:
        f0 = trace[0]
        print("frame keys:", sorted(f0.keys()) if isinstance(f0, dict) else type(f0))
        print(str(f0)[:300])
        Path("output/bk11_wc_trace47.txt").write_text("\n".join(str(f) for f in trace))
