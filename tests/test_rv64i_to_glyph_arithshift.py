"""
Arithmetic right shift (`sra` / `srai`) of a NEGATIVE value.

Glyph ISA v2 has only a logical `SHR`; before this test the transpiler
lowered both `srl` and `sra` to it, so `srai`/`sra` of a negative operand
did not sign-extend on GlyphCPUv2 (`(-12345) >> 31` gave `1`, not
`0xFFFFFFFF`). Found while scoping the software-division fixture (item 2),
where GCC's branchless signed-`abs` idiom `srai rX,31; xor; sub` needs a
real arithmetic shift.

The transpiler now sign-extends branchlessly (no NOT opcode):
    sar(x, n) = ((x ^ 0x80000000) >>u n) - (0x80000000 >>u n)

NOTE -- this is a **native-vs-Glyph** test, not the usual three-way. The GPU
oracle is excluded on purpose: `SpatialRV64ICore` is a 64-bit model and its
`srai` of an rv32 negative value is separately broken (it produces 0 here --
the same rv32-code-on-rv64 class as the G10 hazard). Fixing that is a
`SpatialRV64ICore` change, out of scope for this roadmap. The GPU leg below
is run and asserted to STILL be wrong, so that if someone repairs the GPU
core this test fails loudly and can be promoted to full three-way.
"""
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
volatile int g_a, g_sh;
int g_ar1, g_ar4, g_ar31, g_reg;
int g_pos4;          /* arith shift of a positive value: must be unchanged */
int g_checksum;

__attribute__((noinline)) void run_test(void) {
  g_a = -12345;   /* 0xFFFFCFC7 */
  g_sh = 5;
  g_ar1  = g_a >> 1;        /* srai 1  -> -6173  (0xFFFFE7E3) */
  g_ar4  = g_a >> 4;        /* srai 4  -> -772   (0xFFFFFCFC) */
  g_ar31 = g_a >> 31;       /* srai 31 -> -1     (0xFFFFFFFF) */
  g_reg  = g_a >> g_sh;     /* sra (reg) -> -386 (0xFFFFFE7E) */
  g_pos4 = 12344 >> 4;      /* 771 -- sign bit clear, sanity */
  g_checksum = g_ar1 ^ g_ar4 ^ g_ar31 ^ g_reg ^ g_pos4;
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
    assert(g_ar1 == -6173);
    assert(g_ar4 == -772);
    assert(g_ar31 == -1);
    assert(g_reg == -386);
    assert(g_pos4 == 771);
    return 0;
}
"""

EXPECTED = {
    "g_ar1": (-6173) & 0xFFFFFFFF,
    "g_ar4": (-772) & 0xFFFFFFFF,
    "g_ar31": 0xFFFFFFFF,
    "g_reg": (-386) & 0xFFFFFFFF,
    "g_pos4": 771,
}
EXPECTED["g_checksum"] = (
    EXPECTED["g_ar1"] ^ EXPECTED["g_ar4"] ^ EXPECTED["g_ar31"]
    ^ EXPECTED["g_reg"] ^ EXPECTED["g_pos4"]
) & 0xFFFFFFFF


def test_arith_shift_negative_native_vs_glyph():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "src.c"
        elf_path = tmp / "src.elf"
        bin_path = tmp / "src.bin"
        native_c_path = tmp / "native_src.c"
        native_bin_path = tmp / "native_src"

        # 1. Native host ground truth
        native_c_path.write_text(NATIVE_HARNESS_C)
        r = subprocess.run(["gcc", "-DHOST_TEST", "-O1", "-w", str(native_c_path), "-o", str(native_bin_path)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert subprocess.run([str(native_bin_path)]).returncode == 0, "native assertions failed"

        # 2. RISC-V compile
        c_path.write_text(SRC_C)
        r = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin", "-w", "-Wl,-Ttext=0x0", str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        objdump = subprocess.run(["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
                                 capture_output=True, text=True).stdout
        assert "srai" in objdump and "sra" in objdump, "fixture did not emit srai/sra"

        subprocess.run([_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)], check=True)
        bin_data = bin_path.read_bytes()

        nm_out = subprocess.run(["riscv64-unknown-elf-nm", str(elf_path)],
                                capture_output=True, text=True).stdout
        sym = {}
        for line in nm_out.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[2] in EXPECTED:
                sym[parts[2]] = int(parts[0], 16)
        assert set(sym) == set(EXPECTED), f"missing: {set(EXPECTED) - set(sym)}"

        elf_bytes = elf_path.read_bytes()
        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # 3. Glyph (the leg this test exists for)
        glyph_source = transpile_elf_to_glyph(elf_bytes, entry_symbol="_start", byte_to_word_mem=True)
        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
        pixels, _ = assemble_glyph_to_pixels(glyph_source, cols_instrs=64, min_rows=32)
        cpu.memory = [0] * 16384
        for vaddr, blob in parse_elf_data_sections(elf_bytes):
            for i, b in enumerate(blob):
                a = vaddr + i
                w = a >> 2
                s = (a & 3) * 8
                cpu.memory[w] = (cpu.memory[w] & ~(0xFF << s)) | (b << s)
        cpu.pc = (0, 0)
        cpu.running = True
        for _ in range(300000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"
        glyph = {k: cpu.memory[a >> 2] for k, a in sym.items()}
        for k, exp in EXPECTED.items():
            assert glyph[k] == exp, f"Glyph {k}: 0x{glyph[k]:08x} != 0x{exp:08x}"

        # 4. GPU leg -- asserted STILL broken (see module docstring). If this
        #    starts matching, SpatialRV64ICore's srai was fixed: delete this
        #    block and add the GPU asserts above for full three-way.
        core = SpatialRV64ICore(4096)
        core.load_program(bin_data, entry_point=entry_addr)
        core.run_until_halt(max_cycles=200000, chunk_size=64)
        gpu_ar31 = core.read_mem_word(sym["g_ar31"])
        assert gpu_ar31 != EXPECTED["g_ar31"], (
            "SpatialRV64ICore srai of a negative rv32 value now matches native "
            "-- promote this test to full three-way")
