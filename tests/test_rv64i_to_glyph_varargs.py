"""
Varargs differential test (loop item 3 / pre-printf.c).

Exercises the RISC-V ilp32 variadic ABI end to end: the named arg in a0, the
remaining integer args a1..a7 spilled by the callee into its
register-save area, args past a7 read from the *caller's* outgoing stack,
and `va_list` walked one word at a time (`lw` + `addi 4`).  `vprintf`'s
`va_arg(ap, int)` per `%`-conversion is exactly this pattern -- G12 reuses it.

Fixture is `<stdarg.h>` only (GCC builtins `__builtin_va_start` /
`__builtin_va_arg`), no libc.  Compiled codegen census: add/addi/blez/bne/
jal/li/lui/lw/mv/or/slli/sw/xor -- all already lowered, so no transpiler
change is expected.

Scenario: `vsum(9, 10,20,...,90)` -> 450 (nine varargs, so #8 and #9 land
past a7 on the caller stack), and `vmix(0, 0x11,0x22,0x33)` packing three
small varargs into one word.  Layout-independent checksum.

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

SRC_C = r"""
#include <stdarg.h>
typedef unsigned int uint;

__attribute__((noinline)) int vsum(int n, ...) {
  va_list ap;
  va_start(ap, n);
  int s = 0;
  for (int i = 0; i < n; i++)
    s += va_arg(ap, int);
  va_end(ap);
  return s;
}

__attribute__((noinline)) int vmix(int tag, ...) {
  va_list ap;
  va_start(ap, tag);
  int a = va_arg(ap, int);
  int b = va_arg(ap, int);
  int c = va_arg(ap, int);
  va_end(ap);
  return (a << 16) | (b << 8) | c;
}

volatile int g_dummy;
int g_sum9, g_mix, g_checksum;

__attribute__((noinline)) void run_test(void) {
  g_dummy = 1;
  g_sum9 = vsum(9, 10, 20, 30, 40, 50, 60, 70, 80, 90);  /* 450 */
  g_mix  = vmix(0, 0x11, 0x22, 0x33);                     /* 0x00112233 */
  g_checksum = g_sum9 ^ (g_mix << 4);
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

NATIVE_HARNESS_C = "#include <assert.h>\n" + SRC_C + r"""
int main(void) {
    run_test();
    assert(g_sum9 == 450);
    assert(g_mix == 0x00112233);
    assert((unsigned)g_checksum == (450u ^ (0x00112233u << 4)));
    return 0;
}
"""

EXPECTED = {
    "g_sum9": 450,
    "g_mix": 0x00112233,
    "g_checksum": (450 ^ (0x00112233 << 4)) & 0xFFFFFFFF,
}


def test_varargs_differential():
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
        # The variadic register-save-area spill must actually be emitted:
        # a callee storing a1..a7 to consecutive stack slots on entry.
        assert re.search(r"sw\s+a7,\s*\d+\(sp\)", objdump), "no a7 register-save spill -- varargs ABI not exercised"
        assert re.search(r"sw\s+a1,\s*\d+\(sp\)", objdump), "no a1 register-save spill"
        mnem = set(re.findall(r"\t([a-z][a-z0-9.]+)\t", objdump))
        forbidden = {"auipc", "mul", "div", "rem", "lh", "sh", "srai", "sra"}
        assert not (mnem & forbidden), f"varargs codegen uses unlowered/unsafe opcode(s): {mnem & forbidden}"

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
            f"Missing symbols: {set(EXPECTED.keys()) - set(sym_addrs.keys())}"
        )

        elf_bytes = elf_path.read_bytes()
        _text_vaddr, _text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # 3. GPU ground truth
        core = SpatialRV64ICore(36864)  # 192*192, perfect square for Hilbert map
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=500000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"
        gpu = {k: core.read_mem_word(a) for k, a in sym_addrs.items()}

        # 4. Transpiled Glyph on GlyphCPUv2
        glyph_source = transpile_elf_to_glyph(elf_bytes, entry_symbol="_start",
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
        for _ in range(600000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"
        glyph = {k: cpu.memory[a >> 2] for k, a in sym_addrs.items()}

        # 5. Differential cross-check
        for key, exp_val in EXPECTED.items():
            assert gpu[key] == exp_val, f"GPU {key}: 0x{gpu[key]:08x} != 0x{exp_val:08x}"
            assert glyph[key] == exp_val, f"Glyph {key}: 0x{glyph[key]:08x} != 0x{exp_val:08x}"
            assert glyph[key] == gpu[key], (
                f"Differential mismatch {key}: Glyph=0x{glyph[key]:08x} GPU=0x{gpu[key]:08x}")
