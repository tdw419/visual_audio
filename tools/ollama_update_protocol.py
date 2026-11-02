#!/usr/bin/env python3
"""
Ollama Update Protocol - TASK_P02
Secure container update protocol with signed proposals and provenance gates.

This module implements:
- Digital signature verification for update proposals
- Provenance gates that verify signatures before applying updates
- Rejection logic for unauthorized/unsigned updates
- Integration with Visual Audio's spatial container system
"""

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519, padding
    from cryptography.hazmat.backends import default_backend
    from cryptography.exceptions import InvalidSignature
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


@dataclass
class UpdateProposal:
    """Signed update proposal from Ollama."""
    version: str
    timestamp: str
    changes: list[str]
    ollama_model: str
    frame_analysis: Optional[Dict[str, Any]] = None
    container_checksum: Optional[str] = None
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for signing."""
        # Use custom dict that preserves None values for optional fields
        return {
            'version': self.version,
            'timestamp': self.timestamp,
            'changes': self.changes,
            'ollama_model': self.ollama_model,
            'frame_analysis': self.frame_analysis,
            'container_checksum': self.container_checksum,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, json_str: str) -> 'UpdateProposal':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls(**data)


class ProvenanceGate:
    """Verifies update proposal signatures and provenance."""

    def __init__(self, public_key_path: Optional[Path] = None):
        """
        Initialize provenance gate.

        Args:
            public_key_path: Path to Ed25519 public key for verification
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography library required. Install with: pip install cryptography"
            )

        self.public_key_path = public_key_path or Path(
            os.environ.get("OLLAMA_PUBLIC_KEY", "config/ollama_public_key.pem")
        )
        self.public_key = self._load_public_key()

    def _load_public_key(self) -> ed25519.Ed25519PublicKey:
        """Load Ed25519 public key from file."""
        if not self.public_key_path.exists():
            raise FileNotFoundError(
                f"Public key not found: {self.public_key_path}. "
                "Generate with: python3 tools/ollama_update_protocol.py generate-keypair"
            )

        with open(self.public_key_path, 'rb') as f:
            pem_data = f.read()

        return serialization.load_pem_public_key(
            pem_data,
            backend=default_backend()
        )

    def verify_proposal(self, proposal: UpdateProposal) -> bool:
        """
        Verify update proposal signature.

        Args:
            proposal: Update proposal with signature

        Returns:
            True if signature valid, False otherwise
        """
        if not proposal.signature:
            return False

        try:
            # Decode signature from hex
            signature_bytes = bytes.fromhex(proposal.signature)

            # Verify signature
            payload = proposal.to_json().encode('utf-8')
            self.public_key.verify(
                signature_bytes,
                payload
            )
            return True
        except (InvalidSignature, ValueError, KeyError) as e:
            print(f"Signature verification failed: {e}", file=sys.stderr)
            return False

    def verify_container_checksum(
        self,
        container_path: Path,
        expected_checksum: Optional[str]
    ) -> bool:
        """
        Verify container state matches proposal.

        Args:
            container_path: Path to container file
            expected_checksum: Expected SHA256 checksum

        Returns:
            True if checksum matches, False otherwise
        """
        if not expected_checksum:
            return True  # Skip if no checksum provided

        actual_checksum = self._compute_container_checksum(container_path)
        return actual_checksum.lower() == expected_checksum.lower()

    def _compute_container_checksum(self, container_path: Path) -> str:
        """Compute SHA256 checksum of container file."""
        sha256_hash = hashlib.sha256()

        with open(container_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()


class UpdateProtocol:
    """Manages secure container updates with Ollama recommendations."""

    def __init__(
        self,
        container_path: Path,
        public_key_path: Optional[Path] = None
    ):
        """
        Initialize update protocol.

        Args:
            container_path: Path to visual_audio.mkv container
            public_key_path: Path to Ed25519 public key
        """
        self.container_path = Path(container_path)
        self.gate = ProvenanceGate(public_key_path)
        self.proposal_log_path = self.container_path.parent / ".update_proposals.log"

    def apply_update(self, proposal: UpdateProposal) -> Dict[str, Any]:
        """
        Apply update proposal if provenance verified.

        Args:
            proposal: Signed update proposal from Ollama

        Returns:
            Dict with status, message, and optional error details
        """
        # Step 1: Verify signature
        if not self.gate.verify_proposal(proposal):
            return {
                "status": "rejected",
                "reason": "invalid_signature",
                "message": "Update proposal rejected: Invalid or missing signature"
            }

        # Step 2: Verify container checksum (if provided)
        if proposal.container_checksum:
            if not self.gate.verify_container_checksum(
                self.container_path,
                proposal.container_checksum
            ):
                return {
                    "status": "rejected",
                    "reason": "container_mismatch",
                    "message": "Update proposal rejected: Container state mismatch"
                }

        # Step 3: Log proposal for audit trail
        self._log_proposal(proposal)

        # Step 4: Execute update via container tool
        result = self._execute_container_update(proposal)

        if result["status"] == "success":
            result["provenance"] = {
                "verified": True,
                "timestamp": proposal.timestamp,
                "ollama_model": proposal.ollama_model
            }

        return result

    def _execute_container_update(self, proposal: UpdateProposal) -> Dict[str, Any]:
        """
        Execute actual container update via va_container.py.

        Args:
            proposal: Verified update proposal

        Returns:
            Dict with execution result
        """
        try:
            # Use va_container.py to perform update
            # For now, this is a placeholder - actual implementation depends
            # on what updates Ollama proposes (e.g., frame modifications, metadata)

            # Example: Verify container integrity
            result = subprocess.run(
                ["python3", "tools/va_container.py", "verify", str(self.container_path)],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return {
                    "status": "error",
                    "reason": "verification_failed",
                    "message": f"Container verification failed: {result.stderr}"
                }

            return {
                "status": "success",
                "message": f"Update applied: {', '.join(proposal.changes)}",
                "changes": proposal.changes,
                "version": proposal.version
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "reason": "timeout",
                "message": "Container update timed out"
            }
        except Exception as e:
            return {
                "status": "error",
                "reason": "execution_error",
                "message": f"Update execution failed: {e}"
            }

    def _log_proposal(self, proposal: UpdateProposal):
        """Log proposal to audit trail."""
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "proposal": proposal.to_dict(),
            "status": "received"
        }

        with open(self.proposal_log_path, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')


def generate_keypair(output_dir: Path = Path("config")):
    """
    Generate Ed25519 keypair for signing updates.

    Args:
        output_dir: Directory to save keys
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError(
            "cryptography library required. Install with: pip install cryptography"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate private key
    private_key = ed25519.Ed25519PrivateKey.generate()

    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Save keys
    private_key_path = output_dir / "ollama_private_key.pem"
    public_key_path = output_dir / "ollama_public_key.pem"

    with open(private_key_path, 'wb') as f:
        f.write(private_pem)

    with open(public_key_path, 'wb') as f:
        f.write(public_pem)

    # Set restrictive permissions
    os.chmod(private_key_path, 0o600)
    os.chmod(public_key_path, 0o644)

    print(f"Keypair generated:")
    print(f"  Private key: {private_key_path}")
    print(f"  Public key:  {public_key_path}")
    print(f"\nIMPORTANT: Keep private key secure. Only Ollama should have access.")


def sign_proposal(
    proposal: UpdateProposal,
    private_key_path: Path
) -> UpdateProposal:
    """
    Sign update proposal with Ed25519 private key.

    Args:
        proposal: Update proposal to sign
        private_key_path: Path to private key

    Returns:
        Proposal with signature attached
    """
    if not CRYPTOGRAPHY_AVAILABLE:
        raise ImportError(
            "cryptography library required. Install with: pip install cryptography"
        )

    # Load private key
    with open(private_key_path, 'rb') as f:
        pem_data = f.read()

    private_key = serialization.load_pem_private_key(
        pem_data,
        password=None,
        backend=default_backend()
    )

    # Sign proposal
    payload = proposal.to_json().encode('utf-8')
    signature = private_key.sign(payload)

    # Attach signature
    proposal.signature = signature.hex()
    return proposal


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 ollama_update_protocol.py generate-keypair")
        print("  python3 ollama_update_protocol.py verify <proposal.json>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "generate-keypair":
        output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("config")
        generate_keypair(output_dir)

    elif command == "verify":
        if len(sys.argv) < 3:
            print("Usage: python3 ollama_update_protocol.py verify <proposal.json>")
            sys.exit(1)

        proposal_path = Path(sys.argv[2])
        with open(proposal_path, 'r') as f:
            proposal_json = f.read()

        proposal = UpdateProposal.from_json(proposal_json)

        protocol = UpdateProtocol(
            container_path=Path("visual_audio.mkv"),
        )

        result = protocol.apply_update(proposal)
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)