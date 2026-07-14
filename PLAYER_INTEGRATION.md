# Visual Audio Player Integration

This document describes how to play Visual Audio `.upic.json` project files in music players and audio software.

## Quick Start

### Method 1: Python Player (Recommended - Works Immediately)

```bash
# Play with auto-detected player
python3 tools/upic_play.py demo.upic.json

# Play with specific player
python3 tools/upic_play.py demo.upic.json --player ffplay

# Stream in real-time (low latency)
python3 tools/upic_play.py demo.upic.json --stream

# Convert to WAV for use in any player
python3 tools/upic_play.py demo.upic.json --output output.wav
```

### Method 2: GStreamer Plugin (Requires Compilation)

Once compiled and installed, `.upic.json` files can be played directly in GStreamer-based players:

```bash
cd plugins/gst-upic
sudo python3 install_plugin.py all
```

Then open `.upic.json` files in Rhythmbox, Clementine, Audacious, etc.

## Python Player Details

### Features

- **Auto-detection**: Automatically finds available audio players
- **Multiple Players**: Supports ffplay, VLC, MPV, MPlayer, GStreamer, PulseAudio, ALSA
- **Real-time Streaming**: Low-latency playback with `--stream` flag
- **WAV Conversion**: Export to standard WAV files for any player
- **Flexible Duration**: Control playback length with `--duration`

### Supported Players

| Player | Description | Seeking | Installation |
|--------|-------------|---------|--------------|
| ffplay | FFmpeg-based | ✓ | `sudo apt-get install ffmpeg` |
| vlc | VLC Media Player | ✓ | `sudo apt-get install vlc` |
| mpv | MPV Media Player | ✓ | `sudo apt-get install mpv` |
| mplayer | MPlayer | ✓ | `sudo apt-get install mplayer` |
| gst-play-1.0 | GStreamer Play | ✓ | Usually installed with GStreamer |
| paplay | PulseAudio | ✗ | Usually installed with PulseAudio |
| aplay | ALSA | ✗ | Usually installed with ALSA |

### Usage Examples

#### Basic Playback

```bash
# Auto-detect player and play
python3 tools/upic_play.py my_composition.upic.json

# Specify duration (30 seconds)
python3 tools/upic_play.py my_composition.upic.json --duration 30

# Use specific sample rate (better quality)
python3 tools/upic_play.py my_composition.upic.json --sample-rate 96000
```

#### Player Selection

```bash
# Play with VLC
python3 tools/upic_play.py my_composition.upic.json --player vlc

# Play with MPV
python3 tools/upic_play.py my_composition.upic.json --player mpv

# Play with FFmpeg (no GUI, good for scripts)
python3 tools/upic_play.py my_composition.upic.json --player ffplay
```

#### Real-time Streaming

```bash
# Stream directly to audio output (lowest latency)
python3 tools/upic_play.py my_composition.upic.json --stream

# Stream with custom duration
python3 tools/upic_play.py my_composition.upic.json --stream --duration 60
```

#### WAV Conversion

```bash
# Convert to WAV file
python3 tools/upic_play.py my_composition.upic.json --output my_track.wav

# High-quality conversion
python3 tools/upic_play.py my_composition.upic.json --output hq.wav \
    --sample-rate 96000 --duration 120
```

#### Utility Commands

```bash
# List available players
python3 tools/upic_play.py --list-players

# Show help
python3 tools/upic_play.py --help

# Keep temporary WAV file for inspection
python3 tools/upic_play.py my_composition.upic.json --keep-temp
```

## GStreamer Plugin Details

### Features

- **Native GStreamer Integration**: Seamless integration with GStreamer ecosystem
- **Universal Playback**: Works with any GStreamer-based player
- **Real-time Synthesis**: No pre-conversion needed
- **Seek Support**: Jump to any position in the project
- **Format Registration**: Auto-registers `.upic.json` MIME type

### Installation

```bash
# Check dependencies
python3 plugins/gst-upic/install_plugin.py check

# Build and install
python3 plugins/gst-upic/install_plugin.py all

# Or install with sudo
sudo python3 plugins/gst-upic/install_plugin.py install
```

### Supported Players (GStreamer)

- Rhythmbox (default GNOME music player)
- Clementine
- Audacious
- Banshee
- Totem (Videos)
- Any GStreamer-based application

### Usage

After installation, `.upic.json` files behave like regular audio files:

```bash
# Open in Rhythmbox
rhythmbox my_composition.upic.json

# Play with gst-launch
gst-launch-1.0 filesrc location=my_composition.upic.json ! upicdec ! autoaudiosink

# Convert to WAV with gst-launch
gst-launch-1.0 filesrc location=my_composition.upic.json ! upicdec ! \
    audioconvert ! wavenc ! filesink location=output.wav
```

## Integration with Audio Software

### Audacity

```bash
# Convert to WAV first
python3 tools/upic_play.py project.upic.json --output for_audacity.wav

# Open in Audacity
audacity for_audacity.wav
```

### LMMS (Linux MultiMedia Studio)

```bash
# Convert to WAV
python3 tools/upic_play.py project.upic.json --output for_lmms.wav

# Import as Audio File Processor in LMMS
```

### Ardour

```bash
# Convert to WAV
python3 tools/upic_play.py project.upic.json --output for_ardour.wav

# Import audio in Ardour
ardour my_session
# File → Import → Select for_ardour.wav
```

### FFmpeg Pipeline

```bash
# Direct FFmpeg processing
python3 tools/upic_play.py project.upic.json --output temp.wav && \
    ffmpeg -i temp.wav -af "equalizer=f=1000:width_type=h:width=100:g=5" \
           processed.wav
```

## Performance Considerations

### Python Player Performance

- **Synthesis Speed**: ~100x real-time on modern CPU (10s audio in ~100ms)
- **Memory**: Minimal (processes in chunks)
- **Latency**: 
  - File conversion: ~100-500ms startup
  - Streaming: ~50ms (with aplay)
- **Quality**: Depends on synthesis parameters (sample rate, duration)

### GStreamer Plugin Performance

- **Real-time**: True real-time synthesis
- **CPU Usage**: ~5-10% for typical projects (10 voices)
- **Latency**: Minimal (push-based source)
- **Memory**: Small (keeps project structure only)

## Troubleshooting

### "No suitable audio player found"

Install one of the supported players:

```bash
sudo apt-get install vlc        # VLC (GUI)
sudo apt-get install mpv        # MPV (GUI)
sudo apt-get install ffmpeg     # FFmpeg (CLI)
sudo apt-get install pulseaudio # PulseAudio (system audio)
```

### "Error importing UPIC engine"

Make sure you're running from the project directory:

```bash
cd /path/to/visual_audio
python3 tools/upic_play.py demo.upic.json
```

### Audio sounds distorted

Lower voice amplitudes in your UPIC project:

```bash
python3 tools/upic_play.py project.upic.json --duration 5
```

### Seeking doesn't work

Use a player that supports seeking:

```bash
# Good (supports seeking)
python3 tools/upic_play.py project.upic.json --player vlc
python3 tools/upic_play.py project.upic.json --player mpv

# Limited (no seeking support)
python3 tools/upic_play.py project.upic.json --player paplay
python3 tools/upic_play.py project.upic.json --player aplay
```

## Advanced Usage

### Batch Processing

```bash
# Play all UPIC projects in a directory
for file in *.upic.json; do
    python3 tools/upic_play.py "$file" --duration 30
done

# Convert all to WAV
for file in *.upic.json; do
    output="${file%.upic.json}.wav"
    python3 tools/upic_play.py "$file" --output "$output"
done
```

### Integration with Shell Scripts

```bash
#!/bin/bash
# play_upic.sh - Quick UPIC player wrapper

if [ -z "$1" ]; then
    echo "Usage: $0 <project.upic.json> [duration]"
    exit 1
fi

PROJECT="$1"
DURATION="${2:-10}"

python3 tools/upic_play.py "$PROJECT" --duration "$DURATION"
```

### Integration with Python

```python
from tools.upic_play import import_upic_engine, synthesize_to_wav
import subprocess

# Convert to WAV
synthesize_to_wav("project.upic.json", "temp.wav", duration=30)

# Play with custom command
subprocess.run(["ffplay", "-nodisp", "-autoexit", "temp.wav"])
```

## Future Enhancements

Planned improvements:

- [ ] GUI player with real-time controls
- [ ] ALSA MIDI integration for live performance
- [ ] JACK audio server support
- [ ] Network streaming (RTP, Icecast)
- [ ] Playlist management
- [ ] Visualization support (spectrum, waveform)
- [ ] Real-time parameter editing

## See Also

- [README.md](../README.md) - Main project documentation
- [GStreamer Plugin README](../plugins/gst-upic/README.md) - GStreamer plugin details
- [tools/upic_play.py](../tools/upic_play.py) - Player implementation

## Contributing

Contributions welcome! Please see main repository guidelines.