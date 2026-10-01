#!/usr/bin/env python3
"""Debug leg 3 (GREEN-leg demonstration, /tmp only, no engine landing):
with _COMMON prepended + wc_name seeded, does native wc compile, run on
the glyph engine, and match the host shim byte-exactly? Also head."""
import sys, tempfile, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "experiments"))

from tools.glyph_gpt.coreutils_port import _TOOL_SOURCES, _COMMON  # noqa: E402
from tests.test_gh23_libc_runtime import _load_posix_program, LIBC_C, SHIM_S  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
from tools.glyph_gpt.libc_runtime import GH23_WRITE_CURSOR, GH23_WRITE_RING_BASE  # noqa: E402


def run_native(verb, seeds, derived, aliases, data):
    body = _TOOL_SOURCES[verb]
    src_text = (_COMMON + "\n" + "\n".join(seeds) + "\n"
                + "\n".join(derived) + "\n" + "\n".join(aliases) + "\n" + body)
    with tempfile.TemporaryDirectory(prefix="b9g_") as td:
        tmp = Path(td)
        src = tmp / "tool.c"
        src.write_text(src_text)
        libc = tmp / "gh23_libc.c"
        libc.write_text(LIBC_C)
        shim = tmp / "shim.S"
        shim.write_text(SHIM_S)
        gcc = "riscv64-unknown-elf-gcc"
        objs = []
        for i, cfile in enumerate((src, libc)):
            obj = tmp / f"tool_{i}.o"
            proc = subprocess.run(
                [gcc, "-march=rv32i", "-mabi=ilp32", "-O1",
                 "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                 "-ffixed-x31", "-nostdlib", "-fno-builtin",
                 "-ffreestanding", "-w", "-c", str(cfile),
                 "-o", str(obj)], capture_output=True, timeout=60)
            if proc.returncode != 0:
                return f"COMPILE_FAIL:{proc.stderr.decode()[:300]}"
            objs.append(obj)
        elf = tmp / "tool.elf"
        proc = subprocess.run(
            [gcc, "-march=rv32i", "-mabi=ilp32",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
             "-ffixed-x31", "-nostdlib", "-Wl,-Ttext=0x0",
             "-Wl,-N", "-Wl,--entry=_start", "-w",
             *map(str, objs), str(shim), "-o", str(elf)],
            capture_output=True, timeout=60)
        if proc.returncode != 0:
            return f"LINK_FAIL:{proc.stderr.decode()[:300]}"
        program = _load_posix_program(elf.read_bytes())
        image = tmp / "shell_native.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=image,
                                  user_program=program)
        runner = GlyphRunner(image, ram_words=16384)
        receipt = runner.run(max_instructions=300000, trace=True)
        if not receipt.get("halted") or receipt.get("faulted"):
            return f"RUN_FAIL:halted={receipt.get('halted')} faulted={receipt.get('faulted')}"
        mem = receipt["memory"]
        cursor = mem[GH23_WRITE_CURSOR]
        raw = b"".join(int(mem[w]).to_bytes(4, "little")
                       for w in range(GH23_WRITE_RING_BASE, cursor))
        return raw.rstrip(b"\x00").decode("ascii", errors="replace").rstrip("\n")


import math  # noqa: E402

# wc on the 29-byte fixture, mirroring _shell_native's seed block + the
# TWO missing pieces: _COMMON preamble and the wc_name seed.
data = "hello world\nsecond line here\n"
seeds = [
    f'static const char *wc_data = "{data.replace(chr(10), chr(92)+"n")}";',
    'static const char *wc_name = "small.txt";',
]
derived = [f"static unsigned WC_LEN = {len(data)};"]
aliases = ["#define WC_DATA wc_data", "#define WC_NAME wc_name"]
native_wc = run_native("wc", seeds, derived, aliases, data)
print("native wc  ->", repr(native_wc))

# host shim reference (same math as glyph_l1_shell._wc single-file)
def host_wc(text, name):
    words = len(text.split())
    lines = text.count("\n")
    return f"{lines} {words} {len(text)} {name}"

ref = host_wc(data, "small.txt")
print("host shim  ->", repr(ref))

# wc on the LARGE file (309 bytes) — counters >= 10: does the 2-wide
# pad logic hold, and does the report stay within the ring?
data2 = "".join(f"line {i}\n" for i in range(40))
seeds2 = [
    f'static const char *wc_data = "{data2.replace(chr(10), chr(92)+"n")}";',
    'static const char *wc_name = "multi.txt";',
]
derived2 = [f"static unsigned WC_LEN = {len(data2)};"]
native_wc2 = run_native("wc", seeds2, derived2, aliases, data2)
print("native wc2 ->", repr(native_wc2))
ref2 = host_wc(data2, "multi.txt")
print("host shim2 ->", repr(ref2))

# head on a 401-byte file (stream > old 16-byte window)
data3 = (b"word " * 80).decode() + "\n"
seeds3 = [
    f'static const char *head_data = "{data3.replace(chr(10), chr(92)+"n")}";',
]
derived3 = ["static long HEAD_N = 1;"]
aliases3 = ["#define HEAD_DATA head_data", "#define HEAD_N head_n"]
native_head = run_native("head", seeds3, derived3, aliases3, data3)
print("native head->", repr(native_head[:60]))
