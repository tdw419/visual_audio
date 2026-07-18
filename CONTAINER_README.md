# Visual Audio Container (visual_audio.mkv)

One lossless MKV file containing the entire Visual Audio project — spec, codec tables, state registers, cache management, and content. The file grows as the project grows.

## File Structure

**Format**: FFV1 codec (lossless), RGB24, 450×450 frames
**Architecture**: Self-describing per docs/research/485_visual_audio_to_software123.txt

```
Frame 0: Directory (VAC1 JSON - entries with name, role, frame span, sha256)
Frames 1+: Payload entries wrapped in dense_encoder [UA][LEN][PAYLOAD][CRC32] format
```

## Current Contents

| Entry | Role | Size | Description |
|-------|------|------|-------------|
| bootstrap/va_container.py | bootstrap | 8862 bytes | Self-contained reader/writer (extract to bootstrap) |
| spec/485_video_state_architecture.txt | spec | 14859 bytes | Research doc this container implements |
| codec/tables.json | codec | 3971 bytes | Phoneme (39 ARPAbet) + MFSK (16-tone) layer specs |
| state/register.json | state | 2270 bytes | Global state registers (playback, cache, layer selection) |
| cache/allocation_table.json | cache | 394 bytes | Voicebook cache allocation bitmap (4096 entries max) |
| content/hello.json | content | 101 bytes | First test content entry |
| content/hello_world.wav | content | 141164 bytes | Phoneme-encoded audio: 'hello world this is visual audio' |

## Usage

```bash
# List all entries
python3 tools/va_container.py ls visual_audio.mkv

# Extract an entry
python3 tools/va_container.py cat visual_audio.mkv content/hello_world.wav -o extracted.wav

# Verify integrity (CRC32 + sha256)
python3 tools/va_container.py verify visual_audio.mkv

# Add new content
python3 tools/va_container.py add visual_audio.mkv myfile.json --name content/new.json --role content

# Self-hosting bootstrap test
python3 tools/va_container.py cat visual_audio.mkv bootstrap/va_container.py -o va_container_extracted.py
python3 va_container_extracted.py verify visual_audio.mkv  # extracts its own reader to verify the container
```

## Role Types

- **bootstrap**: Self-hosting tools (reader/writer for this container)
- **spec**: Design documents, research, architecture
- **codec**: Codec tables, ARPAbet mappings, MFSK frequencies
- **state**: Global state registers, playback position, layer selection
- **cache**: Cache allocation tables, voicebook metadata
- **content**: Encoded data (audio, pixels, text, software)

## Architecture Per 485 Doc

- **Frame 0**: Directory (self-describing, allows anyone to find everything else)
- **Frames 1+**: Entry payloads (dense-encoder wrapped at 3 bytes/pixel)
- **Append-only growth**: Adding content rewrites frame 0, appends payload frames
- **Time-travel debug**: Any historical frame remains seekable forever (FFV1 is intra-only)

## File Status

- Size: 196K (10 frames)
- Entries: 7
- Integrity: 100% verified (CRC32 + sha256)
- Self-hosting: YES (bootstrap entry extracts successfully)

## Next Growth Path

1. Add voicebook cache entries (real synthesized words)
2. Add encoded software examples (Python scripts, Rust binaries)
3. Add pixel OS command sequences (Geometry OS integration)
4. Add dual-band encoded content (human-readable + machine-readable)
5. Migrate loose repo files into container until repo = bootstrap script + container

## Limitations

- Directory must fit in one frame (~65KB JSON — hundreds of entries)
- External deps: ffmpeg + dense_encoder.py (next: fold dense_encoder into bootstrap)
- Role: visualization not implemented (frames are raw memory, not images)

## Verification

```bash
# Extract test content and verify round-trip
python3 tools/va_container.py cat visual_audio.mkv content/hello_world.wav -o test.wav
python3 tools/speak.py decode test.wav -o decoded.txt
# Output: "hello world this is visual audio" (byte-identical)
```