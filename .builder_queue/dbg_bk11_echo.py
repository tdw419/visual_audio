"""One-off BK-11 debug: reproduce the echo duplicate-label IR failure."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.coreutils_port import coreutils_tool_elf  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    try:
        elf = coreutils_tool_elf("echo", "one_word", tmp)
    except Exception as e:
        print("ELF BUILD FAILED:", e)
        sys.exit(1)
    p = tmp / "echo.elf"
    p.write_bytes(elf)
    out = subprocess.run(["riscv64-unknown-elf-readelf", "-s", str(p)],
                         capture_output=True)
    print(out.stdout.decode())
