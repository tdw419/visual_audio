# Sonic Code Translator

## Overview

The Sonic Code Translator transforms programming code into melodious, pleasant-sounding audio that humans can enjoy listening to while still conveying the code's structure and meaning through musical patterns.

## How It Works

### Architecture

```
Code → AST Parser → Musical Events → UPIC Synthesis → Pleasant Audio
```

1. **Code Analysis**: Parse Python code into an Abstract Syntax Tree (AST)
2. **Musical Mapping**: Map programming constructs to musical patterns:
   - **Pitch**: Different pitches for different construct types
   - **Duration**: Longer durations for major constructs, shorter for operations
   - **Waveform**: Different timbres for different code elements
   - **Amplitude**: Softer/louder to indicate importance

### Musical Mapping

#### Programming Constructs → Musical Elements

| Construct | Pitch | Duration | Waveform | Amplitude |
|-----------|-------|----------|----------|-----------|
| `def function` | C4 (261 Hz) | 0.8s | Sine | 0.7 |
| `class MyClass` | D4 (293 Hz) | 1.0s | Sine | 0.75 |
| `if condition` | E4 (329 Hz) | 0.4s | Sine | 0.6 |
| `for loop` | G4 (392 Hz) | 0.5s | Sine | 0.65 |
| `while loop` | A4 (440 Hz) | 0.6s | Sine | 0.65 |
| `variable` | G4 (392 Hz) | 0.3s | Triangle | 0.5 |
| `string` | C5 (523 Hz) | 0.4s | Sine | 0.6 |
| `number` | D5 (587 Hz) | 0.2s | Triangle | 0.5 |
| `assignment =` | D5 (587 Hz) | 0.15s | Square | 0.6 |
| `comparison ==` | E5 (659 Hz) | 0.2s | Square | 0.55 |
| `operation +` | E5 (659 Hz) | 0.15s | Square | 0.5 |
| `function_call()` | G5 (783 Hz) | 0.25s | Triangle | 0.65 |
| `return` | A5 (880 Hz) | 0.5s | Sine | 0.7 |

#### Musical Scale

Uses **C Major Pentatonic Scale** for pleasant, consonant sounds:
- C4 (261.63 Hz)
- D4 (293.66 Hz)  
- E4 (329.63 Hz)
- G4 (392.00 Hz)
- A4 (440.00 Hz)
- C5 (523.25 Hz)
- D5 (587.33 Hz)
- E5 (659.25 Hz)
- G5 (783.99 Hz)
- A5 (880.00 Hz)

Pentatonic scales are inherently musical and pleasant because they avoid dissonant intervals.

#### Waveform Timbres

- **Sine**: Pure, clean tones for control structures
- **Triangle**: Softer, warmer tones for variables and calls
- **Square**: Brighter, more percussive tones for operations

### Nesting Depth & Variation

The system adds pitch variation based on code nesting depth:
```python
def outer():              # Base pitch: C4
    def inner():          # Variated pitch for musical interest
        x = 1             # Variables reflect current depth
```

This creates musical interest through octave and stepwise variations.

## Usage

### Basic Usage

```bash
# Convert a Python file to pleasant audio
python tools/sonic_code_translator.py my_code.py -o pleasant.wav

# With verbose output showing musical events
python tools/sonic_code_translator.py my_code.py -o pleasant.wav -v

# Save metadata for analysis
python tools/sonic_code_translator.py my_code.py -o pleasant.wav -p metadata.json
```

### Converting Code Strings

```bash
# Direct code string
python tools/sonic_code_translator.py "def hello(): print('world')" -o hello.wav
```

### Example Output

```
Converting code to pleasant audio...
Code length: 1205 characters
Generated 125 musical events from code
Total duration: 30.25s
Saved audio to: pleasant_code.wav

Musical Event Summary:
------------------------------------------------------------
function            :   4 events
  Example: def fibonacci
  Pitch: 261.6 Hz, Duration: 0.800s

class               :   1 events
  Example: class DataProcessor
  Pitch: 293.7 Hz, Duration: 1.000s

for_loop            :   1 events
  Example: for
  Pitch: 392.0 Hz, Duration: 0.500s

variable            :  26 events
  Example: n
  Pitch: 440.0 Hz, Duration: 0.300s

✓ Success! Generated 30.25s of pleasant code audio
```

## Benefits

### For Humans
- **Enjoyable Listening**: Code sounds like pleasant music, not robotic reading
- **Pattern Recognition**: Musical patterns reveal code structure intuitively
- **Accessibility**: Musicians can "hear" code organization
- **Multimodal Learning**: Combine reading with auditory understanding

### For AI Systems
- **Better Speech Training**: AI can learn to speak code melodiously
- **Auditory Code Review**: Listen to code changes like music
- **Pattern Recognition**: AI can learn code patterns through audio
- **Cross-Modal Understanding**: Connect visual, textual, and auditory code representations

### For Education
- **Code Appreciation**: Students can experience code as art
- **Structure Visualization**: Hear nesting, loops, and conditionals
- **Debugging by Ear**: Identify code patterns through sound
- **Collaborative Coding**: Code reviews become musical sessions

## Advanced Features

### Metadata File

The `-p` option saves a JSON file with detailed information:

```json
{
  "source_code": "def fibonacci(n): ...",
  "events": [
    {
      "construct": "function",
      "start_time": 0.0,
      "duration": 0.8,
      "pitch": 261.63,
      "amplitude": 0.7,
      "waveform": "sine",
      "text": "def fibonacci"
    }
  ],
  "total_duration": 30.25,
  "sample_rate": 44100
}
```

This enables:
- Code reconstruction from audio
- Audio visualization
- Pattern analysis
- AI training data

### Integration with Visual Audio

This translator works seamlessly with the existing Visual Audio system:

```python
from tools.sonic_code_translator import code_to_pleasant_audio
from tools.speak import encode_dual_band

# Convert code to pleasant audio
audio, events = code_to_pleasant_audio(code, "pleasant.wav")

# Create dual-band encoding (human + machine)
encode_dual_band(
    text="Here's a fibonacci implementation",
    software_path="fibonacci.py",
    wav_path="dual_band_code.wav"
)
```

## Technical Details

### Audio Generation
- **Sample Rate**: 44.1 kHz (CD quality)
- **Bit Depth**: 16-bit PCM
- **Channels**: Mono
- **Synthesis**: UPIC engine with envelope control

### Performance
- **Throughput**: ~4 events/second of code
- **File Size**: ~2.6 MB for 30 seconds of audio
- **Latency**: Real-time generation capable

### Dependencies
- Python 3.8+
- NumPy
- SciPy
- SoundFile
- Visual Audio UPIC Engine

## Future Enhancements

### Planned Features
1. **Harmony**: Add chord progressions based on code structure
2. **Rhythm**: Implement musical meters (4/4, 3/4) for different code patterns
3. **Dynamics**: Crescendo/decrescendo for emphasis
4. **Multi-voice**: Parallel voices for concurrent code execution
5. **Language Support**: JavaScript, Rust, Go, etc.

### Research Directions
- **Human Studies**: Can programmers recognize code patterns by ear?
- **AI Training**: Train models to generate code from audio descriptions
- **Musical Code Review**: Collaborative listening sessions
- **Debugging by Ear**: Identify bugs through audio patterns

## Examples

### Simple Function
```python
def add(a, b):
    return a + b
```
- Sounds like: A gentle ascent (function def), two soft notes (variables), a bright return tone, and a crisp operation

### Loop
```python
for i in range(10):
    print(i)
```
- Sounds like: A steady rhythmic pattern with percussive loop marker and consistent iteration sounds

### Class Definition
```python
class Calculator:
    def add(self, a, b):
        return a + b
```
- Sounds like: A foundational bass note (class), followed by higher melodic phrases (methods)

## Philosophical Implications

### Code as Music
This translator treats software not just as functional text, but as an aesthetic experience. Code becomes music you can listen to, appreciate, and discuss.

### Embodied AI
When AI systems "speak" code, they shouldn't sound robotic. This system enables AI to speak code melodiously, making human-AI collaboration more natural and enjoyable.

### Multimodal Programming
Programming becomes a sensory experience involving:
- **Visual**: Reading code on screen
- **Textual**: Understanding syntax and semantics  
- **Auditory**: Hearing code structure and patterns
- **Spatial**: Visualizing code through pixel cartridges

## Troubleshooting

### Common Issues

**Issue**: "No musical events generated"
- **Cause**: Empty code or syntax error
- **Fix**: Check code syntax and ensure it contains valid Python

**Issue**: Audio sounds too short/long
- **Cause**: Default duration values may not suit your code
- **Fix**: Modify `DURATIONS` dictionary in `MusicalCodeMapper`

**Issue**: Pitch sounds dissonant
- **Cause**: Non-pentatonic intervals
- **Fix**: All pitches use pentatonic scale by design

## Contributing

To extend the system:

1. **Add new constructs**: Extend `MusicalConstruct` enum
2. **Customize mappings**: Modify `MusicalCodeMapper` class
3. **New languages**: Create language-specific AST visitors
4. **Enhance synthesis**: Add harmony, rhythm, dynamics

## License

Part of the Visual Audio project for Geometry OS.

---

*Transform code from text you read into music you can listen to.*