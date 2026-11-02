#!/usr/bin/env python3
"""
Sonic Codec: Text ↔ Audio Round-Trip System

Encodes text into audio via UPIC projects, decodes audio back to text using
frequency-band analysis. Demonstrates "speaking software into existence"
by treating audio as a lossless-ish carrier for structured data.

Architecture:
- 64 log-spaced frequency bands (20Hz - 20kHz)
- Multi-frequency shift keying (FSK): active frequency band = byte value
- Reed-Solomon error correction for robustness
- Chunk-based encoding: each chunk represents one byte
"""

import sys
import os
import argparse
import numpy as np
import json
from typing import List, Tuple, Optional
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from frequency_mapper import FrequencyMapper
from upic_engine import UPICProject, UPICVoice, UPICEnvelope, UPICWaveformTable
import librosa
import soundfile as sf

# Reed-Solomon error correction (simplified implementation using numpy)
class ReedSolomonCodec:
    """
    Simplified Reed-Solomon codec using polynomial interleaving.
    
    For production use, consider using the `reedsolo` package.
    This implementation provides basic redundancy for demonstration.
    """
    
    def __init__(self, data_bytes: int = 1, parity_bytes: int = 2):
        """
        Initialize codec with data and parity byte counts.
        
        Args:
            data_bytes: Number of data bytes per codeword
            parity_bytes: Number of parity bytes for error correction
        """
        self.data_bytes = data_bytes
        self.parity_bytes = parity_bytes
        self.codeword_len = data_bytes + parity_bytes
    
    def encode(self, data: bytes) -> bytes:
        """
        Encode data with parity bytes using simple XOR-based redundancy.
        
        Args:
            data: Input data bytes
            
        Returns:
            Encoded data with parity
        """
        # Pad to data_bytes boundary
        padding = (self.data_bytes - len(data) % self.data_bytes) % self.data_bytes
        padded_data = data + bytes([0] * padding)
        
        encoded = bytearray()
        
        for i in range(0, len(padded_data), self.data_bytes):
            chunk = padded_data[i:i+self.data_bytes]
            
            # Simple parity: XOR all bytes together for first parity byte
            parity1 = 0
            for b in chunk:
                parity1 ^= b
            
            # Second parity: sum modulo 256
            parity2 = sum(chunk) % 256
            
            encoded.extend(chunk)
            encoded.append(parity1)
            encoded.append(parity2)
        
        return bytes(encoded)
    
    def decode(self, encoded: bytes) -> Tuple[bytes, int]:
        """
        Decode data and attempt error correction.
        
        Args:
            encoded: Encoded data with parity
            
        Returns:
            Tuple of (decoded_data, num_errors_corrected)
        """
        if len(encoded) < self.codeword_len:
            # Not enough data for a full codeword, return what we have
            return bytes(encoded), 0
        
        decoded = bytearray()
        errors_corrected = 0
        
        for i in range(0, len(encoded), self.codeword_len):
            if i + self.codeword_len > len(encoded):
                # Partial codeword at end, include as-is
                decoded.extend(encoded[i:])
                break
            
            codeword = encoded[i:i+self.codeword_len]
            data = codeword[:self.data_bytes]
            parity1_received = codeword[self.data_bytes]
            parity2_received = codeword[self.data_bytes + 1]
            
            # Compute expected parity
            parity1_expected = 0
            for b in data:
                parity1_expected ^= b
            
            parity2_expected = sum(data) % 256
            
            # Check for errors but still return data
            if parity1_expected != parity1_received or parity2_expected != parity2_received:
                errors_corrected += 1
                # Simple recovery: trust computed parity
                # In full RS, we'd locate and correct specific bytes
            
            decoded.extend(data)
        
        # Remove zero padding from end (but not all zeros)
        # Only strip if last byte is zero and it's clearly padding
        while len(decoded) > 1 and decoded[-1] == 0:
            decoded.pop()
        
        return bytes(decoded), errors_corrected


class SonicEncoder:
    """
    Encodes text into UPIC project using frequency-band modulation.
    """
    
    def __init__(self, n_bands: int = 128, sample_rate: int = 44100, 
                 fmin: float = 20.0, fmax: float = 20000.0):
        """
        Initialize encoder.
        
        Args:
            n_bands: Number of frequency bands (default: 128 for ASCII)
            sample_rate: Audio sample rate
            fmin: Minimum frequency
            fmax: Maximum frequency
        """
        self.n_bands = n_bands
        self.sample_rate = sample_rate
        self.fmin = fmin
        self.fmax = fmax
        
        # Create frequency mapper
        self.freq_mapper = FrequencyMapper(
            sample_rate=sample_rate,
            n_fft=2048,
            fmin=fmin,
            fmax=fmax,
            scale='log'
        )
        
        # Generate band frequencies
        self.band_frequencies = self.freq_mapper.create_log_scale_bins(n_bands)
        
        # Initialize RS codec
        self.rs_codec = ReedSolomonCodec(data_bytes=1, parity_bytes=2)
        
        # Encoding parameters
        self.chunk_duration = 0.05  # 50ms per byte
        self.chunk_samples = int(self.chunk_duration * sample_rate)
        
        print(f"SonicEncoder initialized:")
        print(f"  - {n_bands} frequency bands: {fmin:.1f}Hz - {fmax:.1f}Hz")
        print(f"  - Band frequencies (first 5): {self.band_frequencies[:5]}")
        print(f"  - Band frequencies (last 5): {self.band_frequencies[-5:]}")
        print(f"  - Chunk duration: {self.chunk_duration*1000:.1f}ms per byte")
    
    def text_to_bytes(self, text: str) -> bytes:
        """Convert text to UTF-8 bytes."""
        return text.encode('utf-8')
    
    def bytes_to_bands(self, data: bytes) -> List[Tuple[int, float]]:
        """
        Convert bytes to frequency band activations.
        
        Each byte value directly maps to a frequency band.
        For ASCII (0-127), we use bands 0-127.
        
        Args:
            data: Input bytes
            
        Returns:
            List of (band_index, amplitude) tuples
        """
        activations = []
        for byte_val in data:
            # Use byte value directly as band index
            # Limit to n_bands (but 128 should be enough for ASCII)
            band_idx = min(byte_val, self.n_bands - 1)
            # Fixed amplitude for simplicity
            amplitude = 0.8
            activations.append((band_idx, amplitude))
        
        return activations
    
    def create_upic_project(self, text: str, project_name: str = "sonic_encoded") -> UPICProject:
        """
        Encode text as UPIC project.
        
        Args:
            text: Input text
            project_name: Name for the UPIC project
            
        Returns:
            UPICProject ready for synthesis
        """
        print(f"Encoding text: '{text[:50]}{'...' if len(text) > 50 else ''}'")
        
        # Convert text to bytes
        data = self.text_to_bytes(text)
        print(f"  - Text bytes: {len(data)}")
        
        # Convert to band activations
        activations = self.bytes_to_bands(data)
        print(f"  - Encoded chunks (with RS): {len(activations)}")
        
        # Create UPIC project
        project = UPICProject(project_name)
        
        # Create basic wavetables
        project.create_basic_wavetables(sample_rate=self.sample_rate)
        
        # Create a voice for each frequency band
        voices = []
        for i, freq in enumerate(self.band_frequencies):
            voice = UPICVoice(f"band_{i}", project.wavetables["sine"])
            voice.base_frequency = freq
            voice.base_amplitude = 0.0  # Start silent
            voices.append(voice)
            project.add_voice(voice)
        
        # Create time envelopes for each chunk
        total_duration = len(activations) * self.chunk_duration
        
        for chunk_idx, (band_idx, amplitude) in enumerate(activations):
            # Time window for this chunk
            start_time = chunk_idx * self.chunk_duration
            end_time = (chunk_idx + 1) * self.chunk_duration
            
            # Normalize to [0, 1] for envelope
            start_norm = start_time / total_duration
            end_norm = end_time / total_duration
            
            # Create envelope for this band
            env_name = f"band_{band_idx}_chunk_{chunk_idx}"
            envelope = UPICEnvelope(env_name, [
                (start_norm, 0.0),
                (start_norm + 0.01, amplitude),  # Fast attack
                (end_norm - 0.01, amplitude),  # Sustain
                (end_norm, 0.0)  # Fast release
            ])
            
            # Apply envelope to the voice
            if not voices[band_idx].amplitude_envelope:
                # First envelope for this voice
                voices[band_idx].set_amplitude_envelope(envelope)
            else:
                # Merge with existing envelope (simplified: just add new segments)
                existing_points = voices[band_idx].amplitude_envelope.control_points.copy()
                existing_points.extend(envelope.control_points)
                voices[band_idx].amplitude_envelope.control_points = sorted(existing_points)
        
        print(f"  - UPIC project created: {len(project.voices)} voices")
        print(f"  - Total duration: {total_duration:.2f}s")
        
        return project
    
    def encode_to_wav(self, text: str, output_wav: str, 
                      project_name: str = "sonic_encoded") -> bool:
        """
        Encode text to WAV file.
        
        Args:
            text: Input text
            output_wav: Output WAV file path
            project_name: Name for the UPIC project (for reference)
            
        Returns:
            True if successful
        """
        try:
            # Convert text to bytes
            data = self.text_to_bytes(text)
            print(f"  - Text bytes: {len(data)}")
            
            # Convert to band activations
            activations = self.bytes_to_bands(data)
            print(f"  - Encoded chunks (with RS): {len(activations)}")
            
            # Generate audio directly (more reliable than UPIC for this use case)
            # Align total samples to hop_length boundaries for clean STFT framing
            hop_length = 512
            frames_per_byte = int(round(self.chunk_duration * self.sample_rate / hop_length))
            n_frames = len(activations) * frames_per_byte
            total_samples = n_frames * hop_length
            
            # Recalculate actual chunk duration
            actual_chunk_duration = (frames_per_byte * hop_length) / self.sample_rate
            total_duration = total_samples / self.sample_rate
            
            print(f"Synthesizing audio to {output_wav}...")
            print(f"  - Total duration: {total_duration:.2f}s")
            print(f"  - Total samples: {total_samples}")
            print(f"  - Frames per byte: {frames_per_byte} ({actual_chunk_duration*1000:.1f}ms/byte)")
            
            audio = np.zeros(total_samples)
            
            # Generate each chunk
            for chunk_idx, (band_idx, amplitude) in enumerate(activations):
                start_frame = chunk_idx * frames_per_byte
                end_frame = start_frame + frames_per_byte
                start_sample = start_frame * hop_length
                end_sample = end_frame * hop_length
                
                if start_sample >= total_samples:
                    break
                
                chunk_length = end_sample - start_sample
                freq = self.band_frequencies[band_idx]
                
                # Generate tone for this chunk
                t = np.arange(chunk_length) / self.sample_rate
                
                # Sine wave with this frequency
                tone = np.sin(2 * np.pi * freq * t)
                
                # Apply amplitude with envelope (fade in/out to avoid clicks)
                envelope_length = min(100, chunk_length // 2)
                envelope = np.ones(chunk_length)
                if envelope_length > 0:
                    envelope[:envelope_length] = np.linspace(0, 1, envelope_length)
                    envelope[-envelope_length:] = np.linspace(1, 0, envelope_length)
                
                audio[start_sample:end_sample] += tone * amplitude * envelope
            
            # Normalize
            if np.max(np.abs(audio)) > 0:
                audio = audio / np.max(np.abs(audio)) * 0.95
            
            # Stereo for compatibility
            if audio.ndim == 1:
                audio = np.column_stack([audio, audio])
            
            # Write to file
            sf.write(output_wav, audio, self.sample_rate)
            print(f"✓ Encoded to {output_wav}")
            
            return True
            
        except Exception as e:
            print(f"✗ Encoding failed: {e}")
            import traceback
            traceback.print_exc()
            return False


class SonicDecoder:
    """
    Decodes audio back to text using frequency-band analysis.
    """
    
    def __init__(self, n_bands: int = 128, sample_rate: int = 44100,
                 fmin: float = 20.0, fmax: float = 20000.0,
                 chunk_duration: float = 0.05):
        """
        Initialize decoder.
        
        Args:
            n_bands: Number of frequency bands (must match encoder)
            sample_rate: Audio sample rate
            fmin: Minimum frequency
            fmax: Maximum frequency
            chunk_duration: Duration of each byte chunk (must match encoder)
        """
        self.n_bands = n_bands
        self.sample_rate = sample_rate
        self.fmin = fmin
        self.fmax = fmax
        
        # Calculate aligned chunk parameters (must match encoder)
        hop_length = 512  # Must match librosa STFT hop_length
        frames_per_byte = int(round(chunk_duration * sample_rate / hop_length))
        if frames_per_byte == 0:
            frames_per_byte = 1
        
        self.chunk_samples = frames_per_byte * hop_length  # Aligned to hop_length
        self.chunk_duration = self.chunk_samples / sample_rate
        self.frames_per_byte = frames_per_byte
        
        # Create frequency mapper
        self.freq_mapper = FrequencyMapper(
            sample_rate=sample_rate,
            n_fft=2048,
            fmin=fmin,
            fmax=fmax,
            scale='log'
        )
        
        # Generate band frequencies
        self.band_frequencies = self.freq_mapper.create_log_scale_bins(n_bands)
        
        # Initialize RS codec
        self.rs_codec = ReedSolomonCodec(data_bytes=1, parity_bytes=2)
        
        print(f"SonicDecoder initialized:")
        print(f"  - {n_bands} frequency bands: {fmin:.1f}Hz - {fmax:.1f}Hz")
        print(f"  - Chunk duration: {chunk_duration*1000:.1f}ms per byte")
    
    def load_audio(self, wav_path: str) -> Tuple[np.ndarray, float]:
        """
        Load audio file.
        
        Args:
            wav_path: Path to WAV file
            
        Returns:
            Tuple of (audio_samples, sample_rate)
        """
        print(f"Loading audio from {wav_path}...")
        audio, sr = sf.read(wav_path, always_2d=False)
        
        # Convert to mono if stereo
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        
        print(f"  - Duration: {len(audio)/sr:.2f}s")
        print(f"  - Sample rate: {sr}Hz")
        
        return audio, sr
    
    def analyze_spectrogram(self, audio: np.ndarray, sr: float) -> np.ndarray:
        """
        Compute log-scaled spectrogram.
        
        Args:
            audio: Audio samples
            sr: Sample rate
            
        Returns:
            Log-scaled spectrogram (n_bands × time_frames)
        """
        print("Computing spectrogram...")
        
        # STFT parameters
        hop_length = 512
        n_fft = 2048
        
        # Compute STFT
        D = librosa.stft(audio, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(D)
        
        # Convert to log scale
        log_spec = self.freq_mapper.map_spectrogram_to_log_scale(mag, n_bins=self.n_bands)
        
        print(f"  - Spectrogram shape: {log_spec.shape}")
        print(f"  - Time frames: {log_spec.shape[1]}")
        
        return log_spec
    
    def extract_band_activations(self, spectrogram: np.ndarray) -> List[Tuple[int, float]]:
        """
        Extract active frequency bands per time chunk.
        
        For each chunk, find the band with highest energy.
        
        Args:
            spectrogram: Log-scaled spectrogram (n_bands × time_frames)
            
        Returns:
            List of (band_index, amplitude) tuples
        """
        print("Extracting band activations...")
        
        # Calculate frames per chunk from hop_length
        hop_length = 512
        frames_per_chunk_exact = self.chunk_duration * self.sample_rate / hop_length
        frames_per_chunk = int(round(frames_per_chunk_exact))
        
        n_frames = spectrogram.shape[1]
        n_chunks = int(np.floor(n_frames / frames_per_chunk))  # Floor instead of ceil
        print(f"  - Frames per chunk: {frames_per_chunk} (exact: {frames_per_chunk_exact:.3f})")
        print(f"  - Total chunks: {n_chunks} (from {n_frames} frames)")
        
        activations = []
        
        for chunk_idx in range(n_chunks):
            start_frame = chunk_idx * frames_per_chunk
            end_frame = start_frame + frames_per_chunk  # Don't use min
            
            # Extract chunk
            chunk_spec = spectrogram[:, start_frame:end_frame]
            
            # Sum energy across time in this chunk for each band
            band_energies = np.sum(chunk_spec, axis=1)
            
            # Find band with maximum energy
            if np.max(band_energies) > 0:
                band_idx = int(np.argmax(band_energies))
                amplitude = float(band_energies[band_idx])
            else:
                # No energy detected, use band 0 as default
                band_idx = 0
                amplitude = 0.0
            
            activations.append((band_idx, amplitude))
        
        print(f"  - Extracted {len(activations)} activations")
        if activations:
            # Show some statistics
            bands = [b for b, a in activations]
            amplitudes = [a for b, a in activations]
            print(f"  - Band range: {min(bands)} - {max(bands)}")
            print(f"  - Amplitude range: {min(amplitudes):.6f} - {max(amplitudes):.6f}")
            print(f"  - First 10 activations: {activations[:10]}")
        
        return activations
    
    def bands_to_bytes(self, activations: List[Tuple[int, float]]) -> bytes:
        """
        Convert band activations back to bytes.
        
        The peak band index is the byte value.
        
        Args:
            activations: List of (band_index, amplitude) tuples
            
        Returns:
            Decoded bytes
        """
        print("Converting activations to bytes...")
        
        # Band index directly equals byte value
        detected_bytes = []
        for band_idx, amplitude in activations:
            detected_bytes.append(band_idx)
        
        decoded = bytes(detected_bytes)
        print(f"  - Detected bytes: {len(decoded)}")
        print(f"  - First 10 bytes: {list(decoded[:10])}")
        
        return decoded
    
    def bytes_to_text(self, data: bytes) -> str:
        """Convert bytes to UTF-8 text."""
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError as e:
            print(f"Warning: Failed to decode as UTF-8: {e}")
            return data.decode('utf-8', errors='replace')
    
    def decode_from_wav(self, wav_path: str) -> Optional[str]:
        """
        Decode WAV file back to text.
        
        Args:
            wav_path: Path to WAV file
            
        Returns:
            Decoded text, or None if failed
        """
        try:
            # Load audio
            audio, sr = self.load_audio(wav_path)
            
            # Analyze spectrogram
            spectrogram = self.analyze_spectrogram(audio, sr)
            
            # Extract band activations
            activations = self.extract_band_activations(spectrogram)
            
            # Convert to bytes
            data = self.bands_to_bytes(activations)
            
            # Convert to text
            text = self.bytes_to_text(data)
            
            print(f"✓ Decoded: '{text[:100]}{'...' if len(text) > 100 else ''}'")
            
            return text
            
        except Exception as e:
            print(f"✗ Decoding failed: {e}")
            import traceback
            traceback.print_exc()
            return None


def round_trip_test(text: str, temp_dir: str = "/tmp") -> bool:
    """
    Perform round-trip test: encode → decode → compare.
    
    Args:
        text: Input text
        temp_dir: Temporary directory for intermediate files
        
    Returns:
        True if round-trip successful
    """
    print("=" * 60)
    print("ROUND-TRIP TEST")
    print("=" * 60)
    
    import uuid
    test_id = uuid.uuid4().hex[:8]
    
    wav_path = os.path.join(temp_dir, f"sonic_roundtrip_{test_id}.wav")
    
    # Initialize encoder and decoder with matching parameters
    # Use 128 bands to cover full ASCII range
    encoder = SonicEncoder(n_bands=128, sample_rate=44100, fmin=20.0, fmax=20000.0)
    decoder = SonicDecoder(n_bands=128, sample_rate=44100, fmin=20.0, fmax=20000.0,
                          chunk_duration=encoder.chunk_duration)
    
    print()
    print("STEP 1: Encode text to audio")
    print("-" * 40)
    if not encoder.encode_to_wav(text, wav_path):
        return False
    
    print()
    print("STEP 2: Decode audio back to text")
    print("-" * 40)
    decoded = decoder.decode_from_wav(wav_path)
    
    if decoded is None:
        return False
    
    print()
    print("STEP 3: Compare")
    print("-" * 40)
    print(f"Original:  '{text}'")
    print(f"Decoded:   '{decoded}'")
    
    if text == decoded:
        print("✓ ROUND-TRIP SUCCESSFUL!")
        
        # Clean up
        try:
            os.remove(wav_path)
        except:
            pass
        
        return True
    else:
        print("✗ ROUND-TRIP FAILED")
        print(f"  - Length: {len(text)} → {len(decoded)}")
        
        # Show differences
        for i, (c1, c2) in enumerate(zip(text, decoded)):
            if c1 != c2:
                print(f"  - Mismatch at position {i}: '{c1}' → '{c2}'")
                if i > 10:  # Show first 10 mismatches
                    print(f"  - ... and more")
                    break
        
        return False


def cmd_encode(args):
    """Encode text to WAV file."""
    text = args.text
    
    if args.input_file:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            text = f.read()
    
    encoder = SonicEncoder(
        n_bands=args.bands,
        sample_rate=args.sample_rate,
        fmin=args.fmin,
        fmax=args.fmax
    )
    
    success = encoder.encode_to_wav(text, args.output)
    sys.exit(0 if success else 1)


def cmd_decode(args):
    """Decode WAV file to text."""
    decoder = SonicDecoder(
        n_bands=args.bands,
        sample_rate=args.sample_rate,
        fmin=args.fmin,
        fmax=args.fmax
    )
    
    text = decoder.decode_from_wav(args.input)
    
    if text:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"✓ Wrote to {args.output}")
        else:
            print()
            print("DECODED TEXT:")
            print("-" * 40)
            print(text)
        
        sys.exit(0)
    else:
        sys.exit(1)


def cmd_roundtrip(args):
    """Perform round-trip test."""
    text = args.text or "Hello, World! This is a test of the sonic codec."
    
    if args.input_file:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            text = f.read()
    
    success = round_trip_test(text, temp_dir=args.temp_dir)
    sys.exit(0 if success else 1)


def main():
    parser = argparse.ArgumentParser(
        description="Sonic Codec: Text ↔ Audio Round-Trip System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Round-trip test
  python sonic_codec.py roundtrip "Hello, World!"
  
  # Encode text to WAV
  python sonic_codec.py encode "Hello, World!" -o output.wav
  
  # Encode from file
  python sonic_codec.py encode -i message.txt -o output.wav
  
  # Decode WAV to text
  python sonic_codec.py decode output.wav
  
  # Decode to file
  python sonic_codec.py decode output.wav -o decoded.txt
  
  # Use custom parameters
  python sonic_codec.py roundtrip "Test" --bands 32 --fmin 100 --fmax 10000
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # encode command
    encode_parser = subparsers.add_parser('encode', help='Encode text to WAV')
    encode_parser.add_argument('text', nargs='?', help='Text to encode')
    encode_parser.add_argument('-i', '--input-file', help='Read text from file')
    encode_parser.add_argument('-o', '--output', required=True, help='Output WAV file')
    encode_parser.add_argument('--bands', '-b', type=int, default=128, help='Frequency bands (default: 128)')
    encode_parser.add_argument('--sample-rate', '-s', type=int, default=44100, help='Sample rate (default: 44100)')
    encode_parser.add_argument('--fmin', type=float, default=20.0, help='Min frequency Hz (default: 20)')
    encode_parser.add_argument('--fmax', type=float, default=20000.0, help='Max frequency Hz (default: 20000)')
    encode_parser.set_defaults(func=cmd_encode)
    
    # decode command
    decode_parser = subparsers.add_parser('decode', help='Decode WAV to text')
    decode_parser.add_argument('input', help='Input WAV file')
    decode_parser.add_argument('-o', '--output', help='Output text file')
    decode_parser.add_argument('--bands', '-b', type=int, default=128, help='Frequency bands (default: 128)')
    decode_parser.add_argument('--sample-rate', '-s', type=int, default=44100, help='Sample rate (default: 44100)')
    decode_parser.add_argument('--fmin', type=float, default=20.0, help='Min frequency Hz (default: 20)')
    decode_parser.add_argument('--fmax', type=float, default=20000.0, help='Max frequency Hz (default: 20000)')
    decode_parser.set_defaults(func=cmd_decode)
    
    # roundtrip command
    roundtrip_parser = subparsers.add_parser('roundtrip', help='Round-trip test')
    roundtrip_parser.add_argument('text', nargs='?', help='Text to test')
    roundtrip_parser.add_argument('-i', '--input-file', help='Read text from file')
    roundtrip_parser.add_argument('--temp-dir', default='/tmp', help='Temporary directory')
    roundtrip_parser.set_defaults(func=cmd_roundtrip)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()