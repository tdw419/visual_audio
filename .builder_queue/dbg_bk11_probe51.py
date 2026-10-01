"""BK-11 probe 51: trace with on-the-fly opcode decode — log (step,
cell, opcode) for the whole run and dump the window around the space
iteration, so we see exactly which instruction the CPU executed at
each traced cell (catches bake/relocation skew between program text
and image).
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

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    program = _load_posix_program(elf)
    out = tmp / "wc.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    with contextlib.redirect_stdout(io.StringIO()):
        cpu = runner.get_cpu()
    img = runner.image
    rowpx = cpu.cols_instrs * 4

    def dec(x, y):
        op = omap.rgb_to_opcode(tuple(img[y, x]))
        rs1, rs2, rd = [int(v) for v in img[y, x + 1]]
        imm = _unpack_immediate(tuple(img[y, x + 2]), tuple(img[y, x + 3]))
        return f"{op} rd={rd} rs2={rs2} imm={imm:#x}"

    cpu.running = True
    steps = 0
    lines = []
    while cpu.running and steps < 60000:
        x, y = cpu.pc
        cell = y * cpu.cols_instrs + x // 4
        lines.append((steps, cell, dec(x, y), tuple(cpu.registers)))
        cpu.step(img)
        steps += 1
    # print steps 3388..3430 (the space-byte iteration)
    for s, c, dis, r in lines:
        if 3388 <= s <= 3432:
            print(s, c, dis, f"r12={r[12]} r14={r[14]:#x} r16={r[16]} r17={r[17]} r28={r[28]:#x} r29={r[29]:#x} r30={r[30]:#x}")
    mem = cpu.memory
    from test_gh23_libc_runtime import GH23_STDOUT_WORDS
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in GH23_STDOUT_WORDS).rstrip(b"\0")
    print("stdout:", got)
