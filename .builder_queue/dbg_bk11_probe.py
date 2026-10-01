"""BK-11 root-cause probe: t3 (x28) survival across a taken BLTU branch.

GCC wc: `li t3,32` ... `bltu a3,a4,.space_check` where the TAKEN path
clears in_word via `li a2,0` — and t3=32 must survive to the NEXT byte's
space test. Hypothesis: the BLTU lowering's scratch (r28 = glyph name of
x28=t3) clobbers t3 on EVERY BLTU, so the next space-test compares
against garbage and the second word on a line is never counted.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tests.test_gh23_libc_runtime import (  # noqa: E402
    _load_posix_program, GH23_EXIT_CODE)

# C program: count words in a 2-word line using the exact wc idiom
# (unsigned compare against 10 for the space bucket via bltu ladder).
PROBE_C = r"""
static const char DATA[] = "aa bb\n";
static unsigned LEN = 6;
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
static void bk11_out_str(const char *s) { while (*s) bk11_out_ch(*s++); }
void _start(void) {
    unsigned lines = 0, words = 0, chars = LEN;
    unsigned i; int in_word = 0;
    for (i = 0; i < LEN; i++) {
        char c = DATA[i];
        if (c == '\n') lines++;
        if (c == ' ' || c == '\n' || c == '\t') in_word = 0;
        else if (!in_word) { in_word = 1; words++; }
    }
    unsigned v = words;
    char buf[3];
    buf[2] = 0;
    buf[1] = '0' + (char)(v % 10);
    buf[0] = (v >= 10) ? ('0' + (char)(v / 10)) : ' ';
    bk11_out_str(buf);
    while (_n < 16) bk11_out_ch(' ');
    bk11_flush();
    exit(words == 2 ? 7 : 9);
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
        import subprocess
        subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                        "-mabi=ilp32", "-O1", "-nostdlib", "-fno-builtin",
                        "-ffreestanding", "-w", "-c", str(o), "-o", str(obj)],
                       check=True)
        objs.append(obj)
    elf = tmp / "probe.elf"
    subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                    "-mabi=ilp32", "-nostdlib", "-Wl,-Ttext=0x0",
                    "-Wl,--entry=_start", "-w", *map(str, objs),
                    str(shim), "-o", str(elf)], check=True)
    program = _load_posix_program(elf.read_bytes())
    out = tmp / "probe.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    mem = receipt["memory"]
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in (718, 719, 720, 721)).rstrip(b"\0")
    print("probe stdout:", got)
    print("exit code:", mem[GH23_EXIT_CODE], "(7 = words==2 correct,",
          "9 = words!=2 BUG confirmed)")
