"""BK-11 probe 50: decode the BAKED image cells 3650..3720 to recover
the actual executed instructions (opcode/reg/imm from the pixel RGB),
resolving the cell->instruction mystery from probe 49's trace.
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
sys.path.insert(0, "tests")

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.coreutils_port import coreutils_tool_elf  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from glyph_isa_v2 import OpcodeMapV2, _unpack_immediate  # noqa: E402
from test_gh23_libc_runtime import _load_posix_program  # noqa: E402

omap = OpcodeMapV2()

def decode(image, cell):
    x = (cell * 4) % (8 * 4)  # placeholder, cols resolved below
    raise SystemExit("cols handled in main")

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    program = _load_posix_program(elf)
    out = tmp / "wc.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    img = runner.image
    h, w, _ = img.shape
    cols_instrs = runner.cols_instrs
    print("image", img.shape, "cols_instrs", cols_instrs)

    def decode_cell(cell):
        px = cell * 4
        y = px // (cols_instrs * 4)
        x = px % (cols_instrs * 4)
        op = omap.rgb_to_opcode(tuple(img[y, x]))
        rs1, rs2, rd = [int(v) for v in img[y, x + 1]]
        imm = _unpack_immediate(tuple(img[y, x + 2]), tuple(img[y, x + 3]))
        return op, rs1, rs2, rd, imm

    for cell in range(3648, 3722):
        op, rs1, rs2, rd, imm = decode_cell(cell)
        print(f"cell {cell}: {op} rs1={rs1} rs2={rs2} rd={rd} imm={imm:#x}")
