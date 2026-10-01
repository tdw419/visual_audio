"""BK-11 root-cause probe 40: probe38's failing loop but the branch
target also writes a DIFFERENT letter: replace the 'S' branch body with
'MASK[MASK_N++] = 'Z'' (0x5A — the value GCC kept in t6/li t3 slot in
probe28's disasm). Then dump. If byte2 now holds 'A' again (0x41) while
'Z' (0x5A) is nowhere, the issue isn't which constant — some earlier
'letter' store lands in byte2 after the branch's store. KEY NEW ANGLE:
the write in the NOT-taken path is 'A'+i where i=2 gives 0x43 — but
memory had 0x41. GCC's actual code at 104: `sb t5,0(a5)` (letter 'S')
and at 130: `sb a3,0(a5)` (letter). NOTE probe28's failing program had
the 'A'+i letter path ALSO executing for the space byte? No: sb t5 only
on the 32-branch. The 'A' byte at position 2 suggests the LETTER store
used the LOOP-COUNTER value from the PREVIOUS iteration (stale a2/i?)
— GCC: `sb a3,0(a5)` where a3=a7+a2, a7=65, a2=i. If a2 is stale by one
iteration on the not-taken path after a taken branch earlier, byte2
could get 'A'+1=0x42... it's 0x41='A'+0. Dump this probe and also
'a2/a3 trail' — keep it simple: emit the letter chosen each iteration
AS WE STORE (both to MASK and to stdout). The live stream shows what
the loop thought it stored.
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
        bk11_out_ch(letter);          /* live stream: what we just stored */
        i++;
        if (i == LEN) break;
    }
    bk11_out_ch('|');
    /* then the readback */
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
    print("stream vs readback:", got, "(expect b'ABSDEF|ABSDEF|')")
