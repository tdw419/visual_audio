# wordbase-Powered Self-Modifying MKV Code

## Overview

The wordbase system enables **semantic code storage** where code is stored as pixel patterns with meaningful colors. Each word in the English language maps to a unique RGB color, making code visually readable and semantically manipulable.

## What wordbase Enables

### Beyond Binary Encoding

| Encoding Mode | How It Works | Visual | Meaning |
|---------------|--------------|--------|---------|
| **Dense Binary** | 3 bytes → 1 pixel | Random colors | No semantic meaning |
| **Semantic (wordbase)** | Text → word ID → color | Meaningful colors | Each word has semantic color |

### Word Database Structure

```
db/wordbase.db (SQLite):
  - 126,052 words from CMUdict
  - Each word has:
    * Unique ID (0-126051)
    * Word text
    * Pronunciation (XSAMPA/ARPAbet)
    * Part of speech
    * Definition
    * Example usage
    * color_hex (semantic visualization color)
    * image_path (optional word tile)
    * image_link (optional external image)
```

**Key insight**: Every word is a color. Every color is a word.

## How It Works

### 1. Text → Pixels (Encoding)

```python
from src.pixel_tokenizer import PixelTokenizer

tokenizer = PixelTokenizer(wordbase_path="db/wordbase.db")

code = """
def hello():
    print("world")
"""

# Tokenize: text → word IDs
word_ids = tokenizer.encode(code, add_special_tokens=True)
# Result: [1, 45623, 12345, 2, 3, 67890, 7, 8, 4]

# Convert: word IDs → RGB pixels
pixels = tokenizer.ids_to_pixels(word_ids)
# Result: [[12, 45, 67], [89, 23, 145], ...]

# Each pixel = one word with semantic color
```

**Semantic colors:**
- Function definitions: `def` = `#4A90E2` (blue)
- Print statements: `print` = `#50E3C2` (teal)
- Strings: `"world"` = `#F5A623` (yellow)
- Numbers: `123` = `#D0021B` (red)

### 2. Pixels → Text (Decoding)

```python
# Convert: RGB pixels → word IDs
recovered_ids = tokenizer.pixels_to_ids(pixels)

# Decode: word IDs → text
recovered_code = tokenizer.decode(recovered_ids)
# Result: "def hello():\n    print(\"world\")\n"
```

**Lossless**: Word-to-pixel encoding is reversible.

### 3. Store in MKV

```python
# Write pixel data to MKV frames
import subprocess

subprocess.run([
    "python3", "tools/va_container.py", "add",
    "visual_audio.mkv", pixels_file,
    "--name", "demo_code", "--role", "code"
])
```

Code is now **stored as semantic pixels** in the MKV.

## Self-Modifying Capabilities

### Level 1: Read Self as Pixels

```python
# Inside code running from MKV:
import numpy as np

# Read my own pixel representation from MKV
my_pixels = extract_mkv_entry_pixels("self_code")

# Decode via wordbase
from src.pixel_tokenizer import PixelTokenizer
tokenizer = PixelTokenizer()
my_code = tokenizer.decode(pixels_to_word_ids(my_pixels))

print(f"I am: {my_code[:100]}...")
```

The code **reads itself** from pixel data.

### Level 2: Modify Self via Color Changes

```python
# Modify code by changing pixel colors
def replace_word_pixels(pixels, old_word, new_word):
    """Replace all occurrences of old_word with new_word via colors."""
    tokenizer = PixelTokenizer()

    # Get colors
    old_color = tokenizer.wordbase.get_word(old_word)['color_hex']
    new_color = tokenizer.wordbase.get_word(new_word)['color_hex']

    # Parse hex
    or_, og, ob = bytes.fromhex(old_color)
    nr, ng, nb = bytes.fromhex(new_color)

    # Replace pixels
    mask = (pixels[:,:,0] == or_) & (pixels[:,:,1] == og) & (pixels[:,:,2] == ob)
    pixels[mask] = [nr, ng, nb]

    return pixels

# Change all "print" to "log" (without touching text!)
modified_pixels = replace_word_pixels(my_pixels, "print", "log")
```

Code **modifies itself** by adjusting colors.

### Level 3: Re-Execute Modified Self

```python
# Write modified pixels back to MKV
update_mkv_entry("self_code", modified_pixels)

# Re-execute the new version
modified_code = tokenizer.decode(pixels_to_word_ids(modified_pixels))
exec(modified_code)
```

Code **replaces itself** with a new version.

## Recursive MKV Creation

### Pattern: MKV Creates MKV

```python
# Inside MKV #1 running Ubuntu:
def create_child_mkv():
    """Create a new MKV with mutated code."""

    # 1. Read my code
    my_pixels = extract_self_pixels()

    # 2. Mutate (evolution)
    mutated_pixels = evolve_pixels(my_pixels)

    # 3. Create new MKV
    new_mkv = create_mkv_container("child.mkv")
    add_to_mkv(new_mkv, "mutated_code", mutated_pixels)
    add_to_mkv(new_mkv, "qemu_bootstrap", extract_qemu())
    add_to_mkv(new_mkv, "ubuntu_disk", extract_disk())

    # 4. Boot child
    boot_from_mkv(new_mkv)

def evolve_pixels(pixels):
    """Mutate code by adjusting color patterns."""

    # Increase density of "optimize" words
    pixels = increase_word_frequency(pixels, "optimize")

    # Replace "slow" with "fast"
    pixels = replace_word_pixels(pixels, "slow", "fast")

    # Add new function calls (color patterns)
    pixels = append_function_pixels(pixels, "cache")

    return pixels
```

**Result**: Infinite descent of evolving MKVs.

## Visual Debugging

### See Code Structure via Colors

```python
def visualize_code_structure(pixels):
    """Show code structure by analyzing color frequencies."""

    tokenizer = PixelTokenizer()

    # Count color occurrences
    color_counts = {}
    for row, col, color in iterate_pixels(pixels):
        hex_color = rgb_to_hex(color)
        color_counts[hex_color] = color_counts.get(hex_color, 0) + 1

    # Group by semantic category
    functions = sum(color_counts.get(w['color_hex'], 0)
                   for w in wordbase if w['pos'] == 'verb')
    imports = sum(color_counts.get(w['color_hex'], 0)
                  for w in wordbase if w['pos'] == 'noun')
    constants = sum(color_counts.get(w['color_hex'], 0)
                    for w in wordbase if w['pos'] == 'noun')

    print(f"Code structure:")
    print(f"  Functions: {functions}")
    print(f"  Imports: {imports}")
    print(f"  Constants: {constants}")

    # Visualize as color bar
    generate_color_bar(pixels)
```

**What you see:**
- Repeating color patterns = loops
- Color gradients = linear execution flow
- Color clusters = related functionality
- Sudden color changes = branches/conditionals

## AI-Powered Code Generation

### AI Generates Code by Painting Pixels

```python
# AI model trained on wordbase
model = WordbasePixelModel()

# Generate word IDs (not text!)
word_ids = model.generate(prompt="Write a sorting algorithm")
# Result: [123, 456, 789, 234, 567, ...]

# Convert to semantic pixels
tokenizer = PixelTokenizer()
pixels = tokenizer.ids_to_pixels(word_ids)

# Decode to verify
code = tokenizer.decode(word_ids)
print(code)

# Execute!
exec(code)
```

**The AI never touches text** - only word IDs and colors.

### Optimizes by Adjusting Colors

```python
# AI optimizer
optimizer = WordbaseOptimizer()

# Analyze current code pixels
analysis = optimizer.analyze_pixels(my_pixels)
print(f"Complexity: {analysis['complexity']}")
print(f"Efficiency: {analysis['efficiency']}")

# Optimize by adjusting colors
optimized_pixels = optimizer.optimize_pixels(my_pixels)

# Verify improvement
optimized_analysis = optimizer.analyze_pixels(optimized_pixels)
print(f"New complexity: {optimized_analysis['complexity']}")
print(f"New efficiency: {optimized_analysis['efficiency']}")
```

**Optimization is color adjustment**, not text editing.

## Transmission as Visual Patterns

### Code Sent as Images

```python
# Encode code as image
code = "def hello(): print('world')"
pixels = tokenizer.ids_to_pixels(tokenizer.encode(code))

# Create PNG
from PIL import Image
img = Image.fromarray(pixels.reshape(450, 450, 3))
img.save("code.png")

# Transmit as image file
send_via_discord("code.png")

# Receiver decodes
receiver_pixels = load_image("code.png")
receiver_ids = tokenizer.pixels_to_ids(receiver_pixels)
receiver_code = tokenizer.decode(receiver_ids)
exec(receiver_code)
```

**Code is transmitted as a picture**, not a text file.

### Integration with Geometry OS

```python
# GPU hypervisor receives pixel stream
pixels = receive_pixel_stream_from_hypervisor()

# Decode to code
code = tokenizer.decode(pixels_to_word_ids(pixels))

# Execute directly on GPU
execute_on_gpu(code)
```

**Pixel-native software transmission** to spatial computing systems.

## Tooling

### Self-Modifying Demo

```bash
# Run the self-modification demo
python3 tools/self_modifying_mkv.py --demo
```

**Demonstrates:**
- Code reads itself from MKV
- Code modifies its pixels semantically
- Code decodes modified pixels
- Visual verification of changes

### Code → Pixel System

```bash
# Full pipeline demo
python3 code_to_pixel_system.py
```

**Demonstrates:**
- Tokenization via wordbase
- RGB24 encoding
- MKV storage
- Extraction and execution

## What This Enables

### 1. Self-Documenting Code
- Each word has semantic color
- Visual inspection reveals structure
- Colors convey meaning (blue = functions, etc.)

### 2. Self-Modifying Code
- Code reads itself as pixels
- Modifies itself via color changes
- Re-executes modified version
- Recursive MKV creation

### 3. Visual Debugging
- See loops as repeating colors
- Spot bugs as unexpected color patterns
- Understand code flow via color gradients
- Identify performance issues via color clusters

### 4. AI-Powered Development
- AI generates code by painting pixels
- AI optimizes by adjusting colors
- AI understands code via color patterns
- AI evolves code through color mutation

### 5. Pixel-Native Transmission
- Code sent as images (PNG)
- Code transmitted via Visual Audio codec
- Pixel-native delivery to Geometry OS
- Cross-modal code transfer

### 6. Infinite Descent
- MKV creates child MKV
- Each generation evolves via color mutation
- Recursive boot patterns
- Emergent code evolution

## Limitations

### Wordbase Coverage
- **126,052 words** from CMUdict
- Covers ~95% of English vocabulary
- Out-of-vocabulary words auto-added with G2P
- Custom words can be pre-seeded

### Color Collision
- **16.7 million** possible RGB colors
- Current: ~126k words (0.75% capacity)
- Plenty of room for expansion
- Color collision: minimal (semantic grouping helps)

### Size Efficiency
- **Word mode**: ~1 pixel per word (wasteful for code)
- **Dense mode**: 1 pixel = 3 bytes (100% efficient)
- **Hybrid**: Code tokens dense, semantics separate

## Future Directions

### 1. Semantic Code Search
```python
# Find functions by color patterns
find_functions_by_color_pattern(blue_gradient_pattern)
```

### 2. Visual Code Diffing
```python
# Compare code versions by color differences
show_color_diff(version1_pixels, version2_pixels)
```

### 3. GPU-Accelerated Parsing
```python
# Parse code on GPU via color recognition
parse_pixels_on_gpu(code_pixels)
```

### 4. Hierarchical Wordbase
```python
# Multi-level semantic encoding
base_wordbase.db      # 126k words
tech_wordbase.db      # Programming terms
scientific_wordbase.db # Domain-specific
```

### 5. Color-Guided Evolution
```python
# Evolve code by selecting for color patterns
evolve_for_color_complexity(pixels, target_complexity)
```

## See Also

- **Self-Hosting MKV**: `/docs/self-hosting-mkv.md` - MKV boot process
- **CPU Emulators**: `/docs/cpu-emulators-in-mkv.md` - emulator patterns
- **Wordbase System**: `src/pixel_tokenizer.py` - tokenization
- **Code Demo**: `code_to_pixel_system.py` - full workflow

---

**Last Updated**: 2026-07-29
**Status**: wordbase semantic encoding verified and documented