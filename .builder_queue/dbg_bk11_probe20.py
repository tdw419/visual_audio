"""BK-11 root-cause probe 20: WAIT. probe19's output shows 'S2' and NO
hex at all — the hex block output VANISHED and spaces=2. 'a\\nb c' has
bytes 61 0A 62 20 63: TWO bytes >= 0x0A?? No... S2 means the loop counted
2 spaces. KEY INSIGHT CANDIDATE: 'if (c == 10) newlines++' emits a
`li a3,10`-style constant, and the SPACE test `beq a4,t1` compares
against t1. If the nl-constant load CLOBBERS the space constant... but
probe18-D had NO nl counter and still failed (S3).
Compare probe18-D (fail, S3) vs probe17 (pass, S1): probe17 data had NO
newline byte, probe18-D data 'aa bb\\ncc\\n' HAS newline bytes. When the
LOOP reads the 0x0A byte, something corrupts state so a LATER byte is
miscounted as space. Hex-dump disappeared too — output got mangled.
Theory: reading the 0x0A byte via LBU triggers the bug — LBU's lowering
clobbers something the write-side needs. Emit ONLY the space count for
'a\\na' (expect 0):"""
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


def run_case(tag, data_c, n, expect, tmp):
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
    print(f"{tag}: {got!r} expect {expect!r} {'OK' if ok else 'MISMATCH'}")


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    run_case("nl only 'a\\na'", "a\\na", 3, "S0|", tmp)
    run_case("nl+sp 'a\\na '", "a\\na ", 4, "S1|", tmp)
    run_case("sp+nl 'a a\\n'", "a a\\n", 4, "S1|", tmp)
    run_case("no nl 'a a'", "a a", 3, "S1|", tmp)
