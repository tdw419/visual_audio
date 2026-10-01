"""
Test suite for tools/wordbase_audio_cmd.py — real wordbase.db lookup ->
data band audio -> real glyph_isa_v2 execution.

This replaces an earlier version of both the tool and its tests that only
*looked* like this pipeline: word IDs came from a hardcoded shortcut dict
(not real wordbase.db lookups), were packed as uint16 (silently truncating
real wordbase IDs, many of which exceed 65535), and "execution" stopped at
printing a list of opcode mnemonic strings without ever reaching
GlyphAssemblerV2/GlyphCPUv2. These tests exercise the corrected version:
real lookups, 24-bit-safe packing, and actual execution with a readable
memory location proving the result.
"""

import sys
from pathlib import Path

import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase_audio_cmd import (
    FRAMEBUFFER_ADDR,
    audio_to_word_ids,
    compile_to_glyph_assembly,
    execute_glyph_assembly,
    text_to_word_ids,
    word_ids_to_audio,
    word_ids_to_words,
)
from tools.wordbase import WordbaseManager


@pytest.fixture(scope="module")
def db():
    manager = WordbaseManager()
    yield manager
    manager.close()


class TestTextToWordIDs:
    """text -> real wordbase.db ID lookup (no shortcut/demo table)."""

    def test_real_words_get_their_actual_wordbase_id(self, db):
        ids = text_to_word_ids("clear blue halt", db)
        assert len(ids) == 3
        # Must match live wordbase.db, not a hardcoded constant.
        assert ids[0] == db.get_word("clear")["id"]
        assert ids[1] == db.get_word("blue")["id"]
        assert ids[2] == db.get_word("halt")["id"]

    def test_ids_exceed_uint16_range(self, db):
        # Confirms the fix: real wordbase IDs are NOT guaranteed to fit in
        # 16 bits (the original bug silently truncated these).
        ids = text_to_word_ids("red", db)
        assert ids[0] > 0xFFFF

    def test_case_insensitive(self, db):
        assert text_to_word_ids("BLUE", db) == text_to_word_ids("blue", db)

    def test_unknown_word_is_skipped_not_faked(self, db, capsys):
        ids = text_to_word_ids("clear zzznotarealword blue", db)
        assert len(ids) == 2  # the unknown word is skipped, not given a fake id
        captured = capsys.readouterr()
        assert "not found" in captured.err


class TestAudioRoundTrip:
    """word IDs <-> 24-bit-packed data band audio."""

    def test_roundtrip_preserves_large_ids(self, tmp_path):
        # 92795 ("red"'s real id) doesn't fit in uint16 - this is exactly
        # the case the original implementation silently corrupted.
        ids = [20782, 92795, 48445]
        wav_path = str(tmp_path / "roundtrip.wav")
        word_ids_to_audio(ids, wav_path)
        assert Path(wav_path).exists()
        assert audio_to_word_ids(wav_path) == ids

    def test_id_over_24_bits_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            word_ids_to_audio([0x1000000], str(tmp_path / "bad.wav"))

    def test_duration_scales_with_id_count(self, tmp_path):
        p1 = str(tmp_path / "one.wav")
        p3 = str(tmp_path / "three.wav")
        word_ids_to_audio([20782], p1)
        word_ids_to_audio([20782, 92795, 48445], p3)
        d1 = len(sf.read(p1)[0]) / 44100
        d3 = len(sf.read(p3)[0]) / 44100
        assert 2.5 < d3 / d1 < 3.5


class TestWordIdsToWords:
    """Reverse id -> word lookup (wordbase.db has no built-in reverse index)."""

    def test_reverse_lookup_matches_forward(self, db):
        ids = text_to_word_ids("clear blue halt", db)
        words = word_ids_to_words(ids, db)
        assert [w["word"] for w in words] == ["clear", "blue", "halt"]
        # color_hex must be the real value, not a fabricated one.
        assert words[1]["color_hex"] == db.get_word("blue")["color_hex"]


class TestCompileAndExecute:
    """The actual proof: compiled assembly really executes on GlyphCPUv2,
    with a readable memory location, not a printed opcode string."""

    @pytest.mark.parametrize("color,expected_hex", [
        ("blue", "#0000FF"),
        ("red", "#FF0000"),
        ("green", "#008000"),
    ])
    def test_clear_color_writes_real_wordbase_color_to_framebuffer(self, db, color, expected_hex):
        words = word_ids_to_words(text_to_word_ids(f"clear {color} halt", db), db)
        asm = compile_to_glyph_assembly(words)
        result = execute_glyph_assembly(asm)
        assert result["framebuffer_value_hex"] == expected_hex
        assert result["framebuffer_addr"] == FRAMEBUFFER_ADDR
        assert result["instructions_run"] == 4  # LDI, LDI, ST, HALT

    def test_colors_are_genuinely_distinct(self, db):
        # Regression guard: the original bug mapped every color to the
        # identical no-op instruction. These must all differ.
        results = {}
        for color in ("blue", "red", "green"):
            words = word_ids_to_words(text_to_word_ids(f"clear {color} halt", db), db)
            results[color] = execute_glyph_assembly(compile_to_glyph_assembly(words))["framebuffer_value_hex"]
        assert len(set(results.values())) == 3

    def test_halt_alone(self, db):
        words = word_ids_to_words(text_to_word_ids("halt", db), db)
        asm = compile_to_glyph_assembly(words)
        assert asm == ["HALT"]
        result = execute_glyph_assembly(asm)
        assert result["instructions_run"] == 1

    def test_unrecognized_word_skipped_from_grammar(self, db, capsys):
        words = word_ids_to_words(text_to_word_ids("banana halt", db), db)
        asm = compile_to_glyph_assembly(words)
        assert asm == ["HALT"]
        captured = capsys.readouterr()
        assert "not recognized" in captured.err


class TestFullPipeline:
    """LLM text -> real wordbase IDs -> audio -> decode -> execute, end to end."""

    def test_clear_blue_halt_full_pipeline(self, db, tmp_path):
        wav_path = str(tmp_path / "pipeline.wav")
        ids = text_to_word_ids("clear blue halt", db)
        word_ids_to_audio(ids, wav_path)

        decoded_ids = audio_to_word_ids(wav_path)
        assert decoded_ids == ids

        words = word_ids_to_words(decoded_ids, db)
        asm = compile_to_glyph_assembly(words)
        result = execute_glyph_assembly(asm)

        assert result["framebuffer_value_hex"] == "#0000FF"
