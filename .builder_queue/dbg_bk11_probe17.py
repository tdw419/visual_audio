"""BK-11 root-cause probe 17: DATA layout & collision.

DATA 'aa bb\\ncc\\n' + trailing NUL + name 'f.txt\\0' all sit in .data.
The data section base word collides with... the glyph r31 hardware call
STACK? The stack grows DOWN from stack_addr (near ram top), not here.
But WAIT: probe16 says with LEN=5 'ab cd' the count is CORRECT (S1).
probe15's failing cases have LEN=6,7,8. Data bytes at word boundaries:
'aa bb\\ncc\\n' = 9 bytes + NUL = 10 bytes = 2.5 words.
Test single-byte-classify loops with data of length 5 vs 6 to find the
length threshold where the count breaks: 'ab cd' (5), 'ab cde' (6),
'ab cdef' (7), each one space, expect S1."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tests.test_gh23_libc_runtime import (  # noqa: E402
    _load_posix_program, GH23_STDOUT_WORDS)

PROBE_TEMPLATE = r"""
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

static const char DATA[] = "%(data)s";
static unsigned LEN = %(len)d;

void _start(void) {
    unsigned spaces = 0;
    unsigned i;
    for (i = 0; i < LEN; i++) {
        char c = DATA[i];
        if (c == ' ') spaces++;
    }
    bk11_out_ch('S');
    bk11_out_ch('0' + (char)spaces);
    bk11_out_ch('|');
    bk11_flush();
    exit(0);
}
"""


def run_case(data_c, n, expect, tmp):
    src = tmp / "p.c"
    src.write_text(PROBE_TEMPLATE % {"data": data_c, "len": n})
    from tests.test_gh23_libc_runtime import LIBC_C, SHIM_S
    libc = tmp / "libc.c"
    libc.write_text(LIBC_C)
    shim = tmp / "shim.S"
    shim.write_text(SHIM_S)
    objs = []
    for i, o in enumerate((src, libc)):
        obj = tmp / f"p_{i}.o"
        subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                        "-mabi=ilp32", "-O1", "-nostdlib", "-fno-builtin",
                        "-w", "-c", str(o), "-o", str(obj)], check=True)
        objs.append(obj)
    elf = tmp / "p.elf"
    subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                    "-mabi=ilp32", "-nostdlib", "-Wl,-Ttext=0x0",
                    "-Wl,--entry=_start", "-w", *map(str, objs),
                    str(shim), "-o", str(elf)], check=True,
                   capture_output=True)
    program = _load_posix_program(elf.read_bytes())
    out = tmp / "p.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    mem = receipt["memory"]
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in GH23_STDOUT_WORDS).rstrip(b"\0")
    ok = got.decode() == expect
    print(f"len={n}: {got!r} expect {expect!r} "
          f"{'OK' if ok else 'MISMATCH'}")


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    run_case("ab cd", 5, "S1|", tmp)
    run_case("ab cde", 6, "S1|", tmp)
    run_case("ab cdef", 7, "S1|", tmp)
    run_case("ab cdefg", 8, "S1|", tmp)
    run_case("a cdefgh", 8, "S1|", tmp)
