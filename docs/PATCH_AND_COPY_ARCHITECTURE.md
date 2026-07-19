# Patch-and-Copy Architecture (GPU Code Emission)

The Patch-and-Copy pattern is the pinnacle of Geometry OS's "Fully Native Glyph-Based OS" mandate. It completely eliminates the host CPU from the compilation and execution loop, establishing the GPU as a fully autonomous execution substrate capable of writing and spawning its own logic.

## The Spatial Compiler Pattern

In traditional architectures, a host CPU parses source code, compiles it into binary instructions, uploads those instructions to RAM, and then points an execution core at them.

In the Patch-and-Copy architecture, a **WGSL Compute Shader** acts as a spatial compiler:
1. **The ROM**: A pre-loaded read-only texture buffer containing "Template Opcodes" (the visual signatures of `LDI`, `ADD`, `PRT`, etc., derived from `wordbase.db`).
2. **The VRAM**: An empty dense pixel canvas (Format 1).
3. **The Emission**: The compiler shader pulls a base pixel from ROM, manipulates its RGB channels via bitwise patching to encode operands, and drops the resulting pixel into the VRAM canvas.

## Encoding & Patching Scheme

Because instructions are RGB pixels, emitting code is fundamentally a color manipulation operation.

### Base Templates (ROM)
Loaded as an array of `Pixel` structs representing the raw semantic opcodes:
- `TEMPLATE_LDI` = (236, 80, 80)
- `TEMPLATE_ADD` = (80, 236, 120)
- `TEMPLATE_PRT` = (247, 83, 80)

### Operand Patching (Registers)
Registers are grayscale where the base intensity is `50` and steps by `25` per register number.
- `r0` = (50, 50, 50)
- `r3` = (125, 125, 125)
To patch a register operand, the shader executes:
`val = 50 + (reg_num * 25); emit_pixel(val, val, val);`

### Operand Patching (Immediates)
Immediate integers are stored in the Blue channel.
To patch an immediate operand `42`, the shader executes:
`emit_pixel(0, 0, 42 + 1);`  -> (0, 0, 43)

## The Infinite Loop

Once the spatial compiler shader completes emitting the program (e.g. `LDI r3 42; PRT r3`), it updates the `cpus` buffer to awaken a new Spatial CPU, pointing its Program Counter `(x, y)` at the newly painted pixels.

The new CPU executes the program natively on the GPU, producing output, without the host system ever being aware that the program was written.
