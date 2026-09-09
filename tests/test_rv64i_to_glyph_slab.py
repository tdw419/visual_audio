"""
Slab / Free-List Allocator differential test: pointer chasing + LIFO reuse.

The previous differential tests isolated:
  1. bump_alloc: monotonic heap allocation and simple globals
  2. negoffset: negative load/store offsets and tail-call RET halting
  3. fifo: struct field layout, circular buffer arithmetic (& mask), and wraparound

This test isolates the fourth critical memory primitive:
  - Dynamic free-list memory management with embedded struct headers
  - In-memory pointer chasing through node link pointers (b->next)
  - Selective deallocation (free) and LIFO block reclamation/reuse
  - Out-of-memory / exhaustion rejection (returning 0 / NULL on empty pool)
  - Data preservation across free and re-allocation

Ground truth is verified three ways:
  1. Native host compilation (x86_64) asserting algorithmic correctness
  2. GPU SpatialRV64ICore (WGPU/WGSL) running compiled RISC-V ELF
  3. Transpiled Glyph Assembly executed on GlyphCPUv2
All three must agree bit-for-bit.
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

SLAB_C = r"""
struct block {
    struct block *next;
    long val1;
    long val2;
    long val3;
};

struct pool {
    struct block *free_head;
    long num_free;
};

struct pool g_pool;
struct block g_storage[4];
long g_alloc1;
long g_alloc2;
long g_alloc3;
long g_alloc4;
long g_alloc5;
long g_realloc;
long g_checksum;

__attribute__((noinline)) void slab_init(struct pool *p, struct block *storage, int n) {
    p->free_head = storage;
    p->num_free = n;
    for (int i = 0; i < n - 1; i++) {
        storage[i].next = &storage[i + 1];
    }
    storage[n - 1].next = 0;
}

__attribute__((noinline)) struct block *slab_alloc(struct pool *p) {
    struct block *b = p->free_head;
    if (!b) return 0;
    p->free_head = b->next;
    p->num_free--;
    return b;
}

__attribute__((noinline)) void slab_free(struct pool *p, struct block *b) {
    b->next = p->free_head;
    p->free_head = b;
    p->num_free++;
}

__attribute__((noinline)) void run_test(void) {
    slab_init(&g_pool, g_storage, 4);
    struct block *b1 = slab_alloc(&g_pool);
    struct block *b2 = slab_alloc(&g_pool);
    struct block *b3 = slab_alloc(&g_pool);
    struct block *b4 = slab_alloc(&g_pool);
    struct block *b5 = slab_alloc(&g_pool); /* NULL: pool exhausted */

    b1->val1 = 0x1111;
    b2->val1 = 0x2222;
    b3->val1 = 0x3333;
    b4->val1 = 0x4444;

    /* Free b2 (storage slot 1), then free b3 (storage slot 2) */
    slab_free(&g_pool, b2);
    slab_free(&g_pool, b3);

    /* LIFO reuse: next allocation must return b3, then b2 */
    struct block *b_re1 = slab_alloc(&g_pool);
    struct block *b_re2 = slab_alloc(&g_pool);
    struct block *b_re3 = slab_alloc(&g_pool); /* NULL: pool exhausted again */

    g_alloc1 = (long)b1;
    g_alloc2 = (long)b2;
    g_alloc3 = (long)b3;
    g_alloc4 = (long)b4;
    g_alloc5 = (long)b5;
    g_realloc = (long)b_re1;

    /* Checksum verifies:
       - b1 payload preserved
       - b2 payload preserved across free and re-allocation (as b_re2)
       - LIFO reuse pointer matches b3
       - both null allocations are 0
    */
    g_checksum = b1->val1 ^ b_re2->val1 ^ (long)b_re1 ^ (long)b5 ^ (long)b_re3;
}

#ifndef HOST_TEST
void _start(void) {
    __asm__ volatile (
        "li sp, 0x800\n"
        "call run_test\n"
        "ecall\n"
    );
}
#endif
"""

NATIVE_HARNESS_C = r"""
#include <stdio.h>
#include <assert.h>

""" + SLAB_C + r"""

int main(void) {
    run_test();
    assert(g_alloc1 == (long)&g_storage[0]);
    assert(g_alloc2 == (long)&g_storage[1]);
    assert(g_alloc3 == (long)&g_storage[2]);
    assert(g_alloc4 == (long)&g_storage[3]);
    assert(g_alloc5 == 0);
    assert(g_realloc == (long)&g_storage[2]);
    assert(g_checksum == (0x1111 ^ 0x2222 ^ (long)&g_storage[2]));
    return 0;
}
"""

# Fixed memory addresses under:
#   -Wl,--section-start=.sbss=0x300
#   -Wl,--section-start=.bss=0x400
# g_storage is at 0x400 (4 blocks * 16 bytes = 0x40 bytes)
#   block 0: 0x400
#   block 1: 0x410
#   block 2: 0x420
#   block 3: 0x430
EXPECTED = {
    "g_alloc1": 0x400,
    "g_alloc2": 0x410,
    "g_alloc3": 0x420,
    "g_alloc4": 0x430,
    "g_alloc5": 0x000,
    "g_realloc": 0x420,
    "g_checksum": 0x1111 ^ 0x2222 ^ 0x420,  # 0x3713 = 14099
}


def test_slab_allocator_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "slab.c"
        elf_path = tmp / "slab.elf"
        bin_path = tmp / "slab.bin"
        native_c_path = tmp / "native_slab.c"
        native_bin_path = tmp / "native_slab"

        # 1. Native host compilation & verification
        native_c_path.write_text(NATIVE_HARNESS_C)
        native_res = subprocess.run(
            ["gcc", "-DHOST_TEST", "-O1", str(native_c_path), "-o", str(native_bin_path)],
            capture_output=True, text=True)
        assert native_res.returncode == 0, f"Host GCC failed: {native_res.stderr}"
        host_exec = subprocess.run([str(native_bin_path)], capture_output=True, text=True)
        assert host_exec.returncode == 0, "Native host slab assertion failed"

        # 2. RISC-V compilation for GPU & Glyph transpilation
        c_path.write_text(SLAB_C)
        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-Wl,-Ttext=0x0",
             "-Wl,--section-start=.sbss=0x300",
             "-Wl,--section-start=.bss=0x400",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"

        # Sanity check: verify disassembly contains pointer chasing (lw through ptr) and beqz/bnez
        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        assert "beqz" in objdump or "beq" in objdump, "No conditional branch in slab alloc"
        assert re.search(r"lw\s+\w+,\d+\(\w+\)", objdump), "No pointer dereference in slab codegen"

        res = subprocess.run(
            [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        bin_data = bin_path.read_bytes()

        # Extract symbol addresses from ELF
        nm_out = subprocess.run(
            ["riscv64-unknown-elf-nm", str(elf_path)],
            capture_output=True, text=True).stdout
        sym_addrs = {}
        for line in nm_out.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2] in EXPECTED:
                sym_addrs[parts[2]] = int(parts[0], 16)
        assert set(sym_addrs.keys()) == set(EXPECTED.keys()), (
            f"Missing symbols in ELF: {set(EXPECTED.keys()) - set(sym_addrs.keys())}"
        )

        elf_bytes = elf_path.read_bytes()
        text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # 3. Ground truth: GPU RV64 core
        core = SpatialRV64ICore(4096)
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=100000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

        gpu_results = {name: core.read_mem_word(addr) for name, addr in sym_addrs.items()}

        # 4. Transpiled Glyph on GlyphCPUv2
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
        for _ in range(30000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"

        glyph_results = {name: cpu.memory[addr >> 2] for name, addr in sym_addrs.items()}

        # 5. Differential cross-check
        for key, exp_val in EXPECTED.items():
            assert gpu_results[key] == exp_val, (
                f"GPU {key}: 0x{gpu_results[key]:08x} != expected 0x{exp_val:08x}")
            assert glyph_results[key] == exp_val, (
                f"Glyph {key}: 0x{glyph_results[key]:08x} != expected 0x{exp_val:08x}")
            assert glyph_results[key] == gpu_results[key], (
                f"Differential mismatch for {key}: Glyph=0x{glyph_results[key]:08x} vs GPU=0x{gpu_results[key]:08x}")

