#!/usr/bin/env python3
"""glyph_prompt_bridge.py — Host-side prompt bridge for Glyph-native virtual terminal.

Slice 2A: In-memory mechanism connecting GlyphVT to local Ollama.
Watches a GlyphVT instance's line queue for committed user prompts (terminated
by Enter), queries local Ollama (reusing query_ollama from tools.ollama_guest_listener),
and feeds the generated response back into the VT's screen buffer.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Optional

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.glyph_vt import GlyphVT, VTDisplay
from tools.ollama_guest_listener import DEFAULT_MODEL, query_ollama


def get_active_model(default: str = DEFAULT_MODEL) -> str:
    """Returns the currently loaded Ollama model name if any, else default."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/ps")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read())
            models = data.get("models", [])
            if models:
                return models[0].get("name", default)
    except Exception:
        pass
    return default


class GlyphPromptBridge:
    """Binds a GlyphVT virtual terminal to local Ollama inference."""

    def __init__(
        self,
        vt: GlyphVT,
        model: Optional[str] = None,
        timeout: float = 60.0,
        prefix: str = "\r\n[AI]: ",
        suffix: str = "\r\n> ",
    ):
        self.vt = vt
        self.model = model if model is not None else get_active_model()
        self.timeout = timeout
        self.prefix = prefix
        self.suffix = suffix
        self.display = VTDisplay()

    def has_pending_prompt(self) -> bool:
        """Returns True if the VT line queue has at least one committed line."""
        return len(self.vt._line_queue) > 0

    def step(self) -> Optional[dict]:
        """Processes exactly one committed prompt from the VT line queue if available.

        Returns a result dict if a prompt was processed, None otherwise.
        """
        if not self.has_pending_prompt():
            return None

        raw_line = self.vt._line_queue.popleft()
        prompt = raw_line.decode("utf-8", errors="replace").strip()

        if not prompt:
            # Empty line submitted (just Enter) — restore prompt cursor
            self.vt.write(self.suffix.encode("utf-8"))
            return {"prompt": "", "response": "", "status": "empty"}

        try:
            response_text = query_ollama(prompt, model=self.model, timeout=self.timeout)
            out_bytes = (self.prefix + response_text + self.suffix).encode("utf-8")
            self.vt.write(out_bytes)
            return {
                "prompt": prompt,
                "response": response_text,
                "status": "ok",
                "model": self.model,
            }
        except Exception as e:
            err_msg = f"\r\n[ERROR: {e}]\r\n> "
            self.vt.write(err_msg.encode("utf-8"))
            return {
                "prompt": prompt,
                "error": str(e),
                "status": "error",
                "model": self.model,
            }

    def render_pixels(self):
        """Renders the current VT screen into an RGB pixel band."""
        return self.display.render_band(self.vt.screen)

    def decode_pixels(self, band) -> list[str]:
        """Decodes an RGB pixel band back to text via exact font bitmap matching."""
        return self.display.decode_band(band, self.vt.screen.rows, self.vt.screen.cols)
