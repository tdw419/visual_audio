"""
Proves the real spatial ISA (GlyphCPUv2, tools/glyph_isa_v2.py) can read a word's
color directly out of a wordbook bitmap via LD/LDI/PRT — no Python-side dict lookup,
no host CPU touching the word->color mapping at run time.

PROVENANCE (RULING_standing_authorization.md § Ticket rulings, 2026-09-13, Option (a)):
the tracked db/wordbase.db is the colour authority. The expected colour is QUERIED
LIVE from the DB at test time — historical hash constants are never frozen here — and
the bake is a scratch fixture built in tmp_path. No committed wordbook.png binary.
DB churn (e.g. ba13857) is bookkeeping, not an ISA defect: the claim under test is
"the spatial CPU reads a pixel colour out of the bitmap by address", not "the DB
holds any particular colour".
"""
import os
import sqlite3

import numpy as np
import pytest
from PIL import Image

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_REPO_ROOT, "db", "wordbase.db")
WORDBOOK_WIDTH = 4096
WORDBOOK_HEIGHT = 32

TEST_WORDS = [
    ("hello", 50448),
    ("world", 124061),
]


def _db_color(word_id):
    """Live colour provenance: query the tracked DB (RULING Option (a))."""
    if not os.path.exists(DB_PATH):
        pytest.skip("db/wordbase.db absent in this checkout (environment, not an ISA defect)")
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT color_hex FROM words WHERE id = ?", (word_id,)).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        pytest.skip(f"wordbase.db holds no colour for id {word_id} (DB churn is not an ISA defect)")
    hex_val = str(row[0]).strip().lstrip("#")
    assert len(hex_val) == 6, f"malformed colour in DB for id {word_id}: {row[0]!r}"
    return hex_val


def _bake_wordbook_rgb(entries):
    """Scratch bake, layout contract of tools/build_wordbook.py:
    pixel (id % WIDTH, id // WIDTH) holds the word's colour as RGB."""
    arr = np.zeros((WORDBOOK_HEIGHT, WORDBOOK_WIDTH, 3), dtype=np.uint8)
    for _w, wid, hex_val in entries:
        arr[wid // WORDBOOK_WIDTH, wid % WORDBOOK_WIDTH] = [
            int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        ]
    return arr


@pytest.mark.parametrize("word,word_id", TEST_WORDS)
def test_spatial_cpu_reads_word_color_from_wordbook(word, word_id, tmp_path):
    expected_hex = _db_color(word_id)
    wordbook = _bake_wordbook_rgb([(word, word_id, expected_hex)])  # (32, 4096, 3)
    probe_wrong_bake = os.environ.get("WB_PROBE_WRONG_BAKE") == "1"
    if probe_wrong_bake:
        wordbook = _bake_wordbook_rgb([(word, word_id, "0182FE")])
    instr_rows = 1  # program fits in one 4096-wide row (few instructions)

    combined = np.zeros((instr_rows + wordbook.shape[0], WORDBOOK_WIDTH, 3), dtype=np.uint8)
    combined[instr_rows:, :, :] = wordbook

    wb_x = word_id % WORDBOOK_WIDTH
    wb_y = word_id // WORDBOOK_WIDTH
    addr = (instr_rows + wb_y) * WORDBOOK_WIDTH + wb_x

    opcode_map = OpcodeMapV2()
    try:
        program = [
            f"LDI r1 {addr}",  # r1 = address of the word's pixel in the combined image
            "LD r2 r1",        # r2 = mem[r1]  (24-bit RGB packed as one value)
            "PRT r2",
            "HALT",
        ]
        assembler = GlyphAssemblerV2(opcode_map)
        # width_instrs chosen so INSTR_WIDTH(4) * cols == WORDBOOK_WIDTH,
        # keeping the instruction row and the wordbook rows the same width.
        prog_image = assembler.assemble(program, width_instrs=WORDBOOK_WIDTH // 4)
        assert prog_image.shape[1] == WORDBOOK_WIDTH

        combined[:instr_rows, :, :] = prog_image[:instr_rows, :, :]

        cpu = GlyphCPUv2(opcode_map, cols_instrs=WORDBOOK_WIDTH // 4)
        cpu.run(combined, max_instructions=100)

        expected_val = int(expected_hex, 16)
        assert cpu.output == [expected_val], (
            f"expected GPU-side CPU to read {word}'s DB colour #{expected_hex} "
            f"({expected_val}) from the baked bitmap, got {cpu.output}"
        )
    finally:
        opcode_map.close()
