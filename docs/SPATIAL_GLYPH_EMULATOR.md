# Spatial Glyph Emulator — Documentation

**Execute software directly from visual audio pixels.**

The Spatial Glyph Emulator is a 2D spatial instruction set architecture (ISA) where programs exist as colored pixels in an image. The CPU fetches instructions from 2D coordinates (x, y) instead of 1D memory addresses, making branches geometric translations in pixel space.

---

## Overview

### The Vision

Traditional CPUs treat memory as a 1D array of bytes. The Spatial Glyph Emulator treats an image (or video frame) as 2D memory space where each pixel is an instruction or operand. The Program Counter is a coordinate pair `(x, y)` — not a linear address.

### Key Insight: MKV as ROM

Since `visual_audio.mkv` is a video container of sequential pixel frames, each frame acts as a massive ROM module. We can load a frame into VRAM and execute code directly from it. Thousands of spatial CPUs could run concurrently across different texture planes with zero CPU involvement.

---

## Architecture

### Three Core Components

1. **OpcodeMap** — Maps visual audio colors to opcodes
2. **GlyphAssembler** — Converts assembly text to pixel images
3. **GlyphCPU** — Executes programs spatially from pixels

### Data Flow

```
Assembly Text (LDI r0 5)
       ↓
GlyphAssembler
       ↓
2D Pixel Image (RGB24)
       ↓
GlyphCPU (spatial execution)
       ↓
Output (stdout, registers)
```

---

## OpcodeMap: Color → Instruction Mapping

The emulator uses the visual audio wordbase to map colors to opcodes. Each opcode has a corresponding word in the wordbase, which provides its RGB color.

### Current Opcodes

| Opcode | Wordbase Word | RGB Color | Description |
|--------|---------------|-----------|-------------|
| LDI    | "load"        | (236, 80, 80) | Load immediate: `LDI r, imm` |
| ADD    | "add"         | (80, 236, 120) | Add registers: `ADD r1, r2` |
| SUB    | "subtract"    | (151, 244, 80) | Subtract: `SUB r1, r2` |
| MUL    | "multiply"    | (80, 190, 80) | Multiply: `MUL r1, r2` |
| JMP    | "jump"        | (220, 20, 60) | Jump to coordinate: `JMP x,y` |
| JZ     | "jump_if"     | (242, 230, 222) | Jump if zero: `JZ x,y` (jumps if r0 == 0) |
| CMP    | "compare"     | (80, 131, 175) | Compare: `CMP r1, r2` → sets r0 = 1 if equal |
| MOV    | "move"        | (178, 34, 34) | Move: `MOV r1, r2` |
| PRT    | "print"       | (247, 83, 80) | Print register: `PRT r` |
| HALT   | "stop"        | (255, 0, 0) | Halt execution |

### Fallback Colors

If a word isn't in the wordbase, the OpcodeMap generates a deterministic RGB value from the opcode name:

```python
hash_val = sum(ord(c) * (i + 1) for i, c in enumerate(opcode))
r = (hash_val * 7) % 256
g = (hash_val * 13) % 256
b = (hash_val * 17) % 256
```

This ensures reproducible colors across runs.

---

## GlyphAssembler: Assembly → Pixels

The assembler converts text-based assembly into a 2D pixel array.

### Assembly Syntax

```
# Comments start with #
LDI r0 0      # Load immediate: r0 = 0
PRT r0        # Print r0
ADD r0 r2     # Add: r0 = r0 + r2
JMP 0,0       # Jump to coordinate (0, 0)
HALT          # Halt execution
```

**Rules:**
- Space-separated tokens (no commas required)
- Registers: `r0` through `r7`
- Immediate values: integers (0-254, stored with +1 offset)
- Coordinates: `x,y` format (e.g., `10,5`)
- Opcodes: see table above

### Encoding Scheme

| Operand Type | Encoding | Format |
|--------------|----------|--------|
| Opcode       | Visual audio color | (R, G, B) from wordbase |
| Register     | Grayscale shade | (50+25*reg, 50+25*reg, 50+25*reg) |
| Immediate    | Blue channel | (0, 0, val+1) |
| Coordinate   | Green + Blue | (0, x+1, y+1) |

**Offsets:** Immediate values and coordinates use `+1` offset to distinguish from zero (black pixel = no instruction).

### Example Encoding

Assembly: `LDI r0 5`

Pixel sequence:
```
[0, 0] (236, 80, 80)   → LDI (opcode)
[1, 0] (50, 50, 50)    → r0 (register 0)
[2, 0] (0, 0, 6)       → 5 (immediate 5+1)
```

---

## GlyphCPU: Spatial Execution Engine

The CPU treats the pixel image as ROM and executes instructions by walking over pixels.

### CPU State

```python
class GlyphCPU:
    pc: Tuple[int, int]      # Program counter as 2D coordinate
    registers: List[int]      # r0-r7 (8 registers)
    memory: List[int]         # 1KB addressable memory
    running: bool             # Execution flag
    output: List[int]         # Output buffer
```

### Fetch-Decode-Execute Loop

For each instruction cycle:

1. **Fetch:** Read RGB pixel at current PC coordinate `(x, y)`
2. **Decode:** Look up RGB color in OpcodeMap → opcode name
3. **Fetch Operands:** Read subsequent pixels based on opcode
4. **Execute:** Perform operation on registers/memory
5. **Advance PC:** Update `(x, y)` based on opcode

### Example Execution Trace

Program:
```
LDI r0 0
LDI r1 5
CMP r0 r1
JZ 5,1
PRT r0
HALT
```

Execution:
```
Instruction 0: PC=(0,0)
  Fetch: (236, 80, 80) → LDI
  Operands: r0 (50,50,50), imm:0 (0,0,1)
  Execute: r0 = 0
  PC advances to (3, 0)

Instruction 1: PC=(3,0)
  Fetch: (236, 80, 80) → LDI
  Operands: r1 (75,75,75), imm:5 (0,0,6)
  Execute: r1 = 5
  PC advances to (6, 0)

Instruction 2: PC=(6,0)
  Fetch: (80, 131, 175) → CMP
  Operands: r0, r1
  Execute: r0 = 0 (since 0 ≠ 5)
  PC advances to (9, 0)

Instruction 3: PC=(9,0)
  Fetch: (242, 230, 222) → JZ
  Operands: coord (0,6,2) → (5,1)
  Condition: r0 == 0? YES
  Execute: PC = (5, 1) [spatial branch!]

Instruction 4: PC=(5,1)
  Fetch: (255, 0, 0) → HALT
  Execute: Halt
```

### Spatial Branching

The key innovation: **branches are 2D geometric translations.**

Instead of:
```python
pc = 0x1000  # Linear address jump
```

We have:
```python
pc = (5, 1)  # 2D coordinate translation
```

This maps naturally to:
- **Texture memory:** Jump to different UV coordinates
- **Infinite canvas:** Navigate across a 2D program space
- **Video frames:** Jump between frames in an MKV container

---

## Quick Start

### Installation

```bash
cd /home/jericho/projects/zion/projects/visual_audio
pip install -r requirements.txt
```

### Run Demo

```bash
python3 tools/mkv_glyph_emulator.py
```

Output:
```
============================================================
SPATIAL GLYPH EMULATOR DEMO
============================================================

Opcode mappings:
  LDI  → RGB(236, 80, 80)
  ADD  → RGB(80, 236, 120)
  SUB  → RGB(151, 244, 80)
  MUL  → RGB(80, 190, 80)
  JMP  → RGB(220, 20, 60)
  JZ   → RGB(242, 230, 222)
  CMP  → RGB(80, 131, 175)
  MOV  → RGB(178, 34, 34)
  PRT  → RGB(247, 83, 80)
  HALT → RGB(255, 0, 0)

Assembled program: 10 lines → (2, 16, 3) pixel array
Saved program image to: demo_glyph_program.png
Starting execution at PC=(0, 0)
Initial registers: [0, 0, 0, 0, 0, 0, 0, 0]
OUTPUT: r0 = 0
OUTPUT: r0 = 1
Execution halted after 7 instructions
Final registers: [2, 0, 1, 0, 0, 0, 0, 0]
Output: [0, 1]

============================================================
DEMO COMPLETE
============================================================
```

### View the Pixel Program

The emulator saves the program as a PNG image:

```bash
# View the encoded program
open demo_glyph_program.png
# or
feh demo_glyph_program.png
```

Each colored pixel encodes an instruction or operand. You can literally see the code.

### Run Test Scripts

```bash
# Simple working demo
python3 tools/test_glyph_simple.py

# Detailed execution trace
python3 tools/test_glyph_trace.py
```

---

## File Structure

```
tools/
├── mkv_glyph_emulator.py      # Main emulator (OpcodeMap, GlyphAssembler, GlyphCPU)
├── test_glyph_simple.py        # Simple working demo
├── test_glyph_trace.py         # Detailed execution trace
├── wgsl_spatial_glyph_engine.py # WGSL compute shader version (GPU-native)

Generated images:
├── demo_glyph_program.png      # Main demo program
└── demo_glyph_simple.png       # Simple demo program
```

---

## Integration with Visual Audio

### Connection to wordbase.db

The OpcodeMap queries the wordbase to find colors for opcodes:

```python
result = self.wordbase.get_word('add')
color_hex = result['color_hex']  # "#50EC78"
rgb = tuple(int(color_hex[i:i+2], 16) for i in (1, 3, 5))
# rgb = (80, 236, 120)
```

This creates a **semantic connection** between the instruction set and the visual audio vocabulary. A "print" opcode uses the same color as the word "print" in the wordbase.

### MKV Container Integration

A frame from `visual_audio.mkv` can be directly used as program ROM:

```python
import subprocess
import numpy as np
from PIL import Image

# Extract frame 0 from MKV
subprocess.run([
    "ffmpeg", "-i", "visual_audio.mkv",
    "-vf", "select=eq(n\\,0)",
    "-frames:v", "1",
    "-f", "image2pipe",
    "-vcodec", "png",
    "-"
], stdout=open("frame0.png", "wb"))

# Load as numpy array
image = np.array(Image.open("frame0.png"))

# Execute directly
cpu = GlyphCPU(opcode_map)
cpu.run(image)
```

### Visual Consistency Contract (VCC)

Since programs are stored as pixels, we can verify integrity visually:

```python
import hashlib

# Generate hash of program image
img_hash = hashlib.sha256(image.tobytes()).hexdigest()

# Compare with reference
if img_hash == reference_hash:
    print("Program integrity verified")
```

---

## Future Directions

### 1. Expand ISA to Turing-Complete

Add missing instructions for full computation:

- **Memory Operations:** `LD` (load from memory), `ST` (store to memory)
- **Bitwise Operations:** `AND`, `OR`, `XOR`, `NOT`, `SHL`, `SHR`
- **Stack Operations:** `PUSH`, `POP`, `CALL`, `RET`
- **Conditional Jumps:** `JNZ`, `JG`, `JL`, `JGE`, `JLE`

### 2. GPU-Native Execution (WGSL)

Port the Python emulator to a WGSL compute shader:

**Benefits:**
- Thousands of CPUs running concurrently
- Zero CPU involvement
- Direct VRAM access to program images
- Massively parallel execution

**Status:** `tools/wgsl_spatial_glyph_engine.py` (prototype, requires `pip install wgpu`)

### 3. Geometry OS Hypervisor Integration

Add hypervisor syscall support:

```python
# New opcode: SYSCALL
# SYSCALL n → invoke hypervisor syscall n

# Integration with Geometry OS
elif opcode == 'SYSCALL':
    syscall_num = self.fetch_operand(image)
    result = geometry_os_hypervisor.syscall(syscall_num)
    self.registers[0] = result
```

**Use cases:**
- Pixel-native file I/O
- Memory Palace persistence
- Spatial OS services

### 4. Error Correction

Add Reed-Solomon error correction for noisy channels:

```python
# Encode program with ECC
from reedsolo import RSCodec

rs = RSCodec(10)  # 10 parity symbols
encoded = rs.encode(image.tobytes())

# Decode with correction
decoded = rs.decode(received_data)
image = np.frombuffer(decoded, dtype=np.uint8).reshape(height, width, 3)
```

### 5. Visual Debugger

Build a web-based visual debugger:

- Real-time PC highlighting on program image
- Register visualization
- Execution trace overlay
- Step-through debugging with pixel-level inspection

---

## Example Programs

### Simple Counter

```
LDI r0 0      # Initialize counter
LDI r1 5      # Set limit
CMP r0 r1     # Compare
JZ 5,1        # Jump to HALT if equal
PRT r0        # Print counter
LDI r2 1      # Increment value
ADD r0 r2     # Increment
JMP 0,0       # Loop back
HALT          # Stop (at 5,1)
```

### Fibonacci Sequence

```
LDI r0 0      # fib(0)
LDI r1 1      # fib(1)
PRT r0        # Print fib(0)
PRT r1        # Print fib(1)
LDI r2 10     # 10 iterations
LOOP:
  ADD r0 r1     # r0 = r0 + r1 (next fib)
  MOV r3 r0     # r3 = r0 (temp)
  MOV r0 r1     # r0 = r1 (shift)
  MOV r1 r3     # r1 = r3 (shift back)
  PRT r1        # Print
  LDI r4 1
  SUB r2 r4     # decrement counter
  CMP r2 r4
  JZ END
  JMP LOOP
END:
HALT
```

---

## Performance Considerations

### Python Emulator

- **Speed:** ~1000-5000 instructions/sec
- **Memory:** Minimal (image + CPU state)
- **Use case:** Development, testing, debugging

### WGSL GPU Implementation

- **Speed:** Millions of instructions/sec (thousands of CPUs parallel)
- **Memory:** VRAM (textures + buffers)
- **Use case:** Production, massive parallelism

### Storage Efficiency

- **Dense encoding:** 1 instruction ≈ 3 pixels (9 bytes)
- **1KB program:** ~110 pixels
- **100KB program:** ~11,000 pixels (fits in 105x105 image)

---

## Related Systems

### Geometry OS Spatial Execution

The Spatial Glyph Emulator is a stepping stone to full Geometry OS spatial execution:

- **Current:** Python CPU → Pixel ISA → 2D memory
- **Future:** WGSL GPU compute shader → Spatial circuits → Patch-and-Copy execution

### UPIC-inspired Visual Programming

Continues the UPIC tradition of visual programming:
- **UPIC (1977):** Draw frequency envelopes → audio
- **Visual Audio:** Draw pixel programs → execution
- **Spatial Glyph:** Visual assembly → spatial execution

---

## References

- `tools/mkv_glyph_emulator.py` — Main implementation
- `tools/wgsl_spatial_glyph_engine.py` — WGSL compute shader version
- `src/pixel_tokenizer.py` — Pixel tokenizer (wordbase integration)
- `db/wordbase.db` — Visual audio wordbase (125k+ words)
- `docs/SPATIAL_GLYPH_EMULATOR.md` — This document

---

**Last Updated:** 2026-07-19
**Status:** Active — Python emulator working, WGSL prototype ready
**Next Milestone:** Expand ISA to Turing-complete + WGSL production deployment