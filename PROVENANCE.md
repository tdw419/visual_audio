# Provenance System - Ed25519 Signed Utterances

## Overview

The provenance system ensures that the visual audio OS only executes commands from trusted sources by requiring Ed25519 digital signatures on utterances.

## Security Model

**Problem**: Without provenance, the daemon in live-mic mode would execute any utterance it can decode from any audio in range (the Eve problem). Any sound in the room could control the system.

**Solution**: Ed25519 public-key cryptography. Utterances are signed with a private key; the daemon verifies signatures against a trusted public key before applying operations.

## Architecture

### Key Generation

```bash
python3 tools/pixel_screen.py gen-keys [--key-dir <path>]
```

Creates:
- `pixel_os_private.pem` - Private signing key (keep secret!)
- `pixel_os_public.pem` - Public verification key (share with daemon)

### Creating Signed Utterances

```bash
python3 tools/pixel_screen.py utter "turn the screen blue" \
  --ops '[["fill","#1a3a8a"]]' \
  -o command.wav \
  --private-key keys/pixel_os_private.pem
```

Creates:
- `command.wav` - Dual-band utterance (narration + ops)
- `command.wav.sig` - Ed25519 signature file (base64-encoded)

### Verifying Utterances

**CLI mode:**
```bash
python3 tools/pixel_screen.py listen command.wav \
  --public-key keys/pixel_os_public.pem \
  --fb framebuffer.png
```

**Daemon mode:**
```bash
python3 tools/pixel_os_listener.py \
  --mode queue \
  --watch-dir ./voicebook/queue \
  --fb framebuffer.png \
  --provenance \
  --public-key keys/pixel_os_public.pem
```

## Implementation Details

### Signature Format

- **What gets signed**: The ops JSON payload (the actual command)
- **Algorithm**: Ed25519 (fast, secure, no padding overhead)
- **Encoding**: Base64 text file alongside WAV
- **File naming**: `command.wav` → `command.wav.sig`

### Verification Process

1. Check if `.sig` file exists alongside `.wav`
2. Load public key from trusted path
3. Load and decode signature from `.sig` file
4. Verify signature against ops JSON payload
5. Reject if missing, invalid, or tampered

### Error Cases

- **No signature file**: `WARNING - Rejected unsigned or invalid signature`
- **Invalid signature**: `✗ Invalid signature for file.wav`
- **Missing public key**: `parser.error("--provenance requires --public-key to be specified")`

## Testing

### Generate keys:
```bash
python3 tools/pixel_screen.py gen-keys
```

### Create signed utterance:
```bash
python3 -c "
import sys
sys.path.insert(0, 'tools')
from pixel_screen import utter
utter('green screen', [['fill', '#00ff00']], 'test.wav', 'keys/pixel_os_private.pem')
"
```

### Create unsigned utterance (should be rejected):
```bash
python3 -c "
import sys
sys.path.insert(0, 'tools')
from pixel_screen import utter
utter('blue screen', [['fill', '#0000ff']], 'unsigned.wav')
"
```

### Run daemon with provenance:
```bash
python3 tools/pixel_os_listener.py \
  --mode queue \
  --watch-dir test_queue \
  --fb test.png \
  --provenance \
  --public-key keys/pixel_os_public.pem
```

**Expected behavior:**
- Signed utterances: Applied successfully
- Unsigned utterances: Rejected with warning
- Modified ops: Signature verification fails

## Integration Points

### Pixel Screen (`tools/pixel_screen.py`)

**New functions:**
- `generate_keypair()` - Generate Ed25519 keypair
- `sign_utterance()` - Sign utterance with private key
- `verify_utterance()` - Verify utterance with public key

**Modified functions:**
- `utter()` - Optional `private_key_path` parameter for signing

**New CLI command:**
- `gen-keys` - Generate cryptographic keys

### Listener Daemon (`tools/pixel_os_listener.py`)

**New parameters:**
- `public_key_path` - Path to trusted public key

**New methods:**
- `_verify_signature()` - Verify utterance signatures

**Modified behavior:**
- `--provenance` flag now enforces signature verification
- Unsigned/invalid utterances are rejected before ops execution

## Security Properties

1. **Authentication**: Only private key holders can create valid utterances
2. **Integrity**: Any modification to ops breaks the signature
3. **Non-repudiation**: Signature proves who created the utterance
4. **Forward security**: Compromised daemon doesn't expose private keys
5. **Key rotation**: Public keys can be updated without breaking the system

## Future Enhancements

1. **Multiple trusted keys**: Support list of authorized public keys
2. **Timestamp validation**: Add expiration to signatures
3. **Policy enforcement**: Limit which ops each key can authorize
4. **Hardware signing**: Integrate with TPM/HSM for private key protection
5. **Revocation**: Add key revocation mechanism

## Relationship to 01_CODES.txt

This implementation addresses the core security concern from `/home/jericho/zion/docs/research/01_CODES.txt`:

> "ai powered nn analog hypervisor simulate computational ideas that is able to ai -> analog pixel device drivers / analog opcodes -> device -> daemon -> loop"

Before provenance, the daemon loop would accept any input. After provenance, the daemon only accepts authenticated commands, making autonomous and executable-opcode development safe.

## Testing Checklist

- ✅ Generate Ed25519 keypair
- ✅ Create signed utterances with private key
- ✅ Verify signatures with public key (CLI mode)
- ✅ Daemon rejects unsigned utterances with --provenance
- ✅ Daemon accepts signed utterances with --provenance
- ✅ Signature files stored alongside WAV files
- ✅ Modified ops break signature verification
- ✅ Integration with existing wordbase and tile system

## Status

✅ **IMPLEMENTED** - Ed25519-based provenance system is live and verified. The `--provenance` flag now provides real security, not just decoration.