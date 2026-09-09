"""
G6: sub-word (byte) memory access differential test -- checksum_str + copy_str.

The coverage table (tools/GLYPH_TRANSPILER_OPCODE_COVERAGE.md) flagged this as
the most consequential gap: every xv6-shaped string/path operation is
byte-indexed, and nothing before this used LBU/SB. Glyph memory is
word-indexed, so byte access needs address-alignment splitting (word_addr =
addr>>2, lane = addr&3, shift = lane*8) -- real lowering logic, not a
mapping-table entry. Verified against the coverage table BEFORE writing this:
only LBU/SB are implemented, not signed LB or halfword LH/LHU/SH -- the
fixture uses `unsigned char` throughout to avoid needing signed loads.

Ground truth: GPU SpatialRV64ICore, byte values extracted via masked word
reads (there's no LBU on the *test's* side of the GPU core API, only
read_mem_word -- this differential test IS the LBU oracle, so it can't use
LBU-via-glyph to also build its own reference).
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
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "checksum_str.c"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

SYM = {"g_dst": 0x300, "g_src": 0x308, "g_len": 0x310, "g_checksum": 0x314}
EXPECTED_CHECKSUM = ord('a') + ord('b') + ord('c') + ord('d') + ord('e')
EXPECTED_LEN = 5
EXPECTED_STR = b"abcde\x00"


def _compile():
    tmp = Path(tempfile.mkdtemp())
    elf_path = tmp / "csum.elf"
    bin_path = tmp / "csum.bin"
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
    assert re.search(r"\blbu\b", objdump), "no lbu in codegen; fixture lost its point"
    assert re.search(r"\bsb\b", objdump), "no sb in codegen; fixture lost its point"
    assert "mulsi3" not in objdump

    res = subprocess.run(
        [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return elf_path.read_bytes(), bin_path.read_bytes()


def _read_bytes_via_words(read_word, base, n):
    """Extract n bytes starting at `base` using only word-granularity reads
    -- the ground-truth side must not depend on LBU (that's what's on trial)."""
    out = []
    for i in range(n):
        addr = base + i
        w = read_word(addr & ~3)
        shift = (addr & 3) * 8
        out.append((w >> shift) & 0xFF)
    return bytes(out)


def test_bytemem_differential():
    elf_bytes, bin_data = _compile()
    text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
    entry_addr = next(a for a, n in symbols.items() if n == "_start")

    # ---------- ground truth: GPU RV64 core ----------
    core = SpatialRV64ICore(4096)
    core.load_program(bin_data, entry_point=entry_addr)
    gpu_state = core.run_until_halt(max_cycles=100000, chunk_size=64)
    assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

    gpu_checksum = core.read_mem_word(SYM["g_checksum"])
    gpu_len = core.read_mem_word(SYM["g_len"])
    gpu_src = _read_bytes_via_words(core.read_mem_word, SYM["g_src"], 6)
    gpu_dst = _read_bytes_via_words(core.read_mem_word, SYM["g_dst"], 6)

    assert gpu_checksum == EXPECTED_CHECKSUM
    assert gpu_len == EXPECTED_LEN
    assert gpu_src == EXPECTED_STR, f"GPU g_src {gpu_src!r} != {EXPECTED_STR!r}"
    assert gpu_dst == EXPECTED_STR, f"GPU g_dst {gpu_dst!r} != {EXPECTED_STR!r}"

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
    for _ in range(50000):
        if not cpu.step(pixels):
            break
    assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"

    def glyph_read_word(addr):
        return cpu.memory[addr >> 2]

    glyph_checksum = cpu.memory[SYM["g_checksum"] >> 2]
    glyph_len = cpu.memory[SYM["g_len"] >> 2]
    glyph_src = _read_bytes_via_words(glyph_read_word, SYM["g_src"], 6)
    glyph_dst = _read_bytes_via_words(glyph_read_word, SYM["g_dst"], 6)

    assert glyph_checksum == gpu_checksum, (
        f"Glyph checksum {glyph_checksum} != GPU {gpu_checksum}")
    assert glyph_len == gpu_len
    assert glyph_src == gpu_src, f"Glyph g_src {glyph_src!r} != GPU {gpu_src!r}"
    assert glyph_dst == gpu_dst, f"Glyph g_dst {glyph_dst!r} != GPU {gpu_dst!r}"
