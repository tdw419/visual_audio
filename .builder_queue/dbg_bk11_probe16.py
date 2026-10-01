"""BK-11 root-cause probe 16: space-count minus-one is EXACTLY +1.
Every case: glyph spaces = real + 1. Test whether the +1 comes from the
loop's exit byte: read DATA[LEN] (the NUL terminator) — does the last
iteration see the NUL (0) or a stale space byte? Emit the hex of what
the loop body sees at i == LEN-1 and i == LEN (guard removed)."""
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

static const char DATA[] = "ab cd";   /* NO trailing newline; LEN=5 */
static unsigned LEN = 5;

static void out_hex(unsigned v) {
    char lo = v & 15;
    char hi = (v >> 4) & 15;
    bk11_out_ch(hi < 10 ? '0' + hi : 'A' + hi - 10);
    bk11_out_ch(lo < 10 ? '0' + lo : 'A' + lo - 10);
    bk11_out_ch(' ');
}

void _start(void) {
    unsigned spaces = 0;
    unsigned i;
    /* loop WITH the guard, but also read DATA[LEN] explicitly after */
    for (i = 0; i < LEN; i++) {
        char c = DATA[i];
        if (c == ' ') spaces++;
    }
    bk11_out_ch('S');
    bk11_out_ch('0' + (char)spaces);
    bk11_out_ch(' ');
    /* what does DATA[LEN] read as? (NUL expected = 00) */
    out_hex((unsigned)(unsigned char)DATA[LEN]);
    out_hex((unsigned)(unsigned char)DATA[LEN + 1]);
    out_hex((unsigned)(unsigned char)DATA[LEN + 2]);
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
    p = subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i",
                        "-mabi=ilp32", "-nostdlib", "-Wl,-Ttext=0x0",
                        "-Wl,--entry=_start", "-w", *map(str, objs),
                        str(shim), "-o", str(elf)], capture_output=True)
    if p.returncode != 0:
        print("LINK FAIL:", p.stderr.decode())
        sys.exit(1)
    from tools.rv64i_to_glyph import parse_elf_data_sections
    for addr, blob in parse_elf_data_sections(elf.read_bytes()):
        print("data section:", hex(addr), blob.hex(), repr(blob))
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
    print("expect: S1 00 00 00 |")
