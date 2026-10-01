"""BK-11 probe 46: step the real wc/two_lines glyph program and dump
(a0, a2, a5, a6, a7, t1, t3, t4) each time pc enters the counting loop
head (pc 0x110 region). Watch which words-increment is skipped and what
the compare-branch scratch actually did.
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

# pc -> instr index: code is byte_to_word_mem, 1 instr/word from base.
# The GH-23 loader places text at a known base; find from program metadata.
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    program = _load_posix_program(elf)
    print("program keys:", sorted(program.keys()) if isinstance(program, dict) else type(program))
    print(str(program)[:800])
