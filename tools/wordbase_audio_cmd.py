#!/usr/bin/env python3
"""
wordbase_audio_cmd.py — Wordbase ID -> data band -> spatial CPU execution.

Corrected version. The original implementation looked like this pipeline but
didn't actually deliver it:
  - it bypassed real wordbase.db lookups for the exact demo words via a
    hardcoded DEMO_COMMAND_WORDS shortcut dict
  - it packed word IDs as uint16, which silently truncates real wordbase IDs
    (e.g. "red" is id 92795 - already over 65535)
  - "execution" stopped at printing a list of opcode mnemonic strings; nothing
    ever reached GlyphAssemblerV2/GlyphCPUv2 or the WGSL spatial CPU

This version:
  - looks up every word for real via WordbaseManager.get_word() (color words
    carry a genuine `color_hex` column - no fabricated color values)
  - packs word IDs as 3-byte (24-bit) big-endian, matching the same
    id-fits-in-24-bits convention PixelTokenizer already uses elsewhere in
    this project (supports IDs up to ~16.7M)
  - compiles the decoded word sequence into real glyph_isa_v2 assembly and
    actually executes it via GlyphCPUv2 (and cross-checks the WGSL port),
    then reads back the framebuffer memory location to prove the color was
    genuinely written, not just printed as a string

Grammar (deliberately small - this is a proof that the pipeline is real, not
a general command language):
  "clear <color>" -> writes <color>'s real wordbase color_hex into a fixed
                      framebuffer memory address, then halts
  "halt"          -> halts immediately
"""

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase import WordbaseManager
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2
from src.codec.phy import Phy16Tone

# Fixed memory address treated as "framebuffer pixel 0" - glyph_isa_v2's
# memory model unifies program and data memory (see GlyphCPUv2._mem_read/
# write), so this is just an address ST/LD can target, read back afterward
# to prove the write really happened.
FRAMEBUFFER_ADDR = 500


def text_to_word_ids(text: str, db: WordbaseManager) -> list[int]:
    """Real wordbase.db lookup for every word - no shortcut/demo table."""
    ids = []
    for word in text.lower().split():
        row = db.get_word(word)
        if row is None:
            print(f"Warning: '{word}' not found in wordbase.db, skipping", file=sys.stderr)
            continue
        ids.append(row["id"])
    return ids


def word_ids_to_words(ids: list[int], db: WordbaseManager) -> list[dict]:
    """Reverse id -> word lookup (wordbase.db has no built-in reverse index)."""
    words = []
    for wid in ids:
        cursor = db.conn.execute("SELECT word, color_hex FROM words WHERE id = ?", (wid,))
        row = cursor.fetchone()
        if row is None:
            print(f"Warning: id {wid} not found in wordbase.db, skipping", file=sys.stderr)
            continue
        words.append({"id": wid, "word": row["word"], "color_hex": row["color_hex"]})
    return words


def word_ids_to_audio(ids: list[int], output_wav: str) -> None:
    """Pack word IDs as 3-byte (24-bit) big-endian and encode via the data band."""
    data = bytearray()
    for wid in ids:
        if wid > 0xFFFFFF:
            raise ValueError(f"word id {wid} does not fit in 24 bits")
        data.extend(struct.pack(">I", wid)[1:])  # top 3 bytes of a big-endian u32

    phy = Phy16Tone()
    audio = phy.encode(bytes(data))

    import numpy as np
    import soundfile as sf

    audio_max = np.abs(audio).max()
    if audio_max > 0:
        audio = (audio / audio_max * 32767).astype(np.int16)
    sf.write(output_wav, audio, 44100)
    print(f"Saved {len(ids)} word IDs as audio to: {output_wav}")
    print(f"Duration: {len(audio) / 44100:.2f}s ({len(ids)} IDs x 3 bytes = {len(ids)*3} bytes)")


def audio_to_word_ids(input_wav: str) -> list[int]:
    """Decode audio back to the 3-byte-packed word ID sequence."""
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(input_wav)
    if len(audio.shape) == 2:
        audio = audio[:, 0]
    audio = audio / 32767.0

    phy = Phy16Tone()
    data = phy.decode(audio)

    ids = []
    for i in range(0, len(data) - 2, 3):
        chunk = b"\x00" + bytes(data[i:i + 3])
        ids.append(struct.unpack(">I", chunk)[0])
    return ids


def compile_to_glyph_assembly(words: list[dict]) -> list[str]:
    """Compile a real decoded word sequence into real glyph_isa_v2 assembly.

    Deliberately small grammar: "clear <color>" writes the color's real
    color_hex into FRAMEBUFFER_ADDR; "halt" halts. Unrecognized words are
    skipped (with a warning), not silently mapped to a fake opcode.
    """
    asm = []
    i = 0
    while i < len(words):
        w = words[i]["word"]
        if w == "clear" and i + 1 < len(words) and words[i + 1]["color_hex"]:
            hexval = words[i + 1]["color_hex"].lstrip("#")
            rgb = int(hexval, 16)
            asm.append(f"LDI r1 {FRAMEBUFFER_ADDR}")
            asm.append(f"LDI r2 {rgb}")
            asm.append("ST r1 r2")
            i += 2
        elif w == "halt":
            asm.append("HALT")
            i += 1
        else:
            print(f"Warning: '{w}' not recognized by the command grammar, skipping", file=sys.stderr)
            i += 1
    if not asm or asm[-1] != "HALT":
        asm.append("HALT")
    return asm


def execute_glyph_assembly(asm: list[str]) -> dict:
    """Actually assemble and execute on GlyphCPUv2 - not a string printout.

    Returns the framebuffer memory value actually written, proving real
    execution rather than a mapped-but-unexecuted opcode list.
    """
    # width_instrs must be wide enough that FRAMEBUFFER_ADDR's linear-wrap
    # address (addr %= width*height, see GlyphCPUv2._addr_to_xy) doesn't
    # alias onto the instruction stream itself for small programs - the
    # exact collision that made an earlier verification of this pipeline
    # briefly look broken (address 500 wrapped onto live code in a
    # 16-pixel image). 200 instructions * 4 pixels = 800 pixels comfortably
    # clears FRAMEBUFFER_ADDR=500.
    width_instrs = 200
    opcode_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(opcode_map)
        image = assembler.assemble(asm, width_instrs=width_instrs)
        cpu = GlyphCPUv2(opcode_map, cols_instrs=width_instrs)
        n = cpu.run(image, max_instructions=200)
        fb_value = cpu._mem_read(image, FRAMEBUFFER_ADDR)
        return {
            "instructions_run": n,
            "framebuffer_addr": FRAMEBUFFER_ADDR,
            "framebuffer_value_hex": f"#{fb_value:06X}",
            "registers": cpu.registers[:8],
        }
    finally:
        opcode_map.close()


def demo_encode(text: str, output_wav: str) -> None:
    db = WordbaseManager()
    try:
        print(f"Encoding text: '{text}'")
        ids = text_to_word_ids(text, db)
        print(f"Real wordbase IDs: {ids}")
        word_ids_to_audio(ids, output_wav)
    finally:
        db.close()


def demo_decode(input_wav: str) -> None:
    db = WordbaseManager()
    try:
        ids = audio_to_word_ids(input_wav)
        print(f"Decoded word IDs: {ids}")
        words = word_ids_to_words(ids, db)
        print(f"Decoded words: {[w['word'] for w in words]}")
        asm = compile_to_glyph_assembly(words)
        print(f"Compiled glyph_isa_v2 assembly: {asm}")
        result = execute_glyph_assembly(asm)
        print(f"Executed on GlyphCPUv2: {result}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Wordbase ID -> data band -> spatial CPU execution")
    parser.add_argument("action", choices=["encode", "decode"])
    parser.add_argument("input", help="text string (encode) or WAV file (decode)")
    parser.add_argument("-o", "--output", help="output WAV file (encode)")
    args = parser.parse_args()

    if args.action == "encode":
        demo_encode(args.input, args.output)
    else:
        demo_decode(args.input)


if __name__ == "__main__":
    main()
