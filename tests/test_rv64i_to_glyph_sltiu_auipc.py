"""
SLTIU + AUIPC differential test (G11): the last two armed opcode tripwires,
converted into a real three-way fixture.

  * SLTIU -- immediate unsigned set-less-than. Lowered like SLTU (XOR both
    ends with the sign bit, signed-subtract, take the sign of the
    difference) with the subtrahend a constant. GCC emits it directly for
    `(unsigned)x < K` and via the `seqz`/`snez` pseudo-ops for `== 0` /
    `!= 0` boolean-normalize.
  * AUIPC -- `rd = pc + (imm20 << 12)`. The transpiler walks .text at fixed
    linked addresses, so `pc` is a compile-time constant and the whole
    instruction folds to a single `LDI`. Forced into codegen here with
    `-mcmodel=medany -msmall-data-limit=0`, which makes every global
    reference materialize its address as `auipc rd,%pcrel_hi; addi
    rd,rd,%pcrel_lo` -- so a correct global read/write value is itself the
    proof the AUIPC address math is right.

Scenario: two `< 10u` range checks (one true, one false), a `== 0` (seqz),
a `>= 20u` (snez-shaped), and `< (unsigned)-1` (imm sign-extends to
0xFFFFFFFF), folded into a bitmask. Layout-independent -- native and RISC-V
expected values are identical.

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

volatile unsigned g_x, g_y;
int g_lt10_x, g_lt10_y, g_eqz_x, g_ge, g_wrap;
int g_checksum;

__attribute__((noinline)) void run_test(void) {
  g_x = 3;
  g_y = 50;
  g_lt10_x = (g_x < 10u);            /* sltiu           -> 1 */
  g_lt10_y = (g_y < 10u);            /* sltiu           -> 0 */
  g_eqz_x  = (g_x == 0u);            /* seqz (sltiu ,1) -> 0 */
  g_ge     = (g_y >= 20u);           /* !(sltiu)        -> 1 */
  g_wrap   = (g_x < (unsigned)-1);   /* sltiu rs,-1: sext 0xFFFFFFFF -> 1 */
  g_checksum = g_lt10_x | (g_lt10_y << 1) | (g_eqz_x << 2)
             | (g_ge << 3) | (g_wrap << 4);
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
    assert(g_lt10_x == 1);
    assert(g_lt10_y == 0);
    assert(g_eqz_x == 0);
    assert(g_ge == 1);
    assert(g_wrap == 1);
    assert(g_checksum == 25);
    return 0;
}
"""

EXPECTED = {
    "g_lt10_x": 1,
    "g_lt10_y": 0,
    "g_eqz_x": 0,
    "g_ge": 1,
    "g_wrap": 1,
    "g_checksum": 25,
}


def test_sltiu_auipc_differential():
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

        # 2. RISC-V compile -- medany + small-data-limit=0 forces auipc for
        #    every global address.
        c_path.write_text(SRC_C)
        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin", "-w",
             "-mcmodel=medany", "-msmall-data-limit=0",
             "-Wl,-Ttext=0x0",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"

        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        assert re.search(r"\bsltiu\b", objdump), "no sltiu in codegen -- rework the fixture"
        assert re.search(r"\bauipc\b", objdump), "no auipc in codegen -- rework the fixture"

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
        glyph = {k: cpu.memory[a >> 2] for k, a in sym_addrs.items()}

        # 5. Differential cross-check
        for key, exp_val in EXPECTED.items():
            assert gpu[key] == exp_val, f"GPU {key}: 0x{gpu[key]:08x} != 0x{exp_val:08x}"
            assert glyph[key] == exp_val, f"Glyph {key}: 0x{glyph[key]:08x} != 0x{exp_val:08x}"
            assert glyph[key] == gpu[key], (
                f"Differential mismatch {key}: Glyph=0x{glyph[key]:08x} GPU=0x{gpu[key]:08x}")
