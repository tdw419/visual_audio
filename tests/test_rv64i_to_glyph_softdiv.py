"""
Software UNSIGNED integer division differential test (loop item 2 /
pre-printf.c).

RV32I has no divide instruction, and `-nostdlib -march=rv32i` GCC lowers
every runtime `/` and `%` to a call to libgcc's `__udivsi3` / `__umodsi3` --
which don't link under `-nostdlib`. So this fixture *ships* those two
symbols in pure C (shift-and-subtract, one bit per iteration), exactly the
way a bare-metal kernel provides them. GCC then resolves its own division
calls to this code, and every op in it is already lowered.

This is the divider `printf.c`'s `printint`
(`do { buf[i++] = digits[x % base]; } while (x /= base); `) depends on --
G12 reuses it.

SCOPE -- unsigned only, deliberately. The signed wrappers `__divsi3` /
`__modsi3` are NOT included: at `-O1` GCC compiles their `abs` as the
branchless idiom `srai rX,rX,31 ; xor ; sub`, and an arithmetic shift-right
of a *negative* value is not consistent across the three engines
(GlyphCPUv2's `SRA` is logical -- it does not sign-extend; `SpatialRV64ICore`
is a 64-bit model, so bit 31 isn't the sign bit -- the same class as the
G10 hazard). xv6's real `printint` never needs `__divsi3`: it does the
signed->unsigned conversion itself with an explicit `if (xx < 0) x = -xx;`
branch (which transpiles fine -- `neg` + branch, verified elsewhere), then
divides unsigned. So signed `__divsi3` is off the path to printf.c.

Scenario: `12345 / 10` and `% 10`; a high-bit case (`0xFFFF0007 / 3`); a
divide that yields 0 (`3 / 10`); all runtime operands (volatile) so nothing
constant-folds, folded into a layout-independent checksum.

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
typedef unsigned int uint;

/* --- shift-and-subtract libgcc stand-ins (bare-metal style) --- */
unsigned __udivsi3(unsigned n, unsigned d) {
  unsigned q = 0, r = 0;
  for (int i = 31; i >= 0; i--) {
    r = (r << 1) | ((n >> i) & 1u);
    if (r >= d) { r -= d; q |= (1u << i); }
  }
  return q;
}
unsigned __umodsi3(unsigned n, unsigned d) {
  unsigned r = 0;
  for (int i = 31; i >= 0; i--) {
    r = (r << 1) | ((n >> i) & 1u);
    if (r >= d) r -= d;
  }
  return r;
}

volatile unsigned g_n, g_base, g_n2, g_base2, g_small, g_big;
unsigned g_q, g_r, g_q2, g_r2, g_qz;
unsigned g_checksum;

__attribute__((noinline)) void run_test(void) {
  g_n = 12345;  g_base = 10;
  g_n2 = 0xFFFF0007u;  g_base2 = 3;
  g_small = 3;  g_big = 10;

  g_q  = g_n  / g_base;    /* __udivsi3 -> 1234 */
  g_r  = g_n  % g_base;    /* __umodsi3 -> 5    */
  g_q2 = g_n2 / g_base2;   /* __udivsi3 -> 1431633922 */
  g_r2 = g_n2 % g_base2;   /* __umodsi3 -> 1    */
  g_qz = g_small / g_big;  /* __udivsi3 -> 0    */

  g_checksum = g_q ^ (g_r << 8) ^ g_q2 ^ (g_r2 << 16) ^ (g_qz << 24);
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
    assert(g_q == 1234);
    assert(g_r == 5);
    assert(g_q2 == 1431633922u);
    assert(g_r2 == 1);
    assert(g_qz == 0);
    assert(g_checksum == (1234u ^ (5u << 8) ^ 1431633922u ^ (1u << 16) ^ (0u << 24)));
    return 0;
}
"""

_CK = 1234 ^ (5 << 8) ^ 1431633922 ^ (1 << 16) ^ (0 << 24)
EXPECTED = {
    "g_q": 1234,
    "g_r": 5,
    "g_q2": 1431633922,
    "g_r2": 1,
    "g_qz": 0,
    "g_checksum": _CK & 0xFFFFFFFF,
}


def test_softdiv_unsigned_differential():
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
        # Division must be a real runtime call to the C stand-ins.
        assert re.search(r"jal\s+\w+\s*<__udivsi3>", objdump), "no runtime __udivsi3 call"
        assert re.search(r"jal\s+\w+\s*<__umodsi3>", objdump), "no runtime __umodsi3 call"
        # No hardware divide/multiply, no signed-div wrappers (see SCOPE note).
        assert "__divsi3" not in objdump and "__modsi3" not in objdump, \
            "signed division wrapper crept in -- see the module SCOPE note"
        mnem = set(re.findall(r"\t([a-z][a-z0-9.]+)\t", objdump))
        forbidden = {"mul", "mulh", "mulhu", "div", "divu", "rem", "remu", "lh", "sh"}
        assert not (mnem & forbidden), f"softdiv codegen uses unlowered opcode(s): {mnem & forbidden}"

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
        gpu_state = core.run_until_halt(max_cycles=2_000_000, chunk_size=64)
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
        for _ in range(3_000_000):
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
