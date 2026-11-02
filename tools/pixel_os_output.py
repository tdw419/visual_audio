#!/usr/bin/env python3
"""
pixel_os_output.py — Pixel OS output channel: OS state/results to LM-readable pixels.

Symmetric counterpart to tools/pixel_os_listener.py (TASK_M007, the LM -> OS
input channel). Where the input channel decodes an LM's pixel-token stream
into dispatched OS commands, this module renders OS output (command results,
status, framebuffer-derived text) back into the same pixel-token encoding
(PixelTokenizer's 24-bit RGB = word ID scheme) so an LM consuming the OS's
video feed can read what happened.

This is a thin wrapper over the already-verified PixelTokenizer round-trip
(encode_to_pixels / decode_from_pixels, exercised by TASK_M004-M006) - it
does not reinvent pixel encoding, it just gives the OS -> LM direction its
own named entry point and dispatch-result convention.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pixel_tokenizer import PixelTokenizer


def render_output_to_pixels(text: str, tokenizer: PixelTokenizer = None):
    """
    Render OS output text as an LM-readable pixel-token strip.

    Args:
        text: OS output text (command result, status message, etc.)
        tokenizer: Optional shared PixelTokenizer (created if not given)

    Returns:
        NumPy array of shape (N, 3) with RGB pixel values
    """
    owns_tokenizer = tokenizer is None
    if tokenizer is None:
        tokenizer = PixelTokenizer()
    try:
        return tokenizer.encode_to_pixels(text)
    finally:
        if owns_tokenizer:
            tokenizer.close()


def read_pixels_as_text(pixels, tokenizer: PixelTokenizer = None, skip_special_tokens: bool = True) -> str:
    """
    Decode an LM-readable pixel-token strip back to text.

    Args:
        pixels: NumPy array of shape (N, 3) with RGB pixel values
        tokenizer: Optional shared PixelTokenizer (created if not given)
        skip_special_tokens: Skip BOS/EOS/whitespace-marker tokens

    Returns:
        Decoded text
    """
    owns_tokenizer = tokenizer is None
    if tokenizer is None:
        tokenizer = PixelTokenizer()
    try:
        return tokenizer.decode_from_pixels(pixels, skip_special_tokens=skip_special_tokens)
    finally:
        if owns_tokenizer:
            tokenizer.close()


def render_dispatch_result(success: bool, detail: str = "", tokenizer: PixelTokenizer = None):
    """
    Render a pixel_os_listener dispatch result (as returned by
    ListenerDaemon._dispatch_ops) as an LM-readable pixel-token strip.

    Args:
        success: Whether the dispatched ops applied cleanly
        detail: Optional extra detail (e.g. an error message)
        tokenizer: Optional shared PixelTokenizer (created if not given)

    Returns:
        NumPy array of shape (N, 3) with RGB pixel values
    """
    status = "ok" if success else "error"
    text = f"{status} {detail}".strip()
    return render_output_to_pixels(text, tokenizer=tokenizer)
