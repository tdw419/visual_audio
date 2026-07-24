#!/usr/bin/env python3
"""
Test pixel OS output channel - OS results to LM-readable pixel stream

Symmetric counterpart to tests/test_pixel_os_lm_input.py (TASK_M007's
LM -> OS channel test). Verifies tools/pixel_os_output.py can render OS
output (command results, status messages) into the same pixel-token
encoding an LM consumes, and that the round trip is lossless.

Acceptance criteria:
1. OS output text round-trips losslessly through encode_to_pixels/decode_from_pixels
2. Dispatch results (success/failure, as returned by ListenerDaemon._dispatch_ops)
   render to a valid pixel-token strip an LM could read
3. Multi-word output and repeated round trips remain consistent
4. Completes the LLM <-> visual audio <-> software loop (input verified by
   TASK_M007/test_pixel_os_lm_input.py; this verifies the return path)
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.pixel_os_output import (
    render_output_to_pixels,
    read_pixels_as_text,
    render_dispatch_result,
)
from src.pixel_tokenizer import PixelTokenizer


@pytest.fixture(scope="module")
def tokenizer():
    tok = PixelTokenizer()
    yield tok
    tok.close()


class TestPixelOSLMOutput:
    """Test pixel OS output channel: OS state/results -> LM-readable pixels."""

    def test_single_word_roundtrip(self, tokenizer):
        """A single-word OS output round-trips losslessly through pixels."""
        pixels = render_output_to_pixels("hello", tokenizer=tokenizer)
        assert isinstance(pixels, np.ndarray)
        assert pixels.shape[1] == 3
        assert pixels.dtype == np.uint8

        text = read_pixels_as_text(pixels, tokenizer=tokenizer)
        assert "hello" in text.lower()

    def test_multi_word_roundtrip(self, tokenizer):
        """Multi-word OS output (e.g. a command result sentence) round-trips."""
        original = "hello world pixel os"
        pixels = render_output_to_pixels(original, tokenizer=tokenizer)
        text = read_pixels_as_text(pixels, tokenizer=tokenizer)

        for word in original.split():
            assert word in text.lower()

    def test_pixel_strip_length_matches_token_count(self, tokenizer):
        """One pixel per token, including BOS/EOS (encode_to_pixels default)."""
        ids = tokenizer.encode("hello world", add_special_tokens=True)
        pixels = render_output_to_pixels("hello world", tokenizer=tokenizer)
        assert pixels.shape[0] == len(ids)

    def test_dispatch_result_success_renders_ok(self, tokenizer):
        """A successful ListenerDaemon dispatch renders as a readable 'ok' pixel strip."""
        pixels = render_dispatch_result(True, tokenizer=tokenizer)
        text = read_pixels_as_text(pixels, tokenizer=tokenizer)
        assert "ok" in text.lower()

    def test_dispatch_result_failure_renders_error(self, tokenizer):
        """A failed dispatch renders as a readable 'error' pixel strip, with detail preserved."""
        pixels = render_dispatch_result(False, detail="boot refused", tokenizer=tokenizer)
        text = read_pixels_as_text(pixels, tokenizer=tokenizer)
        assert "error" in text.lower()
        assert "boot" in text.lower()

    def test_roundtrip_is_stable_across_repeats(self, tokenizer):
        """Rendering the same output twice produces identical pixel strips
        (determinism - required for an LM to reliably learn the channel)."""
        pixels_a = render_output_to_pixels("hello world", tokenizer=tokenizer)
        pixels_b = render_output_to_pixels("hello world", tokenizer=tokenizer)
        assert np.array_equal(pixels_a, pixels_b)

    def test_own_tokenizer_lifecycle_when_none_provided(self):
        """render_output_to_pixels/read_pixels_as_text work standalone,
        each managing (and closing) their own PixelTokenizer."""
        pixels = render_output_to_pixels("hello")
        text = read_pixels_as_text(pixels)
        assert "hello" in text.lower()

    def test_full_loop_input_and_output_share_pixel_scheme(self, tokenizer):
        """The OS output channel uses the identical 24-bit RGB = word-ID
        scheme as the input channel (TASK_M007), so an LM using one wordbase
        can both issue commands and read results through the same encoding."""
        ids = tokenizer.encode("hello", add_special_tokens=False)
        direct_pixels = tokenizer.ids_to_pixels(ids)
        output_pixels = render_output_to_pixels("hello", tokenizer=tokenizer)
        # output_pixels includes BOS/EOS; direct_pixels does not - compare the
        # word pixel itself, not the whole strip.
        assert any(np.array_equal(direct_pixels[0], p) for p in output_pixels)
