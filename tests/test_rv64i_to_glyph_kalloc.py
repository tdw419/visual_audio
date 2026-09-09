"""
xv6 kalloc.c differential test: the transpiler's first run against REAL kernel
source (not a fixture merely *shaped* like kernel code).

Every prior primitive (bump_alloc, negoffset, fifo, slab, proc-table,
switch_to, round-robin, inode table) used hand-written C designed to exercise
one instruction class. This test instead lifts xv6-riscv's physical page
allocator verbatim:

  - `freerange`, `kfree`, `kalloc`  -- copied byte-for-byte from
    xv6-riscv/kernel/kalloc.c
  - `PGROUNDUP`                     -- copied byte-for-byte from
    xv6-riscv/kernel/riscv.h
  - `memset`                        -- xv6-riscv/kernel/string.c, byte-loop
    branch only (see NOTE below)

Faithfulness compromises, all mechanical, none touching allocator logic:

  * PGSIZE 4096 -> 32.  The mask math (`& ~(PGSIZE-1)`), the loop bounds
    (`p + PGSIZE <= pa_end`) and the memset length all derive from PGSIZE
    symbolically, so shrinking it changes only how many bytes move, not the
    algorithm.  4096-byte pages do not fit a few-KiB emulator core.
  * `initlock`/`acquire`/`release` -> no-ops.  Single hart, no contention.
  * `panic` -> sets a flag and spins.  The fixture's scenario never trips a
    panic guard; `g_panicked` is folded into the checksum so a spurious trip
    would corrupt the result rather than pass silently.
  * `end` / `PHYSTOP` -> fixture-controlled addresses instead of linker
    symbols (`end` is normally from kernel.ld).
  * memset's `uint64` fast path is dropped: on rv32/ilp32 under `-nostdlib`
    it needs libgcc `__ashldi3`/`__ordi3`, which will not link.  The retained
    byte loop is precisely the path this fixture exists to stress -- a
    per-page `sb` storm across word boundaries and all four byte lanes,
    exercising the G6 sub-word store lowering at volume.

Scenario: 4-page pool, fill the freelist via `freerange`, drain it with
`kalloc` (5th call must return 0), verify `kalloc`'s `memset(_, 5, PGSIZE)`
actually painted a freshly handed-out page (`0x05050505`), free two pages,
confirm LIFO reuse order, checksum.

Ground truth three ways, all must agree bit-for-bit:
  1. Native host compilation (x86_64) asserting algorithmic correctness
  2. GPU SpatialRV64ICore running the compiled RISC-V ELF
  3. Transpiled Glyph Assembly on GlyphCPUv2
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

# ---------------------------------------------------------------------------
# Shim + verbatim xv6 kalloc.c / string.c(memset) / riscv.h(PGROUNDUP)
# ---------------------------------------------------------------------------
KALLOC_C = r"""
typedef unsigned int   uint;
typedef unsigned long  uint64;   /* ilp32: 32-bit, exactly as xv6 treats it */
typedef unsigned char  uchar;

#define PGSIZE 32                                  /* xv6 riscv.h: 4096 */
#define PGROUNDUP(sz)  (((sz) + PGSIZE - 1) & ~(PGSIZE - 1))   /* verbatim */

__attribute__((section(".pool"), aligned(PGSIZE)))
static char g_pool[PGSIZE * 5];
#define PHYSTOP ((uint64)(g_pool + PGSIZE * 4))

char *k_end;                                       /* xv6: extern char end[] */
#define end k_end

struct spinlock { int locked; };
static void initlock(struct spinlock *lk, char *nm) { lk->locked = 0; (void)nm; }
static void acquire(struct spinlock *lk) { lk->locked = 1; }
static void release(struct spinlock *lk) { lk->locked = 0; }

static int g_panicked;
static void panic(char *s) { g_panicked = 1; (void)s; for (;;); }

/* xv6 string.c memset -- byte-loop branch only (see module docstring) */
void *memset(void *dst, int c, uint n) {
  char *cdst = (char *)dst;
  int i;
  for (i = 0; i < n; i++)
    cdst[i] = c;
  return dst;
}

/* ===== verbatim from xv6-riscv/kernel/kalloc.c ===== */
void freerange(void *pa_start, void *pa_end);

struct run {
  struct run *next;
};

struct {
  struct spinlock lock;
  struct run *freelist;
} kmem;

void
kinit()
{
  initlock(&kmem.lock, "kmem");
  freerange(end, (void *)PHYSTOP);
}

void
freerange(void *pa_start, void *pa_end)
{
  char *p;
  p = (char *)PGROUNDUP((uint64)pa_start);
  for (; p + PGSIZE <= (char *)pa_end; p += PGSIZE)
    kfree(p);
}

void
kfree(void *pa)
{
  struct run *r;

  if (((uint64)pa % PGSIZE) != 0 || (char *)pa < end || (uint64)pa >= PHYSTOP)
    panic("kfree");

  memset(pa, 1, PGSIZE);

  r = (struct run *)pa;

  acquire(&kmem.lock);
  r->next = kmem.freelist;
  kmem.freelist = r;
  release(&kmem.lock);
}

void *
kalloc(void)
{
  struct run *r;

  acquire(&kmem.lock);
  r = kmem.freelist;
  if (r)
    kmem.freelist = r->next;
  release(&kmem.lock);

  if (r)
    memset((char *)r, 5, PGSIZE);
  return (void *)r;
}
/* ===== end verbatim ===== */

int g_p1, g_p2, g_p3, g_p4, g_p5;
unsigned int g_fill_after_alloc;
int g_re1, g_re2, g_re3;
int g_checksum;

__attribute__((noinline)) void run_test(void) {
  k_end = g_pool;
  g_panicked = 0;
  kmem.freelist = 0;

  kinit();                              /* freerange(end, PHYSTOP): 4 pages */

  void *a1 = kalloc();
  g_fill_after_alloc = *(unsigned int *)a1;   /* kalloc memset(_,5,_) => 0x05050505 */
  void *a2 = kalloc();
  void *a3 = kalloc();
  void *a4 = kalloc();
  void *a5 = kalloc();                  /* 0: pool drained */

  *(int *)a1 = 0x1111;
  *(int *)a2 = 0x2222;
  *(int *)a3 = 0x3333;
  *(int *)a4 = 0x4444;

  kfree(a2);
  kfree(a3);

  void *r1 = kalloc();                  /* LIFO: a3 */
  void *r2 = kalloc();                  /* LIFO: a2 */
  void *r3 = kalloc();                  /* 0: drained again */

  g_p1 = (int)(uint64)a1;
  g_p2 = (int)(uint64)a2;
  g_p3 = (int)(uint64)a3;
  g_p4 = (int)(uint64)a4;
  g_p5 = (int)(uint64)a5;
  g_re1 = (int)(uint64)r1;
  g_re2 = (int)(uint64)r2;
  g_re3 = (int)(uint64)r3;

  g_checksum = (int)g_fill_after_alloc
             ^ (int)(uint64)r1
             ^ (int)(uint64)r2
             ^ (int)(uint64)a5
             ^ (int)(uint64)r3
             ^ g_panicked;
}

#ifndef HOST_TEST
void _start(void) {
  __asm__ volatile (
      ".option push\n"
      ".option norelax\n"
      /* GCC small-data refs are gp-relative; set gp with absolute lui/addi
         (not `la`, which expands to auipc -- unhandled by the transpiler). */
      "lui gp, %hi(__global_pointer$)\n"
      "addi gp, gp, %lo(__global_pointer$)\n"
      ".option pop\n"
      "li sp, 0x4000\n"
      "call run_test\n"
      "ecall\n"
  );
}
#endif
"""

NATIVE_HARNESS_C = r"""
#include <stdio.h>
#include <assert.h>

""" + KALLOC_C + r"""

int main(void) {
    run_test();
    assert(g_p1 == (int)(unsigned long)(g_pool + 96));   /* slot 3 */
    assert(g_p2 == (int)(unsigned long)(g_pool + 64));   /* slot 2 */
    assert(g_p3 == (int)(unsigned long)(g_pool + 32));   /* slot 1 */
    assert(g_p4 == (int)(unsigned long)(g_pool + 0));    /* slot 0 */
    assert(g_p5 == 0);
    assert(g_fill_after_alloc == 0x05050505u);
    assert(g_re1 == (int)(unsigned long)(g_pool + 32));  /* LIFO: a3 */
    assert(g_re2 == (int)(unsigned long)(g_pool + 64));  /* LIFO: a2 */
    assert(g_re3 == 0);
    assert(g_checksum == (0x05050505
                          ^ (int)(unsigned long)(g_pool + 32)
                          ^ (int)(unsigned long)(g_pool + 64)));
    printf("native ok\n");
    return 0;
}
"""

# RISC-V link map: -Wl,-Ttext=0x0, -Wl,--section-start=.pool=0x2000
#   g_pool @ 0x2000, PGSIZE 32  ->  slots 0x2000 0x2020 0x2040 0x2060
#   PHYSTOP = 0x2000 + 4*32 = 0x2080
EXPECTED = {
    "g_p1": 0x2060,
    "g_p2": 0x2040,
    "g_p3": 0x2020,
    "g_p4": 0x2000,
    "g_p5": 0x0000,
    "g_fill_after_alloc": 0x05050505,
    "g_re1": 0x2020,
    "g_re2": 0x2040,
    "g_re3": 0x0000,
    "g_checksum": 0x05050505 ^ 0x2020 ^ 0x2040,   # 0x05050565
}


def test_kalloc_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "kalloc.c"
        elf_path = tmp / "kalloc.elf"
        bin_path = tmp / "kalloc.bin"
        native_c_path = tmp / "native_kalloc.c"
        native_bin_path = tmp / "native_kalloc"

        # 1. Native host ground truth
        native_c_path.write_text(NATIVE_HARNESS_C)
        native_res = subprocess.run(
            ["gcc", "-DHOST_TEST", "-O1", str(native_c_path), "-o", str(native_bin_path)],
            capture_output=True, text=True)
        assert native_res.returncode == 0, f"Host GCC failed: {native_res.stderr}"
        host_exec = subprocess.run([str(native_bin_path)], capture_output=True, text=True)
        assert host_exec.returncode == 0, f"Native host kalloc assertion failed: {host_exec.stdout}\n{host_exec.stderr}"

        # 2. RISC-V compile for GPU core + Glyph transpiler
        c_path.write_text(KALLOC_C)
        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin",
             "-Wl,-Ttext=0x0",
             "-Wl,--section-start=.pool=0x2000",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"

        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        # This fixture's reason to exist: the memset byte-store loop must be
        # real `sb`, and the allocator must contain a NULL/exhaustion branch.
        assert re.search(r"\bsb\s+\w+,\s*-?\d+\(\w+\)", objdump), "no sb (byte store) in kalloc codegen"
        assert ("beqz" in objdump or "bnez" in objdump or "beq" in objdump), "no NULL-check branch in kalloc codegen"
        assert re.search(r"\b(lw|lbu)\s+\w+,", objdump), "no load in kalloc codegen"

        res = subprocess.run(
            [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        bin_data = bin_path.read_bytes()

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
        _text_vaddr, _text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # 3. GPU ground truth
        core = SpatialRV64ICore(36864)  # 192*192, Hilbert map needs a perfect square
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=500000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"
        gpu_results = {name: core.read_mem_word(addr) for name, addr in sym_addrs.items()}

        # 4. Transpiled Glyph on GlyphCPUv2
        glyph_source = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start",
            byte_to_word_mem=True)

        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=64)
        pixels, _ = assemble_glyph_to_pixels(
            glyph_source, cols_instrs=64, min_rows=32)
        cpu.memory = [0] * 16384
        cpu.pc = (0, 0)
        cpu.running = True
        for _ in range(400000):
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
                f"Differential mismatch for {key}: "
                f"Glyph=0x{glyph_results[key]:08x} vs GPU=0x{gpu_results[key]:08x}")
