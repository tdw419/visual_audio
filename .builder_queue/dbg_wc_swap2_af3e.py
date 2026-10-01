#!/usr/bin/env python3
"""Debug leg 2: instrument INSIDE the wc compile chain to find which
loud-refusal site fires. Replicates glyph_l1_shell._shell_native for
verb=wc verbatim, but prints the compile/transpile/run intermediates."""
import sys, tempfile, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "experiments"))

from tools.glyph_gpt.coreutils_port import _TOOL_SOURCES  # noqa: E402
from tests.test_gh23_libc_runtime import _load_posix_program, LIBC_C, SHIM_S  # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image  # noqa: E402
from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402
import numpy as np  # noqa: E402

data = "hello world\nsecond line here\n"
name = "small.txt"
data_len = len(data)
seeds = [f'static const char *wc_data = "{data.replace(chr(10), chr(92)+"n")}";']
derived = [f"static unsigned WC_LEN = {data_len};"]
aliases = ["#define WC_DATA wc_data", "#define WC_NAME wc_name"]
body = _TOOL_SOURCES["wc"]
print("=== generated wc source ===")
src_text = "\n".join(seeds + derived + aliases) + "\n" + body
print(src_text[:1200])

with tempfile.TemporaryDirectory(prefix="b9d2_") as td:
    tmp = Path(td)
    src = tmp / "tool.c"
    src.write_text(src_text)
    libc = tmp / "gh23_libc.c"
    libc.write_text(LIBC_C)
    shim = tmp / "shim.S"
    shim.write_text(SHIM_S)
    gcc = "riscv64-unknown-elf-gcc"
    for i, cfile in enumerate((src, libc)):
        obj = tmp / f"tool_{i}.o"
        proc = subprocess.run(
            [gcc, "-march=rv32i", "-mabi=ilp32", "-O1",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
             "-ffixed-x31", "-nostdlib", "-fno-builtin",
             "-ffreestanding", "-w", "-c", str(cfile),
             "-o", str(obj)], capture_output=True, timeout=60)
        print(f"compile {cfile.name}: rc={proc.returncode}")
        if proc.returncode != 0:
            print(proc.stderr.decode()[:2000])
            raise SystemExit(0)
    elf = tmp / "tool.elf"
    proc = subprocess.run(
        [gcc, "-march=rv32i", "-mabi=ilp32",
         "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
         "-ffixed-x31", "-nostdlib", "-Wl,-Ttext=0x0",
         "-Wl,-N", "-Wl,--entry=_start", "-w",
         *map(str, [tmp / "tool_0.o", tmp / "tool_1.o", shim]), "-o", str(elf)],
        capture_output=True, timeout=60)
    print(f"link: rc={proc.returncode}")
    if proc.returncode != 0:
        print(proc.stderr.decode()[:2000])
        raise SystemExit(0)
    program = _load_posix_program(elf.read_bytes())
    print("load_posix_program OK")
    image = tmp / "shell_native.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=image,
                              user_program=program)
    runner = GlyphRunner(image, ram_words=16384)
    receipt = runner.run(max_instructions=300000, trace=True)
    print("halted:", receipt.get("halted"), "faulted:", receipt.get("faulted"),
          "exit:", receipt.get("exit_code"), "steps:", receipt.get("steps"))
    from tools.glyph_gpt.libc_runtime import GH23_WRITE_CURSOR, GH23_WRITE_RING_BASE
    mem = receipt["memory"]
    print("write cursor word:", mem[GH23_WRITE_CURSOR],
          "| ring base:", GH23_WRITE_RING_BASE)
    print("exit-code word (722):", mem[722])
