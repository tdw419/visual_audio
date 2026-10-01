"""BK-11 root-cause probe 6: replicate the FULL wc loop shape with the
in_word register-moves, byte data, t3 live — then bisect which clause
flips the result by removing one at a time. Fixture 'aa bb\\ncc\\n'."""
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

DATA = "aa bb\\ncc\\n"

PROBE_C = r"""
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

void _start(void) {
    register long keep __asm__("t3") = 32;
    unsigned lines = 0, words = 0, chars = LEN;
    unsigned i; int in_word = 0;
    for (i = 0; i < LEN; i++) {
        char c = DATA[i];
        if (c == '\n') lines++;
        if (c == ' ' || c == '\n' || c == '\t') in_word = 0;
        else if (!in_word) { in_word = 1; words++; }
    }
    /* emit words count, then t3 check, then lines/chars */
    unsigned v = words;
    bk11_out_ch('0' + (char)v);
    bk11_out_ch((char)keep);
    v = lines;
    bk11_out_ch('0' + (char)v);
    v = chars;
    bk11_out_ch('0' + (char)v);
    bk11_out_ch('|');
    bk11_flush();
    exit(0);
}
"""

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    src = tmp / "probe.c"
    src.write_text(PROBE_C)
    from tests.test_gh23_libc_runtime import LIBC_C, SHIM_S
    libc = tmp / "libc.c"
    libc.write_text(LIBC_C)
    shim = tmp / "shim.S"
    shim.write_text(SHIM_S)
    objs = []
    for i, o in enumerate((src, libc)):
        obj = tmp / f"probe_{i}.o"
        subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                        "-mabi=ilp32", "-O1", "-nostdlib", "-fno-builtin",
                        "-w", "-c", str(o), "-o", str(obj)], check=True)
        objs.append(obj)
    elf = tmp / "probe.elf"
    p = subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                        "-mabi=ilp32", "-nostdlib", "-Wl,-Ttext=0x0",
                        "-Wl,--entry=_start", "-w", *map(str, objs),
                        str(shim), "-o", str(elf)], capture_output=True)
    if p.returncode != 0:
        print("LINK FAILED:", p.stderr.decode())
        sys.exit(1)
    dis = subprocess.run(["riscv64-unknown-elf-objdump", "-d",
                          "--no-show-raw-insn", str(elf)],
                         capture_output=True).stdout.decode()
    show = False
    for line in dis.splitlines():
        if "<_start>:" in line:
            show = True
        if show and line.strip():
            print(line)
        if show and "ret" in line and len(line.strip().split("\t")) > 1:
            break
    program = _load_posix_program(elf.read_bytes())
    out = tmp / "probe.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    mem = receipt["memory"]
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in GH23_STDOUT_WORDS).rstrip(b"\0")
    print("probe stdout:", got)
    print("expected: '3 2 9|'  (3 words, t3=' ', 9 chars)")
