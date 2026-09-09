"""
switch_to (swtch.S-style cooperative context switch) differential test.

This is the primitive that forces the RET/resume ambiguity flagged after
proc-table: switch_to's terminal `ret` (jalr zero, 0(ra)) ALWAYS executes with
ra freshly reloaded from a data pointer two instructions earlier
(`lw ra, 0(a1)`) -- whether the jump lands on a task's fresh entry point
(task_b's first activation) or resumes it mid-function (every switch back).
Confirmed in the compiled fixture's disassembly: switch_to's ret at offset
0x10 is `lw ra,0(a1) / lw sp,4(a1) / ret`, structurally identical to (and
statically adjacent to) run_all's ORDINARY call-preserved ret at 0x150
(`lw ra,12(sp) / addi sp,sp,16 / ret`) -- both are plain `jalr zero,0(ra)`,
and the transpiler's syntactic rule (rd==0 && rs1==ra && imm==0 -> RET) cannot
tell them apart by inspecting one instruction. The fixture deliberately
contains both cases so the suite can't pass by only exercising one.

Ground truth: hand-traced (not native x86 -- the mechanism is raw RV32 asm,
doesn't port). Verified against the compiled fixture's own disassembly
(addresses below read directly off `riscv64-unknown-elf-objdump -d`, not
guessed) before trusting the expected constants -- same discipline as the
proc-table SYM table.

  run_all: ctx_a={ra:&task_a}, ctx_b={ra:&task_b}
  1. switch_to(main, a)   -> FRESH START task_a         log[0]=0x1111
  2. switch_to(a, b)      -> FRESH START task_b          log[1]=0x2222
  3. switch_to(b, a)      -> RESUME task_a (mid-function) log[2]=0x3333
  4. switch_to(a, b)      -> RESUME task_b (mid-function) log[3]=0x4444, done=1
  5. switch_to(b, main)   -> RESUME run_all (ordinary return via its own
                              call-preserved ra) -> _start -> ecall

Expected: g_log = [0x1111,0x2222,0x3333,0x4444], g_log_idx=4, g_done=1.
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
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "switch_to.c"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

# Addresses read off the compiled fixture's objdump, not guessed.
SYM = {
    "g_done": 0x300,
    "g_log_idx": 0x304,
    "g_log": 0x400,
}
EXPECTED_LOG = [0x1111, 0x2222, 0x3333, 0x4444]
EXPECTED_LOG_IDX = 4
EXPECTED_DONE = 1


def _compile():
    tmp = Path(tempfile.mkdtemp())
    elf_path = tmp / "switch_to.elf"
    bin_path = tmp / "switch_to.bin"
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
    # Sanity: the fixture must contain BOTH ret shapes, or it lost its point.
    assert re.search(r"lw\s+ra,0\(a1\)", objdump), (
        "no data-reload-then-ret in codegen; switch_to collision not exercised")
    assert re.search(r"lw\s+ra,\d+\(sp\)", objdump), (
        "no ordinary call-preserved ret in codegen; can't prove the two "
        "cases are distinguished, not just both broken/both special-cased")

    res = subprocess.run(
        [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return elf_path.read_bytes(), bin_path.read_bytes()


def test_switch_to_differential():
    elf_bytes, bin_data = _compile()
    text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
    entry_addr = next(a for a, n in symbols.items() if n == "_start")

    # ---------- ground truth: GPU RV64 core ----------
    core = SpatialRV64ICore(4096)
    core.load_program(bin_data, entry_point=entry_addr)
    gpu_state = core.run_until_halt(max_cycles=100000, chunk_size=64)
    assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

    gpu_done = core.read_mem_word(SYM["g_done"])
    gpu_log_idx = core.read_mem_word(SYM["g_log_idx"])
    gpu_log = [core.read_mem_word(SYM["g_log"] + 4 * i) for i in range(4)]

    assert gpu_done == EXPECTED_DONE, f"GPU g_done {gpu_done} != {EXPECTED_DONE}"
    assert gpu_log_idx == EXPECTED_LOG_IDX, (
        f"GPU g_log_idx {gpu_log_idx} != {EXPECTED_LOG_IDX}")
    assert gpu_log == EXPECTED_LOG, f"GPU log {gpu_log!r} != {EXPECTED_LOG!r}"

    # ---------- transpiled glyph ----------
    glyph_source = transpile_elf_to_glyph(
        elf_bytes, entry_symbol="_start",
        byte_to_word_mem=True)
    pixels, coords = assemble_glyph_to_pixels(
        glyph_source, cols_instrs=64, min_rows=16)
    ptr_table = build_pointer_table(text_bytes, text_vaddr, coords)

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    cpu.memory = [0] * 8192
    for word_idx, packed in ptr_table.items():
        cpu.memory[(PTR_TABLE_BASE >> 2) + word_idx] = packed
    cpu.pc = (0, 0)
    cpu.running = True
    for _ in range(20000):
        if not cpu.step(pixels):
            break
    assert not cpu.running, (
        "GlyphCPUv2 failed to halt cleanly -- likely the RET/resume "
        "ambiguity: switch_to's ret popped the glyph call stack instead of "
        "an indirect jump through the reloaded ra, and the program is now "
        "spinning or has run off into garbage")

    glyph_done = cpu.memory[SYM["g_done"] >> 2]
    glyph_log_idx = cpu.memory[SYM["g_log_idx"] >> 2]
    glyph_log = [cpu.memory[(SYM["g_log"] >> 2) + i] for i in range(4)]

    assert glyph_done == gpu_done, f"Glyph g_done {glyph_done} != GPU {gpu_done}"
    assert glyph_log_idx == gpu_log_idx, (
        f"Glyph g_log_idx {glyph_log_idx} != GPU {gpu_log_idx}")
    assert glyph_log == gpu_log, f"Glyph log {glyph_log!r} != GPU {gpu_log!r}"
