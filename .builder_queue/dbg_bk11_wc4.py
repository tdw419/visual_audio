"""BK-11 wc debug 4: does the RUNNER see the seeded data? Dump the glyph
runner's memory at the data words (1720..1723) AFTER the run, plus the
exit-time registers if the receipt has a trace tail."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.coreutils_port import coreutils_tool_elf  # noqa: E402
from tests.test_gh23_libc_runtime import _load_posix_program  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    program = _load_posix_program(elf)
    out = tmp / "wc.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    mem = receipt["memory"]
    print("data words 1720..1735 (byte-wise):")
    for w in range(1720, 1736):
        b = int(mem[w]).to_bytes(4, "little")
        print(f"  word {w}: {int(mem[w]):#010x}  {b!r}")
    # byte addressing check: lbu a5,0(a5) with a5 = 1720 — if the engine
    # addresses LD/LBU by WORD index, byte addr 1720 = word 430 = data at
    # byte 1720 is word 430*4=1720 ... print both candidates
    for w in (429, 430, 431):
        b = int(mem[w]).to_bytes(4, "little")
        print(f"  word {w} (byte-addr view): {int(mem[w]):#010x}  {b!r}")
