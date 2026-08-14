# Natural Language Programming with Wordbase + Visual Audio

## Overview

The Natural Language Compiler (NLC) enables **plain English programming** through the wordbase database and Visual Audio encoding system. Users can write natural language commands that compile to Python code, which can then be encoded as pixels and synthesized into audio.

## Architecture

```
Plain English Command
         ↓
  Semantic Parser
         ↓
  ParsedCommand (verb + object + parameters)
         ↓
  Code Generator
         ↓
  Python Code
         ↓
  PixelTokenizer (via wordbase.db)
         ↓
  RGB Pixels (.npy)
         ↓
  UPIC/WAV Encoding (optional)
```

## Components

### 1. SemanticParser (`src/nlp/natural_language_compiler.py`)

Parses English commands into structured semantic representations:

- **Verbs**: CREATE, MAKE, DRAW, SET, PRINT, CALCULATE, CLEAR, DELETE, MOVE, COPY
- **Objects**: PIXEL, RECTANGLE, CIRCLE, LINE, TEXT, WINDOW, IMAGE, DATA
- **Parameters**: Coordinates, colors, values, text, expressions

### 2. CodeGenerator

Generates Python code from parsed commands. Maps semantic structures to Python API calls.

### 3. NaturalLanguageCompiler

End-to-end pipeline: parse → generate → encode to pixels → optional WAV output.

## Usage

### Command Line

```bash
# Compile a command to pixels
python3 tools/speak.py natural "create a red pixel at 10, 20"

# Generate code only (no pixels)
python3 tools/speak.py natural "print hello world" --no-pixels

# Compile to pixels AND encode to WAV
python3 tools/speak.py natural "create a blue pixel at 100, 200" --to-wav output.wav

# Batch compile from file
python3 -c "
from src.nlp.natural_language_compiler import NaturalLanguageCompiler

with open('commands.txt', 'r') as f:
    commands = [line.strip() for line in f if line.strip()]

compiler = NaturalLanguageCompiler()
results = compiler.compile_batch(commands)
"
```

### Python API

```python
from src.nlp.natural_language_compiler import NaturalLanguageCompiler

compiler = NaturalLanguageCompiler()

# Single command
result = compiler.compile("create a red pixel at 10, 20")
print(result['code'])  # pixels.set_pixel(10, 20, (255, 0, 0))

# Access pixels
pixels = result['pixels']  # numpy array (N, 3) RGB

# Batch compilation
commands = [
    "create a red pixel at 0, 0",
    "create a green pixel at 10, 10",
    "print hello world"
]
results = compiler.compile_batch(commands)
```

## Supported Commands

### Pixel Operations

```bash
create a red pixel at 10, 20
make a green pixel at 5, 15
draw a blue pixel at 100, 200
set pixel color to yellow
clear pixels
```

### Text Output

```bash
print hello world
print "Hello, Visual Audio!"
```

### Calculations

```bash
calculate 5 + 3
calculate 42 * 2
calculate (10 + 5) / 3
```

### Colors

Supports named colors and hex codes:

- **Named**: red, green, blue, yellow, white, black, cyan, magenta, orange, purple, brown, gray
- **Hex**: #ff0000, #00ff00, #0000ff, etc.

## Examples

### Example 1: Simple Drawing

```python
from src.nlp.natural_language_compiler import NaturalLanguageCompiler

compiler = NaturalLanguageCompiler()

# Create a red pixel at origin
result = compiler.compile("create a red pixel at 0, 0")
print(result['code'])
# Output: pixels.set_pixel(0, 0, (255, 0, 0))

# Pixels are (9, 3) array:
# [[112, 114, 105], [110, 116, 40], ...]  # "p r i n t ( 0 ,  0"
```

### Example 2: Batch Compilation

```python
commands = [
    "create a red pixel at 0, 0",
    "create a green pixel at 10, 10",
    "print hello world",
    "calculate 42 * 2",
]

compiler = NaturalLanguageCompiler()
results = compiler.compile_batch(commands)

for result in results:
    print(f"{result['original']:30} -> {result['code']}")
```

### Example 3: End-to-End Pipeline

```python
# 1. Parse English command
result = compiler.compile("create a red pixel at 10, 20")

# 2. Access generated code
code = result['code']
print(code)  # pixels.set_pixel(10, 20, (255, 0, 0))

# 3. Access pixel representation
pixels = result['pixels']
print(f"Pixels shape: {pixels.shape}")  # (N, 3) RGB

# 4. Save pixels
import numpy as np
np.save('code_pixels.npy', pixels)

# 5. Optional: Encode to WAV using speak.py
# python3 tools/speak.py encode code_pixels.npy -o code.wav
```

## Wordbase Integration

The NLC uses the wordbase database (`db/wordbase.db`) for pixel encoding:

```bash
# Query wordbase for color mapping
sqlite3 db/wordbase.db "SELECT word, color_hex FROM words WHERE word IN ('red', 'green', 'blue')"
# Output:
# red|#76EA50
# green|#50EA6B
# blue|#5088EA
```

The PixelTokenizer maps Python code to pixels by looking up each word in the wordbase.

## Testing

Run the test suite:

```bash
python3 -m pytest tests/test_natural_language_compiler.py -v
```

Test coverage:
- Semantic parsing (28 tests)
- Code generation
- Pixel encoding
- Color parsing
- Edge cases

## Performance

| Metric | Value |
|--------|-------|
| Parse time | <1ms per command |
| Code generation | <1ms per command |
| Pixel encoding | ~10ms per 100 chars |
| Total per command | ~15ms |

## Limitations

1. **Vocabulary**: Limited to known verbs, objects, and colors
2. **Context**: No state tracking between commands (each command is independent)
3. **Complexity**: No nested expressions or compound statements
4. **Wordbase**: Requires words in wordbase for pixel encoding

## Future Extensions

- [ ] Support for loops and conditionals
- [ ] Variable assignment and usage
- [ ] Function definitions
- [ ] Stateful programming (variable persistence)
- [ ] Grammar extensions for complex queries
- [ ] LLM-assisted parsing for unknown commands

## Files

- `src/nlp/natural_language_compiler.py` — Core NLC implementation
- `src/nlp/__init__.py` — Module exports
- `tests/test_natural_language_compiler.py` — Test suite
- `tools/speak.py` — CLI integration (`natural` subcommand)
- `db/wordbase.db` — Word database for pixel encoding

## Related Systems

- **PixelTokenizer** — Text → pixel encoding
- **Visual Audio Codec** — Phoneme/byte encoding to audio
- **Wordbase** — Spatial word database
- **Geometry OS** — Spatial computing environment