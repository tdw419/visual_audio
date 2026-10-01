# Pixel OS Listener Daemon

The resident listener daemon that transforms the visual audio system from a demo into a living OS.

## What It Is

`pixel_os_listener.py` is a continuously-running daemon that:
- **Watches for audio commands** (either file queue or live microphone)
- **Decodes dual-band utterances** (narration + pixel ops)
- **Updates framebuffer.png in real-time**
- **Runs until stopped** (signal-safe, logging included)

This is the actual OS experience you described — a surface that lives and responds.

## Architecture

```
┌─────────────┐
│  LLM / AI   │  (creates utterances with pixel_screen.py utter)
└──────┬──────┘
       │ dual-band WAV (narration + ops)
       ▼
┌──────────────────────────┐
│  Listener Daemon         │  (this daemon)
│  - Queue mode: watches dir│
│  - Live mode: monitors mic│
│  - Decodes high band      │
│  - Applies ops to FB      │
└──────┬───────────────────┘
       │
       ▼
┌──────────────────┐
│  framebuffer.png │  (persistent screen state)
└──────────────────┘
```

## Usage

### Queue Mode (File-based)

```bash
# Start daemon watching a directory
python3 tools/pixel_os_listener.py --mode queue --watch-dir voicebook/queue --fb framebuffer.png

# In another terminal, create utterances
python3 tools/pixel_screen.py utter "turn screen blue" --ops '[["fill","#1a3a8a"]]' -o voicebook/queue/test.wav
```

The daemon automatically detects new `.wav` files, decodes the high-band data, and applies the ops to `framebuffer.png`.

### Live Mode (Microphone)

```bash
# List available audio devices
python3 -c "import sounddevice as sd; print(sd.query_devices())"

# Start daemon with device ID
python3 tools/pixel_os_listener.py --mode live --device-id 0 --fb framebuffer.png

# Play utterances through speakers
python3 tools/pixel_screen.py utter "test command" --ops '[["fill","#ff0000"]]' -o test.wav
aplay test.wav  # or your audio player
```

The daemon monitors the microphone and processes commands heard through the room.

## Command Line Options

```
--mode           Operation mode: queue (watch directory) or live (monitor audio device)
--watch-dir      Directory to watch for WAV files (queue mode) [default: ./voicebook/queue]
--device-id      Audio device ID (live mode) [default: 0]
--fb             Framebuffer image path [default: framebuffer.png]
--poll-interval  Polling interval for queue mode in seconds [default: 1.0]
--provenance     Require signed utterances (future security feature)
```

## Operations Supported

The daemon applies the same pixel ops as `pixel_screen.py`:

```json
["fill", "#1a3a8a"]                  // Fill entire screen with color
["rect", x, y, w, h, "#ffffff"]      // Draw filled rectangle
["frame", x, y, w, h, "#ff0000"]     // Draw rectangle outline
["word", "text", x, y, "#000000"]    // Blit wordbase tiles (with auto-coloring)
```

## Logs

The daemon writes to both stdout and `pixel_os_listener.log`:

```
2026-07-16 07:35:46 - INFO - Worker thread started
2026-07-16 07:35:46 - INFO - Listener daemon started
2026-07-16 07:35:46 - INFO - Starting queue mode: watching test_queue
2026-07-16 07:37:13 - INFO - Processing new file: new_test.wav
2026-07-16 07:37:13 - INFO - Decoded 1 ops from test_queue/new_test.wav
2026-07-16 07:37:13 - INFO - Applied 1 ops to test_framebuffer.png
```

## Testing

Run the automated test suite:

```bash
python3 tools/test_pixel_os_daemon.py
```

This creates example utterances and provides commands to start the daemon and watch it update the framebuffer in real-time.

## Architecture Details

### Thread Design

- **Main thread**: Polls for new audio sources (files or live input)
- **Worker thread**: Processes ops from a queue and applies to framebuffer
- **Signal-safe**: Handles SIGINT/SIGTERM for graceful shutdown

### Error Handling

- **Resilient**: Logs errors but continues running
- **Per-file isolation**: One bad utterance doesn't break the loop
- **Timeout-safe**: Worker thread checks running flag regularly

### Security (Future)

The `--provenance` flag will require signed utterances before executing, addressing the "Eve problem" where any sound in range could execute commands.

## What Makes This an OS

1. **Persistent state**: The framebuffer survives across sessions
2. **Continuous operation**: It doesn't exit after one command
3. **Dual-band design**: Human hears narration, machine executes ops
4. **One substrate**: Display, storage, code, transport are all images/spectrograms
5. **Extensible**: Ops → opcodes path exists (GlyphLang spatial opcodes coming next)

## Next Steps

The daemon works. What's next from the original roadmap:

1. **Ops → opcodes**: Convert fill/rect/word to GlyphLang spatial opcodes
2. **Provenance**: Implement signed frame verification
3. **Spatial execution**: Make utterances place executable pixels

The daemon is the foundation that makes these advances possible — a living surface waiting for the next command.

## Files

- `tools/pixel_os_listener.py` - The daemon
- `tools/test_pixel_os_daemon.py` - Test suite and examples
- `tools/pixel_screen.py` - Utterance creation (AI side)
- `pixel_os_listener.log` - Runtime logs