#!/usr/bin/env python3
"""VA→Glyph closed loop demo: emit glyph image → Visual Audio codec → decode → execute.

The experiment Jericho asked for: use the Visual Audio byte codec (16-tone MFSK,
UPIC-synthesized) as the transport for a Glyph engine program. The program is
assembled to a pixel image, the raw image bytes are spoken to WAV, decoded back,
and executed on the Glyph CPU. Fidelity = execute-identity between direct and
audio-transported images.
"""
import sys
import numpy as np

sys.path.insert(0, "tools")
sys.path.insert(0, ".")

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools import speak  # noqa: E402

PROGRAM = [
    "LDI r5 0",    # counter
    "LDI r1 5",    # limit
    "CMP r5 r1",
    "JZ 0,1",      # -> HALT when counter==limit
    "PRT r5",
    "LDI r2 1",
    "ADD r5 r2",
    "JMP 2,0",     # -> CMP
    "HALT",
]

W = 8  # instructions per row


def build():
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(PROGRAM, width_instrs=W)
    return om, asm, img


def execute(image):
    om2 = OpcodeMapV2()
    cpu = GlyphCPUv2(om2, cols_instrs=W)
    cpu.run(np.ascontiguousarray(image, dtype=np.uint8), max_instructions=200)
    om2.close()
    return cpu


def main():
    om, asm, img = build()
    raw = img.tobytes()
    print(f"program      : {len(PROGRAM)} instrs -> image {img.shape} {img.dtype} ({len(raw)} bytes)")

    for ecc in (False, True):
        tag = "ecc" if ecc else "raw"
        wav = f"/tmp/va_glyph_{tag}.wav"
        speak.encode(raw, wav, use_ecc=ecc)
        back = speak.decode(wav, use_ecc=ecc)
        arr = np.frombuffer(back, dtype=np.uint8)
        ok = False
        if arr.size == img.size:
            ok = bool((arr.reshape(img.shape) == img).all())
        dur = speak.SYMBOL_SEC * (len(raw) * 2)  # 2 symbols per byte
        print(f"[{tag}] wav       : {wav}  roundtrip={'IDENTICAL' if ok else 'CORRUPT'}")
        if ok:
            cpu = execute(arr.reshape(img.shape))
            print(f"[{tag}] execution : {cpu.output}")
        else:
            print(f"[{tag}] execution : SKIPPED (image damaged in transport)")

    om.close()


if __name__ == "__main__":
    main()
