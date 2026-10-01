"""BK-11 probe 48: run wc/two_lines with the real glyph_isa_v2 CPU so
we can step and inspect registers at each pc. Use the runner's own CPU
class directly: build the image via libc_runtime_kernel_image, then
instantiate the CPU (as runner.run does) and step manually, logging
(a0..a7, t1..t6, sp) around the wc counting loop.
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

import glyph_isa_v2 as gi  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    program = _load_posix_program(elf)
    out = tmp / "wc.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)

    # Peek how GlyphRunner constructs its CPU so we mirror it exactly.
    import inspect
    src = inspect.getsource(GlyphRunner.run)
    print(src[:1500])
