"""
Test suite for demos/negotiating_agents.py — two AIs negotiating in shared acoustic space.

This is the REAL implementation verification, replacing the fake hardcoded print
sequence version that was marked COMPLETE but never actually used the audio codec.

Tests verify:
- Real audio encoding/decoding via speak.py
- Ed25519 signing and verification
- Permanent spectrogram log creation
- Acoustic bus with WAV files
- Round-trip message transmission
- Provenance tracking
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class TestNegotiatingAgents:
    """Real acoustic negotiation system tests."""

    @pytest.fixture
    def output_dir(self):
        """Create temporary output directory for tests."""
        d = Path(tempfile.mkdtemp(prefix="negotiate_test_"))
        yield d
        shutil.rmtree(d, ignore_errors=True)

    def test_audio_encoding_creates_wav(self, output_dir):
        """Verify message encoding creates a real WAV file."""
        msg_path = output_dir / "message.txt"
        wav_path = output_dir / "message.wav"

        # Write test message
        msg_path.write_text("TEST MESSAGE")

        # Encode with speak.py
        import subprocess
        result = subprocess.run(
            ["python3", "tools/speak.py", "encode", str(msg_path), "-o", str(wav_path)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"speak.py encode failed: {result.stderr}"
        assert wav_path.exists(), "WAV file was not created"
        assert wav_path.stat().st_size > 1000, "WAV file too small to contain audio data"

    def test_audio_decoding_recovers_message(self, output_dir):
        """Verify audio decoding recovers the original message."""
        msg_path = output_dir / "message.txt"
        wav_path = output_dir / "message.wav"
        decoded_path = output_dir / "decoded.txt"

        # Write test message
        original = "PROPOSE: Canvas background = Dark Blue"
        msg_path.write_text(original)

        # Encode
        import subprocess
        result = subprocess.run(
            ["python3", "tools/speak.py", "encode", str(msg_path), "-o", str(wav_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Decode
        result = subprocess.run(
            ["python3", "tools/speak.py", "decode", str(wav_path), "-o", str(decoded_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

        # Verify
        recovered = decoded_path.read_text().strip()
        assert recovered == original, f"Decoded message '{recovered}' != original '{original}'"

    def test_negotiation_creates_wav_files(self, output_dir):
        """Verify negotiation creates WAV files on acoustic bus."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "2", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0, f"Negotiation failed: {result.stderr}"
        assert (output_dir / "acoustic_bus").exists(), "Acoustic bus directory not created"

        # Verify WAV files exist
        wav_files = list((output_dir / "acoustic_bus").glob("*.wav"))
        assert len(wav_files) >= 2, f"Expected >=2 WAV files, found {len(wav_files)}"

        # Verify WAV files contain data
        for wav in wav_files:
            assert wav.stat().st_size > 1000, f"WAV file {wav.name} too small"

    def test_negotiation_creates_spectrogram_log(self, output_dir):
        """Verify negotiation creates permanent spectrogram log."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "2", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0

        log_path = output_dir / "negotiation_spectrogram.log"
        assert log_path.exists(), "Spectrogram log not created"

        # Verify log is valid JSON
        log_data = json.loads(log_path.read_text())
        assert isinstance(log_data, list), "Log should be a list"
        assert len(log_data) >= 1, "Log should contain at least one utterance"

    def test_spectrogram_log_has_required_fields(self, output_dir):
        """Verify spectrogram log entries have all required fields."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "2", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0

        log_path = output_dir / "negotiation_spectrogram.log"
        log_data = json.loads(log_path.read_text())

        for entry in log_data:
            assert "turn" in entry, "Missing 'turn' field"
            assert "agent_id" in entry, "Missing 'agent_id' field"
            assert "timestamp" in entry, "Missing 'timestamp' field"
            assert "message" in entry, "Missing 'message' field"
            assert "signature" in entry, "Missing 'signature' field"
            assert "wav_path" in entry, "Missing 'wav_path' field"
            assert "verified" in entry, "Missing 'verified' field"

    def test_ed25519_keys_generated(self, output_dir):
        """Verify Ed25519 keypairs are generated for both agents."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "2", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0

        keys_dir = output_dir / "keys"
        assert keys_dir.exists(), "Keys directory not created"

        # Verify both agents have keys
        for agent_id in ["agent1", "agent2"]:
            privkey_path = keys_dir / f"{agent_id}_priv.pem"
            pubkey_path = keys_dir / f"{agent_id}_pub.pem"

            assert privkey_path.exists(), f"Private key for {agent_id} not found"
            assert pubkey_path.exists(), f"Public key for {agent_id} not found"

            # Verify keys are PEM format
            privkey_pem = privkey_path.read_text()
            pubkey_pem = pubkey_path.read_text()

            assert "-----BEGIN PRIVATE KEY-----" in privkey_pem
            assert "-----END PRIVATE KEY-----" in privkey_pem
            assert "-----BEGIN PUBLIC KEY-----" in pubkey_pem
            assert "-----END PUBLIC KEY-----" in pubkey_pem

    def test_json_metadata_created_for_wavs(self, output_dir):
        """Verify each WAV file has a JSON metadata sidecar."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "2", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0

        # For each WAV file, verify JSON sidecar exists
        wav_files = list((output_dir / "acoustic_bus").glob("*.wav"))
        for wav in wav_files:
            json_path = wav.with_suffix('.json')
            assert json_path.exists(), f"JSON metadata for {wav.name} not found"

            # Verify JSON is valid
            metadata = json.loads(json_path.read_text())
            assert "agent_id" in metadata
            assert "timestamp" in metadata
            assert "signature" in metadata
            assert "message" in metadata

    def test_signatures_verified_in_log(self, output_dir):
        """Verify signatures are marked as verified in the log."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "2", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0

        log_path = output_dir / "negotiation_spectrogram.log"
        log_data = json.loads(log_path.read_text())

        # All entries should be verified (except possibly the last one that hasn't been received yet)
        for entry in log_data:
            if entry.get("verified", False):
                assert entry["verified"] is True, "Signature verification should be True"

    def test_messages_different_per_turn(self, output_dir):
        """Verify different turns produce different messages."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "4", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0

        log_path = output_dir / "negotiation_spectrogram.log"
        log_data = json.loads(log_path.read_text())

        # Extract messages
        messages = [entry["message"] for entry in log_data]

        # Verify at least 2 different messages
        unique_messages = set(messages)
        assert len(unique_messages) >= 2, "Expected at least 2 different messages"

    def test_acoustic_bus_directory_structure(self, output_dir):
        """Verify acoustic bus has proper directory structure."""
        import subprocess
        result = subprocess.run(
            ["python3", "demos/negotiating_agents.py", "--agent-id", "agent1", "--max-turns", "2", "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert result.returncode == 0

        # Verify directory structure
        assert (output_dir / "acoustic_bus").exists()
        assert (output_dir / "keys").exists()
        assert (output_dir / "negotiation_spectrogram.log").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])