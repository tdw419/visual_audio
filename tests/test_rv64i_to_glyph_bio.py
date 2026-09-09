"""
xv6 kernel/bio.c differential test: circular doubly-linked-list LRU surgery.

Third run against real xv6 source (after kalloc.c and string.c).  `binit`,
`bget` and `brelse` are lifted **verbatim** from xv6-riscv/kernel/bio.c --
the buffer-cache list core: a circular doubly-linked list with a sentinel
`head`, MRU at `head.next`, LRU at `head.prev`, in-place recycle on a miss
and a full unlink/relink move-to-front on the last `brelse`.

Nothing here needs an opcode the mapper lacks (checked: the compiled fixture
uses only add/addi/sub/and/or/xor/sll/slli/srai/lui/lw/sw/beq/bne/jal) --
this milestone is about whether the *list surgery* transpiles correctly, the
first fixture to exercise a doubly-linked circular list rather than a
singly-linked freelist (slab/kalloc) or an array of structs (inode).

Faithfulness compromises, all in the shim, none in the three functions:
  * `struct buf` is trimmed to the fields the list logic touches
    (valid/dev/blockno/refcnt/prev/next) plus a dummy `int lock` so
    `&b->lock` still compiles -- real xv6 has a `struct sleeplock` and a
    1 KiB `data[]` there, neither reachable from `binit`/`bget`/`brelse`.
  * `NBUF` 30 -> 5.
  * locks / sleeplocks -> no-op macros; `holdingsleep` -> 1; `panic` -> set
    a flag and spin (`g_panic`, folded into the checksum so a spurious
    `bget: no buffers` would corrupt the result, not pass).

Scenario: `binit`, then miss/miss/hit/`brelse`x3 -- forcing an LRU recycle
of two buffers, a cache hit that bumps refcnt to 2, a `brelse` that only
decrements, and two `brelse`s that each move-to-front.  Recorded as
buf-relative indices (`b - bcache.buf`), so the expected table is
layout-independent and identical native vs RISC-V.

Ground truth three ways, all must agree bit-for-bit:
  1. Native host compilation (x86_64)
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
    parse_elf_data_sections,
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

BIO_C = r"""
typedef unsigned int  uint;
typedef unsigned char uchar;

struct buf {
  int valid;
  int lock;          /* shim: real xv6 has a struct sleeplock here */
  uint dev;
  uint blockno;
  uint refcnt;
  struct buf *prev;
  struct buf *next;
};

#define NBUF 5
#define initlock(a,b)        ((void)0)
#define acquire(x)           ((void)0)
#define release(x)           ((void)0)
#define initsleeplock(a,b)   ((void)0)
#define acquiresleep(x)      ((void)0)
#define releasesleep(x)      ((void)0)
#define holdingsleep(x)      1
#define panic(s)             do { g_panic = 1; for (;;); } while (0)

int g_panic;

struct {
  int lock;
  struct buf buf[NBUF];
  struct buf head;
} bcache;

/* ===== verbatim from xv6-riscv/kernel/bio.c ===== */
void
binit(void)
{
  struct buf *b;

  initlock(&bcache.lock, "bcache");

  bcache.head.prev = &bcache.head;
  bcache.head.next = &bcache.head;
  for (b = bcache.buf; b < bcache.buf + NBUF; b++) {
    b->next = bcache.head.next;
    b->prev = &bcache.head;
    initsleeplock(&b->lock, "buffer");
    bcache.head.next->prev = b;
    bcache.head.next = b;
  }
}

static struct buf *
bget(uint dev, uint blockno)
{
  struct buf *b;

  acquire(&bcache.lock);

  for (b = bcache.head.next; b != &bcache.head; b = b->next) {
    if (b->dev == dev && b->blockno == blockno) {
      b->refcnt++;
      release(&bcache.lock);
      acquiresleep(&b->lock);
      return b;
    }
  }

  for (b = bcache.head.prev; b != &bcache.head; b = b->prev) {
    if (b->refcnt == 0) {
      b->dev = dev;
      b->blockno = blockno;
      b->valid = 0;
      b->refcnt = 1;
      release(&bcache.lock);
      acquiresleep(&b->lock);
      return b;
    }
  }
  panic("bget: no buffers");
  return 0;
}

void
brelse(struct buf *b)
{
  if (!holdingsleep(&b->lock))
    panic("brelse");

  releasesleep(&b->lock);

  acquire(&bcache.lock);
  b->refcnt--;
  if (b->refcnt == 0) {
    b->next->prev = b->prev;
    b->prev->next = b->next;
    b->next = bcache.head.next;
    b->prev = &bcache.head;
    bcache.head.next->prev = b;
    bcache.head.next = b;
  }

  release(&bcache.lock);
}
/* ===== end verbatim ===== */

int g_order[NBUF];
int g_hitcnt, g_ncached, g_checksum;

__attribute__((noinline)) void run_test(void) {
  binit();
  struct buf *a  = bget(10, 100);   /* miss -> recycle LRU buf[0] */
  struct buf *c  = bget(10, 101);   /* miss -> recycle buf[1] */
  struct buf *a2 = bget(10, 100);   /* hit  -> refcnt 2 */
  g_hitcnt = a2->refcnt;
  brelse(a);                        /* refcnt 1, no move */
  brelse(a2);                       /* refcnt 0, move buf[0] to front */
  brelse(c);                        /* refcnt 0, move buf[1] to front */

  struct buf *p = bcache.head.next;
  for (int i = 0; i < NBUF; i++) { g_order[i] = (int)(p - bcache.buf); p = p->next; }
  g_ncached = 0;
  for (int i = 0; i < NBUF; i++)
    if (bcache.buf[i].dev == 10) g_ncached++;

  g_checksum = g_hitcnt ^ (g_ncached << 4);
  for (int i = 0; i < NBUF; i++)
    g_checksum ^= (g_order[i] << (i * 3));
  g_checksum ^= g_panic;
}

#ifndef HOST_TEST
void _start(void) {
  __asm__ volatile (
      ".option push\n"
      ".option norelax\n"
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

NATIVE_HARNESS_C = "#include <assert.h>\n" + BIO_C + r"""
int main(void) {
    run_test();
    int expect_order[5] = {1, 0, 4, 3, 2};
    for (int i = 0; i < 5; i++) assert(g_order[i] == expect_order[i]);
    assert(g_hitcnt == 2);
    assert(g_ncached == 2);
    assert(g_panic == 0);
    assert((unsigned)g_checksum == 0x00002723u);
    return 0;
}
"""

# Buf-relative indices -> identical on both targets.
EXPECTED = {
    "g_hitcnt": 2,
    "g_ncached": 2,
    "g_checksum": 0x00002723,
}
EXPECTED_ORDER = [1, 0, 4, 3, 2]


def test_bio_lru_list_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "bio.c"
        elf_path = tmp / "bio.elf"
        bin_path = tmp / "bio.bin"
        native_c_path = tmp / "native_bio.c"
        native_bin_path = tmp / "native_bio"

        # 1. Native host ground truth
        native_c_path.write_text(NATIVE_HARNESS_C)
        native_res = subprocess.run(
            ["gcc", "-DHOST_TEST", "-O1", "-w", str(native_c_path), "-o", str(native_bin_path)],
            capture_output=True, text=True)
        assert native_res.returncode == 0, f"Host GCC failed: {native_res.stderr}"
        host_exec = subprocess.run([str(native_bin_path)], capture_output=True, text=True)
        assert host_exec.returncode == 0, f"Native host bio assertion failed: {host_exec.stderr}"

        # 2. RISC-V compile
        c_path.write_text(BIO_C)
        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin", "-w",
             "-Wl,-Ttext=0x0",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"

        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        # Prove the list surgery is really there: pointer loads/stores and the
        # miss/hit branch. And that nothing snuck in an unlowered opcode.
        assert re.search(r"\blw\s+\w+,\s*-?\d+\(\w+\)", objdump), "no pointer load in bio codegen"
        assert re.search(r"\bsw\s+\w+,\s*-?\d+\(\w+\)", objdump), "no pointer store in bio codegen"
        assert ("beq" in objdump or "bne" in objdump), "no list-scan branch in bio codegen"
        mnem = set(re.findall(r"\t([a-z][a-z0-9.]+)\t", objdump))
        forbidden = {"auipc", "lhu", "lh", "sh", "sltiu", "mul", "mulh", "mulhu",
                     "div", "divu", "rem", "remu"}
        assert not (mnem & forbidden), f"bio codegen uses unlowered opcode(s): {mnem & forbidden}"

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
            if len(parts) == 3 and parts[2] in (set(EXPECTED) | {"g_order"}):
                sym_addrs[parts[2]] = int(parts[0], 16)
        assert set(sym_addrs.keys()) == (set(EXPECTED) | {"g_order"}), (
            f"Missing symbols: {(set(EXPECTED) | {'g_order'}) - set(sym_addrs.keys())}"
        )

        elf_bytes = elf_path.read_bytes()
        _text_vaddr, _text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        def read_results(word_at):
            r = {k: word_at(sym_addrs[k]) for k in EXPECTED}
            r["order"] = [word_at(sym_addrs["g_order"] + 4 * i) for i in range(len(EXPECTED_ORDER))]
            return r

        # 3. GPU ground truth
        core = SpatialRV64ICore(36864)  # 192*192, perfect square for Hilbert map
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=500000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"
        gpu = read_results(core.read_mem_word)

        # 4. Transpiled Glyph on GlyphCPUv2
        glyph_source = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start",
            byte_to_word_mem=True)
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
        pixels, _ = assemble_glyph_to_pixels(glyph_source, cols_instrs=64, min_rows=32)
        cpu.memory = [0] * 16384
        for vaddr, blob in parse_elf_data_sections(elf_bytes):
            for i, byte in enumerate(blob):
                addr = vaddr + i
                w = addr >> 2
                shift = (addr & 3) * 8
                cpu.memory[w] = (cpu.memory[w] & ~(0xFF << shift)) | (byte << shift)
        cpu.pc = (0, 0)
        cpu.running = True
        for _ in range(400000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"
        glyph = read_results(lambda a: cpu.memory[a >> 2])

        # 5. Differential cross-check
        assert gpu["order"] == EXPECTED_ORDER, f"GPU order {gpu['order']} != {EXPECTED_ORDER}"
        assert glyph["order"] == EXPECTED_ORDER, f"Glyph order {glyph['order']} != {EXPECTED_ORDER}"
        for key, exp_val in EXPECTED.items():
            assert gpu[key] == exp_val, f"GPU {key}: 0x{gpu[key]:08x} != 0x{exp_val:08x}"
            assert glyph[key] == exp_val, f"Glyph {key}: 0x{glyph[key]:08x} != 0x{exp_val:08x}"
            assert glyph[key] == gpu[key], (
                f"Differential mismatch {key}: Glyph=0x{glyph[key]:08x} GPU=0x{gpu[key]:08x}")
