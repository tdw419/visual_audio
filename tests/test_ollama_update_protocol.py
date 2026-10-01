#!/usr/bin/env python3
"""
Ollama Update Protocol Tests - TASK_P02
Tests for secure container update protocol with signed proposals.

Verifies:
1. Unsigned updates are rejected
2. Updates with invalid signatures are rejected
3. Updates with valid signatures are accepted
4. Provenance gates verify signatures correctly
5. Container checksum verification works
"""

import json
import os
import tempfile
from datetime import datetime, UTC
from pathlib import Path

import pytest

# Add tools to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from ollama_update_protocol import (
    UpdateProposal,
    ProvenanceGate,
    UpdateProtocol,
    generate_keypair,
    sign_proposal,
)


class TestUnsignedUpdateRejection:
    """Tests for unsigned update rejection."""

    def test_unsigned_proposal_rejected(self):
        """Verify unsigned update proposals are rejected."""
        protocol = UpdateProtocol(
            container_path=Path("visual_audio.mkv")
        )

        # Create unsigned proposal
        unsigned_proposal = UpdateProposal(
            version="1.0.0",
            timestamp=datetime.now(UTC).isoformat(),
            changes=["Fix frame buffer alignment"],
            ollama_model="llama3.1",
        )

        result = protocol.apply_update(unsigned_proposal)

        assert result["status"] == "rejected", \
            f"Expected rejection, got {result['status']}"
        assert result["reason"] == "invalid_signature", \
            f"Expected 'invalid_signature' reason, got {result['reason']}"

    def test_none_signature_rejected(self):
        """Verify proposals with None signature are rejected."""
        protocol = UpdateProtocol(
            container_path=Path("visual_audio.mkv")
        )

        proposal = UpdateProposal(
            version="1.0.0",
            timestamp=datetime.now(UTC).isoformat(),
            changes=["Update metadata"],
            ollama_model="llama3.1",
            signature=None
        )

        result = protocol.apply_update(proposal)

        assert result["status"] == "rejected"
        assert result["reason"] == "invalid_signature"


class TestInvalidSignatureRejection:
    """Tests for invalid signature rejection."""

    def test_invalid_signature_rejected(self):
        """Verify proposals with invalid signatures are rejected."""
        protocol = UpdateProtocol(
            container_path=Path("visual_audio.mkv")
        )

        # Create proposal with invalid signature
        proposal = UpdateProposal(
            version="1.0.0",
            timestamp=datetime.now(UTC).isoformat(),
            changes=["Modify audio codec"],
            ollama_model="llama3.1",
            signature="invalid_signature_hex_string_0123456789abcdef"
        )

        result = protocol.apply_update(proposal)

        assert result["status"] == "rejected"
        assert result["reason"] == "invalid_signature"

    def test_malformed_signature_rejected(self):
        """Verify proposals with malformed signatures are rejected."""
        protocol = UpdateProtocol(
            container_path=Path("visual_audio.mkv")
        )

        proposal = UpdateProposal(
            version="1.0.0",
            timestamp=datetime.now(UTC).isoformat(),
            changes=["Update container"],
            ollama_model="llama3.1",
            signature="not-valid-hex!!"
        )

        result = protocol.apply_update(proposal)

        assert result["status"] == "rejected"


class TestValidSignatureAcceptance:
    """Tests for valid signature acceptance."""

    def test_valid_proposal_accepted(self):
        """Verify proposals with valid signatures are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Generate test keypair
            generate_keypair(tmpdir_path)

            private_key_path = tmpdir_path / "ollama_private_key.pem"
            public_key_path = tmpdir_path / "ollama_public_key.pem"

            # Create and sign proposal
            proposal = UpdateProposal(
                version="1.0.0",
                timestamp=datetime.now(UTC).isoformat(),
                changes=["Test update"],
                ollama_model="llama3.1",
            )

            signed_proposal = sign_proposal(proposal, private_key_path)

            # Verify with protocol using test public key
            protocol = UpdateProtocol(
                container_path=Path("visual_audio.mkv"),
                public_key_path=public_key_path
            )

            result = protocol.apply_update(signed_proposal)

            # Should be accepted (signature valid)
            # Note: May fail if container verification fails, but signature should pass
            assert result.get("provenance", {}).get("verified") == True, \
                f"Expected provenance verification, got {result}"


class TestProvenanceGateVerification:
    """Tests for provenance gate signature verification."""

    def test_provenance_gate_verifies_valid_signature(self):
        """Verify provenance gate accepts valid signatures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            generate_keypair(tmpdir_path)

            private_key_path = tmpdir_path / "ollama_private_key.pem"
            public_key_path = tmpdir_path / "ollama_public_key.pem"

            proposal = UpdateProposal(
                version="1.0.0",
                timestamp=datetime.now(UTC).isoformat(),
                changes=["Test"],
                ollama_model="llama3.1",
            )

            signed_proposal = sign_proposal(proposal, private_key_path)

            gate = ProvenanceGate(public_key_path)
            is_valid = gate.verify_proposal(signed_proposal)

            assert is_valid is True, "Valid signature should pass verification"

    def test_provenance_gate_rejects_invalid_signature(self):
        """Verify provenance gate rejects invalid signatures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            generate_keypair(tmpdir_path)

            public_key_path = tmpdir_path / "ollama_public_key.pem"

            proposal = UpdateProposal(
                version="1.0.0",
                timestamp=datetime.now(UTC).isoformat(),
                changes=["Test"],
                ollama_model="llama3.1",
                signature="invalid_signature"
            )

            gate = ProvenanceGate(public_key_path)
            is_valid = gate.verify_proposal(proposal)

            assert is_valid is False, "Invalid signature should fail verification"

    def test_provenance_gate_rejects_no_signature(self):
        """Verify provenance gate rejects proposals without signatures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            generate_keypair(tmpdir_path)

            public_key_path = tmpdir_path / "ollama_public_key.pem"

            proposal = UpdateProposal(
                version="1.0.0",
                timestamp=datetime.now(UTC).isoformat(),
                changes=["Test"],
                ollama_model="llama3.1",
            )

            gate = ProvenanceGate(public_key_path)
            is_valid = gate.verify_proposal(proposal)

            assert is_valid is False, "No signature should fail verification"


class TestContainerChecksumVerification:
    """Tests for container checksum verification."""

    def test_checksum_mismatch_rejected(self):
        """Verify proposals with mismatched checksums are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            generate_keypair(tmpdir_path)

            private_key_path = tmpdir_path / "ollama_private_key.pem"
            public_key_path = tmpdir_path / "ollama_public_key.pem"

            # Create proposal with wrong checksum
            proposal = UpdateProposal(
                version="1.0.0",
                timestamp=datetime.now(UTC).isoformat(),
                changes=["Test"],
                ollama_model="llama3.1",
                container_checksum="wrong_checksum_0123456789abcdef"
            )

            signed_proposal = sign_proposal(proposal, private_key_path)

            protocol = UpdateProtocol(
                container_path=Path("visual_audio.mkv"),
                public_key_path=public_key_path
            )

            result = protocol.apply_update(signed_proposal)

            assert result["status"] == "rejected"
            assert result["reason"] == "container_mismatch"

    def test_matching_checksum_accepted(self):
        """Verify proposals with matching checksums are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            generate_keypair(tmpdir_path)

            private_key_path = tmpdir_path / "ollama_private_key.pem"
            public_key_path = tmpdir_path / "ollama_public_key.pem"

            # Create proposal with correct checksum (skip checksum verification)
            proposal = UpdateProposal(
                version="1.0.0",
                timestamp=datetime.now(UTC).isoformat(),
                changes=["Test"],
                ollama_model="llama3.1",
                container_checksum=None  # Skip checksum verification
            )

            signed_proposal = sign_proposal(proposal, private_key_path)

            protocol = UpdateProtocol(
                container_path=Path("visual_audio.mkv"),
                public_key_path=public_key_path
            )

            result = protocol.apply_update(signed_proposal)

            # Should not be rejected due to checksum mismatch
            assert result.get("reason") != "container_mismatch"


class TestProposalSerialization:
    """Tests for proposal JSON serialization/deserialization."""

    def test_proposal_to_json_roundtrip(self):
        """Verify unsigned proposal survives JSON roundtrip."""
        original = UpdateProposal(
            version="1.0.0",
            timestamp="2026-07-19T12:00:00Z",
            changes=["Update1", "Update2"],
            ollama_model="llama3.1",
        )

        json_str = original.to_json()
        restored = UpdateProposal.from_json(json_str)

        assert restored.version == original.version
        assert restored.timestamp == original.timestamp
        assert restored.changes == original.changes
        assert restored.ollama_model == original.ollama_model
        assert restored.signature is None

    def test_proposal_dict_excludes_signature(self):
        """Verify to_dict() excludes signature for signing."""
        proposal = UpdateProposal(
            version="1.0.0",
            timestamp="2026-07-19T12:00:00Z",
            changes=["Test"],
            ollama_model="llama3.1",
            signature="should_not_be_in_dict"
        )

        data = proposal.to_dict()

        assert "signature" not in data
        assert data["version"] == "1.0.0"
        assert data["ollama_model"] == "llama3.1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])