"""BK-11 root-cause probe 11: dump the glyph IR for the failing
newline-only loop and simulate it in Python to find where branch 3 goes.
"""
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

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    # reuse wc tool (contains the same beq-to-newline shape) - one_line
    # fixture: DATA 'hello\n' has 1 newline; glyph counted that fine (cat
    # and 1-NL fixtures pass). two_lines has 2 NLs -> glyph says 2, real
    # says... wait: wc/two_lines says lines=2 (correct!) but words=2
    # (should be 3). probe10 says newlines=2 for TWO newlines?? No —
    # DATA has 2 newlines total ('aa bb\ncc\n'): probe10 expect was WRONG.
    # Recheck: probe9 '612' = letters 6, spaces 1(!), newlines 2.
    # Real counts: letters 6, spaces 2, newlines 2 -> SPACE count is 1.
    # One space MISSED. Probe8 echo showed 'aa bb' so data reads right.
    # New theory: the FIRST space (index 2) or SECOND (index 3) fails the
    # ==32 test. Print byte values in hex to see exactly what the loop
    # reads at each index.
    pass

PROBE_C2 = r"""
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

static const char DATA[] = "aa bb\ncc\n";
static unsigned LEN = 9;

static void out_hex(unsigned v) {
    char lo = v & 15;
    char hi = (v >> 4) & 15;
    bk11_out_ch(hi < 10 ? '0' + hi : 'A' + hi - 10);
    bk11_out_ch(lo < 10 ? '0' + lo : 'A' + lo - 10);
    bk11_out_ch(' ');
}

void _start(void) {
    unsigned i;
    for (i = 0; i < LEN; i++) {
        out_hex((unsigned)(unsigned char)DATA[i]);
    }
    bk11_out_ch('|');
    bk11_flush();
    exit(0);
}
"""

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    src = tmp / "p.c"
    src.write_text(PROBE_C2)
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
                    str(shim), "-o", str(elf)], check=True)
    # what's in the data section?
    from tools.rv64i_to_glyph import parse_elf_data_sections
    for addr, blob in parse_elf_data_sections(elf.read_bytes()):
        print(hex(addr), blob.hex(), repr(blob))
    program = _load_posix_program(elf.read_bytes())
    out = tmp / "p.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    mem = receipt["memory"]
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in GH23_STDOUT_WORDS).rstrip(b"\0")
    print("probe stdout:", got)
    print("expect: 61 61 20 62 62 0A 63 63 0A |")
