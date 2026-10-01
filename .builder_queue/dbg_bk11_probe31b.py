"""BK-11 probe 31b: locate BOTH 'LDI r31' lines in the loaded program
for the SPACES-counter C (the shape that trips the baker's re-seed
assert) and print context, so we can see what glyph code the second
one comes from."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

C = r"""
extern void exit(int code);
extern int write(int fd, const void *buf, unsigned len);
static char _buf[16];
static unsigned _n;
static void bk11_flush(void) {
    while (_n < 16) _buf[_n++] = '\0';
    write(1, _buf, 16);
    _n = 0;
}
static void bk11_out_ch(char c) { if (_n == 16) bk11_flush(); _buf[_n++] = c; }
static const char DATA[] = "aa bb\n";
static unsigned LEN = 6;
static char MASK[8];
static unsigned MASK_N;
static unsigned SPACES;
void _start(void) {
    unsigned i = 0;
    if (LEN == 0) { bk11_out_ch('E'); bk11_out_ch('|'); bk11_flush(); exit(0); }
    for (;;) {
        char c = DATA[i];
        if (c == 32) { SPACES++; MASK[MASK_N++] = 'S'; }
        else if (c == 10) MASK[MASK_N++] = 'Z';
        else MASK[MASK_N++] = 'A' + (char)i;
        i++;
        if (i == LEN) break;
    }
    for (i = 0; i < MASK_N; i++) bk11_out_ch(MASK[i]);
    bk11_out_ch('|');
    bk11_flush();
    exit(0);
}
"""

from tests.test_gh23_libc_runtime import _load_posix_program, LIBC_C, SHIM_S

tmp = Path(tempfile.mkdtemp())
(tmp / "p.c").write_text(C)
(tmp / "libc.c").write_text(LIBC_C)
(tmp / "shim.S").write_text(SHIM_S)
objs = []
for i, o in enumerate(("p.c", "libc.c")):
    obj = tmp / f"p_{i}.o"
    subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32",
                    "-O1", "-nostdlib", "-fno-builtin", "-w", "-c",
                    str(tmp / o), "-o", str(obj)], check=True)
    objs.append(obj)
elf = tmp / "p.elf"
subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32",
                "-nostdlib", "-Wl,-Ttext=0x0", "-Wl,--entry=_start", "-w",
                *map(str, objs), str(tmp / "shim.S"), "-o", str(elf)],
               check=True, capture_output=True)
program = _load_posix_program(elf.read_bytes())
lines = program.splitlines()
for i, l in enumerate(lines):
    if l.strip().startswith("LDI r31"):
        print(f"--- LDI r31 at line {i}:")
        print("\n".join(lines[max(0, i - 8):i + 4]))
        print()
# also: which RV instruction produced 'Z' constant 0x5a? find its elf pc
base, text, symbols = __import__("rv64i_to_glyph").parse_elf(elf.read_bytes())
import struct
for off in range(0, len(text), 4):
    w = int.from_bytes(text[off:off+4], "little")
    imm_field = (w >> 20)
    if imm_field == 0x5a:
        print(f"0x{base+off:08x}: word {w:08x} (imm 0x5a = 'Z')")
