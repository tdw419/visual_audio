"""
G4: xv6 fs.c-shaped in-memory inode table differential test.

New pattern vs. fifo/slab: NESTED indexing -- `itable[inum].addrs[slot]`
combines a struct-array index (`inum`, a runtime function parameter, not a
sequential loop induction variable GCC can strength-reduce into a running
pointer the way round_robin's ctx_task[] indexing was) with an inner array
field access (`addrs[slot]`). `struct inode` is padded to 32 bytes (power of
2) so this doesn't need `__mulsi3` (verified: no `mulsi3` reference in the
compiled ELF; -nostdlib has none, so it would be a link error, not a silent
miscompile, if needed).

Ground truth: GPU SpatialRV64ICore. Symbol addresses read off
`riscv64-unknown-elf-readelf -s`, not guessed.
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
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "inode_table.c"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

SYM = {
    "g_r3": 0x300,
    "g_r2": 0x304,
    "g_r1": 0x308,
    "g_r0": 0x30C,
    "g_ialloc_idx": 0x310,
    "g_ialloc_log": 0x480,
    "itable": 0x400,
}
EXPECTED_LOG = [0, 1, 2, 1]
EXPECTED_R = {"g_r0": 0x1000, "g_r1": 0x1004, "g_r2": 0x3000, "g_r3": 0x4000}


def _compile():
    tmp = Path(tempfile.mkdtemp())
    elf_path = tmp / "inode.elf"
    bin_path = tmp / "inode.bin"
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
    assert "mulsi3" not in objdump, (
        "runtime multiply crept in; struct inode must stay power-of-2 sized")
    # Sanity: the fixture must contain nested indexing -- a load/store whose
    # offset is a NON-ZERO, NON-trivial immediate combined with a computed
    # base (the addrs[] field access inside a struct-array element), not
    # just flat globals. Loose check: at least one lw/sw with a two-digit+
    # hex/decimal offset off a register other than sp/zero.
    assert re.search(r"[ls]w\s+\w+,\s*\d{2,}\(a", objdump), (
        "no non-trivial struct-field offset found; nested indexing may not "
        "be exercised")

    res = subprocess.run(
        [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return elf_path.read_bytes(), bin_path.read_bytes()


def test_inode_table_differential():
    elf_bytes, bin_data = _compile()
    text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
    entry_addr = next(a for a, n in symbols.items() if n == "_start")

    # ---------- ground truth: GPU RV64 core ----------
    core = SpatialRV64ICore(4096)
    core.load_program(bin_data, entry_point=entry_addr)
    gpu_state = core.run_until_halt(max_cycles=100000, chunk_size=64)
    assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

    gpu_log = [core.read_mem_word(SYM["g_ialloc_log"] + 4 * i) for i in range(4)]
    gpu_r = {name: core.read_mem_word(SYM[name]) for name in EXPECTED_R}

    assert gpu_log == EXPECTED_LOG, f"GPU ialloc log {gpu_log!r} != {EXPECTED_LOG!r}"
    for name, expected in EXPECTED_R.items():
        assert gpu_r[name] == expected, (
            f"GPU {name} = 0x{gpu_r[name]:x} != 0x{expected:x}")

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

    glyph_log = [cpu.memory[(SYM["g_ialloc_log"] >> 2) + i] for i in range(4)]
    glyph_r = {name: cpu.memory[SYM[name] >> 2] for name in EXPECTED_R}

    assert glyph_log == gpu_log, f"Glyph log {glyph_log!r} != GPU {gpu_log!r}"
    for name in EXPECTED_R:
        assert glyph_r[name] == gpu_r[name], (
            f"Glyph {name} = 0x{glyph_r[name]:x} != GPU 0x{gpu_r[name]:x}")
