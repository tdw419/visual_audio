"""BK-11 root-cause probe 36: PROBE THE SB LOWERING ITSELF with a C
snippet mirroring MASK[MASK_N++]='S' (RMW byte store) reading back the
word. Actually simpler: directly test a byte store to a global, then
immediately re-read and hex it — no loop, no branches:

  MASK[0]='A'; MASK[1]='B'; MASK[2]='S'; hex-dump all three.

If the third byte reads back wrong AFTER these three plain RMW stores,
the SB lowering corrupts adjacent bytes in the same word (MASK word 0
holds bytes 0..3; three SBs hit the SAME word — the RMW may be losing
earlier bytes when a later SB in the same word runs).
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

static char MASK[8];

void _start(void) {
    MASK[0] = 'A';
    MASK[1] = 'B';
    MASK[2] = 'S';
    MASK[3] = 'D';
    for (int i = 0; i < 4; i++) {
        unsigned char b = (unsigned char)MASK[i];
        char hi = (b >> 4) & 15, lo = b & 15;
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
    print("4 SB same word:", got, "(expect b'41425344|')")
