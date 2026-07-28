# Visual Audio Signed Boot vs Normal QEMU Linux VM

## TL;DR

| Normal QEMU VM | Visual Audio Signed Boot |
|----------------|---------------------------|
| Run `qemu-system-x86_64` directly | Decode audio, verify signature, then run QEMU |
| Command-line args are your source of truth | Boot instructions live inside a signed audio file |
| No provenance tracking | Ed25519 signature + timestamp = cryptographically verifiable authorization |
| Anyone with shell access can boot | Only holders of private key can authorize boots |
| Manual command-line configuration | Safe-gated manifest parser (allowlisted arches, bare filenames only) |

---

## Normal QEMU Linux VM

You run QEMU directly:

```bash
qemu-system-x86_64 \
  -M pc \
  -m 2048M \
  -enable-kvm \
  -vnc :1 \
  -device qxl-vga \
  -usb -device usb-tablet \
  -drive file=ubuntu.qcow2,format=qcow2
```

**Characteristics:**
- Command-line arguments are the entire specification
- No verification of who issued the command
- Shell history is your audit trail (if you're lucky)
- Anyone with access can run any QEMU command
- No constraints on images, architectures, or options

---

## Visual Audio Signed Boot

Boot instructions are encoded into an audio file with cryptographic provenance:

```python
# 1. Create a boot manifest
manifest = ["boot", "x86_64", "arch_desktop.qcow2", {"gui": True, "mem": "2048M"}]

# 2. Encode into signed dual-band audio
utter("Booting Arch Desktop", manifest, "boot.wav", "/tmp/key.pem")
# Output: boot.wav contains:
#   - Low band (500-3000Hz): "Booting Arch Desktop" (human voice)
#   - High band (4000-8000Hz): Signed binary payload (manifest)

# 3. Decode and verify
audio, sr = sf.read("boot.wav")
payload = decode_data_band(audio, sr, "/tmp/key.pub")  # Verifies Ed25519 signature
manifest = json.loads(payload)

# 4. Launch with safety gates
launch_boot(manifest, image_dir="boot_images")
# This:
#   - Validates architecture is allowlisted
#   - Resolves image to trusted directory (no path traversal)
#   - Builds safe QEMU argv
#   - Launches QEMU
```

**Characteristics:**
- **Provenance**: Ed25519 signature proves who authorized the boot
- **Timestamp**: Built into the signature, cannot be forged
- **Safety**: Manifest parser rejects anything not explicitly allowlisted
- **Auditability**: Every authorized boot is a signed artifact
- **Separation**: Audio transport layer is independent of execution layer

---

## Key Technical Differences

### 1. Transport Layer

| Normal QEMU | Visual Audio |
|-------------|--------------|
| Command-line or script | Dual-band audio encoding |
| Human-readable | Humans hear voice, machines decode data |
| No replay protection | Timestamped signatures prevent replay |

The high-band data channel (4000-8000Hz) uses **16-tone MFSK** (Multi-Frequency Shift Keying):
- 16 frequencies = 4 bits per symbol
- ~24 bytes/second throughput
- Survives voice mixing and playback

### 2. Provenance Chain

**Normal QEMU:**
```
User → Shell → QEMU (no proof of authorization)
```

**Visual Audio Signed Boot:**
```
User (private key) → Ed25519 signature → Audio payload →
Listener (public key) → Verify signature →
Boot manifest parser → Validate safety → QEMU
```

At each step, you can verify:
- Signature matches public key (cryptographic proof)
- Timestamp is recent (replay protection)
- Manifest passes all safety checks (no path traversal, allowlisted arch)

### 3. Safety Gates

`tools/boot_manifest.py` implements strict safety checks:

```python
def parse_boot_op(op):
    # 1. Validate structure
    if not (isinstance(op, list) and len(op) >= 3):
        raise BootManifestError("malformed boot op")

    # 2. Allowlisted architecture only
    if op[1] not in ARCH_QEMU:
        raise BootManifestError(f"disallowed arch: {op[1]}")

    # 3. Bare filename (no path traversal)
    if "/" in op[2] or op[2] in (".", ".."):
        raise BootManifestError("filename must be bare")

    # 4. Bios must be allowlisted
    if manifest.bios not in ALLOWED_BIOS:
        raise BootManifestError(f"disallowed bios: {manifest.bios}")
```

This prevents attacks like:
```json
["boot", "x86_64", "../../../etc/passwd", {"gui": true}]  # Rejected
["boot", "malicious", "exploit.img", {"bios": "/root/malicious.fw"}]  # Rejected
```

### 4. Boot Manifest vs Raw QEMU Args

**Normal QEMU (unconstrained):**
```bash
qemu-system-x86_64 \
  -drive file=../../../etc/passwd,readonly=on \
  -netdev user,id=net0,hostfwd=tcp::22-:22 \
  -serial file:/tmp/steal.log
```

**Visual Audio Boot (constrained manifest):**
```json
{
  "arch": "x86_64",
  "image": "ubuntu.qcow2",
  "gui": true,
  "mem": "2048M",
  "ports": ["2222:22"]  // Only explicit forwards allowed
}
```

The manifest parser maps safe fields to QEMU args:
- `arch` → validates against `ARCH_QEMU` allowlist
- `image` → resolves to `boot_images/<image>` (cannot escape)
- `mem` → passed to `-m` (prevents oversubscribing host)
- `ports` → maps to `-netdev user,hostfwd=...` (restricted format)

### 5. Replay Protection

**Normal QEMU:**
- Run command twice = boots twice
- No way to prove it wasn't replayed

**Visual Audio Signed Boot:**
```python
# Signature includes timestamp
timestamp = struct.pack("!Q", int(time.time()))
signature = private_key.sign(timestamp + payload)

# Verification checks timestamp is recent
payload_bytes = decode_data_band(audio, sr, pub_key_path)
timestamp = struct.unpack("!Q", payload_bytes[:8])[0]
if time.time() - timestamp > MAX_AGE_SECONDS:
    raise ValueError("signature too old - possible replay")
```

---

## Use Cases

### Normal QEMU

- Development/testing
- Local VMs on your own machine
- CI/CD pipelines (trusted environment)
- Quick ad-hoc boots

### Visual Audio Signed Boot

- **Air-gapped systems**: Encode boot commands to audio, play over trusted channel
- **Auditable operations**: Every boot is a signed artifact with provenance
- **Multi-operator workflows**: Different operators have different private keys
- **Compliance**: Cryptographic proof of who authorized what, when
- **Remote deployment**: Play audio over network/radio to remote systems

---

## Example Workflow Comparison

### Normal QEMU

```bash
# Admin runs command
$ qemu-system-x86_64 -drive file=ubuntu.qcow2,format=qcow2

# No provenance - was this authorized?
# Who ran it? When?
# Can we prove it wasn't tampered with?
# Shell history: maybe, but easily deleted or falsified
```

### Visual Audio Signed Boot

```bash
# Operator creates signed boot audio
$ python3 generate_signed_boot.py
# ✓ Signed with Ed25519 (64-byte signature + timestamp)
# Generated: boot_ubuntu.wav

# Audio is stored/distributed
$ cp boot_ubuntu.wav /shared/authorized_boots/

# Any system with the public key can verify and boot
$ python3 boot_single.py boot_ubuntu.wav /tmp/key.pub boot_images
# ✓ Signature verified (key ID: abc123...)
# ✓ Timestamp: 2026-07-25T09:30:00Z
# ✓ Manifest validated
# ✓ QEMU launched
```

**Audit trail:**
- `boot_ubuntu.wav` file contains cryptographic proof
- Anyone with `/tmp/key.pub` can verify
- Timestamp proves when it was signed
- Private key proves who signed it

---

## Performance Considerations

| Metric | Normal QEMU | Visual Audio Boot |
|--------|-------------|-------------------|
| Boot time | Same (both run same QEMU) | Same (QEMU runtime identical) |
| Setup time | ~1 second (type command) | ~5 seconds (encode/decode audio) |
| Provenance | None | Ed25519 verification (~1ms) |
| Bandwidth | Not applicable | 24 bytes/second (data channel) |
| Replay protection | None | Built-in (timestamp) |

The overhead is only in the **setup phase** (encoding/decoding). Once QEMU launches, it's identical to a normal VM.

---

## Security Properties

| Property | Normal QEMU | Visual Audio Boot |
|----------|-------------|-------------------|
| Integrity | Unverified | Ed25519 signature |
| Authenticity | Shell access required | Private key required |
| Non-repudiation | Shell logs (unreliable) | Cryptographic proof |
| Replay resistance | None | Timestamp validation |
| Input sanitization | None | Manifest parser with allowlists |
| Path traversal protection | None | Bare filename enforcement |

---

## When to Use Which

**Use Normal QEMU if:**
- You're the only operator on a trusted machine
- Speed of setup is critical
- You don't need audit trails
- Development/testing environment

**Use Visual Audio Signed Boot if:**
- Multiple operators with different access levels
- You need cryptographic provenance
- Boot commands are stored/transmitted
- Compliance requires auditability
- You want replay protection
- Remote/delegated boot authorization

---

## Summary

Normal QEMU is just a command you run. Visual Audio Signed Boot is a **provenance system**:

- Boot instructions are **signed artifacts**
- **Cryptographic verification** proves who authorized what, when
- **Safety gates** prevent accidental or malicious misuse
- **Dual-band audio** means humans can hear the intent while machines decode the payload
- **Replay protection** prevents old authorized boots from being replayed

The goal isn't to replace normal QEMU — it's to add a layer of **verifiable authorization** on top of it, for use cases where provenance and auditability matter.