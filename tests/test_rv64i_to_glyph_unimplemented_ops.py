"""
Guard for the RV32I opcodes the transpiler deliberately does NOT lower.

History: this file held executable tripwires (compile a snippet that emits
the op, assert `transpile_elf_to_glyph` raises `ValueError`) for the opcodes
real `-nostdlib` C could still reach. They have all since been implemented:

  * `LBU` / `SB`  -- G6
  * `LHU` / `SH`  -- G10 (`test_rv64i_to_glyph_dinode.py`)
  * `SLTIU` / `AUIPC` -- G11 (`test_rv64i_to_glyph_sltiu_auipc.py`)

Every remaining unhandled opcode in `GLYPH_TRANSPILER_OPCODE_COVERAGE.md` is
either RV64-only (`*W`), an extension the base ISA fixtures can't reach
without libgcc (`MUL`/`DIV`/`REM`), or privileged/atomic/fence -- none
emitted by GCC from portable rv32i `-O1` C. So there is no armed tripwire
left; what stays here is the one *negative* finding that still needs
guarding:

  * Signed `LB` / `LH` are NOT reachable gaps. GCC rv32i `-O1` compiles a
    `signed char` load to `lbu` + `slli` + `srai` (shift-pair sign
    extension), never `lb`. If a toolchain change ever starts emitting real
    `lb`/`lh`, `test_signed_char_load_uses_shift_substitution` below flips
    red -- that is the signal that signed sub-word loads now need a real
    lowering. (Companion to the `lb`-absent assertion in
    `test_rv64i_to_glyph_stringc.py`.)
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

from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402

_GCC_BIN = "riscv64-unknown-elf-gcc"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

_SCAFFOLD = r"""
typedef unsigned int   uint;
typedef unsigned long  uint64;

volatile unsigned       gin_u;
volatile int            gout;
volatile signed char    gsc[4];
volatile short          gsh[4];
volatile unsigned short gush[4];

__attribute__((noinline)) void run_test(void) {
  %s
}

void _start(void) {
  __asm__ volatile (
      ".option push\n.option norelax\n"
      "lui gp, %%hi(__global_pointer$)\n"
      "addi gp, gp, %%lo(__global_pointer$)\n"
      ".option pop\n"
      "li sp, 0x4000\n"
      "call run_test\n"
      "ecall\n"
  );
}
"""


def _compile(tmp, body, extra_flags):
    c_path = tmp / "op.c"
    elf_path = tmp / "op.elf"
    c_path.write_text(_SCAFFOLD % body)
    res = subprocess.run(
        [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
         "-fno-builtin", "-w", "-Wl,-Ttext=0x0", *extra_flags,
         str(c_path), "-o", str(elf_path)],
        capture_output=True, text=True)
    assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"
    objdump = subprocess.run(
        ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
        capture_output=True, text=True).stdout
    return elf_path.read_bytes(), objdump


def test_signed_char_load_uses_shift_substitution():
    """A `signed char` load compiles to `lbu` + `slli` + `srai`, not `lb` --
    and that sequence already transpiles. If GCC ever switches to real `lb`,
    this starts raising `ValueError` and this file is where to look.
    (`short` goes through `lhu` + shift pair, implemented in G10.)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        elf_bytes, objdump = _compile(tmp, "gout = gsc[2];", [])
        run_body = re.search(r"<run_test>:(.*?)\bret\b", objdump, re.S).group(1)
        assert "lbu" in run_body and "srai" in run_body, "expected lbu + shift-pair"
        assert not re.search(r"\blb\b", run_body), (
            "GCC now emits real lb for a signed char load -- the transpiler "
            "has no LB lowering; add one or a fixture")
        # Must not raise: every op in the substitution is already lowered.
        glyph = transpile_elf_to_glyph(elf_bytes, entry_symbol="_start")
        assert "HALT" in glyph
