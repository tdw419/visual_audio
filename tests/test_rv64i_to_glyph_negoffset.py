"""
Negative-offset memory differential test: the gap the bump_alloc fixture missed.

GCC -O1 memcpy-style codegen emits `lbu a4,-1(a1)` / `sb a4,-1(a5)` (negative
load/store offsets). The mapper lowers ALL offsets via 2's-complement
LDI+ADD into a scratch register, which SHOULD handle negative values — but no
existing test exercised that path (bump_alloc's codegen contains none).

This test compiles a function that loads and stores at negative offsets, runs
it on the GPU RV64 core, transpiles the same ELF, runs it on GlyphCPUv2, and
asserts bit-identical memory + return value.
"""
import os
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
    assemble_glyph_to_pixels,
    parse_elf,
    transpile_elf_to_glyph,
)
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.spatial_rv64i_cpu import SpatialRV64ICore  # noqa: E402

_GCC_BIN = "riscv64-unknown-elf-gcc"
_OBJCOPY_BIN = "riscv64-unknown-elf-objcopy"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

NEG_OFF_C = r"""
__attribute__((noinline)) long neg_test(long *base) {
    /* load base[-1] and base[+1]; store to base[-2]: negative offsets on both
       the load and store paths, word-aligned. */
    long a = base[-1];
    long b = base[1];
    base[-2] = a + b;
    return base[-2];
}

long result;  /* lands in .bss (0x210): where results are compared */

void _start(void) {
    __asm__ volatile (
        "li sp, 0x800\n"
        "li a0, 0x100\n"
        "call neg_test\n"
        "la t0, result\n"
        "sw a0, 0(t0)\n"
        "ecall\n"
    );
}
"""


def test_negative_offset_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "neg.c"
        elf_path = tmp / "neg.elf"
        bin_path = tmp / "neg.bin"

        c_path.write_text(NEG_OFF_C)
        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-Wl,-Ttext=0x0",
             "-Wl,--section-start=.data=0x200",
             "-Wl,--section-start=.sdata=0x208",
             "-Wl,--section-start=.sbss=0x210",
             "-Wl,--section-start=.bss=0x218",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"Compilation failed: {res.stderr}"

        # Sanity: the fixture really produced negative-offset mem ops
        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        assert re.search(r"-[0-9a-f]+\(r", objdump.replace("0x", "")) or \
            re.search(r"-[0-9]+\(", objdump), (
                "fixture failed to produce negative-offset mem ops; "
                "codegen changed, test loses its point")

        res = subprocess.run(
            [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        bin_data = bin_path.read_bytes()

        elf_bytes = elf_path.read_bytes()
        text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # Preload layout (byte addresses, word-aligned):
        #   0x0F0: base[-2] store target  -> 0
        #   0x0F8: base[-2] store target  -> 0 (checked after run)
        #   0x0FC: base[-1]               -> 0x11111111
        #   0x100: base[0]                -> 0x22222222
        #   0x104: base[+1]               -> 0x44444444
        BASE = 0x100
        WORDS = {
            0x0F8: 0,
            0x0FC: 0x11111111,
            BASE: 0x22222222,
            0x104: 0x44444444,
        }
        expected_sum = (0x11111111 + 0x44444444) & 0xFFFFFFFF

        # ---------- ground truth: GPU RV64 core ----------
        core = SpatialRV64ICore(4096)
        core.load_program(bin_data, entry_point=entry_addr)
        for addr, val in WORDS.items():
            core.write_mem_word(addr, val)
        gpu_state = core.run_until_halt(max_cycles=10000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

        gpu_result = core.read_mem_word(0x210)   # `result` global (.bss)
        gpu_negslot = core.read_mem_word(0x0F8)  # base[-2] store target

        # ---------- transpiled glyph ----------
        glyph_source = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start",
            byte_to_word_mem=True)

        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=64)
        pixels, _ = assemble_glyph_to_pixels(
            glyph_source, cols_instrs=64, min_rows=16)
        cpu.memory = [0] * 8192
        for addr, val in WORDS.items():
            cpu.memory[addr >> 2] = val
        cpu.pc = (0, 0)
        cpu.running = True
        for _ in range(5000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"

        glyph_result = cpu.memory[0x210 >> 2]
        glyph_negslot = cpu.memory[0x0F8 >> 2]

        # ---------- differential assertions ----------
        assert gpu_result == expected_sum, (
            f"GPU result 0x{gpu_result:08x} != 0x{expected_sum:08x}")
        assert gpu_negslot == expected_sum, (
            f"GPU base[-2] 0x{gpu_negslot:08x} != 0x{expected_sum:08x}")
        assert glyph_result == gpu_result, (
            f"Glyph result 0x{glyph_result:08x} != GPU 0x{gpu_result:08x}")
        assert glyph_negslot == gpu_negslot, (
            f"Glyph base[-2] 0x{glyph_negslot:08x} != GPU 0x{gpu_negslot:08x}")
