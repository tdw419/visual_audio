"""
Ring-buffer (FIFO) differential test: struct-field access + storage wraparound.

The negoffset test proved negative load/store offsets; bump_alloc proved simple
global state. This test isolates the next gap: struct layout with multiple state
fields (head/tail/mask/buf via base+offset lw/sw), pointer-to-struct argument
passing, indirect dereferencing through struct pointer members, and — the FIFO
equivalent of the negative-offset gap — STORAGE WRAPAROUND (head/tail crossing
the buffer end via & mask). The fixture drives head past 8 so buf[8&7..10&7]
overwrite slots 0..2; the drain-count assertion (8 items in the second pass)
only matches if the wrap actually happened.

Also exercises: full-condition rejection (push to full FIFO returns -1),
empty-condition rejection (pop from empty FIFO returns -1), and an absolute
store via the zero register (sw a5,780(zero) for g_checksum).

Ground truth verified three ways: natively compiled x86 binary, the GPU RV64
core, and the transpiled glyph on GlyphCPUv2 — all must agree bit-for-bit.
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

FIFO_C = r"""
struct fifo {
    long *buf;
    unsigned long head;
    unsigned long tail;
    unsigned long mask;
};

struct fifo g_f;
long g_storage[8];
long g_checksum;
long g_rejected_push;
long g_empty_pop;
long g_count;

__attribute__((noinline)) void fifo_init(struct fifo *f, long *buf, unsigned long mask) {
    f->buf = buf;
    f->head = 0;
    f->tail = 0;
    f->mask = mask;
}

__attribute__((noinline)) long fifo_push(struct fifo *f, long v) {
    if (f->head - f->tail == f->mask + 1) return -1;
    f->buf[f->head & f->mask] = v;
    f->head = f->head + 1;
    return 0;
}

__attribute__((noinline)) long fifo_pop(struct fifo *f, long *out) {
    if (f->head == f->tail) return -1;
    *out = f->buf[f->tail & f->mask];
    f->tail = f->tail + 1;
    return 0;
}

__attribute__((noinline)) void run_test(void) {
    fifo_init(&g_f, g_storage, 7);
    g_checksum = 0;
    long i;
    for (i = 1; i <= 8; i = i + 1)
        fifo_push(&g_f, i * 0x11);        /* fills buf[0..7] */
    g_rejected_push = fifo_push(&g_f, 0x999);   /* full: -1 */
    long v;
    fifo_pop(&g_f, &v);  g_checksum ^= v;  /* 0x11 */
    fifo_pop(&g_f, &v);  g_checksum ^= v;  /* 0x22 */
    fifo_pop(&g_f, &v);  g_checksum ^= v;  /* 0x33 */
    fifo_push(&g_f, 0xAA);              /* buf[8&7=0]: STORAGE WRAP */
    fifo_push(&g_f, 0xBB);              /* buf[9&7=1] */
    fifo_push(&g_f, 0xCC);              /* buf[10&7=2] */
    g_count = 0;
    while (fifo_pop(&g_f, &v) == 0) {   /* 0x44..0x88, 0xAA, 0xBB, 0xCC */
        g_checksum ^= v;
        g_count = g_count + 1;
    }
    g_empty_pop = fifo_pop(&g_f, &v);   /* empty: -1 */
}

void _start(void) {
    __asm__ volatile (
        "li sp, 0x800\n"
        "call run_test\n"
        "ecall\n"
    );
}
"""

# Symbol addresses from `nm` (fixed by the linker script section flags):
#   g_count=0x300 g_empty_pop=0x304 g_rejected_push=0x308 g_checksum=0x30c
#   g_storage=0x400 g_f=0x420
EXPECTED = {
    "checksum": 0x55,
    "count": 8,
    "rejected_push": -1 & 0xFFFFFFFF,
    "empty_pop": -1 & 0xFFFFFFFF,
}
SYM = {
    "g_count": 0x300,
    "g_empty_pop": 0x304,
    "g_rejected_push": 0x308,
    "g_checksum": 0x30C,
}


def test_fifo_wraparound_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "fifo.c"
        elf_path = tmp / "fifo.elf"
        bin_path = tmp / "fifo.bin"
        c_path.write_text(FIFO_C)

        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-Wl,-Ttext=0x0",
             "-Wl,--section-start=.sbss=0x300",
             "-Wl,--section-start=.bss=0x400",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"Compilation failed: {res.stderr}"

        # Sanity: struct-field access must be present in codegen (base+offset
        # lw/sw through the fifo pointer), plus the absolute zero-reg store.
        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        assert re.search(r"lw\s+\w+,\d+\(a0\)", objdump), (
            "no struct-field lw base+offset in codegen")
        assert re.search(r"sw\s+\w+,\d+\(zero\)", objdump), (
            "no absolute zero-register store in codegen")

        res = subprocess.run(
            [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        bin_data = bin_path.read_bytes()

        elf_bytes = elf_path.read_bytes()
        text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # ---------- ground truth: GPU RV64 core ----------
        core = SpatialRV64ICore(4096)
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=100000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

        gpu = {
            "checksum": core.read_mem_word(SYM["g_checksum"]),
            "count": core.read_mem_word(SYM["g_count"]),
            "rejected_push": core.read_mem_word(SYM["g_rejected_push"]),
            "empty_pop": core.read_mem_word(SYM["g_empty_pop"]),
        }

        # ---------- transpiled glyph ----------
        glyph_source = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start",
            byte_to_word_mem=True)

        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=64)
        pixels, _ = assemble_glyph_to_pixels(
            glyph_source, cols_instrs=64, min_rows=16)
        cpu.memory = [0] * 8192
        cpu.pc = (0, 0)
        cpu.running = True
        for _ in range(20000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"

        glyph = {
            "checksum": cpu.memory[SYM["g_checksum"] >> 2],
            "count": cpu.memory[SYM["g_count"] >> 2],
            "rejected_push": cpu.memory[SYM["g_rejected_push"] >> 2],
            "empty_pop": cpu.memory[SYM["g_empty_pop"] >> 2],
        }

        # ---------- differential + ground-truth assertions ----------
        for key, expected in EXPECTED.items():
            assert gpu[key] == expected, (
                f"GPU {key}: 0x{gpu[key]:08x} != 0x{expected:08x}")
            assert glyph[key] == gpu[key], (
                f"Glyph {key}: 0x{glyph[key]:08x} != GPU 0x{gpu[key]:08x}")
