"""BK-11 wc debug 3: where does the wc data land, and does the loop read
it right? Dump IR data-seed lines + the transpiled loads around them."""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.coreutils_port import coreutils_tool_elf  # noqa: E402
from tests.test_gh23_libc_runtime import _load_posix_program  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    program = _load_posix_program(elf)
    lines = program.splitlines()
    print("total IR lines:", len(lines))
    # all data-seed lines
    seeds = [ln for ln in lines if re.search(r"memory\[\d+\]\s*=", ln)]
    print("seed-style lines:", len(seeds))
    for ln in seeds[:40]:
        print("  ", ln.strip())
    # find the loop: occurrences of literal 1720 (data base)
    for i, ln in enumerate(lines):
        if "1720" in ln:
            print(f"line {i}: {ln.strip()}")
