import numpy as np
from tools.consonant_ecc import (
    encode_bits_to_consonance,
    decode_consonance_to_bits,
    ROOT_FREQ,
    CONSONANT_RATIOS,
    SAMPLE_RATE
)

def test_perfect_decode():
    """Verify clean encode/decode of all bit combinations."""
    data_bits = [0, 0, 0, 1, 1, 0, 1, 1]
    
    audio = encode_bits_to_consonance(data_bits)
    assert len(audio) > 0
    
    decoded = decode_consonance_to_bits(audio)
    assert decoded == data_bits

def test_aesthetic_error_correction():
    """
    Simulate a corrupted transmission (e.g. tape flutter / doppler) 
    that detunes the signal, creating dissonance. The decoder should 
    'tune' it back to consonance and recover the original bits.
    """
    # 0b01 -> Perfect Fourth (4:3) -> 440 * 1.3333 = 586.67 Hz
    # Let's artificially generate a corrupted version at 605 Hz (Dissonant)
    # The nearest consonant is still Perfect Fourth (586.67 Hz) since 
    # the next is Perfect Fifth (660 Hz) or Major Third (550 Hz).
    # 605 / 440 = 1.375. 
    # Abs dist to 1.3333 = 0.041. Abs dist to 1.5 = 0.125. 
    # It should quantize down to 4:3 (0b01).
    
    symbol_samples = int(SAMPLE_RATE * 100 / 1000)
    t = np.arange(symbol_samples) / SAMPLE_RATE
    
    root_wave = np.sin(2 * np.pi * ROOT_FREQ * t)
    corrupted_data_wave = np.sin(2 * np.pi * 605.0 * t)
    
    corrupted_audio = (root_wave + corrupted_data_wave) * 0.5
    
    # Decoder should 'hear' the dissonance and tune it back to 0b01
    decoded = decode_consonance_to_bits(corrupted_audio)
    assert decoded == [0, 1]
