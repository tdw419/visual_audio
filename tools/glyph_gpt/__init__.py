#!/usr/bin/env python3
"""
GlyphGPT — opcode-level LLM for Glyph assembly generation.

Boundary map (see SKELETON_SIGNED_OFF.md):

    .glyph corpus (repo files)   RV64I/C binaries + synth templates
            │                            │
            ▼                            ▼
       corpus.py                    synth.py  (transpile + oracle gate)
            │                            │
            └──────────┬─────────────────┘
                       ▼
                  dataset.py   tokenized (ids, values) → npz
                       │
                       ▼
                   model.py     tiny causal transformer + value embeddings
                       │
                       ▼
                   train.py     training loop → checkpoint.npz
                       │
                       ▼
                 generate.py    sample → assemble → execute → receipt
"""

from glyph_gpt.tokenizer import (
    GlyphTokenizer,
    build_default_vocab,
    PAD, BOS, EOS, NEWLINE, COMMENT, NUM, LABEL, STR, COMMA, COLON,
    SPECIAL_NAMES, NUM_SPECIAL, N_REGISTERS,
)

__all__ = [
    "GlyphTokenizer", "build_default_vocab",
    "PAD", "BOS", "EOS", "NEWLINE", "COMMENT", "NUM", "LABEL", "STR", "COMMA", "COLON",
    "SPECIAL_NAMES", "NUM_SPECIAL", "N_REGISTERS",
]
