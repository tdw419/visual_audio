#!/usr/bin/env python3
"""
VAMP Audio Export Module

Integrates dual-band audio export into the Visual Audio Memory Palace workflow.

This module provides a Python API for encoding knowledge batches into dual-band
audio files using the existing Visual Audio tools/speak.py infrastructure.

Usage:
    from vamp_audio_export import VAMPAudioExporter
    
    exporter = VAMPAudioExporter()
    
    # Export memory batch with summary and full data
    exporter.export_batch(
        summary="User prefers local LLMs",
        data={"user": {"preferences": {"inference": "local"}}},
        output_path="memory_batch.wav"
    )
"""

import json
import os
import subprocess
import tempfile
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


class VAMPAudioExporter:
    """
    Export Visual Audio Memory Palace (VAMP) knowledge to dual-band audio.
    
    Generates dual-band WAV files with:
    - Phoneme band (500-3000Hz): Human-readable summaries
    - Byte band (4000-8000Hz): Full structured JSON data
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize VAMP audio exporter.
        
        Args:
            project_root: Path to Visual Audio project root. If None, auto-detects.
        """
        if project_root is None:
            # Auto-detect project root from this file's location
            self.project_root = Path(__file__).parent.parent
        else:
            self.project_root = Path(project_root)
        
        self.speak_py = self.project_root / "tools" / "speak.py"
        
        if not self.speak_py.exists():
            raise FileNotFoundError(f"speak.py not found at {self.speak_py}")
    
    def export_batch(
        self,
        summary: str,
        data: Dict[str, Any],
        output_path: str,
        use_ecc: bool = False
    ) -> Dict[str, Any]:
        """
        Export a memory batch to dual-band audio.
        
        Args:
            summary: Human-readable summary for phoneme encoding
            data: Full structured data for byte encoding
            output_path: Path for output WAV file
            use_ecc: Whether to add Reed-Solomon error correction
        
        Returns:
            Dict with export metadata:
                - duration: Audio duration in seconds
                - summary_length: Length of summary text
                - data_length: Length of encoded data in bytes
                - data_hash: MD5 hash of encoded data
                - crc_check: Whether CRC verification passed (if available)
        """
        # Create temporary files
        with tempfile.NamedTemporaryFile(mode='w', suffix='_summary.txt', delete=False) as f:
            f.write(summary)
            summary_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='_data.json', delete=False) as f:
            json.dump(data, f)
            data_file = f.name
        
        try:
            # Build command
            cmd = [
                'python3', str(self.speak_py), 'encode_dual',
                '-t', summary_file,
                '-b', data_file,
                '-o', output_path
            ]
            
            if use_ecc:
                cmd.append('--ecc')
            
            # Execute encoding
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, cwd=str(self.project_root)
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Encoding failed: {result.stderr}")
            
            # Parse output for metadata
            metadata = self._parse_speak_output(result.stdout)
            
            # Add additional metadata
            metadata['summary_length'] = len(summary)
            metadata['data_length'] = len(json.dumps(data))
            
            # Calculate data hash
            data_str = json.dumps(data, sort_keys=True)
            metadata['data_hash'] = hashlib.md5(data_str.encode()).hexdigest()
            
            return metadata
            
        finally:
            # Clean up temporary files
            for f in [summary_file, data_file]:
                if os.path.exists(f):
                    os.unlink(f)
    
    def decode_batch(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        verify_crc: bool = True
    ) -> Dict[str, Any]:
        """
        Decode a dual-band audio file to recover data.
        
        Args:
            audio_path: Path to dual-band WAV file
            output_path: Path for decoded JSON output. If None, creates temp file.
            verify_crc: Whether to verify CRC (if available)
        
        Returns:
            Dict with decoded data and metadata:
                - data: Decoded structured data
                - data_hash: MD5 hash of decoded data
                - crc_check: CRC verification status (if available)
        """
        if output_path is None:
            output_path = tempfile.NamedTemporaryFile(suffix='_decoded.json', delete=False).name
        
        # Build command
        cmd = [
            'python3', str(self.speak_py), 'decode_dual',
            audio_path,
            '-b', output_path
        ]
        
        # Execute decoding
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, cwd=str(self.project_root)
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Decoding failed: {result.stderr}")
        
        # Read decoded data
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        # Calculate hash
        data_str = json.dumps(data, sort_keys=True)
        data_hash = hashlib.md5(data_str.encode()).hexdigest()
        
        # Parse output for metadata
        metadata = self._parse_speak_output(result.stdout)
        
        metadata['data'] = data
        metadata['data_hash'] = data_hash
        
        return metadata
    
    def _parse_speak_output(self, output: str) -> Dict[str, Any]:
        """Parse speak.py output for metadata."""
        metadata = {}
        
        lines = output.strip().split('\n')
        for line in lines:
            if 'Duration:' in line:
                # Extract duration: "Duration: 3.80s"
                duration_str = line.split('Duration:')[1].strip().rstrip('s')
                try:
                    metadata['duration'] = float(duration_str)
                except ValueError:
                    pass
            
            if 'CRC verification passed' in line:
                metadata['crc_check'] = True
            elif 'CRC verification failed' in line:
                metadata['crc_check'] = False
            
            if 'Phonemes:' in line:
                # Extract frequency info
                phonemes_info = line.split('Phonemes:')[1].strip()
                metadata['phoneme_band'] = phonemes_info
            
            if 'Bytes:' in line:
                # Extract frequency info
                bytes_info = line.split('Bytes:')[1].strip()
                metadata['byte_band'] = bytes_info
        
        return metadata
    
    def verify_roundtrip(
        self,
        summary: str,
        data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify that encoding and decoding preserves data exactly.
        
        Args:
            summary: Summary text to encode
            data: Data to encode
        
        Returns:
            Tuple of (success, verification_metadata)
        """
        with tempfile.NamedTemporaryFile(suffix='_verify.wav', delete=False) as f:
            wav_path = f.name
        
        try:
            # Encode
            encode_metadata = self.export_batch(
                summary=summary,
                data=data,
                output_path=wav_path
            )
            
            # Decode
            decode_metadata = self.decode_batch(wav_path)
            
            # Verify hashes match
            original_hash = hashlib.md5(
                json.dumps(data, sort_keys=True).encode()
            ).hexdigest()
            decoded_hash = decode_metadata['data_hash']
            
            success = (original_hash == decoded_hash)
            
            verification_metadata = {
                'encode_metadata': encode_metadata,
                'decode_metadata': decode_metadata,
                'original_hash': original_hash,
                'decoded_hash': decoded_hash,
                'hash_match': success
            }
            
            return success, verification_metadata
            
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


def main():
    """Demo of VAMP audio export functionality."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vamp_audio_export.py <summary.txt> <data.json> [output.wav]")
        print("\nDemo mode: python vamp_audio_export.py --demo")
        sys.exit(1)
    
    if sys.argv[1] == '--demo':
        # Demo mode
        print("VAMP Audio Export Demo")
        print("=" * 50)
        
        exporter = VAMPAudioExporter()
        
        # Create test data
        test_summary = "User prioritizes privacy and local inference"
        test_data = {
            "batch_id": "demo_batch_001",
            "timestamp": 1710655200,
            "facts": [
                {"statement": "User prefers Ollama over cloud APIs", "confidence": 0.95},
                {"statement": "Privacy is a core concern", "confidence": 0.90}
            ]
        }
        
        print(f"\nSummary: {test_summary}")
        print(f"Data: {json.dumps(test_data, indent=2)}")
        
        # Export
        output_path = "/tmp/vamp_demo_output.wav"
        print(f"\nExporting to: {output_path}")
        
        metadata = exporter.export_batch(
            summary=test_summary,
            data=test_data,
            output_path=output_path
        )
        
        print(f"\nExport metadata:")
        print(f"  Duration: {metadata.get('duration', 'N/A')}s")
        print(f"  Summary length: {metadata.get('summary_length', 'N/A')} chars")
        print(f"  Data length: {metadata.get('data_length', 'N/A')} bytes")
        print(f"  Data hash: {metadata.get('data_hash', 'N/A')}")
        
        # Verify roundtrip
        print("\nVerifying roundtrip...")
        success, verification = exporter.verify_roundtrip(test_summary, test_data)
        
        print(f"  Hash match: {verification['hash_match']}")
        print(f"  Original hash: {verification['original_hash']}")
        print(f"  Decoded hash: {verification['decoded_hash']}")
        
        if success:
            print("\n✓ Demo completed successfully!")
            print(f"  Audio file: {output_path}")
        else:
            print("\n✗ Roundtrip verification failed!")
            sys.exit(1)
    else:
        # Normal mode
        summary_file = sys.argv[1]
        data_file = sys.argv[2]
        output_path = sys.argv[3] if len(sys.argv) > 3 else "output.wav"
        
        exporter = VAMPAudioExporter()
        
        # Read inputs
        with open(summary_file, 'r') as f:
            summary = f.read().strip()
        
        with open(data_file, 'r') as f:
            data = json.load(f)
        
        # Export
        metadata = exporter.export_batch(summary, data, output_path)
        
        print(f"Exported to: {output_path}")
        print(f"Duration: {metadata.get('duration', 'N/A')}s")
        print(f"Data hash: {metadata.get('data_hash', 'N/A')}")


if __name__ == '__main__':
    main()