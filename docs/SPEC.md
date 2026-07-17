# Visual Audio — Technical Specification

## Version
**Version**: 1.0  
**Date**: 2026-07-16  
**Status**: Living specification based on current implementation

---

## 1. Pixel Cartridge Format

### 1.1 Dense Pixel Encoding

Visual Audio uses 24-bit RGB pixels as the spatial storage medium. Each pixel carries exactly 3 bytes of data, one per color channel.

#### Byte-to-Pixel Mapping
```
Byte sequence: [b0, b1, b2, b3, b4, b5, ...]
Pixel array:   [(b0, b1, b2), (b3, b4, b5), ...]
```

- **Channel ordering**: Red = byte N, Green = byte N+1, Blue = byte N+2
- **Data type**: `uint8` per channel (0-255)
- **Padding**: Padded with zero bytes to multiple of 3 before pixel packing
- **Density**: 3 bytes per pixel (exactly, no compression)

#### PNG Structure
```python
# Dense cartridge PNG
format: RGB image, 8-bit per channel
metadata: {"framed_length": "<int>"}  # Original framed length for unpadding
arrangement: square grid (side = ceil(sqrt(n_pixels))) or single row
```

#### Example: Small Payload
```
Payload: "HELLO" (5 bytes)
Bytes:   0x48 0x45 0x4C 0x4C 0x4F
Padding: 0x00 (1 byte to reach multiple of 3)
Pixels:  (0x48,0x45,0x4C), (0x4C,0x4F,0x00)
Image:   2×1 PNG (or 2×2 square with padding pixels)
```

### 1.2 Frame Format

All payloads (both spectral and dense) use the same frame structure for integrity checking.

#### Unauthenticated Frame
```
Offset | Size | Field        | Description
-------|------|--------------|-----------------------------------
0      | 2    | MAGIC        | 0x55 0x41 ('UA')
2      | 2    | LENGTH       | uint16 big-endian, payload length
4      | N    | PAYLOAD      | Raw data bytes
4+N    | 4    | CRC32        | uint32 big-endian, CRC over payload
```

- **Maximum payload size**: 65535 bytes (uint16 limit)
- **CRC polynomial**: CRC-32 (IEEE 802.3)
- **Total overhead**: 8 bytes per frame

#### Authenticated Frame (Provenance)
```
Offset | Size | Field        | Description
-------|------|--------------|-----------------------------------
0      | 2    | MAGIC        | 0x56 0x41 ('VA')
2      | 2    | TOTAL_LEN    | uint16 big-endian, payload + sig + timestamp
4      | 2    | PAYLOAD_LEN  | uint16 big-endian, payload length
6      | N    | PAYLOAD      | Raw data bytes
6+N    | 64   | SIGNATURE    | Ed25519 signature over payload
70+N   | 8    | TIMESTAMP    | uint64 big-endian, Unix timestamp
78+N   | 4    | CRC32        | uint32 big-endian, CRC over (MAGIC+...+TIMESTAMP)
```

- **Signature algorithm**: Ed25519
- **Timestamp validity**: 300 seconds from creation
- **Maximum payload size**: 65535 bytes

### 1.3 Cartridge Execution

The dense cartridge format stores executable code that runs in the SandboxedExecutor.

#### Execution Flow
```
1. Decode PNG → framed bytes
2. Unframe → payload bytes (validate CRC/magic)
3. Decode payload as UTF-8 text (Python code)
4. Execute in SandboxedExecutor
5. Return ExecutionResult (stdout, stderr, exit code)
```

#### Python Cartridge Format
```python
# Cartridge payloads are UTF-8 encoded Python code
# Example cartridge payload:
def fibonacci(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print(f"Fibonacci(10) = {fibonacci(10)}")
```

---

## 2. Spectral Codec (MFSK) Specification

### 2.1 Physical Layer (16-Tone MFSK)

The spectral codec uses Multiple Frequency-Shift Keying with 16 equally-spaced tones.

#### Tone Parameters
```
Parameter          | Value
-------------------|---------------------
Number of tones    | 16 (0x0 to 0xF)
Base frequency     | 800.0 Hz
Frequency step     | 150.0 Hz
Maximum frequency  | 3050.0 Hz
Sample rate        | 44100 Hz
Symbol duration    | 20 ms
Symbols per second | 50
Raw throughput     | 25 bytes/sec (50 nibbles/sec ÷ 2 nibbles per byte)
Effective throughput| ~24 bytes/sec (with framing overhead)
```

#### Tone-to-Nibble Mapping
```
Nibble | Frequency (Hz) | Binary
-------|----------------|-------
0x0    | 800.0          | 0000
0x1    | 950.0          | 0001
0x2    | 1100.0         | 0010
...
0xE    | 2900.0         | 1110
0xF    | 3050.0         | 1111
```

Formula: `freq = 800.0 + nibble * 150.0`

### 2.2 Symbol Encoding

#### Byte-to-Symbol Conversion
```
Byte: 0xAB (171 decimal)
High nibble: 0xA → tone: 800 + 10*150 = 2300 Hz
Low nibble:  0xB → tone: 800 + 11*150 = 2450 Hz
Symbol sequence: [0xA, 0xB]
Audio: [20ms @ 2300 Hz] followed by [20ms @ 2450 Hz]
```

#### Symbol Decoding (Matched Filtering)
```
Analysis window: Center 50% of each 20ms symbol window
          (samples 0-221: ignore, samples 222-666: analyze, samples 667-882: ignore)
Method: Correlate window with 16 complex exponential templates
          probe[n, t] = exp(-2j * π * freq[n] * t)
Decision: Pick frequency with maximum correlation magnitude
```

### 2.3 Audio Framing

#### Frame Integration
```
Framed bytes → symbols → tone sequence → audio waveform

Example frame:
Framed:  UA 0x00 0x05 0x48 0x45 0x4C 0x4C 0x4F CRC (14 bytes)
Symbols: [0x5,0x5, 0x0,0x0, 0x0,0x5, 0x4,0x8, 0x4,0x5, 0x4,0xC, 0x4,0xC, 0x4,0xF, ...]
Audio:   20ms @ 1550Hz, 20ms @ 1550Hz, 20ms @ 800Hz, ...
```

### 2.4 Dual-Band Frequency Allocation

For true dual-band audio (human speech + machine data):

#### Frequency Bands
```
Band          | Frequency Range | Content
--------------|-----------------|-----------------------------
Low band      | 500 Hz - 3000 Hz| Phoneme codec (human speech)
High band     | 4000 Hz - 8000 Hz| Spectral codec (machine data)
Guard band    | 3000 Hz - 4000 Hz| No signal (prevents crosstalk)
```

#### Filterbank Specification
```
Low band filter:  Butterworth bandpass, 500-3000 Hz, order=6
High band filter: Butterworth bandpass, 4000-8000 Hz, order=6
Separation:      >10 dB midband rejection, <1% crosstalk
```

#### MFSK Frequency Offset for High Band
```
When encoding in high band:
Base frequency: 4000.0 Hz (instead of 800.0 Hz)
Frequency step: 150.0 Hz (unchanged)
Range: 4000-6250 Hz (fits within 4000-8000 Hz band)

Mapping: freq = 4000.0 + nibble * 150.0
```

---

## 3. Execution Model

### 3.1 SandboxedExecutor Architecture

The SandboxedExecutor provides defense-in-depth security for untrusted cartridges.

#### Security Layers
```
Layer 1: Import allowlist (blocks dangerous modules)
Layer 2: Resource limits (CPU, memory, wall time)
Layer 3: Environment isolation (stripped PATH, no internet)
Layer 4: Process isolation (subprocess with seccomp if available)
Layer 5: Output truncation (512KB stdout/stderr limits)
```

### 3.2 Resource Limits

| Resource | Limit | Enforcement |
|----------|-------|-------------|
| CPU time | 5 seconds | `setrlimit(RLIMIT_CPU)` |
| Wall time | 10 seconds | `subprocess.communicate(timeout)` |
| Memory | 64 MB | `setrlimit(RLIMIT_AS)` |
| Disk writes | 10 MB | Post-execution temp dir check |
| stdout/stderr | 512 KB each | Truncation |
| File descriptors | 16 | `setrlimit(RLIMIT_NOFILE)` |
| Processes | 1 | `setrlimit(RLIMIT_NPROC)` |

### 3.3 Import Allowlist

#### Allowed Modules (Safe, Read-Only)
```
math, random, statistics, datetime, collections
itertools, functools, re, string, hashlib
array, bisect, heapq, queue
unicodedata, textwrap, difflib
```

#### Blocked Modules (Dangerous)
```
os, sys, subprocess, shutil, pathlib, io
socket, urllib, http, ftplib, smtplib
pickle, shelve, marshal, eval, exec, compile
importlib, ctypes, multiprocessing, threading
signal, resource, pty, fcntl, termios
```

### 3.4 Environment Isolation

```
PYTHONPATH:      stripped (no site-packages access)
PYTHONNOUSERSITE: set to 1 (disable user site-packages)
PATH:            cleared (cannot execute external commands)
TMPDIR:          set to isolated temp directory
Stdin:           closed (DEV/null, no interactive input)
Working dir:     isolated temp directory
```

### 3.5 ExecutionResult Structure

```python
@dataclass
class ExecutionResult:
    success: bool              # True if exit code == 0 and not timed out
    returncode: int            # Process exit code
    stdout: str                # Captured stdout (truncated to 512KB)
    stderr: str                # Captured stderr (truncated to 512KB)
    timed_out: bool            # True if wall timeout exceeded
    killed_by_system: bool     # True if resource limit violated
    runtime_seconds: float     # Actual execution time
    error_message: Optional[str]  # Human-readable error if failed
```

### 3.6 Cartridge Execution API

```python
from src.executor.sandbox import execute_cartridge

# Execute cartridge payload
result = execute_cartridge(
    code="print('Hello, World!')",
    timeout=10.0,
    allowlist=['math', 'statistics']
)

if result.success:
    print("Output:", result.stdout)
else:
    print("Error:", result.error_message)
```

---

## 4. Opcode Mapping (Future: Geometry OS Integration)

### 4.1 Current Cartridge Format

Currently, cartridges contain Python source code (UTF-8 encoded) that executes in the SandboxedExecutor.

### 4.2 Future: Spatial Opcode Mapping

For Geometry OS integration, cartridges will encode spatial opcodes directly in pixels.

#### Opcode Format (Planned)
```
Opcode structure: [OPCODE, X, Y, ARG1, ARG2, ...]
Pixel encoding:  Each opcode parameter = 1 RGB pixel (3 bytes)
Example: ["spatial_set", 100, 50, 0xFF0000]
Pixels:  (OP_pixel1, OP_pixel2, OP_pixel3),   # OPCODE bytes
         (X_px1, X_px2, X_px3),              # X coordinate
         (Y_px1, Y_px2, Y_px3),              # Y coordinate
         (R_px1, R_px2, R_px3),              # Color (0xFF)
         (G_px1, G_px2, G_px3),              # Color (0x00)
         (B_px1, B_px2, B_px3)               # Color (0x00)
```

#### Opcode Registry (Planned)
```
0x01: spatial_set(x, y, color)    # Set pixel at (x,y) to color
0x02: spatial_copy(src, dst)      # Copy region from src to dst
0x03: spatial_clear(region)       # Clear region to black
0x04: spatial_execute(start)      # Begin execution at address
...
```

### 4.3 Execution Flow (Planned)

```
1. Decode PNG → pixel array
2. Parse pixel stream into opcode sequence
3. Validate opcode signatures
4. Execute opcodes in spatial hypervisor
5. Return spatial state changes
```

---

## 5. Error Correction

### 5.1 Reed-Solomon Over Symbol Sequences

#### ECC Parameters
```
Data bytes: 1 byte per codeword
Parity bytes: 2 bytes per codeword (XOR-based for simplicity)
Correction capability: ~5 byte errors per payload (~5% corruption)
```

#### Encoding Scheme
```
For each data byte chunk:
  chunk = [b0, b1, ..., bn]
  parity1 = XOR(b0, b1, ..., bn)
  parity2 = SUM(b0, b1, ..., bn) mod 256
  encoded = [b0, b1, ..., bn, parity1, parity2]
```

### 5.2 Dense Pixel ECC

#### Parity Blocks
```
Dense cartridge arranged in blocks (e.g., 8×8 pixel blocks)
Parity block computed per block
Single-bit errors detected and recoverable
```

---

## 6. Phoneme Codec Specifications

### 6.1 Phoneme Templates

#### ARPAbet Phonemes
```
39 ARPAbet phonemes mapped to UPIC-style frequency envelopes

Example mappings:
AA  (odd)    → envelope: formant_1=700Hz, formant_2=1100Hz, duration=20ms
AE  (at)     → envelope: formant_1=600Hz, formant_2=1800Hz, duration=20ms
AH  (hut)    → envelope: formant_1=700Hz, formant_2=1200Hz, duration=20ms
...
```

### 6.2 Word-to-Phoneme Mapping

#### CMUdict Integration
```
Word lookup: "hello" → ["HH", "AH", "L", "OW"]
Phoneme sequence → UPIC envelopes → audio waveform
Synthesis: 20ms per phoneme symbol
Throughput: ~7.6 words per second (average word = 5 phonemes)
```

### 6.3 Coarticulation

#### 5ms Crossfade
```
Transition between phonemes:
  - Overlap last 5ms of phoneme N with first 5ms of phoneme N+1
  - Linear amplitude crossfade
  - Prevents robotic gaps between phonemes
```

### 6.4 Prosody

#### Emphasis (Amplitude Modulation)
```
Syntax: ["word", "EMPHASIS", x, y, color]
Effect: Increase amplitude by 20% during phoneme synthesis
Metadata: Store emphasis flags in wordbase for consistent playback
```

#### Intonation (Pitch Variation)
```
Sentence-level pitch contours:
  - Rising pitch for questions
  - Falling pitch for statements
  - Pitch variation: ±10% around base frequency
```

---

## 7. Provenance Model

### 7.1 Signed Frames

#### Ed25519 Signature Flow
```
1. Generate Ed25519 keypair (public/private)
2. Sign payload: signature = sign(private_key, payload)
3. Frame: MAGIC_AUTH | total_len | payload_len | payload | signature | timestamp | CRC
4. Verify: public_key.verify(signature, payload)
5. Reject if: invalid signature, timestamp too old, CRC mismatch
```

### 7.2 Timestamp Validation

```
Timestamp freshness: 300 seconds
Purpose: Replay attack prevention
Logic: if (now - timestamp) > 300: reject
```

### 7.3 Provenance Gate

```python
# Require provenance for sensitive operations
if not provenance_verified:
    raise SecurityError("Unauthenticated payload rejected")

# Example: Boot from audio requires signed manifest
if operation == "boot" and not is_authenticated:
    raise SecurityError("Boot operations require Ed25519 signature")
```

---

## 8. Security Model Summary

### 8.1 Threat Mitigation

| Threat                      | Mitigation                                    |
|-----------------------------|-----------------------------------------------|
| Arbitrary code execution    | SandboxedExecutor, import allowlist           |
| Replay attacks              | Timestamp validation (300s window)            |
| Tampered payloads           | CRC32, Ed25519 signatures                     |
| Resource exhaustion         | CPU/memory/wall time limits                   |
| Filesystem access           | PATH stripped, temp-only filesystem           |
| Network access              | Blocked modules, no internet access           |
| Signal-based escapes        | Blocked signals (SIGINT, SIGHUP, etc.)        |

### 8.2 Security Properties

```
✓ No filesystem access (os, pathlib, tempfile blocked)
✓ No network access (socket, urllib, http blocked)
✓ No process forking (subprocess, multiprocessing blocked)
✓ No code injection (eval, exec, compile blocked)
✓ No persistent state (temp dir auto-cleaned)
✓ Resource limits enforced (CPU, memory, wall time)
✓ Output bounded (stdout/stderr truncated)
✓ No side channels (signals blocked, fd limit)
✓ Provenance verification (Ed25519 signatures)
✓ Replay protection (timestamp freshness)
```

---

## 9. Integration Points

### 9.1 Current Integrations

```
Dense encoder  → SandboxedExecutor (cartridge execution)
Spectral codec → Phy16Tone (MFSK encoding/decoding)
Compose system → Wordbase (semantic color tiles)
Boot system    → Signed manifests (audio boot from WAV)
```

### 9.2 Future Integrations

```
Geometry OS hypervisor → Native spatial opcode execution
Pixel OS daemon       → Real-time cartridge execution
LLM phoneme input     → Text-to-audio-to-opcode pipeline
Visual interfaces     → Interactive tile manipulation
```

---

## 10. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-07-16 | Initial specification based on current implementation |

---

## Appendix A: Test Commands

### Verification Commands

```bash
# Dense codec round-trip
python3 tools/dense_encoder.py encode script.py -o cartridge.png
python3 tools/dense_encoder_sandbox.py run cartridge.png

# Spectral codec round-trip
python3 -m pytest tests/test_spectral_ecc.py -v

# Sandbox security tests
python3 -m pytest tests/test_executor_sandbox.py -v

# Dual-band audio
python3 tests/test_dual_band_roundtrip.py -v

# Boot from audio
python3 tools/boot_over_air.py --simulate --image hello.img
```

### Performance Benchmarks

```bash
# Spectral encoding speed
python3 benchmark_s002.py

# Phoneme synthesis speed
python3 tools/speak.py say "hello world" -o test.wav --benchmark
```

---

## Appendix B: Constants Reference

```python
# Spectral codec (PHY16Tone)
SAMPLE_RATE = 44100
SYMBOL_SEC = 0.020          # 20 ms per symbol
TONE_BASE = 800.0           # Hz for nibble 0x0
TONE_STEP = 150.0           # Hz between adjacent nibbles
NUM_TONES = 16              # 0x0 to 0xF

# Frame formats
MAGIC_UNAUTH = b'UA'        # Unauthenticated frames
MAGIC_AUTH = b'VA'          # Authenticated frames
SIGNATURE_LENGTH = 64       # Ed25519 signature length
TIMESTAMP_LENGTH = 8        # Unix timestamp (int64)
TIMESTAMP_MAX_AGE_SECONDS = 300  # Reject signatures older than 5 minutes

# Sandbox limits
CPU_LIMIT_SECONDS = 5
WALL_TIMEOUT_SECONDS = 10
MEMORY_LIMIT_MB = 64
DISK_WRITE_LIMIT_MB = 10
STDOUT_LIMIT = 512 * 1024   # 512KB
STDERR_LIMIT = 512 * 1024   # 512KB
MAX_FILE_DESCRIPTORS = 16
MAX_PROCESSES = 1
```

---

## Appendix C: Error Codes

| Code | Description |
|------|-------------|
| `BAD_MAGIC` | Invalid frame magic (not 'UA' or 'VA') |
| `CRC_MISMATCH` | CRC validation failed |
| `PAYLOAD_TOO_LARGE` | Exceeds uint16 length limit |
| `INVALID_SIGNATURE` | Ed25519 signature verification failed |
| `TIMESTAMP_TOO_OLD` | Signature timestamp expired |
| `TIMESTAMP_FUTURE` | Timestamp from future (clock skew) |
| `BLOCKED_IMPORT` | Cartridge tried to import dangerous module |
| `TIMEOUT` | Execution exceeded wall time limit |
| `MEMORY_LIMIT` | Exceeded memory allocation limit |
| `KILLED_BY_SYSTEM` | Resource limit violation (system kill) |
| `SYNTAX_ERROR` | Cartridge code has Python syntax error |
| `RUNTIME_ERROR` | Unhandled exception during execution |