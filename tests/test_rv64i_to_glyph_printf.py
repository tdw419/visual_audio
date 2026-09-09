"""
G12 -- real xv6 user/printf.c: `vprintf` format loop + `printint`, lifted
verbatim, rendering `%d %x %u %c %s %%` into a memory console buffer,
verified byte-for-byte across the three engines.

This composes everything the loop built: the ilp32 varargs ABI (item 3),
the pure-C `__udivsi3`/`__umodsi3` divider (item 2), sub-word `lbu`/`sb`
(G6), `auipc` symbol material (G11), and the auto-sized call stack.

The `%`-dispatch is a char chain GCC compiles to a `.rodata` jump table +
`jr` (computed jump). Like the proc-table and round-robin fixtures, the
harness must seed `PTR_TABLE_BASE` from `build_pointer_table(...)` -- without
it the `jr` reads 0 and loops back to pixel (0,0) forever. (That omission,
not any engine bug, was the "hang" this test was briefly skipped for.)

Faithfulness compromises, mechanical, none touching the format/convert logic:
  * `printint`'s `long long xx` / `unsigned long long x` -> `int` /
    `unsigned`. xv6 is 64-bit; on rv32 the 64-bit `/` `%` would pull
    `__udivdi3`/`__umoddi3`. The `%ld`/`%lld` branches (unused here) are
    dropped with them.
  * `printptr` / `%p` are dropped: `printptr`'s `for (...; x <<= 4)` relies
    on `x` being 32 bits, but `SpatialRV64ICore` holds it in a 64-bit
    register and `<<= 4` never discards the high bits, so `x >> 28` reads
    past `digits[]` (same rv32-on-rv64 XLEN class as the G10 / SRA hazards).
    Not a transpiler bug; scoped out like signed `__divsi3`.
  * `putc(fd, c)` -> append to `g_console[g_clen++]` instead of `write()`.
  * `__udivsi3`/`__umodsi3` shipped in the fixture (bare-metal style).

Everything else -- the `state` machine over `fmt[i]`, the `do { buf[i++] =
digits[x % base]; } while (x /= base); ` conversion, the reversed emit, the
`if (sgn && xx < 0)` sign branch, the `%s` loop, the unknown-`%` fallthrough
-- is xv6's code unchanged.

Output for `"%d %x %c %s %u%%\n"` with `-42, 0xBEEF, 'Z', "hi", 7`
is `-42 BEEF Z hi 7%\n` (17 bytes). Compared exactly.

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
    PTR_TABLE_BASE,
    assemble_glyph_to_pixels,
    build_pointer_table,
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

SRC_C = r"""
#include <stdarg.h>
typedef unsigned int uint;
typedef unsigned int uint32;

unsigned __udivsi3(unsigned n, unsigned d) {
  unsigned q = 0, r = 0;
  for (int i = 31; i >= 0; i--) { r = (r << 1) | ((n >> i) & 1u); if (r >= d) { r -= d; q |= (1u << i); } }
  return q;
}
unsigned __umodsi3(unsigned n, unsigned d) {
  unsigned r = 0;
  for (int i = 31; i >= 0; i--) { r = (r << 1) | ((n >> i) & 1u); if (r >= d) r -= d; }
  return r;
}

static char digits[] = "0123456789ABCDEF";

char g_console[128];
int  g_clen;

static void putc(int fd, char c) { (void)fd; if (g_clen < 128) g_console[g_clen++] = c; }

/* verbatim xv6 printint (long long -> int shim) */
static void
printint(int fd, int xx, int base, int sgn)
{
  char buf[20];
  int i, neg;
  unsigned x;

  neg = 0;
  if (sgn && xx < 0) { neg = 1; x = -xx; } else { x = xx; }

  i = 0;
  do { buf[i++] = digits[x % base]; } while ((x /= base) != 0);
  if (neg) buf[i++] = '-';
  while (--i >= 0) putc(fd, buf[i]);
}

/* verbatim xv6 vprintf format loop (%d %u %x %p %c %s %% subset) */
static void
vprintf(int fd, const char *fmt, va_list ap)
{
  char *s;
  int c0, c1, c2, i, state;
  state = 0;
  for (i = 0; fmt[i]; i++) {
    c0 = fmt[i] & 0xff;
    if (state == 0) {
      if (c0 == '%') state = '%'; else putc(fd, c0);
    } else if (state == '%') {
      c1 = c2 = 0;
      if (c0) c1 = fmt[i + 1] & 0xff;
      if (c1) c2 = fmt[i + 2] & 0xff;
      (void)c2;
      if (c0 == 'd') { printint(fd, va_arg(ap, int), 10, 1); }
      else if (c0 == 'u') { printint(fd, va_arg(ap, uint32), 10, 0); }
      else if (c0 == 'x') { printint(fd, va_arg(ap, uint32), 16, 0); }
      else if (c0 == 'c') { putc(fd, va_arg(ap, uint32)); }
      else if (c0 == 's') {
        if ((s = va_arg(ap, char *)) == 0) s = "(null)";
        for (; *s; s++) putc(fd, *s);
      }
      else if (c0 == '%') { putc(fd, '%'); }
      else { putc(fd, '%'); putc(fd, c0); }
      state = 0;
    }
  }
}

__attribute__((noinline)) void do_printf(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vprintf(1, fmt, ap);
  va_end(ap);
}

__attribute__((noinline)) void run_test(void) {
  g_clen = 0;
  do_printf("%d %x %c %s %u%%\n", -42, 0xBEEF, 'Z', "hi", 7u);
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

NATIVE_HARNESS_C = "#include <assert.h>\n#include <string.h>\n" + SRC_C + r"""
int main(void) {
    run_test();
    const char *want = "-42 BEEF Z hi 7%\n";
    assert(g_clen == (int)strlen(want));
    assert(memcmp(g_console, want, g_clen) == 0);
    return 0;
}
"""

WANT = b"-42 BEEF Z hi 7%\n"


def _read_console(word_at, base, clen):
    out = bytearray()
    for i in range(clen):
        w = word_at((base + i) & ~3)
        out.append((w >> (((base + i) & 3) * 8)) & 0xFF)
    return bytes(out)


def test_printf_console_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "src.c"
        elf_path = tmp / "src.elf"
        bin_path = tmp / "src.bin"
        native_c_path = tmp / "native_src.c"
        native_bin_path = tmp / "native_src"

        # 1. Native host ground truth
        native_c_path.write_text(NATIVE_HARNESS_C)
        native_res = subprocess.run(
            ["gcc", "-DHOST_TEST", "-O1", "-w", str(native_c_path), "-o", str(native_bin_path)],
            capture_output=True, text=True)
        assert native_res.returncode == 0, f"Host GCC failed: {native_res.stderr}"
        host_exec = subprocess.run([str(native_bin_path)], capture_output=True, text=True)
        assert host_exec.returncode == 0, f"Native host assertion failed: {host_exec.stderr}"

        # 2. RISC-V compile
        c_path.write_text(SRC_C)
        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin", "-w", "-Wl,-Ttext=0x0",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"

        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        assert re.search(r"jal\s+\w+\s*<__u(div|mod)si3>", objdump), "no software-divide call in printf codegen"
        assert re.search(r"\bsb\s+\w+,\s*-?\d+\(", objdump), "no byte store (buf[i++]) in printf codegen"
        assert re.search(r"\blbu\s+\w+,\s*-?\d+\(", objdump), "no byte load (digits[], fmt[i]) in printf codegen"
        assert "__divsi3" not in objdump and "__udivdi3" not in objdump, "64-bit / signed divide wrapper crept in"
        mnem = set(re.findall(r"\t([a-z][a-z0-9.]+)\t", objdump))
        forbidden = {"mul", "div", "divu", "rem", "remu", "srai", "sra", "lh", "sh"}
        assert not (mnem & forbidden), f"printf codegen uses unlowered/unsafe opcode(s): {mnem & forbidden}"

        res = subprocess.run(
            [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        bin_data = bin_path.read_bytes()

        nm_out = subprocess.run(
            ["riscv64-unknown-elf-nm", str(elf_path)],
            capture_output=True, text=True).stdout
        sym = {}
        for line in nm_out.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2] in ("g_console", "g_clen"):
                sym[parts[2]] = int(parts[0], 16)
        assert {"g_console", "g_clen"} <= set(sym), f"missing symbols: {sym}"

        elf_bytes = elf_path.read_bytes()
        text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # 3. GPU ground truth
        core = SpatialRV64ICore(36864)  # 192*192, perfect square for Hilbert map
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=3_000_000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"
        gpu_len = core.read_mem_word(sym["g_clen"]) & 0xFFFFFFFF
        gpu_bytes = _read_console(core.read_mem_word, sym["g_console"], gpu_len)
        assert gpu_len == len(WANT), f"GPU clen {gpu_len} != {len(WANT)}"
        assert gpu_bytes == WANT, f"GPU console {gpu_bytes!r} != {WANT!r}"

        # 4. Transpiled Glyph on GlyphCPUv2
        glyph_source = transpile_elf_to_glyph(elf_bytes, entry_symbol="_start",
                                              byte_to_word_mem=True)
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
        pixels, coords = assemble_glyph_to_pixels(glyph_source, cols_instrs=64, min_rows=32)
        cpu.memory = [0] * 16384
        for vaddr, blob in parse_elf_data_sections(elf_bytes):
            for i, byte in enumerate(blob):
                addr = vaddr + i
                w = addr >> 2
                shift = (addr & 3) * 8
                cpu.memory[w] = (cpu.memory[w] & ~(0xFF << shift)) | (byte << shift)
        # GCC compiles the `if (c0=='d') ... else if (c0=='u') ...` char chain
        # into a `.rodata` jump table + `jr` (computed jump). The transpiler
        # routes that through PTR_TABLE_BASE; seed it, same as the proc-table
        # and round-robin fixtures. Without this the `jr` reads 0 and loops
        # back to pixel (0,0) forever -- the "hang" this test was skipped for.
        for word_idx, packed in build_pointer_table(text_bytes, text_vaddr, coords).items():
            cpu.memory[(PTR_TABLE_BASE >> 2) + word_idx] = packed
        cpu.pc = (0, 0)
        cpu.running = True
        for _ in range(4_000_000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"
        gl_len = cpu.memory[sym["g_clen"] >> 2] & 0xFFFFFFFF
        gl_bytes = _read_console(lambda a: cpu.memory[a >> 2], sym["g_console"], gl_len)

        assert gl_len == len(WANT), f"Glyph clen {gl_len} != {len(WANT)}"
        assert gl_bytes == WANT, f"Glyph console {gl_bytes!r} != {WANT!r}"
        assert gl_bytes == gpu_bytes, f"Differential: Glyph {gl_bytes!r} vs GPU {gpu_bytes!r}"
