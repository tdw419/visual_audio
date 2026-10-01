"""
G3 scale test: real 3-task round-robin scheduler via switch_to, not just two
sequential yields (Primitive 6). A central scheduler() loop resumes each
non-done task once per sweep; each task runs a genuine `for` loop of work
units, yielding back after each one. Exercises the transpiler + GlyphCPUv2 at
size (~160 RV instructions, several hundred glyph lines) and the RET/resume
dataflow fix under real loop-driven control flow rather than straight-line
sequential switch_to calls.

Ground truth: GPU SpatialRV64ICore (hand-tracing round-robin interleaving by
eye doesn't scale the way it did for the 2-task case; the GPU core is the
independent reference here, as it was for switch_to.c's fixture bug). Symbol
addresses read off `riscv64-unknown-elf-readelf -s`, not guessed -- the
switch_to.c fixture's first draft used wrong hand-guessed addresses here and
they were caught before trusting them.

Layout note: `_start`'s sp MUST be above stack_task's range (0x54c-0x84c
here) or the "main"/scheduler stack silently aliases task 2's stack -- caught
before this test was written, not by it (see switch_round_robin.c comment).
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.rv64i_to_glyph import (  # noqa: E402
    PTR_TABLE_BASE,
    assemble_glyph_to_pixels,
    build_pointer_table,
    parse_elf,
    transpile_elf_to_glyph,
)
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.spatial_rv64i_cpu import SpatialRV64ICore  # noqa: E402

_GCC_BIN = "riscv64-unknown-elf-gcc"
_OBJCOPY_BIN = "riscv64-unknown-elf-objcopy"
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "switch_round_robin.c"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

# Addresses read off `readelf -s` on the compiled fixture, not guessed.
SYM = {
    "g_total_switches": 0x300,
    "g_done_mask": 0x304,
    "g_log_idx": 0x308,
    "g_rounds": 0x500,
    "g_log": 0x4C0,
}
NTASKS = 3
WORK_UNITS = 3
EXPECTED_DONE_MASK = 0b111
EXPECTED_LOG_IDX = NTASKS * WORK_UNITS
EXPECTED_ROUNDS = [WORK_UNITS] * NTASKS


def _compile():
    tmp = Path(tempfile.mkdtemp())
    elf_path = tmp / "rr.elf"
    bin_path = tmp / "rr.bin"
    res = subprocess.run(
        [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
         "-Wl,-Ttext=0x0",
         "-Wl,--section-start=.sbss=0x300",
         "-Wl,--section-start=.bss=0x400",
         str(_FIXTURE), "-o", str(elf_path)],
        capture_output=True, text=True)
    assert res.returncode == 0, f"Compilation failed: {res.stderr}"

    objdump = subprocess.run(
        ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
        capture_output=True, text=True).stdout
    # -nostdlib has no __mulsi3; a runtime multiply (ctx_task[id] indexed by
    # a live loop var) would abort at link time, not silently misbehave --
    # but assert explicitly so a future struct-size change fails loudly here
    # instead of as a confusing undefined-reference at compile time.
    assert "mulsi3" not in objdump, (
        "runtime multiply crept in; struct context must stay power-of-2 sized")
    # Sanity: real loop back-edges (bne/blt to an earlier pc) must be present,
    # or this collapsed to straight-line code and lost the scale-test point.
    assert re.search(r"(bne|blt)\s+\w+,\w+,\s*[0-9a-f]+\s*<[^>]*>\s*$", objdump) or \
           re.search(r"\bj\s+[0-9a-f]+\s*<", objdump), (
        "no backward branch found; scheduler/task loops may have been "
        "unrolled or optimized away")

    res = subprocess.run(
        [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return elf_path.read_bytes(), bin_path.read_bytes()


def test_round_robin_differential():
    elf_bytes, bin_data = _compile()
    text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
    entry_addr = next(a for a, n in symbols.items() if n == "_start")

    # ---------- ground truth: GPU RV64 core ----------
    core = SpatialRV64ICore(16384)
    core.load_program(bin_data, entry_point=entry_addr)
    gpu_state = core.run_until_halt(max_cycles=200000, chunk_size=64)
    assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

    gpu_done = core.read_mem_word(SYM["g_done_mask"])
    gpu_log_idx = core.read_mem_word(SYM["g_log_idx"])
    gpu_switches = core.read_mem_word(SYM["g_total_switches"])
    gpu_rounds = [core.read_mem_word(SYM["g_rounds"] + 4 * i) for i in range(NTASKS)]
    gpu_log = [core.read_mem_word(SYM["g_log"] + 4 * i)
               for i in range(EXPECTED_LOG_IDX)]

    assert gpu_done == EXPECTED_DONE_MASK
    assert gpu_log_idx == EXPECTED_LOG_IDX
    assert gpu_rounds == EXPECTED_ROUNDS
    # Round-robin sweep order: task0-unit0, task1-unit0, task2-unit0,
    # task0-unit1, ... -- (id<<8)|unit for each.
    expected_log = [(t << 8) | u for u in range(WORK_UNITS) for t in range(NTASKS)]
    assert gpu_log == expected_log, f"GPU log {gpu_log!r} != {expected_log!r}"

    # ---------- transpiled glyph ----------
    # stack_addr is a LINEAR pixel index into the SAME image that holds the
    # program's own instructions (GlyphCPUv2._mem_write/_mem_read, used by
    # the hardware CALL/RET stack on r31, address the instruction image
    # directly -- there is no separate stack segment). It is auto-sized now
    # (stack_addr=None default) to a blank band _STACK_GAP_ROWS below the
    # code image, so it can't land on live code the way a hand-picked
    # literal (1500 here) once did for this ~560-line program.
    glyph_source = transpile_elf_to_glyph(
        elf_bytes, entry_symbol="_start",
        byte_to_word_mem=True)
    pixels, coords = assemble_glyph_to_pixels(
        glyph_source, cols_instrs=64, min_rows=32)
    ptr_table = build_pointer_table(text_bytes, text_vaddr, coords)

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    cpu.memory = [0] * 8192
    for word_idx, packed in ptr_table.items():
        cpu.memory[(PTR_TABLE_BASE >> 2) + word_idx] = packed
    cpu.pc = (0, 0)
    cpu.running = True
    for _ in range(200000):
        if not cpu.step(pixels):
            break
    assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"

    glyph_done = cpu.memory[SYM["g_done_mask"] >> 2]
    glyph_log_idx = cpu.memory[SYM["g_log_idx"] >> 2]
    glyph_switches = cpu.memory[SYM["g_total_switches"] >> 2]
    glyph_rounds = [cpu.memory[(SYM["g_rounds"] >> 2) + i] for i in range(NTASKS)]
    glyph_log = [cpu.memory[(SYM["g_log"] >> 2) + i] for i in range(EXPECTED_LOG_IDX)]

    assert glyph_done == gpu_done, f"Glyph done_mask {glyph_done} != GPU {gpu_done}"
    assert glyph_log_idx == gpu_log_idx
    assert glyph_switches == gpu_switches, (
        f"Glyph switches {glyph_switches} != GPU {gpu_switches}")
    assert glyph_rounds == gpu_rounds
    assert glyph_log == gpu_log, f"Glyph log {glyph_log!r} != GPU {gpu_log!r}"
