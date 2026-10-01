"""SE021 probe 3 (decisive): ST-stamped paths land in RAM; _read_path reads pixels."""
import sys, os
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))

import numpy as np, tempfile, io, contextlib, re
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2, INPUT_LEN_ADDR, INPUT_CURSOR_ADDR, INPUT_DATA_ADDR
from experiments.glyph_interactive_shell import build_exec_shell, W

tmp = Path(tempfile.mkdtemp(prefix="se021_probe3_"))
child = tmp / "child.glyph.npy"
om = OpcodeMapV2()
img = GlyphAssemblerV2(om).assemble(["LDI r5 72", "PRT r5", "HALT"], width_instrs=8)
om.close()
np.save(child, img)

out_path = tmp / "child_out.txt"
runner = tmp / "glyph_child_runner.py"
runner.write_text((REPO / "tools" / "glyph_child_runner.py").read_text())
os.chmod(runner, 0o755)

os.chdir(tmp)
image = build_exec_shell(
    write_path="w.dat", audio_path="a.wav",
    runner_path=str(runner), child_path=str(child), child_out_path=str(out_path),
)

cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W, fs_pix_enabled=True)
cpu.memory = [0] * 16384
print("mode at reset:", cpu.mode, "(MODE_SUPER=0, MODE_USER=1)")

data = b"x"
cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
for i, b in enumerate(data):
    cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
cpu.pc = (0, 0); cpu.registers = [0]*32; cpu.output = []
cpu.running = True; cpu.halted = False; cpu.faulted = False

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cpu.run(image, max_instructions=2048)
log = buf.getvalue()
m = re.search(r"at path at (\d+)", log)
target = int(m.group(1))

def ram_bytes(addr, n=64):
    out = bytearray()
    for i in range(n):
        w = cpu.memory[addr + i]
        out.append(w & 0xFF)
        if w & 0xFF == 0:
            break
    return bytes(out)

def pix_bytes(addr, n=64):
    out = bytearray()
    for i in range(n):
        c = cpu._mem_read(image, addr + i) & 0xFF
        out.append(c)
        if c == 0:
            break
    return bytes(out)

print(f"RUN2 was handed path_addr={target}")
print(f"  RAM  view (LD/ST space): {ram_bytes(target)!r}")
print(f"  PIX  view (_mem_read):   {pix_bytes(target)!r}")
print(f"  expected runner path:    {str(runner).encode()!r}")

# and confirm the in-window SE020 paths DID round-trip (pixels), for contrast
def find_in_ram(needle):
    for a in range(0, 16384 - len(needle)):
        if bytes(b & 0xFF for b in cpu.memory[a:a+len(needle)]) == needle:
            return a
    return None

rb = str(runner).encode() + b"\0"
loc = find_in_ram(rb)
print("runner path found in RAM at word:", loc)
