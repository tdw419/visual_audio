import pytest
import numpy as np
from tools.token_chord_codec import encode_token_ids, decode_token_ids, id_to_chords, chords_to_id, NUM_CHORDS

def test_chord_math():
    """Verify the math maps cleanly up to the max supported tokens."""
    # Test min/max values
    assert id_to_chords(0) == (0, 0)
    
    max_id = (NUM_CHORDS * NUM_CHORDS) - 1
    sym1, sym2 = id_to_chords(max_id)
    assert chords_to_id(sym1, sym2) == max_id
    
    # 496 * 496 = 246016 tokens supported
    assert max_id == 246015
    
    # Out of bounds should raise
    with pytest.raises(ValueError):
        id_to_chords(max_id + 1)
        
    with pytest.raises(ValueError):
        id_to_chords(-1)

def test_encode_decode_roundtrip():
    """Test full audio roundtrip for a sequence of token IDs."""
    # Common tokens: 1 (start), 245 (hello), 100000 (random word)
    test_ids = [1, 245, 42, 100000, 246015, 0]
    
    # Encode to audio waveform
    audio = encode_token_ids(test_ids)
    
    assert isinstance(audio, np.ndarray)
    assert len(audio) > 0
    
    # Decode from audio waveform
    decoded_ids = decode_token_ids(audio)
    
    assert decoded_ids == test_ids

def test_empty_sequence():
    """Verify empty sequence handles cleanly."""
    audio = encode_token_ids([])
    assert len(audio) == 0
    assert decode_token_ids(audio) == []
