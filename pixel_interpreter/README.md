# Pixel Interpreter — CPU Emulator for Pixel-Encoded Programs

This emulator implements the pixel-interpreter instruction set architecture (ISA) on the CPU, providing a reference implementation that matches the WGSL microcode interpreter's exact semantics.

## ISA Overview

Programs are encoded as RGBA PNG images where each texel represents either an instruction or data word.

### Memory Layout

| Region | Description |
|--------|-------------|
| Row 0 | CPU State: (0,0)=PC, (1,0)=Accumulator, (2,0)=Zero Flag, (3,0)=Halt Flag |
| Row 1...127 | Code Space (instruction stream) |
| Row 128+ | Data RAM / Stack / Scratchpad |

### Instruction Encoding

Each instruction texel packs fields into RGBA channels:
- **R**: Opcode
- **G**: Source A (coordinate X, immediate, or reserved)
- **B**: Source B (coordinate Y, immediate value, or reserved)
- **A**: Destination/Immediate

For control-flow and memory ops:
- **LOAD/STORE**: G=coord_x, B=coord_y
- **JMP/JZ**: G=dest_x, B=dest_y
- **SET**: A=immediate value
- **ADD/SUB**: B=addend/subtrahend

### Opcodes

| Opcode | Name | Semantics |
|--------|------|-----------|
| 0 | NOP | No operation |
| 1 | SET | Acc = Immediate (from A channel) |
| 2 | ADD | Acc = Acc + src_b |
| 3 | SUB | Acc = Acc - src_b |
| 4 | LOAD | Acc = Memory[(src_a, src_b)] |
| 5 | STORE | Memory[(src_a, src_b)] = Acc |
| 6 | JMP | PC = (src_a, src_b) |
| 7 | JZ | If ZF == 1 then PC = (src_a, src_b) |
| 255 | HALT | Stop execution |

## Usage

### Basic Execution

```bash
# Run built-in test program (SET 5; ADD 3; SUB 8; HALT)
python3 pixel_interpreter/cpu_emulator.py -t

# Run custom program
python3 pixel_interpreter/cpu_emulator.py program.png -t -c 1000

# Save final state
python3 pixel_interpreter/cpu_emulator.py program.png -o final_state.png
```

### Verify State

```bash
# Verify accumulator and flags match expected values
python3 pixel_interpreter/verify_state.py final_state.png --acc 0 --zf 1 --halt 1
```

### Run Smoke Tests

```bash
# Execute full test suite
python3 pixel_interpreter/smoke_test.py
```

## Examples

### Example 1: Arithmetic (SET 5; ADD 3; SUB 8; HALT)

Expected: `Acc = 0, ZF = 1` (since 5 + 3 - 8 = 0)

```python
prog = np.zeros((256, 256, 4), dtype=np.uint8)

# Code at y=1
prog[1, 0] = [OP_SET, 0, 0, 5]    # SET 5
prog[1, 1] = [OP_ADD, 0, 3, 0]    # ADD 3
prog[1, 2] = [OP_SUB, 0, 8, 0]    # SUB 8
prog[1, 3] = [OP_HALT, 0, 0, 0]   # HALT
```

### Example 2: Loop (Countdown to Zero)

```python
prog = np.zeros((16, 16, 4), dtype=np.uint8)

prog[1, 0] = [OP_SET, 0, 0, 3]    # SET 3
prog[1, 1] = [OP_SUB, 0, 1, 0]    # LOOP: SUB 1
prog[1, 2] = [OP_JZ, 4, 1, 0]     # JZ DONE
prog[1, 3] = [OP_JMP, 1, 1, 0]    # JMP LOOP
prog[1, 4] = [OP_HALT, 0, 0, 0]   # DONE: HALT
```

Execution:
- Cycle 0: SET 3 → Acc = 3
- Cycle 1: SUB 1 → Acc = 2
- Cycle 2: JZ not taken (ZF=0), JMP to LOOP
- Cycle 3: SUB 1 → Acc = 1
- Cycle 4: JZ not taken, JMP to LOOP
- Cycle 5: SUB 1 → Acc = 0, ZF = 1
- Cycle 6: JZ taken to DONE
- Cycle 7: HALT

Total: 10 cycles (as traced by smoke test)

## Architecture Rationale

This CPU emulator serves three critical purposes:

1. **Golden Reference**: Provides verified execution traces for validating the WGSL microcode interpreter on real GPU hardware.

2. **Immediate Testability**: Allows developing and debugging pixel-encoded programs without requiring GPU compute submission (which currently hangs in this environment).

3. **ISA Specification**: The Python implementation acts as the authoritative spec for opcode semantics, memory layout, and encoding rules.

## Matching WGSL Microcode

The WGSL microcode interpreter (`microcode.wgsl`) implements identical semantics:

```wgsl
case OP_LOAD: {
    // coord = (src_a, src_b)
    let cell = textureLoad(memory_in, vec2<i32>(i32(src_a), i32(src_b)), 0);
    reg_acc.r = cell.r;
}
case OP_STORE: {
    // coord = (src_a, src_b)
    write_addr = vec2<i32>(i32(src_a), i32(src_b));
    write_val = vec4<u32>(reg_acc.r, 0u, 0u, 255u);
}
```

The CPU emulator mirrors this exactly in `cpu_emulator.py`:

```python
elif opcode == OP_LOAD:
    coord = (int(src_a) % self.width, int(src_b) % self.height)
    cell = self.memory[coord[1], coord[0]]
    self.accumulator = cell[0]

elif opcode == OP_STORE:
    x = int(src_a) % self.width
    y = int(src_b) % self.height
    write_addr = (x, y)
    write_val = np.array([self.accumulator, 0, 0, 255], dtype=np.uint32)
```

## Future Work

When GPU compute submission works, the verification flow will be:

1. Write program → PNG
2. Run CPU emulator → trace.log + golden_state.png
3. Upload PNG to GPU via launcher.py
4. Dispatch WGSL microcode → N cycles
5. Read back GPU state → verify against golden_state.png
6. Compare traces for cycle-accurate equivalence

## Files

- `cpu_emulator.py` — CPU-side PixelCPU emulator class
- `microcode.wgsl` — Fixed WGSL microcode interpreter (never recompiles)
- `smoke_test.py` — Comprehensive test suite
- `verify_state.py` — State PNG verification utility
- `launcher.py` — Future GPU launcher (pending compute fix)

## License

Part of Visual Audio project — pixel-native spatial programming research.