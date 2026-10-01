"""BK-11 root-cause probe 38: reimplement probe33's EXACT loop (branch
per byte, computed store MASK + MASK_N, live SPACES counter) but hex-
dump MASK[0..5] with a HARDCODED 6-iteration readback and also emit
MASK_N hex. probe35 already did this and got 41 42 41 44 45 46 N06 —
byte[2] is 'A' (0x41) in MEMORY, not 'S'. So the SB('S') either never
executed or was overwritten. SPACES=1 proves the branch WAS taken.
Overwrite suspect: the mask letter write 'A'+i for i=2 = 'C' is NOT 'A'
either! Memory holds 'A' at byte 2 — that's byte[0]'s VALUE at byte[2]'s
address. This probe re-runs probe35's exact program but ALSO dumps
MASK word-aligned raw via pointer cast, printing the 32-bit word hex:
if word0 == 0x44414241 ("ABAD" little-endian 41 42 41 44), bytes are
shifted: the 'S' went to byte 2's neighbor. Dump word + all 8 bytes.
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

static void out_hex8(unsigned char b) {
    char hi = (b >> 4) & 15, lo = b & 15;
    bk11_out_ch(hi < 10 ? '0' + hi : 'A' + hi - 10);
    bk11_out_ch(lo < 10 ? '0' + lo : 'A' + lo - 10);
}

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
    /* all 8 MASK bytes */
    for (i = 0; i < 8; i++) out_hex8((unsigned char)MASK[i]);
    /* word 0 of MASK via unsigned read */
    {
        unsigned w0 = *(unsigned *)&MASK[0];
        out_hex8((unsigned char)(w0 >> 24));
        out_hex8((unsigned char)(w0 >> 16));
        out_hex8((unsigned char)(w0 >> 8));
        out_hex8((unsigned char)(w0));
        out_hex8('W');
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
    print("full byte dump:", got, "(expect b'41425344454600004142434446'... word0 little-endian=44434241 -> 'W' tag)")
