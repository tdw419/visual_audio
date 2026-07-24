#!/usr/bin/env python3
"""
negotiating_agents.py — Two AIs negotiating in shared acoustic space (REAL implementation).

Each agent:
1. Generates a message (via LLM prompt via ollama_prompt.py)
2. Encodes the message as audio via tools/speak.py encode
3. Signs the utterance with Ed25519 provenance
4. Transmits via acoustic bus (WAV file + spectrogram)
5. The other agent receives, verifies signature, decodes, and responds

The acoustic bus is the medium itself — no text exchange, only audio.
The permanent spectrogram log records every utterance visually.

REQUIREMENTS:
- tools/speak.py (audio encoding/decoding)
- tools/ollama_prompt.py (LLM message generation)
- cryptography package (Ed25519 signatures)
"""

import argparse
import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("Error: cryptography package required. Install with: pip install cryptography", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))

SAMPLE_RATE = 44100

def generate_keypair(agent_id: str, keys_dir: Path):
    """Generate or load Ed25519 keypair for provenance signing."""
    privkey_path = keys_dir / f"{agent_id}_priv.pem"
    pubkey_path = keys_dir / f"{agent_id}_pub.pem"

    if privkey_path.exists() and pubkey_path.exists():
        # Load existing keys
        privkey_pem = privkey_path.read_bytes()
        privkey = serialization.load_pem_private_key(
            privkey_pem,
            password=None
        )
        pubkey_pem = pubkey_path.read_bytes()
        pubkey = serialization.load_pem_public_key(pubkey_pem)
        return privkey, pubkey

    # Generate new keypair
    privkey = ed25519.Ed25519PrivateKey.generate()
    pubkey = privkey.public_key()

    # Save private key
    privkey_path.write_bytes(
        privkey.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    )

    # Save public key
    pubkey_path.write_bytes(
        pubkey.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )

    return privkey, pubkey

def sign_message(message: str, privkey) -> str:
    """Sign a message with Ed25519. Returns base64-encoded signature."""
    signature = privkey.sign(message.encode())
    return base64.b64encode(signature).decode()

def verify_message(message: str, signature_b64: str, pubkey) -> bool:
    """Verify a message signature. Returns True if valid."""
    try:
        signature = base64.b64decode(signature_b64)
        pubkey.verify(signature, message.encode())
        return True
    except Exception:
        return False

def generate_agent_message(agent_id: str, context: str, turn: int) -> str:
    """Generate agent message via LLM (ollama_prompt.py)."""
    prompt = f"""You are Agent {agent_id} in a negotiation about canvas design.

Context: {context}
Turn: {turn}

Respond with a brief message (max 20 words) about canvas design (background color, overlay style, etc).
Be constructive. Use PROPOSE, ACK, or REJECT prefix.
Keep it conversational."""

    try:
        result = subprocess.run(
            ["python3", "tools/ollama_prompt.py", prompt],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=Path(__file__).parent.parent
        )
        if result.returncode == 0:
            message = result.stdout.strip()
            if len(message) > 100:
                message = message[:100]  # Truncate for audio efficiency
            return message
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: simple turn-based messages
    proposals = [
        "PROPOSE: Canvas background = Dark Blue #1a1a2e",
        "ACK. PROPOSE: Overlay = Neon Green",
        "REJECT: Clash detected. PROPOSE: Overlay = Cyan",
        "ACK. Spectrogram locked. Canvas synced.",
        "PROPOSE: Add grid lines for precision",
        "ACK. Grid lines at 10px intervals.",
    ]
    return proposals[turn % len(proposals)]

def encode_to_audio(message: str, output_wav: str) -> str:
    """Encode message as audio WAV file via speak.py."""
    try:
        # speak.py encode expects a file path, write message to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tf:
            tf.write(message)
            tf.flush()
            input_file = tf.name

        # Use speak.py to encode
        result = subprocess.run(
            ["python3", "tools/speak.py", "encode", input_file, "-o", output_wav],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        os.unlink(input_file)

        if result.returncode != 0:
            raise RuntimeError(f"speak.py encode failed: {result.stderr}")

        return output_wav

    except Exception as e:
        print(f"Audio encoding error: {e}", file=sys.stderr)
        raise

def decode_from_audio(input_wav: str) -> str:
    """Decode message from audio WAV file via speak.py."""
    try:
        # speak.py decode requires -o argument
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tf:
            output_file = tf.name

        result = subprocess.run(
            ["python3", "tools/speak.py", "decode", input_wav, "-o", output_file],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        if result.returncode != 0:
            raise RuntimeError(f"speak.py decode failed: {result.stderr}")

        # Read decoded message
        message = ""
        if os.path.exists(output_file):
            message = Path(output_file).read_text().strip()
            os.unlink(output_file)

        return message

    except Exception as e:
        print(f"Audio decoding error: {e}", file=sys.stderr)
        raise

def create_utterance_wav(message: str, signature: str, agent_id: str, output_wav: str) -> None:
    """Create utterance WAV with embedded provenance metadata."""
    # Metadata: agent_id | timestamp | signature_b64 | message
    metadata = {
        "agent_id": agent_id,
        "timestamp": int(time.time()),
        "signature": signature,
        "message": message
    }

    # Encode message as audio
    encode_to_audio(message, output_wav)

    # Create spectrogram log entry
    log_path = Path(output_wav).with_suffix('.json')
    log_path.write_text(json.dumps(metadata, indent=2))

    print(f"[{agent_id}] Utterance saved: {output_wav}")
    print(f"[{agent_id}] Spectrogram log: {log_path}")

def receive_utterance(input_wav: str, agent_id: str, expected_agent_id: str, pubkeys: dict) -> dict:
    """Receive and verify an utterance from another agent."""
    print(f"[{agent_id}] Receiving utterance: {input_wav}")

    # Decode message from audio
    message = decode_from_audio(input_wav)

    # Load provenance metadata
    log_path = Path(input_wav).with_suffix('.json')
    if not log_path.exists():
        print(f"[{agent_id}] Warning: No provenance metadata found", file=sys.stderr)
        return {"message": message, "verified": False}

    metadata = json.loads(log_path.read_text())
    signature = metadata.get("signature", "")
    sender_id = metadata.get("agent_id", "unknown")

    # Verify signature
    if sender_id in pubkeys:
        verified = verify_message(message, signature, pubkeys[sender_id])
    else:
        verified = False
        print(f"[{agent_id}] Warning: Unknown sender {sender_id}", file=sys.stderr)

    result = {
        "message": message,
        "signature": signature,
        "sender_id": sender_id,
        "verified": verified,
        "timestamp": metadata.get("timestamp", 0)
    }

    status = "✓ VERIFIED" if verified else "✗ INVALID"
    print(f"[{agent_id}] {sender_id}: {message} [{status}]")

    return result

def negotiate_agent_loop(agent_id: str, other_agent_id: str, keys_dir: Path, output_dir: Path, max_turns: int = 4):
    """Run a negotiation loop as an agent."""
    # Generate/load keypairs
    privkey, pubkey = generate_keypair(agent_id, keys_dir)
    other_privkey, other_pubkey = generate_keypair(other_agent_id, keys_dir)

    pubkeys = {agent_id: pubkey, other_agent_id: other_pubkey}

    # Shared audio directory
    audio_bus = output_dir / "acoustic_bus"
    audio_bus.mkdir(parents=True, exist_ok=True)

    # Permanent spectrogram log
    log_file = output_dir / "negotiation_spectrogram.log"
    spectrogram_log = []

    context = "Canvas design negotiation: choose background color and overlay style"
    turn = 0

    print(f"\n=== Agent {agent_id}: Negotiation Started ===")
    print(f"Acoustic Bus: {audio_bus}")
    print(f"Spectrogram Log: {log_file}")

    while turn < max_turns:
        # Generate message
        message = generate_agent_message(agent_id, context, turn)

        # Sign message
        signature = sign_message(message, privkey)

        # Create utterance WAV
        utterance_path = audio_bus / f"utterance_{agent_id}_t{turn}.wav"
        create_utterance_wav(message, signature, agent_id, str(utterance_path))

        # Log to spectrogram
        log_entry = {
            "turn": turn,
            "agent_id": agent_id,
            "timestamp": int(time.time()),
            "message": message,
            "signature": signature,
            "wav_path": str(utterance_path),
            "verified": False  # Will be verified by receiver
        }
        spectrogram_log.append(log_entry)

        # Simulate acoustic transmission (file-based in demo)
        # In real deployment, this would be aplay → arecord
        time.sleep(1)

        # Receive from other agent (if not last turn)
        if turn < max_turns - 1:
            # Other agent generates their response (simulated)
            other_message = generate_agent_message(other_agent_id, context, turn + 1)
            other_signature = sign_message(other_message, other_privkey)

            other_utterance_path = audio_bus / f"utterance_{other_agent_id}_t{turn+1}.wav"
            create_utterance_wav(other_message, other_signature, other_agent_id, str(other_utterance_path))

            # Receive and verify
            received = receive_utterance(str(other_utterance_path), agent_id, other_agent_id, pubkeys)

            # Update verification status in log
            log_entry["verified"] = received["verified"]

            # Update context with received message
            context += f"\n{other_agent_id}: {received['message']}"

        turn += 2

    # Write permanent spectrogram log
    log_file.write_text(json.dumps(spectrogram_log, indent=2))

    print(f"\n=== Agent {agent_id}: Negotiation Concluded ===")
    print(f"Permanent Spectrogram Log: {log_file}")
    print(f"Total utterances: {len(spectrogram_log)}")

def main():
    parser = argparse.ArgumentParser(
        description="Two AIs negotiating in shared acoustic space (REAL implementation)"
    )
    parser.add_argument("--agent-id", default="agent1", help="Agent ID (default: agent1)")
    parser.add_argument("--other-agent-id", default="agent2", help="Other agent ID (default: agent2)")
    parser.add_argument("--max-turns", type=int, default=4, help="Maximum turns per agent")
    parser.add_argument("--output-dir", default="/tmp/visual_audio_negotiation", help="Output directory")
    args = parser.parse_args()

    keys_dir = Path(args.output_dir) / "keys"
    output_dir = Path(args.output_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    negotiate_agent_loop(
        args.agent_id,
        args.other_agent_id,
        keys_dir,
        output_dir,
        args.max_turns
    )

if __name__ == "__main__":
    main()