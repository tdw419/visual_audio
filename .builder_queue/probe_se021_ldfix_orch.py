"""SE021 probe 4: prove the LD-semantics _read_path fix flips both exec legs.

Monkeypatch ONLY (in this process; repo untouched): _read_path reads via the
engine's LD path (FS window -> _fs_pix_read; else RAM) instead of _mem_read,
matching the DEFECT-23-ROOT convention 'LD/ST=RAM for data' that the engine's
own SYSCALL 0x02 comment declares.
"""
import sys, os
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))

import numpy as np, tempfile
from tools.glyph_isa_v2 import (GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2,
                                INPUT_LEN_ADDR, INPUT_CURSOR_ADDR, INPUT_DATA_ADDR)
import tools.glyph_isa_v2 as G
from experiments.glyph_interactive_shell import build_exec_shell, repl, W

tmp = Path(tempfile.mkdtemp(prefix="se021_probe4_"))
child = tmp / "child.glyph.npy"
om = OpcodeMapV2()
img = GlyphAssemblerV2(om).assemble([f"LDI r5 {b}" for b in b"hello"] and
                                    [x for b in b"hello" for x in (f"LDI r5 {b}", "PRT r5")] + ["HALT"],
                                    width_instrs=8)
om.close()
np.save(child, img)

out_path = tmp / "child_out.txt"
runner = tmp / "glyph_child_runner.py"
runner.write_text((REPO / "tools" / "glyph_child_runner.py").read_text())
os.chmod(runner, 0o755)
os.environ["GLYPH_RUN_ALLOW"] = str(runner)
os.environ["GLYPH_REPO"] = str(REPO)
os.chdir(tmp)

# --- the hypothesized fix, applied in-process only -------------------------
cpu_inst = G.GlyphCPUv2
def _read_path_fixed(self, path_addr, image):
    buf = bytearray()
    for i in range(4096):
        if self.fs_pix_enabled and 1024 <= path_addr + i < 1280:
            b = self._fs_pix_read(image, path_addr + i) & 0xFF
        elif 0 <= path_addr + i < len(self.memory):
            b = self.memory[path_addr + i] & 0xFF
        else:
            b = 0
        if b == 0:
            break
        buf.append(b)
    return os.fsdecode(bytes(buf))

orig = G.GlyphCPUv2._handle_syscall
def patched(self, syscall_num, image, imm=0):
    # rebind _read_path inside _handle_syscall's closure is not possible;
    # instead patch G._read_path is not module-level... check
    return orig(self, syscall_num, image, imm)

# _read_path is a nested function inside _handle_syscall — can't monkeypatch
# directly. Simplest faithful proxy: run the REAL test path but swap _mem_read
# on the instance for an LD-semantics shim during the syscall. _read_path is
# the ONLY _mem_read user among path syscalls (0x03/0x04/0x07/0x12 all call
# _read_path; FILE_WRITE/READ do their data via _mem_write/_mem_read though).
# So: patch instance._mem_read to LD semantics for out-of-window addrs only.
class LdMemReadCPU(G.GlyphCPUv2):
    def _mem_read(self, image, addr):
        if self.fs_pix_enabled and 1024 <= addr < 1280:
            return self._fs_pix_read(image, addr)
        if 0 <= addr < len(self.memory):
            return self.memory[addr]
        return 0

# repl() constructs GlyphCPUv2 directly — subclass via monkeypatching the name
G2 = G
orig_repl_cpu = G2.GlyphCPUv2

image = build_exec_shell(
    write_path="w.dat", audio_path="a.wav",
    runner_path=str(runner), child_path=str(child), child_out_path=str(out_path),
)

# run the 'x' turn on the patched class manually (mirror repl/run_turn)
cpu = LdMemReadCPU(OpcodeMapV2(), cols_instrs=W, fs_pix_enabled=True)
cpu.memory = [0] * 16384
data = b"x"
cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
for i, b in enumerate(data):
    cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
cpu.pc = (0, 0); cpu.registers = [0]*32; cpu.output = []
cpu.running = True; cpu.halted = False; cpu.faulted = False

import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cpu.run(image, max_instructions=2048)
out = bytes(cpu.output)
print("with LD-semantics _mem_read, 'x' turn output:", out)
print("rc leg expectation: ['hello'] ->", "MATCH" if out == b"hello" else "MISMATCH")
log = buf.getvalue()
for line in log.splitlines():
    if "RUN2" in line or "CHILD_RUNNER" in line:
        print("LOG:", line)
