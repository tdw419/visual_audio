"""BK-11 probe 45: disassemble the wc/two_lines ELF and list which
 RV registers the text section touches — specifically x31 (t6),
 x28/x29/x30 (t3/t4/t5), to confirm DEFECT-17 (x31 identity-map to
 glyph r31 = HW stack pointer) fires in the real failing program.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt import coreutils_port as cp  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = cp.coreutils_tool_elf("wc", "two_lines", tmp)
    p = tmp / "wc.elf"
    p.write_bytes(elf)
    out = subprocess.run(
        ["riscv64-unknown-elf-objdump", "-d", str(p)],
        capture_output=True, check=True)
    text = out.stdout.decode()
    print(text)
