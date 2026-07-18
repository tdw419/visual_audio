#!/usr/bin/env python3
"""
Unit tests for the phoneme codec (Phase 0).
Verifies ARPAbet templates and basic text-to-audio synthesis flow.
"""

import sys
import os
import pytest
import numpy as np
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import phonemes
import speak

def test_phoneme_templates_exist():
    """Verify ARPAbet phoneme envelope creation."""
    envelopes = phonemes.create_phoneme_envelopes()
    assert len(envelopes) >= 39
    
    # Check for representative phonemes
    expected_phonemes = ['AA', 'AE', 'B', 'CH', 'D', 'DH', 'F', 'G', 'P', 'S', 'T']
    for p in expected_phonemes:
        assert p in envelopes

def test_get_phoneme_envelope():
    """Verify phoneme envelope retrieval."""
    env = phonemes.get_phoneme_envelope('AA')
    assert env is not None
    # Verify fallback for unknown
    with pytest.raises(KeyError):
        phonemes.get_phoneme_envelope('UNKNOWN_PHONEME')

def test_say_text_generates_audio():
    """Verify that say_text successfully creates a WAV file from text."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp_wav:
        speak.say_text(text="hello", wav_path=tmp_wav.name)
        assert os.path.exists(tmp_wav.name)
        # Verify file size indicates it wrote real data
        assert os.path.getsize(tmp_wav.name) > 100
