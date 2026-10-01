"""BK-11 root-cause probe 41: probe40 passed?! Difference vs
probe38/probe33 (which failed): probe40 emits the letter to stdout
INSIDE the loop (an out_ch call between the store and the next
iteration). probe33 stored WITHOUT any intervening call and failed.
Test probe40's exact program with the live out_ch REMOVED (pure
probe33) but readback hex via out_hex-style dump: if it fails again,
the bug needs NO intervening call — pointing at the BNE lowerings
around the taken-branch path interacting with the NEXT iteration's SB
address computation (MASK_N reload). Emit both raw and hex.
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
        char letter;
        if (c == 32) { SPACES++; letter = 'S'; }
        else letter = 'A' + (char)i;
        MASK[MASK_N++] = letter;
        i++;
        if (i == LEN) break;
    }
    for (i = 0; i < 6; i++) bk11_out_ch(MASK[i]);
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
    print("no-call loop:", got, "(expect b'ABSDEF|')")
