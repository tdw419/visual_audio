"""BK-11 root-cause probe 35: MASK dump via index-constant loop instead
of the MASK_N-driven loop — emits exactly 6 bytes with a hardcoded
trip count. If hex bytes now show 41 42 53 44 45 46, the MASK memory
was always right and probe34's inner `for (i < MASK_N)` loop miscounted
(bound register corrupted); if still wrong, the stores landed wrong.
Also emit MASK_N at the end in hex.
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
        else MASK[MASK_N++] = 'A' + (char)i;
        i++;
        if (i == LEN) break;
    }
    /* hardcoded 6-iteration dump */
    for (i = 0; i < 6; i++) {
        unsigned char b = (unsigned char)MASK[i];
        char hi = (b >> 4) & 15, lo = b & 15;
        bk11_out_ch(hi < 10 ? '0' + hi : 'A' + hi - 10);
        bk11_out_ch(lo < 10 ? '0' + lo : 'A' + lo - 10);
    }
    /* MASK_N in hex */
    {
        unsigned char b = (unsigned char)MASK_N;
        char hi = (b >> 4) & 15, lo = b & 15;
        bk11_out_ch('N');
        bk11_out_ch(hi < 10 ? '0' + hi : 'A' + hi - 10);
        bk11_out_ch(lo < 10 ? '0' + lo : 'A' + lo - 10);
    }
    bk11_out_ch('|');
    bk11_flush();
    exit(0);
}
"""

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    src = tmp / "p.c"
    src.write_text(PROBE_C)
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
    print("fixed dump:", got, "(expect b'4142534445464E06|')")
