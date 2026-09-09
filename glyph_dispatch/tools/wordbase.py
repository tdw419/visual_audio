"""
Dummy Wordbase Manager for Glyph ISA

This is a minimal stub to satisfy the import in glyph_isa_v2.py
when the full wordbase system is not available.
"""

class WordbaseManager:
    """Dummy WordbaseManager for standalone execution."""

    def __init__(self, path=None):
        self.path = path

    def get_word(self, word):
        """Return a dummy word entry for any word."""
        return {'color_hex': f'#{(hash(word) & 0xFFFFFF):06x}'}

    def close(self):
        """No-op for stub."""
        pass