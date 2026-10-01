"""
xv6 kernel/string.c differential test: the transpiler's second run against
REAL kernel source (after G7's kalloc.c), and the first that transpiles a
whole *file* of it rather than one allocator.

`memset`, `memcmp`, `memmove`, `memcpy`, `strncmp`, `strncpy`, `safestrcpy`
and `strlen` are lifted **verbatim** from xv6-riscv/kernel/string.c -- the
only edit is deleting `#include "types.h"` and supplying the three typedefs
it pulls (`uint`, `uint64`, `uchar`).

Notes / faithfulness:

  * `memset`'s `uint64` fast path contains `v | (v << 32)`, which is a
    shift-count-overflow no-op on rv32/ilp32 (GCC warns).  It is dead code
    here: this fixture's scenario never calls `memset` (kalloc's test already
    exercises the byte-store storm).  Kept anyway so the lift stays verbatim.
  * `_start` sets `gp` with absolute `lui/addi %hi/%lo(__global_pointer$)`
    -- GCC's `-O1` small-data refs are gp-relative and the transpiler has no
    `auipc` lowering (see the kalloc test for the full rationale).

FINDING recorded by this test: xv6's string.c, at `-O1 -march=rv32i`,
compiles with **zero `lb` instructions** -- every character access is `lbu`.
The comparison/nonzero tests don't need sign extension and the `(uchar)`
casts on the return paths make the widening explicitly unsigned.  So the
long-standing "a char* routine will force signed LB" expectation does *not*
hold for this actual source.  The objdump assertion below pins that: it
asserts `lb` is absent, so a future toolchain that starts emitting it will
fail here and prompt a re-evaluation (signed LB is still an unimplemented
opcode).

Scenario: `strlen`, `strncpy` + re-`strlen`, `safestrcpy` truncation,
three `strncmp` orderings, a `memcmp`, and an **overlapping** backward
`memmove` (`memmove(buf+2, buf, 4)` on `"abcdefgh"` -> `"ababcdgh"`),
folded into a layout-independent checksum (values only, no addresses -- so
the native and RISC-V expected tables are identical).

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

# --- verbatim from xv6-riscv/kernel/string.c (only #include removed) --------
XV6_STRING_C = r"""
void *
memset(void *dst, int c, uint n)
{
  char *cdst = (char *)dst;
  int i;
  if (((uint64)dst % 8) == 0 && (n % 8) == 0) {
    uint64 *wdst = (uint64 *)dst;
    uint64 v = (c & 0xFF);
    v = v | (v << 8) | (v << 16) | (v << 24);
    v = v | (v << 32);
    for (i = 0; i < n / 8; i++) {
      wdst[i] = v;
    }
  } else {
    for (i = 0; i < n; i++) {
      cdst[i] = c;
    }
  }
  return dst;
}

int
memcmp(const void *v1, const void *v2, uint n)
{
  const uchar *s1, *s2;

  s1 = v1;
  s2 = v2;
  while (n-- > 0) {
    if (*s1 != *s2)
      return *s1 - *s2;
    s1++, s2++;
  }

  return 0;
}

void *
memmove(void *dst, const void *src, uint n)
{
  const char *s;
  char *d;

  if (n == 0)
    return dst;

  s = src;
  d = dst;
  if (s < d && s + n > d) {
    s += n;
    d += n;
    while (n-- > 0)
      *--d = *--s;
  } else
    while (n-- > 0)
      *d++ = *s++;

  return dst;
}

// memcpy exists to placate GCC.  Use memmove.
void *
memcpy(void *dst, const void *src, uint n)
{
  return memmove(dst, src, n);
}

int
strncmp(const char *p, const char *q, uint n)
{
  while (n > 0 && *p && *p == *q)
    n--, p++, q++;
  if (n == 0)
    return 0;
  return (uchar)*p - (uchar)*q;
}

char *
strncpy(char *s, const char *t, int n)
{
  char *os;

  os = s;
  while (n-- > 0 && (*s++ = *t++) != 0)
    ;
  while (n-- > 0)
    *s++ = 0;
  return os;
}

// Like strncpy but guaranteed to NUL-terminate.
char *
safestrcpy(char *s, const char *t, int n)
{
  char *os;

  os = s;
  if (n <= 0)
    return os;
  while (--n > 0 && (*s++ = *t++) != 0)
    ;
  *s = 0;
  return os;
}

int
strlen(const char *s)
{
  int n;

  for (n = 0; s[n]; n++)
    ;
  return n;
}
"""

SHIM = r"""
typedef unsigned int   uint;
typedef unsigned long  uint64;   /* ilp32: 32-bit, exactly as xv6 treats it */
typedef unsigned char  uchar;
"""

DRIVER = r"""
static char g_src[32] = "hello world";
static char g_dst[32];
static char g_small[4];
static char g_mv[16] = "abcdefgh";

int g_len_src, g_len_dst, g_safe_trunc;
int g_cmp_eq, g_cmp_lt, g_cmp_gt, g_memcmp;
unsigned int g_mm0, g_mm1;
int g_checksum;

__attribute__((noinline)) void run_test(void) {
  g_len_src = strlen(g_src);                 /* 11 */
  strncpy(g_dst, g_src, 32);
  g_len_dst = strlen(g_dst);                 /* 11 */
  safestrcpy(g_small, "abcdef", 4);          /* "abc\0" */
  g_safe_trunc = strlen(g_small);            /* 3 */

  g_cmp_eq = strncmp("abc", "abc", 3);       /*  0 */
  g_cmp_lt = strncmp("abc", "abd", 3);       /* -1 */
  g_cmp_gt = strncmp("abd", "abc", 3);       /*  1 */
  g_memcmp = memcmp("abcd", "abce", 4);      /* -1 */

  memmove(g_mv + 2, g_mv, 4);                /* overlap, backward copy */
  g_mm0 = *(unsigned int *)&g_mv[0];         /* "abab" -> 0x62616261 */
  g_mm1 = *(unsigned int *)&g_mv[4];         /* "cdgh" -> 0x68676463 */

  g_checksum = g_len_src ^ (g_len_dst << 8) ^ (g_safe_trunc << 16)
             ^ g_cmp_eq ^ g_cmp_lt ^ g_cmp_gt ^ g_memcmp
             ^ (int)g_mm0 ^ (int)g_mm1;
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

STRING_C = SHIM + XV6_STRING_C + DRIVER
NATIVE_HARNESS_C = "#include <assert.h>\n" + SHIM + XV6_STRING_C + DRIVER + r"""
int main(void) {
    run_test();
    assert(g_len_src == 11);
    assert(g_len_dst == 11);
    assert(g_safe_trunc == 3);
    assert(g_cmp_eq == 0);
    assert(g_cmp_lt == -1);
    assert(g_cmp_gt == 1);
    assert(g_memcmp == -1);
    assert(g_mm0 == 0x62616261u);   /* "abab" */
    assert(g_mm1 == 0x68676463u);   /* "cdgh" */
    assert((unsigned)g_checksum == 0x0a050d08u);
    return 0;
}
"""

# Layout-independent: every value is a length / comparison sign / byte
# content, so the RISC-V table equals the native one exactly.
EXPECTED = {
    "g_len_src": 11,
    "g_len_dst": 11,
    "g_safe_trunc": 3,
    "g_cmp_eq": 0,
    "g_cmp_lt": 0xFFFFFFFF,
    "g_cmp_gt": 1,
    "g_memcmp": 0xFFFFFFFF,
    "g_mm0": 0x62616261,
    "g_mm1": 0x68676463,
    "g_checksum": 0x0A050D08,
}


def test_stringc_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "stringc.c"
        elf_path = tmp / "stringc.elf"
        bin_path = tmp / "stringc.bin"
        native_c_path = tmp / "native_stringc.c"
        native_bin_path = tmp / "native_stringc"

        # 1. Native host ground truth
        native_c_path.write_text(NATIVE_HARNESS_C)
        native_res = subprocess.run(
            ["gcc", "-DHOST_TEST", "-O1", "-w", str(native_c_path), "-o", str(native_bin_path)],
            capture_output=True, text=True)
        assert native_res.returncode == 0, f"Host GCC failed: {native_res.stderr}"
        host_exec = subprocess.run([str(native_bin_path)], capture_output=True, text=True)
        assert host_exec.returncode == 0, f"Native host string.c assertion failed: {host_exec.stderr}"

        # 2. RISC-V compile for GPU core + Glyph transpiler
        c_path.write_text(STRING_C)
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
        # This fixture's claims: real byte loads/stores through pointers, real
        # loop back-edges, and -- the recorded finding -- NO signed lb.
        assert re.search(r"\blbu\s+\w+,\s*-?\d+\(\w+\)", objdump), "no lbu (byte load) in string.c codegen"
        assert re.search(r"\bsb\s+\w+,\s*-?\d+\(\w+\)", objdump), "no sb (byte store) in string.c codegen"
        assert not re.search(r"\blb\s+\w+,\s*-?\d+\(\w+\)", objdump), (
            "string.c codegen now contains signed `lb` -- the transpiler has no "
            "LB lowering; re-evaluate this test and the opcode coverage table")
        assert re.search(r"\bb(ne|eq|ltu|geu)\s+\w+,\w+,\s*-?0x", objdump) or "bnez" in objdump, \
            "no loop back-edge branch in string.c codegen"

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
        # Seed initialized data (.data/.sdata/.rodata) into word-packed,
        # little-endian memory -- the transpiler lifts only .text, whereas
        # the GPU core loaded the whole image. First fixture to need this:
        # its globals carry non-zero initializers (string literals).
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
