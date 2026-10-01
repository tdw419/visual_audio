"""BK-11 wc debug 2: run the SAME image twice, dump stdout window + key
data words each time; also verify transpiler determinism on the IR text."""
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
    _load_posix_program, GH23_STDOUT_WORDS, GH23_EXIT_CODE)

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    for trial in range(2):
        elf = coreutils_tool_elf("wc", "two_lines", tmp)
        program = _load_posix_program(elf)
        out = tmp / f"wc_trial{trial}.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                  user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=200000, trace=True)
        mem = receipt["memory"]
        got = b"".join(int(mem[w]).to_bytes(4, "little")
                       for w in GH23_STDOUT_WORDS).rstrip(b"\0")
        print(f"--- trial {trial} ---")
        print("halted:", receipt["halted"], "faulted:", receipt["faulted"])
        print("stdout window bytes:", got)
        print("exit code:", mem[GH23_EXIT_CODE])
        # data words: the IR `lines` dump is the canonical representation
        for line in program.splitlines():
            s = line.strip().lstrip(";").strip()
            if s.startswith("memory["):
                try:
                    addr = int(s[7:s.index("]")])
                except ValueError:
                    continue
                if 1500 <= addr <= 1520:
                    print(s)
        # IR address literals near the data base
        import re
        hits = sorted(set(int(m) for m in re.findall(r"\b(17[0-9]{2})\b",
                                                     program)))
        print("17xx literals in IR:", hits[:20])
