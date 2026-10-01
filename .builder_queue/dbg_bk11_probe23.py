"""BK-11 root-cause probe 23: replicate the EXACT loop shape of wc's
word counter — BNE-form compare-branch with r28/r29/r30 holding live
compare constants (a3=32 at r13) — but the GCC-generated branch is
`bne a4,a2` with an inverted-body layout: init BEFORE the compare block,
latch at the bottom, and the r13==32 compare INSIDE the body. Compare
against the same shape with the r13 test REMOVED (probe21's S-passing
shape) to see if the inner constant compare corrupts the loop bound.
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

TEMPLATE = r"""
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

void _start(void) {
    unsigned i = 0, spaces = 0, nl = 0, words = 0;
    if (LEN == 0) { bk11_out_ch('E'); bk11_out_ch('|'); bk11_flush(); exit(0); }
    for (;;) {
        char c = DATA[i];
        if (c == 32) spaces++;
        %(body)s
        i++;
        if (i == LEN) break;
    }
    bk11_out_ch('0' + (char)spaces);
    bk11_out_ch('0' + (char)nl);
    bk11_out_ch('0' + (char)words);
    bk11_out_ch('|');
    bk11_flush();
    exit(0);
}
"""

VARIANTS = {
    "A_no_inner": "",                      # expect '010|'
    "B_nl_inner": "if (c == 10) nl++;",    # expect '011|'
    "C_word_inner": ("if (c == 32 || c == 10) { if (i && DATA[i-1] != 32 "
                     "&& DATA[i-1] != 10) words++; }"),  # approx, expect '013|'
}

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    from tests.test_gh23_libc_runtime import LIBC_C, SHIM_S
    libc = tmp / "libc.c"
    libc.write_text(LIBC_C)
    shim = tmp / "shim.S"
    shim.write_text(SHIM_S)
    for tag, body in VARIANTS.items():
        src = tmp / f"p_{tag}.c"
        src.write_text(TEMPLATE % {"body": body})
        objs = []
        for i, o in enumerate((src, libc)):
            obj = tmp / f"{tag}_{i}.o"
            subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                            "-mabi=ilp32", "-O1", "-nostdlib", "-fno-builtin",
                            "-w", "-c", str(o), "-o", str(obj)], check=True)
            objs.append(obj)
        elf = tmp / f"{tag}.elf"
        subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                        "-mabi=ilp32", "-nostdlib", "-Wl,-Ttext=0x0",
                        "-Wl,--entry=_start", "-w", *map(str, objs),
                        str(shim), "-o", str(elf)], check=True,
                       capture_output=True)
        program = _load_posix_program(elf.read_bytes())
        out = tmp / f"{tag}.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                  user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=200000, trace=True)
        mem = receipt["memory"]
        got = b"".join(int(mem[w]).to_bytes(4, "little")
                       for w in GH23_STDOUT_WORDS).rstrip(b"\0")
        print(f"{tag}: {got!r}")
