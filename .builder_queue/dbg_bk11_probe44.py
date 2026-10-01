"""BK-11 probe 44: live-trace the wc word-count loop for two_lines data.

The gate now fails ONLY on wc/two_lines: glyph words=2, native=3 ("aa
bb\\ncc\\n" -> words aa, bb, cc). Fixture char count is ALSO wrong (10 vs
real wc's 9) — that's a fixture-table fix. This probe isolates the
counter divergence: replicate wc's exact counting loop, emit one trace
char per input byte (letter emitted, or '.' when a boundary is seen)
via the bk11 buffered stdout, so we can see WHICH boundary the glyph
run missed. Expected trace for correct semantics: 'aa.bb.cc.'
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.coreutils_port import coreutils_tool_elf  # noqa: E402
from tests.test_gh23_libc_runtime import (  # noqa: E402
    _load_posix_program, GH23_STDOUT_WORDS)

PROBE_C = r"""
extern int write(int fd, const void *buf, unsigned len);
extern void exit(int code);
static char _buf[16];
static unsigned _n;
static void p44_out_ch(char c) {
    if (_n == 16) { while (_n < 16) _buf[_n++] = 0; write(1, _buf, 16); _n = 0; }
    _buf[_n++] = c;
}
static void p44_flush(void) {
    while (_n < 16) _buf[_n++] = 0;
    write(1, _buf, 16);
    _n = 0;
}
static const char *DATA = "aa bb\ncc\n";

void _start(void) {
    unsigned i;
    int in_word = 0;
    for (i = 0; i < 9; i++) {
        char c = DATA[i];
        if (c == '\n') { p44_out_ch('.'); in_word = 0; }
        else if (c == ' ') { p44_out_ch('.'); in_word = 0; }
        else if (!in_word) { in_word = 1; p44_out_ch('|'); }
        else p44_out_ch(c);
    }
    p44_flush();
    exit(0);
}
"""

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    src = tmp / "probe44.c"
    src.write_text(PROBE_C)
    elf = coreutils_tool_elf("wc", "one_line", tmp)  # unused, keep import alive
    # compile manually against the gh23 spatial libc like the port does
    import subprocess
    from tools.glyph_gpt import coreutils_port as cp
    libc_c = Path(cp.__file__).parent / "libc_github.c"
    # fall back: reuse the port's own compile helper by monkey-building
    # a fixture-shaped source through coreutils_tool_elf's machinery
    orig = cp._TOOL_SOURCES["wc"]
    cp._TOOL_SOURCES["wc"] = cp._LIBC_EXTERN + PROBE_C
    try:
        elf = cp.coreutils_tool_elf(
            "wc", "one_line", tmp)  # fixture seeds are ignored by the probe
    finally:
        cp._TOOL_SOURCES["wc"] = orig

    program = _load_posix_program(elf)
    out = tmp / "p44.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=200000, trace=True)
    print("halted:", receipt.get("halted"), "faulted:", receipt.get("faulted"))
    mem = receipt["memory"]
    got = b"".join(int(mem[w]).to_bytes(4, "little")
                   for w in GH23_STDOUT_WORDS).rstrip(b"\0")
    print("trace:", got)
    print("expected: aa|bb|cc. pattern -> b'aa. |bb|cc.' style, full: aa. |bb|cc.")
