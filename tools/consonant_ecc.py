import numpy as np
from scipy.io import wavfile

# Base frequency (Root note, e.g., A4)
ROOT_FREQ = 440.0

# 4 Consonant Intervals to represent 2 bits per symbol
# We use simple Just Intonation ratios for pure consonance
CONSONANT_RATIOS = {
    0b00: 5/4,   # Major Third
    0b01: 4/3,   # Perfect Fourth
    0b10: 3/2,   # Perfect Fifth
    0b11: 2/1,   # Octave
}

# Reverse mapping
RATIOS_TO_BITS = {v: k for k, v in CONSONANT_RATIOS.items()}
VALID_RATIOS = list(CONSONANT_RATIOS.values())

SAMPLE_RATE = 44100
SYMBOL_DURATION_MS = 100
SYMBOL_SAMPLES = int(SAMPLE_RATE * SYMBOL_DURATION_MS / 1000)

def encode_bits_to_consonance(data_bits: list[int]) -> np.ndarray:
    """
    Encode pairs of bits into consonant intervals over a root drone.
    data_bits: list of 0s and 1s.
    """
    if len(data_bits) % 2 != 0:
        data_bits.append(0)  # pad to even length
        
    audio_segments = []
    t = np.arange(SYMBOL_SAMPLES) / SAMPLE_RATE
    
    # Root drone plays continuously for each symbol
    root_wave = np.sin(2 * np.pi * ROOT_FREQ * t)
    
    # 5ms fade in/out
    fade_len = int(SAMPLE_RATE * 0.005)
    window = np.ones(SYMBOL_SAMPLES)
    window[:fade_len] = np.linspace(0, 1, fade_len)
    window[-fade_len:] = np.linspace(1, 0, fade_len)
    
    for i in range(0, len(data_bits), 2):
        symbol_val = (data_bits[i] << 1) | data_bits[i+1]
        ratio = CONSONANT_RATIOS[symbol_val]
        freq = ROOT_FREQ * ratio
        
        # Data wave
        data_wave = np.sin(2 * np.pi * freq * t)
        
        # Mix root and data, apply window
        mixed = (root_wave + data_wave) * 0.5 * window
        audio_segments.append(mixed)
        
    if not audio_segments:
        return np.array([], dtype=np.float32)
        
    return np.concatenate(audio_segments)

def _find_nearest_consonance(ratio: float) -> float:
    """Find the nearest valid consonant ratio (tuner)."""
    return min(VALID_RATIOS, key=lambda x: abs(x - ratio))

def decode_consonance_to_bits(audio: np.ndarray) -> list[int]:
    """
    Decode audio by finding the dominant frequency above the root,
    quantizing it to the nearest consonant ratio, and extracting bits.
    """
    if len(audio) == 0:
        return []
        
    num_symbols = len(audio) // SYMBOL_SAMPLES
    decoded_bits = []
    
    for i in range(num_symbols):
        segment = audio[i * SYMBOL_SAMPLES : (i + 1) * SYMBOL_SAMPLES]
        
        spectrum = np.abs(np.fft.rfft(segment))
        freqs = np.fft.rfftfreq(SYMBOL_SAMPLES, 1/SAMPLE_RATE)
        
        # We know the root is ROOT_FREQ. We look for the data peak.
        # Ignore frequencies below or too close to the root
        valid_mask = freqs > (ROOT_FREQ * 1.1)
        
        # Find peak frequency in the valid mask
        masked_spectrum = spectrum.copy()
        masked_spectrum[~valid_mask] = 0
        
        peak_idx = np.argmax(masked_spectrum)
        peak_freq = freqs[peak_idx]
        
        # Calculate ratio
        ratio = peak_freq / ROOT_FREQ
        
        # "Tune" it to nearest consonance
        tuned_ratio = _find_nearest_consonance(ratio)
        symbol_val = RATIOS_TO_BITS[tuned_ratio]
        
        decoded_bits.extend([(symbol_val >> 1) & 1, symbol_val & 1])
        
    return decoded_bits
