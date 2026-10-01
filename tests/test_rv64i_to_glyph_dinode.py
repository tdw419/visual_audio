"""
xv6 fs.h `struct dinode` / `struct dirent` differential test: 16-bit memory
(LHU + SH), G10.

Closes the last operand-width gap. G6 added 8-bit (LBU/SB); this adds 16-bit,
so the transpiler now covers byte / halfword / word memory completely. The
two structs are lifted from xv6-riscv/kernel/fs.h -- `dinode`'s
`short type/major/minor/nlink` and `dirent`'s `ushort inum` are exactly the
fields that made every prior attempt to transpile real fs/dir code raise
`ValueError`.

Lowering (mirrors G6, 16-bit lanes): a naturally-aligned halfword lies
wholly in one 32-bit word; lane = bit 1 of the byte address, shift =
`(addr & 2) << 3` (0 or 16). LHU = `(word >> shift) & 0xFFFF`. SH =
read-modify-write, clearing the lane via `(x | m) ^ m` with
`m = 0xFFFF << shift`. Signed LH is deliberately still unimplemented: GCC
rv32i `-O1` never emits it (uses `lhu` + `slli 16` + `srai 16`), pinned by
`test_rv64i_to_glyph_unimplemented_ops.py`.

Scenario: populate a `dinode` (`nlink = 300` proves no byte truncation, a
word-aligned 32-bit `size` interleaved with the shorts) and a `dirent`
(`inum = 0xBEEF`), read every field back, fold into a layout-independent
checksum.

All field values are deliberately positive: GCC's signed sub-word read-back
is `lhu` + `slli 16` + `srai 16`, an XLEN=32 idiom.  `SpatialRV64ICore` is a
64-bit model, so that idiom does NOT sign-extend a negative halfword there
(bit 15 lands in bit 31, not the sign bit) -- a real rv32-code-on-rv64
hazard, but orthogonal to LHU/SH and out of scope for this ISA-less
transpiler.  Keeping every value >= 0 makes signed and unsigned read-back
identical on any width, so the three engines can still be compared exactly.

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

DINODE_C = r"""
typedef unsigned int   uint;
typedef unsigned short ushort;
typedef unsigned char  uchar;

/* verbatim field layout from xv6-riscv/kernel/fs.h */
struct dinode {
  short type;
  short major;
  short minor;
  short nlink;
  uint  size;
  uint  addrs[13];
};

struct dirent {
  ushort inum;
  char   name[14];
};

volatile struct dinode g_ino;
volatile struct dirent g_dir;

int      g_type, g_major, g_minor, g_nlink;
unsigned g_inum, g_size;
int      g_checksum;

__attribute__((noinline)) void run_test(void) {
  g_ino.type  = 2;
  g_ino.major = 7;
  g_ino.minor = 3;
  g_ino.nlink = 300;         /* > 255: must not byte-truncate */
  g_ino.size  = 0xCAFE1234u; /* word-aligned 32-bit, interleaved */
  g_dir.inum  = 0xBEEFu;

  g_type  = g_ino.type;
  g_major = g_ino.major;
  g_minor = g_ino.minor;
  g_nlink = g_ino.nlink;
  g_inum  = g_dir.inum;
  g_size  = g_ino.size;

  g_checksum = g_type ^ (g_major << 3) ^ (g_minor << 7) ^ (g_nlink << 5)
             ^ (int)g_inum ^ (int)g_size;
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

NATIVE_HARNESS_C = "#include <assert.h>\n" + DINODE_C + r"""
int main(void) {
    run_test();
    assert(g_type == 2);
    assert(g_major == 7);
    assert(g_minor == 3);
    assert(g_nlink == 300);
    assert(g_inum == 0x0000BEEFu);
    assert(g_size == 0xCAFE1234u);
    assert((unsigned)g_checksum == 0xCAFE88E1u);
    return 0;
}
"""

EXPECTED = {
    "g_type": 2,
    "g_major": 7,
    "g_minor": 3,
    "g_nlink": 300,
    "g_inum": 0x0000BEEF,
    "g_size": 0xCAFE1234,
    "g_checksum": 0xCAFE88E1,
}


def test_dinode_halfword_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "dinode.c"
        elf_path = tmp / "dinode.elf"
        bin_path = tmp / "dinode.bin"
        native_c_path = tmp / "native_dinode.c"
        native_bin_path = tmp / "native_dinode"

        # 1. Native host ground truth
        native_c_path.write_text(NATIVE_HARNESS_C)
        native_res = subprocess.run(
            ["gcc", "-DHOST_TEST", "-O1", "-w", str(native_c_path), "-o", str(native_bin_path)],
            capture_output=True, text=True)
        assert native_res.returncode == 0, f"Host GCC failed: {native_res.stderr}"
        host_exec = subprocess.run([str(native_bin_path)], capture_output=True, text=True)
        assert host_exec.returncode == 0, f"Native host dinode assertion failed: {host_exec.stderr}"

        # 2. RISC-V compile
        c_path.write_text(DINODE_C)
        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin", "-w", "-Wl,-Ttext=0x0",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"

        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        assert re.search(r"\bsh\s+\w+,\s*-?\d+\(\w+\)", objdump), "no sh (halfword store) in dinode codegen"
        assert re.search(r"\blhu\s+\w+,\s*-?\d+\(\w+\)", objdump), "no lhu (halfword load) in dinode codegen"
        assert not re.search(r"\blh\s+\w+,\s*-?\d+\(\w+\)", objdump), (
            "dinode codegen contains signed `lh` -- the transpiler has no LH "
            "lowering; add one or re-scope this test")

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
