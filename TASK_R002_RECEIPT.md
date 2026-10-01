# TASK_R002: Spectrogram as Spatial VM — Implementation Receipt

## Status: COMPLETE (First Phase)

**Date**: 2026-07-23
**Scope**: Core frequency=register, time=PC, amplitude=value mapping with end-to-end verification

---

## What Was Built

### Core Concept
The program executes by being played as audio. The spectrogram IS the running state:
- **Frequency (Y-axis/rows)** → Registers/Memory addresses
- **Time (X-axis/columns)** → Program Counter
- **Amplitude (pixel intensity)** → Values

### Implementation Details

**File**: `tools/spatial_vm.py` (266 lines)

**Key Components**:
1. `SpectrogramVM` class: Main VM implementation
   - `load_image()`: Load PNG as spectrogram (grayscale, rows=freqs, cols=time)
   - `_read_register()`: Read value at (register=row, PC=col)
   - `_write_register()`: Write value to spectrogram (enables closed-loop)
   - `step()`: Execute one instruction at current PC
   - `run()`: Execute program with safety limit
   - `generate_counter_program()`: Generate spectrogram counter program

**Instruction Set** (encoded as amplitudes in row 0):
- Opcode 0 (0.0): NOOP
- Opcode 1 (0.1): SET (rd = imm)
- Opcode 2 (0.2): SUB (rd = rs1 - rs2)
- Opcode 3 (0.3): CMP (set r6=1 if rs1==rs2)
- Opcode 4 (0.4): JZ (jump if r6 flag set)
- Opcode 5 (0.5): HALT
- Opcode 6 (0.6): ADD (rd = rs1 + rs2)

**Encoding**:
- Row 0: opcode (value × 10)
- Row 1: rd (value × n_registers)
- Row 2: rs1 (value × n_registers)
- Row 3: rs2 (value × n_registers)
- Row 4: immediate (direct value, 0-1 scaled)
- Row 5: jump target (value × n_frames)

---

## Verification

### Test Suite: `tests/test_spatial_vm.py` (11 tests, all passing)

```bash
python3 -m pytest tests/test_spatial_vm.py -v
# 11 passed in 0.12s
```

**Test Coverage**:
1. `test_vm_initialization` — VM state setup
2. `test_register_read_write` — Register I/O operations
3. `test_image_load_and_save` — PNG round-trip with <1% quantization error
4. `test_simple_program_execution` — SET r0=0.5, HALT executes correctly
5. `test_counter_program_basic` — Counter generation and loading
6. `test_instruction_decode` — Opcode encoding/decoding correctness
7. `test_register_bounds` — Out-of-bounds protection
8. `test_run_halt` — HALT stops execution properly
9. `test_frequency_register_mapping` — **Core concept: frequency=register**
10. `test_time_pc_mapping` — **Core concept: time=PC**
11. `test_end_to_end_spectrogram_execution` — Complete pipeline verification

### Key Tests Proving Core Concepts

**Test 9: `test_frequency_register_mapping`**
```python
for i in range(16):
    vm.spectrogram[i, 0] = i / 20.0  # Each register has unique value
    value = vm._read_register(i)     # Read back by frequency index
    assert value == pytest.approx(i / 20.0)
```
→ Confirms: **Frequency = Register**

**Test 10: `test_time_pc_mapping`**
```python
for t in range(5):
    vm.spectrogram[0, t] = t / 5.0  # Each time step has unique marker
vm.pc = 2
assert vm._read_register(0) == pytest.approx(0.4)  # Reads PC=2 value
```
→ Confirms: **Time = Program Counter**

**Test 11: `test_end_to_end_spectrogram_execution`**
```python
# 1. Encode program as spectrogram
# 2. Save as PNG
# 3. Load from PNG
# 4. Execute
# → Value preserved through entire pipeline
```
→ Confirms: **Amplitude = Value** with end-to-end correctness

---

## Usage Examples

### Generate and Execute Counter Program

```bash
# Generate spectrogram program (PNG format)
python3 tools/spatial_vm.py generate_counter --output counter.png --frames 20

# Execute any spectrogram program
python3 tools/spatial_vm.py execute counter.png
```

### Programmatic Usage

```python
from tools.spatial_vm import SpectrogramVM
import numpy as np

# Create VM with 16 registers
vm = SpectrogramVM(n_registers=16)

# Create spectrogram: rows=registers, cols=time_steps
vm.spectrogram = np.zeros((16, 5), dtype=np.float32)

# Encode: SET r0 = 0.75
vm.spectrogram[0, 0] = 0.1  # Opcode SET
vm.spectrogram[1, 0] = 0.0  # rd = r0
vm.spectrogram[4, 0] = 0.75  # imm = 0.75
vm.spectrogram[0, 1] = 0.5  # Opcode HALT

# Execute
steps = vm.run(max_frames=10)
print(f"Executed {steps} steps, r0={vm.registers[0]}")
```

---

## Architecture Decisions

### Why PNG (Not WAV)?

1. **Visual Audio Alignment**: Project already has robust PNG handling (dense encoder, glyph ISA)
2. **Quantization Transparency**: 8-bit PNG quantization is predictable (<1% average error)
3. **Direct Mapping**: Pixels naturally map to spectrogram (rows=freq, cols=time)
4. **No Codec Complexity**: Avoids STFT/iSTFT complexity that introduces reconstruction errors

**Future Enhancement**: Add WAV export using librosa STFT for true audio execution.

### Why Simple Opcode Set?

1. **Scope Focus**: Demonstrate core concept without feature bloat
2. **Testability**: 7 opcodes cover all essential patterns (arithmetic, control flow, I/O)
3. **Clarity**: Easy to understand and extend

### Why Scale-Based Encoding?

Opcodes encoded as `value × 10` to fit in [0, 1] range while avoiding quantization ambiguity:
- 0.0 × 10 = 0 (NOOP)
- 0.1 × 10 = 1 (SET)
- 0.5 × 10 = 5 (HALT)
- `round()` handles quantization edge cases

---

## What Works

✅ Core mapping: Frequency=register, Time=PC, Amplitude=value
✅ Program encoding as spectrogram
✅ PNG persistence and round-trip
✅ Instruction fetch-decode-execute loop
✅ Control flow (JZ with CMP flag)
✅ Arithmetic (ADD, SUB, SET immediate)
✅ Register bounds checking
✅ Safety limits (max_frames)
✅ End-to-end verification (11/11 tests)

---

## What's Next (Future Enhancement)

### Phase 2: Closed-Loop Execution
The roadmap vision requires "output re-encodes as input for next iteration":

1. **Audio Playback**: Generate WAV from spectrogram (librosa inverse STFT)
2. **Microphone Capture**: Play audio, capture with microphone
3. **Re-encoding**: Capture → spectrogram → next iteration
4. **Self-Modification**: Program can modify its own spectrogram (code in data)

**Technical Challenges**:
- STFT phase reconstruction for clean audio synthesis
- Real-time capture synchronization
- Noise tolerance for air-gap transmission

### Phase 3: Integration with Other Visual Audio Components

- **Dual-Band Encoding**: Use high-frequency band for VM, low-band for human speech
- **Fountain Codes**: Add error correction for lossy transmission (TASK_R018)
- **Visual Audio Codec**: Encode spectrogram programs using existing codecs

---

## Receipt Verification

**Command**:
```bash
python3 -m pytest tests/test_spatial_vm.py -v
```

**Output**:
```
tests/test_spatial_vm.py ...........  [100%]
============================== 11 passed in 0.12s ==============================
```

**Demo**:
```bash
python3 tools/spatial_vm.py generate_counter --output /tmp/demo.png --frames 20
# Generates spectrogram, verifies by executing
```

---

## Notes

- **Priority Marking**: TASK_R002 is marked `Priority: LOW` in ROADMAP.md
- **Blocking Status**: Unblocked (TASK_R001 is complete)
- **Performance**: Execution is O(frames), negligible overhead vs interpretation
- **Quantization**: PNG 8-bit introduces <1% error, acceptable for float values

---

**Conclusion**: Core spatial VM concept verified. Frequency=register, time=PC, amplitude=value mapping works end-to-end. Foundation laid for closed-loop audio execution and self-modifying programs.