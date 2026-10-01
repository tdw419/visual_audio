"""BK-11 root-cause probe 18: the difference between probe15 (fails,
+1 space) and probe17 (passes): probe15's DATA had an ESCAPED \\n in the
C string AND LEN counted it. Test: same data as probe15 but classify
with == 10 too, print S and N. And a variant with NO \\n in data but
TWO classify branches. Hypothesis: having BOTH if(c==' ') and a second
if(c=='\\n') in the SAME loop body re-introduces the bug (shared
compare-constant register pressure -> t-regs -> some OTHER lowering
clobbers, e.g. the BGEU loop bound or BEQ ladder)."""
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
    unsigned spaces = 0%(extra)s;
    unsigned i;
    for (i = 0; i < LEN; i++) {
        char c = DATA[i];
        if (c == ' ') spaces++;%(extracode)s
    }
    bk11_out_ch('S');
    bk11_out_ch('0' + (char)spaces);
    bk11_out_ch('|');
    bk11_flush();
    exit(0);
}
"""


def run_case(tag, data_c, n, expect, extra, extracode, tmp):
    src = tmp / "p.c"
    src.write_text(PROBE_TEMPLATE % {"data": data_c, "len": n,
                                     "extra": extra, "extracode": extracode})
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
    print(f"{tag}: {got!r} expect {expect!r} "
          f"{'OK' if ok else 'MISMATCH'}")


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    # A: one space, no newline in data, ONLY space check (control)
    run_case("A space-only", "ab cd", 5, "S1|", "", "", tmp)
    # B: data 'ab cd' + second counter for '\\n' (never fires)
    run_case("B +nl counter", "ab cd", 5, "S1|",
             ", newlines = 0", "\n        if (c == 10) newlines++;", tmp)
    # C: original failing shape: data with \n, both counters
    run_case("C nl-in-data", "aa bb\\ncc\\n", 9, "S2|",
             ", newlines = 0", "\n        if (c == 10) newlines++;", tmp)
    # D: data with \n but ONLY space counter
    run_case("D nl-data space-only", "aa bb\\ncc\\n", 9, "S2|", "", "", tmp)
