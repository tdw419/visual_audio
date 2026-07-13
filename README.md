# Visual Audio

A UPIC-inspired audio synthesis system with graphical composition interface and audio-to-UPIC converter. Convert your music to visual projects, then synthesize them back to audio.

## What is Visual Audio?

Visual Audio is inspired by UPIC (Unité Polyagogique Informatique CEMAMu), developed by Iannis Xenakis in the 1970s as one of the first computer-assisted composition systems. This implementation captures that pioneering spirit while adding modern features like:

- **Wavetable Synthesis**: High-quality audio generation from mathematical waveforms
- **Envelope Control**: Precise control over frequency, amplitude, and time scaling
- **Multi-Voice Polyphony**: Unlimited voices per project with independent control
- **Audio Analysis**: Convert MP3/WAV files to UPIC projects automatically
- **JSON Project Management**: Human-readable project format for easy editing
- **CLI Interface**: Command-line tools for all operations

## Features

### Core Synthesis Engine
- 4 basic waveforms: sine, triangle, square, sawtooth
- Custom wavetables from extracted audio
- Linear interpolation for smooth playback
- Configurable sample rates (44.1kHz, 48kHz, 96kHz)

### Envelope System
- 3 envelope types per voice: frequency, amplitude, time scaling
- Standard envelopes: ADSR, ramp up/down, LFO sine
- Custom envelope creation via control points
- Linear interpolation for smooth curves

### Audio Converter
- Convert MP3/WAV files to UPIC projects
- Frequency band analysis (logarithmic spacing)
- Automatic wavetable extraction
- Envelope generation from audio analysis
- Configurable analysis parameters

### Project Management
- JSON-based project format (human-readable)
- Complete serialization/deserialization
- Reusable wavetable and envelope libraries
- CLI for all operations

## Installation

### Requirements
- Python 3.8+
- NumPy >= 1.21.0
- SciPy >= 1.7.0
- SoundFile >= 0.11.0
- Librosa >= 0.9.0 (for audio converter)

### Setup
```bash
# Clone repository
git clone https://github.com/tdw419/visual_audio.git
cd visual_audio

# Install dependencies
pip install -r requirements.txt

# Make scripts executable
chmod +x tools/*.py
```

## Quick Start

### 1. Create a UPIC Project
```bash
# Create demo project
python tools/upic.py demo

# Inspect project
python tools/upic.py list demo.upic.json
```

### 2. Synthesize Audio
```bash
# Synthesize demo project
python tools/upic.py synthesize demo.upic.json output.wav --duration 10

# High-quality synthesis
python tools/upic.py synthesize project.upic.json hq.wav --duration 30 --sample-rate 96000
```

### 3. Convert Audio to UPIC
```bash
# Convert MP3 to UPIC project
python tools/mp3_to_upic.py input.mp3 project.upic.json

# With more frequency bands for detail
python tools/mp3_to_upic.py input.mp3 project.upic.json --bands 8

# With fewer control points for simpler envelopes
python tools/mp3_to_upic.py input.mp3 project.upic.json --points 6
```

### 4. Custom Composition
```bash
# Create custom project
python tools/upic.py create-project my_composition

# Add voices
python tools/upic.py add-voice my_composition.upic.json bass --wavetable sawtooth --frequency 55
python tools/upic.py add-voice my_composition.upic.json lead --wavetable triangle --frequency 440

# Add custom envelope
python tools/upic.py add-envelope my_composition.upic.json custom --points 0.0:0.0 1.0:1.0

# Synthesize
python tools/upic.py synthesize my_composition.upic.json output.wav --duration 15
```

## Usage Examples

### Basic UPIC Synthesis
```python
import sys
sys.path.insert(0, 'src')
from upic_engine import UPICProject

# Create project
project = UPICProject("my_song")
project.create_basic_wavetables()
project.create_basic_envelopes()

# Add voice with sine wave
sine_table = project.wavetables['sine']
voice = project.add_voice("melody", sine_table)
voice.base_frequency = 440.0  # A4
voice.base_amplitude = 0.7
voice.set_amplitude_envelope(project.envelopes['ADSR'])

# Synthesize
audio = project.synthesize(duration=10.0)
project.export_audio(audio, "output.wav")
```

### Audio Conversion
```bash
# Convert a song to UPIC format
python tools/mp3_to_upic.py favorite_song.mp3 song_project.upic.json --bands 6

# Inspect the converted project
python tools/upic.py list song_project.upic.json

# Synthesize a variation
python tools/upic.py synthesize song_project.upic.json variation.wav --duration 180
```

### Custom Envelopes
```bash
# Create custom envelope with multiple points
python tools/upic.py add-envelope project.upic.json swell \
  --points 0.0:0.0 0.2:0.3 0.5:1.0 0.8:0.6 1.0:0.0

# Apply to voice
python tools/upic.py set-voice-envelope project.upic.json voice_name swell
```

## CLI Reference

### UPIC CLI (`upic.py`)
```bash
# Project management
upic demo                                    # Create demo project
upic create-project <name>                  # Create new project
upic list <project>                          # Show project details

# Voice management
upic add-voice <project> <name> [options]   # Add voice to project
upic set-voice-envelope <project> <name> <env>  # Set voice envelope

# Envelope management
upic add-envelope <project> <name> [options] # Add envelope to project

# Synthesis
upic synthesize <project> <output> [options] # Synthesize audio from project
```

### MP3 to UPIC CLI (`mp3_to_upic.py`)
```bash
# Basic conversion
mp3_to_upic.py input.mp3 output.upic.json

# Advanced options
mp3_to_upic.py input.mp3 output.upic.json \
  --bands 8 \                    # Frequency bands (default: 4)
  --points 12 \                  # Control points per envelope (default: 12)
  --name "My Project"           # Project name (default: filename)
```

## Documentation

- [ROADMAP.md](ROADMAP.md) - Development roadmap and future features
- [PHASE3.1_COMPLETE.md](completion/PHASE3.1_COMPLETE.md) - Phase 3.1 implementation details
- [PHASE3.3_COMPLETE.md](completion/PHASE3.3_COMPLETE.md) - Phase 3.3 implementation details
- [REPO_SETUP_PLAN.md](REPO_SETUP_PLAN.md) - Repository architecture and setup guide

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_upic_engine.py -v

# Run with coverage
python -m pytest tests/ -v --cov=src --cov-report=html

# Run integration tests
python phase3_upic_integration_test.py

# Run converter tests
python test_mp3_to_upic.py
```

## Project Structure

```
visual_audio/
├── README.md                    # Main documentation
├── pyproject.toml               # Project configuration
├── requirements.txt             # Dependencies
├── ROADMAP.md                   # Project roadmap
├── src/                         # Core source code
│   └── upic_engine.py          # UPIC synthesis engine
├── tests/                       # Test suite
│   ├── test_upic_engine.py
│   ├── phase3_upic_integration_test.py
│   └── test_mp3_to_upic.py
├── tools/                       # CLI tools
│   ├── upic.py                 # Main UPIC CLI
│   ├── mp3_to_upic.py          # Audio converter
│   └── demo_upic.py            # Demo script
├── completion/                  # Phase completion docs
│   ├── PHASE3.1_COMPLETE.md
│   └── PHASE3.3_COMPLETE.md
└── REPO_SETUP_PLAN.md          # Repository architecture
```

## Historical Context

UPIC (Unité Polyagogique Informatique CEMAMu) was developed by Iannis Xenakis in the 1970s as one of the first computer-assisted composition systems. Xenakis, a pioneering composer and architect, created UPIC to allow composers to "draw" sound graphically on a tablet, translating visual gestures into musical events.

This implementation honors that legacy while adding modern features:
- Digital audio synthesis (vs. analog UPIC)
- JSON project format (vs. proprietary UPIC format)
- Audio analysis capabilities (novel addition)
- CLI interface (vs. graphical-only UPIC)

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Code Style**: Follow PEP 8 and use Black formatter
2. **Testing**: Add tests for new features
3. **Documentation**: Update relevant documentation
4. **Commits**: Use clear commit messages

### Development Setup
```bash
# Install development dependencies
pip install -r requirements.txt
pip install pytest black flake8 mypy

# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type check
mypy src/
```

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Iannis Xenakis and the original UPIC system
- Librosa for audio analysis capabilities
- NumPy and SciPy for mathematical operations

## Future Development

See [ROADMAP.md](ROADMAP.md) for detailed plans:

- **Phase 4**: Graphical drawing interface
- **Phase 5**: Advanced synthesis techniques
- **Phase 6**: Real-time performance mode
- **Phase 7**: Machine learning integration
- **Phase 8**: Cloud collaboration features

## Contact

- **Repository**: https://github.com/tdw419/visual_audio
- **Issues**: https://github.com/tdw419/visual_audio/issues
- **Author**: Jericho (tdw419)

## Version

Current version: **0.1.0-alpha**

This is an alpha release with core functionality working. Expect changes and improvements in future releases.