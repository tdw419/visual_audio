#!/usr/bin/env python3
"""Glyph native app demo — a complete worked example of the VA app pipeline.

Proves end-to-end (2026-09-14, during the 'glyph native apps?' discussion):
  assemble -> GlyphCPUv2 executes pixels directly -> speak.encode WAV
  -> speak.decode byte-identical -> boot the app FROM ITS OWN AUDIO
  -> identical behavior.

The app: countdown sum 5+4+3+2+1 = 15, printed via PRT (cpu.output).

ISA facts that cost three debug iterations to establish (see also skill
glyph-cpu-isa-quirks):
  * JMP/JZ/CALL args are (col,row) in INSTRUCTION CELLS: target index =
    row*W + col (mod the program's own layout). Off-by-one in the column
    silently targets the wrong instruction — the engine never faults.
  * GlyphAssemblerV2 has NO labels; the va_glyph_ollama_loop.py label
    resolver adds them upstream. At W=16 a one-row program makes every
    target a plain column index.
  * CMP r1 r2 writes 1/0 (equality flag) into r0; 'JZ' jumps when r0 != 0,
    i.e. JZ jumps on EQUALITY (name lies vs RISC-V; there is no JNZ).
  * PRT appends to cpu.output (a list) — it does not write stdout.

Gate: python3 experiments/glyph_native_app_demo.py -> exit 0 iff all four
legs PASS (direct exec, transport identity, audio boot, output equality).
"""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools import speak  # noqa: E402

W = 16
PROGRAM = """\
LDI r1 5
LDI r2 0
LDI r3 0
LDI r4 1
ADD r2 r1
SUB r1 r4
CMP r1 r3
JZ 9,0
JMP 4,0
PRT r2
HALT
"""


def run_app(arr):
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=W)
    buf = io.StringIO()
    with redirect_stdout(buf):
        cpu.run(np.ascontiguousarray(arr, dtype=np.uint8), max_instructions=500)
    om.close()
    return cpu.output


def main() -> int:
    lines = [l for l in PROGRAM.splitlines() if l.strip()]
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=W)
    om.close()
    print(f'1. assembled {img.shape}, {int((img.reshape(-1, 3).any(axis=1)).sum())} lit pixels')

    out_direct = run_app(img)
    print(f'2. executed from pixels: cpu.output={out_direct}')

    wav = '/tmp/glyph_app_demo.wav'
    raw = img.tobytes()
    speak.encode(raw, wav, use_ecc=True)
    back = speak.decode(wav, use_ecc=True)
    arr = np.frombuffer(back, dtype=np.uint8)
    identical = arr.size == img.size and bool((arr.reshape(img.shape) == img).all())
    print(f'3. spoken {len(raw)}B -> WAV -> decoded byte-identical: {identical}')
    if not identical:
        return 1

    out_audio = run_app(arr.reshape(img.shape))
    print(f'4. booted from audio:    cpu.output={out_audio}')

    ok = out_direct == out_audio == [15]
    print(f'VERDICT: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
