"""BK-11 root-cause probe 19: ISOLATE the newline byte.

Data 'a\\na' (3 bytes, no space, 1 newline): count spaces (expect 0) and
newlines (expect 1). Then data 'a a' (3 bytes, 1 space, no newline).
The failing combos involve '\\n' IN the data — does the \\n byte READ as
32 (space)? Emit hex of each byte in a 5-byte string 'a\\nb c' (expect
61 0A 62 20 63) and count spaces with the loop (expect 1)."""
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

static void out_hex(unsigned v) {
    char lo = v & 15;
    char hi = (v >> 4) & 15;
    bk11_out_ch(hi < 10 ? '0' + hi : 'A' + hi - 10);
    bk11_out_ch(lo < 10 ? '0' + lo : 'A' + lo - 10);
    bk11_out_ch(' ');
}

void _start(void) {
    unsigned spaces = 0;
    unsigned i;
    for (i = 0; i < %(hexlen)d; i++) {
        out_hex((unsigned)(unsigned char)DATA[i]);
    }
    bk11_out_ch('|');
    for (i = 0; i < LEN; i++) {
        char c = DATA[i];
        if (c == ' ') spaces++;
    }
    bk11_out_ch('S');
    bk11_out_ch('0' + (char)spaces);
    bk11_flush();
    exit(0);
}
"""


def run_case(tag, data_c, n, expect_hex, expect_s, tmp):
    src = tmp / "p.c"
    src.write_text(PROBE_TEMPLATE % {"data": data_c, "len": n,
                                     "hexlen": n})
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
    print(f"{tag}: {got!r} (hex want {expect_hex!r}, S want {expect_s})")


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    # 'a\nb c' = 5 bytes: hex 61 0A 62 20 63, 1 space
    run_case("hex+a\\nb c", "a\\nb c", 5, "61 0A 62 20 63 |", 1, tmp)
