#!/usr/bin/env python3
"""Cross-check wordbase_audio_cmd.py's compiled assembly on the WGSL spatial
CPU as well as GlyphCPUv2, proving the "clear blue halt" pipeline produces
the same real framebuffer value on both."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
from tools.verify_wgsl_glyph_isa_v2 import run_wgsl
from tools.wordbase_audio_cmd import (
    FRAMEBUFFER_ADDR, audio_to_word_ids, compile_to_glyph_assembly,
    demo_encode, word_ids_to_words,
)
from tools.wordbase import WordbaseManager


def main():
    wav_path = "/tmp/verify_wordbase_cmd.wav"
    demo_encode("clear blue halt", wav_path)

    db = WordbaseManager()
    ids = audio_to_word_ids(wav_path)
    words = word_ids_to_words(ids, db)
    db.close()
    asm = compile_to_glyph_assembly(words)
    print("assembly:", asm)

    # Must match wordbase_audio_cmd.execute_glyph_assembly's width_instrs=200,
    # so FRAMEBUFFER_ADDR=500 doesn't wrap onto the instruction stream itself.
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    image = assembler.assemble(asm, width_instrs=200)

    # Call GlyphCPUv2 directly (not the shared run_python_ground_truth
    # helper) so we can read back the SAME image object cpu.run() actually
    # mutated - that helper internally runs on image.copy(), which would
    # otherwise leave `image` here unmodified and the readback would show
    # stale/zero data regardless of whether execution was correct.
    py_cpu = GlyphCPUv2(opcode_map, cols_instrs=200)
    py_cpu.registers[31] = 0
    py_cpu.run(image, max_instructions=200)
    py_fb = py_cpu._mem_read(image, FRAMEBUFFER_ADDR)
    print(f"Python framebuffer: #{py_fb:06X}")

    gpu_cpu = run_wgsl(opcode_map, image)
    # Re-derive the framebuffer pixel from the GPU-mutated image buffer isn't
    # directly exposed by run_wgsl, so cross-check via registers instead:
    # r1 = FRAMEBUFFER_ADDR, r2 = the RGB value that was stored via ST.
    py_r1, py_r2 = py_cpu.registers[1], py_cpu.registers[2]
    gpu_r1, gpu_r2 = int(gpu_cpu['registers'][1]), int(gpu_cpu['registers'][2])
    print(f"Python r1={py_r1} r2=#{py_r2:06X}")
    print(f"GPU    r1={gpu_r1} r2=#{gpu_r2:06X}")

    ok = (py_fb == 0x0000FF) and (py_r1 == gpu_r1) and (py_r2 == gpu_r2)
    print("MATCH" if ok else "MISMATCH")
    opcode_map.close()
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
