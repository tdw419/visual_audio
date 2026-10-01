"""BK-11 wc debug: inspect the compiled C text and seeded data words."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")

from tools.glyph_gpt.coreutils_port import coreutils_tool_elf  # noqa: E402
from tools.rv64i_to_glyph import parse_elf_data_sections  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = coreutils_tool_elf("wc", "two_lines", tmp)
    p = tmp / "wc.elf"
    p.write_bytes(elf)
    print("=== data sections (addr, hex, ascii) ===")
    for addr, data in parse_elf_data_sections(p.read_bytes()):
        print(hex(addr), data.hex(), repr(data))
    print("=== disassembly of wc digit loop (objdump) ===")
    out = subprocess.run(
        ["riscv64-unknown-elf-objdump", "-d", "--no-show-raw-insn",
         str(p)], capture_output=True)
    text = out.stdout.decode()
    keep = False
    for line in text.splitlines():
        if "<_start>:" in line:
            keep = True
        if keep:
            print(line)
