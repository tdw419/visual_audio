"""BK-11 probe 49: step wc/two_lines on the real CPU, logging r10..r18
(a0..a7), r6/r7 (t1/t2), r28/r29/r30 (t3/t4/t5) at each step whose pc
maps into the counting loop (RV pc 0xfc..0x144 -> glyph instr rows).
Identify the exact step where the words counter (a6) fails to bump.
"""
import contextlib
import io
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
    out = tmp / "wc.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    with contextlib.redirect_stdout(io.StringIO()):
        cpu = runner.get_cpu()
    # find instr indices: the program text labels pc_XXXXXX by byte addr.
    # text base = 0 in the transpiled module; image row = base_row + pc/4?
    # Instead: locate labels from the program text and the bake.
    prog = program
    # run to exit while logging steps: log everything, filter later
    log = []
    cpu.running = True
    steps = 0
    while cpu.running and steps < 60000:
        x, y = cpu.pc
        idx = y * cpu.cols_instrs + x // 4
        regs = {n: cpu.registers[n] for n in
                (10, 11, 12, 13, 14, 15, 16, 17, 6, 28, 29, 30, 2)}
        log.append((idx, regs))
        cpu.step(runner.image)
        steps += 1
    print("total steps:", steps)
    Path("output/bk11_wc_log49.txt").write_text(
        "\n".join(f"{i} {r}" for i, r in log))
    # also dump final stdout window from cpu.memory
    mem = cpu.memory
    # GH23_STDOUT_WORDS from test module
    from tests.test_gh23_libc_runtime import GH23_STDOUT_WORDS
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in GH23_STDOUT_WORDS).rstrip(b"\0")
    print("stdout:", got)
