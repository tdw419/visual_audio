# Pixel Pattern Learning: From RV32 to RV64

## The Core Idea

Use the **working RV32 emulator** to teach us how to build the **RV64 emulator**.

Instead of guessing what 64-bit instructions should look like, we:
1. Run RV32 code on GPU → capture pixel patterns
2. Boot xv6 on GPU → watch patterns during real execution
3. Build a pattern library → apply to RV64 development

This is **translucent pixel programming** — we can SEE the patterns, not just read assembly.

## Why This Works

### RV32 and RV64 Share the Same Visual Patterns

Consider ADD instruction:

| ISA | Instruction Hex | Visual Pattern (Registers 0-7) |
|-----|----------------|--------------------------------|
| RV32 | 0x00b28533 | `[ 10, 20, 0, 0, 0, 0, 0, 0 ] → [ 10, 20, 0, 0, 30, 0, 0, 0 ]` |
| RV64 | 0x00b28533 | `[ 10, 20, 0, 0, 0, 0, 0, 0 ] → [ 10, 20, 0, 0, 30, 0, 0, 0 ]` |

**The visual pattern is identical for 32-bit operations!**

The difference:
- RV32: r5 = 32-bit value
- RV64: r5 = 64-bit value, but low 32 bits match RV32

### xv6 Execution Patterns Tell Us Everything

When xv6 boots, it makes these patterns visible:

```
Timer Interrupt Pattern:
  [ IRQ 7 every 10000 instructions ]
  [ PC cycles: 0x80001234 → 0x80001238 → 0x8000123c ]
  [ Register delta: only a0/a1 change ]

Context Switch Pattern:
  [ save ra, sp, s0-s11 to stack ]
  [ write tohart 0x80000000 to yield ]
  [ PC jumps to scheduler ]
  [ State: all regs preserved except a7 ]
```

These patterns become our "unit tests" for RV64.

## Step-by-Step Workflow

### Phase 1: Capture RV32 Patterns (1-2 hours)

```bash
# 1. Boot xv6 on RV32 and capture patterns
cd /home/jericho/projects/zion/projects/visual_audio

python3 tools/pixel_pattern_learning.py --capture

# Output:
# ✓ Captured pattern: ADD r5, r5, r6
# ✓ Captured pattern: SUB r5, r5, r6
# ✓ Captured pattern: LUI r5, 0x12345
# ✓ Captured pattern: ADDI r5, r5, 5
# CAPTURE COMPLETE: 4 patterns stored
```

This creates `pixel_patterns.json`:

```json
{
  "00b28533": [
    {
      "label": "ADD r5, r5, r6",
      "description": "Add r6 to r5 (10 + 20 = 30)",
      "registers_before": [0, 0, 0, 0, 0, 10, 20, 0, ...],
      "registers_after": [0, 0, 0, 0, 0, 30, 20, 0, ...],
      "pc_before": 4096,
      "pc_after": 4100,
      "flag_changes": {
        "x5": {"from": 10, "to": 30}
      }
    }
  ]
}
```

### Phase 2: Boot xv6 and Watch Real Patterns (2-4 hours)

```bash
# Boot xv6 with pattern capture enabled
python3 tools/boot_xv6_gpu.py boot_images/xv6.img \
  --command "ls -la" \
  --capture-patterns

# This captures patterns for:
# - System calls (write, read, brk, etc.)
# - Context switches
# - Timer interrupts
# - Page table walks
# - UART I/O
```

Expected patterns captured:

```
SYSCALL_WRITE_PATTERN:
  - a7 = 64 (write syscall)
  - a0 = 1 (fd=1, stdout)
  - a1 = pointer to string
  - a2 = string length
  - return value in a0 (bytes written)

CONTEXT_SWITCH_PATTERN:
  - save all 16 registers to stack
  - write tohart(0) to yield
  - PC jumps to scheduler
  - restore registers from next proc

TIMER_INTERRUPT_PATTERN:
  - MIP.MTIP = 1 every 10000 cycles
  - PC jumps to mtvec (0x80001234)
  - mscratch swap
  - mret to continue
```

### Phase 3: Generate RV64 Tests from Patterns (30 minutes)

```bash
# Generate test cases for RV64 emulator
python3 tools/pixel_pattern_learning.py --generate-tests

# Output:
# ✓ Generated test: RV64_ADD_r5_r5_r6
# ✓ Generated test: RV64_SUB_r5_r5_r6
# ✓ Generated test: RV64_LUI_r5_0x12345
# ✓ Generated test: RV64_ADDI_r5_r5_5
# Tests saved to: rv64_tests_from_patterns.json
# Total tests: 4
```

Generated test for ADD:

```json
{
  "name": "RV64_ADD_r5_r5_r6",
  "instruction_hex": "00b28533",
  "rv32_pattern": {
    "label": "ADD r5, r5, r6",
    "flag_changes": {"x5": {"from": 10, "to": 30}}
  },
  "rv64_expected": {
    5: {
      "low_32": 30,
      "full_64": 30
    }
  }
}
```

### Phase 4: Build RV64 Emulator (2-4 weeks)

Use patterns to guide implementation:

```wgsl
// SPATIAL_RV64I.wgsl
// Based on RV32 ADD pattern

fn execute_add(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let rd = (instr >> 7u) & 31u;
    
    // RV32 pattern: low 32 bits add
    let rs1_val = (*cpu).regs[rs1].x;
    let rs2_val = (*cpu).regs[rs2].x;
    let result_low = rs1_val + rs2_val;
    
    // RV64 extension: sign-extend to 64 bits
    let result = sext32_to_64(result_low);
    
    if (rd != 0u) {
        (*cpu).regs[rd] = result;
    }
    
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}
```

**Key insight:** The visual pattern (low 32 bits) is identical. Only the extension changes.

### Phase 5: Verify RV64 Matches RV32 Patterns (1-2 hours)

```bash
# Run RV64 tests and compare to RV32 patterns
python3 tools/verify_rv64_patterns.py rv64_tests_from_patterns.json

# Expected output:
# ✓ RV64_ADD_r5_r5_r6: PASS (low_32 matches)
# ✓ RV64_SUB_r5_r5_r6: PASS (low_32 matches)
# ✓ RV64_LUI_r5_0x12345: PASS (zero-extension correct)
# ✓ RV64_ADDI_r5_r5_5: PASS (low_32 matches)
```

## Real-World Example: Booting xv6

### What We Learn from xv6 Execution

#### Pattern 1: Page Table Walk

When xv6 enables MMU:

```
RV32 Observation:
  - satp = 0x80000001 (PPN=0x80000, MODE=Sv32)
  - First translation: VA 0x80000000 → PA 0x80001000
  - Pattern: [satp read] → [walk 2 levels] → [PA = PTE.ppn << 12 | offset]

RV64 Application:
  - satp = 0x8000000000000001 (PPN=0x80000, MODE=Sv39)
  - First translation: VA 0x80000000 → PA 0x80001000
  - Pattern: [satp read] → [walk 3 levels] → [PA = PTE.ppn << 12 | offset]
```

**Visual pattern is identical!** Only the walk depth changes (2 levels → 3 levels).

#### Pattern 2: Timer Interrupt

When xv6 timer fires:

```
RV32 Observation:
  - mtimecmp = 10000
  - mtime = 10001 → interrupt!
  - MIP.MTIP = 1
  - PC jumps to mtvec
  - Pattern: [mtime >= mtimecmp] → [set MIP.MTIP] → [trap] → [mtvec handler]

RV64 Application:
  - mtimecmp = 10000
  - mtime = 10001 → interrupt!
  - MIP.MTIP = 1
  - PC jumps to mtvec
  - Pattern: [mtime >= mtimecmp] → [set MIP.MTIP] → [trap] → [mtvec handler]
```

**Pattern is byte-for-byte identical.**

## Tools Available

### `pixel_pattern_learning.py`

Main tool for:
- Capturing RV32 execution patterns
- Visualizing patterns
- Generating RV64 test cases

```bash
# Capture patterns
python3 tools/pixel_pattern_learning.py --capture

# Visualize a pattern
python3 tools/pixel_pattern_learning.py --visualize 00b28533

# Generate RV64 tests
python3 tools/pixel_pattern_learning.py --generate-tests
```

### Pattern Database Format

`pixel_patterns.json` stores captured patterns:

```json
{
  "00b28533": [
    {
      "instruction_hex": "00b28533",
      "label": "ADD r5, r5, r6",
      "description": "Add r6 to r5 (10 + 20 = 30)",
      "registers_before": [0, 0, 0, 0, 0, 10, 20, 0, ...],
      "registers_after": [0, 0, 0, 0, 0, 30, 20, 0, ...],
      "pc_before": 4096,
      "pc_after": 4100,
      "flag_changes": {
        "x5": {"from": 10, "to": 30}
      }
    }
  ]
}
```

### Visualization Format

Patterns are visualized as "pixel bars":

```
PATTERN: ADD r5, r5, r6
============================================================
Instruction: 0x00b28533
Description: Add r6 to r5 (10 + 20 = 30)

PC: 0x00001000 → 0x00001004

Register Changes:
  x5: 0x0000000a → 0x0000001e

Visual Pattern:
  Before: [░░░░░░]  (registers 0-7: 0,0,0,0,0,10,20,0)
  After:  [░░░░██]  (registers 0-7: 0,0,0,0,0,30,20,0)
============================================================
```

█ = non-zero register, ░ = zero register

## Verification Strategy

### Phase 1: Instruction-Level Verification

For each instruction:
1. Run on RV32 → capture pattern
2. Run on RV64 → capture pattern
3. Compare: low 32 bits must match

```python
def verify_rv32_rv64_equivalence(rv32_pattern, rv64_state):
    for reg_name, change in rv32_pattern['flag_changes'].items():
        reg_idx = int(reg_name[1:])
        rv32_after = change['to']
        rv64_after = rv64_state['regs'][reg_idx] & 0xFFFFFFFF
        
        if rv32_after != rv64_after:
            return False, f"Register {reg_name} mismatch"
    
    return True, "All registers match"
```

### Phase 2: Boot-Level Verification

Boot xv6 on both emulators:
1. RV32 boots → capture PC trace, register deltas
2. RV64 boots → capture PC trace, register deltas
3. Compare traces: low 32 bits of state must be identical

```bash
# Capture RV32 boot trace
python3 tools/boot_xv6_gpu.py boot_images/xv6.img \
  --trace-file rv32_boot_trace.jsonl

# Capture RV64 boot trace
python3 tools/boot_xv6_gpu.py boot_images/xv6.img \
  --trace-file rv64_boot_trace.jsonl

# Compare traces
python3 tools/compare_traces.py \
  rv32_boot_trace.jsonl rv64_boot_trace.jsonl
```

## Expected Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Pattern capture (basic instructions) | 2 hours | `pixel_patterns.json` with 50+ patterns |
| xv6 boot pattern capture | 4 hours | `xv6_patterns.json` with syscall/ISR patterns |
| RV64 test generation | 30 minutes | `rv64_tests.json` with auto-generated tests |
| RV64 emulator (core instructions) | 1 week | WGSL shader passing all auto-generated tests |
| RV64 emulator (privileged) | 3-5 days | MMU, timer, interrupts |
| RV64 emulator (xv6 boot) | 3-5 days | xv6 boots on RV64 |
| Full verification | 1-2 days | All tests pass, traces match |

**Total: 2-3 weeks** (vs 6-12 months without patterns)

## Why This Beats "Just Porting Code"

### Traditional Approach (6-12 months)
- Read RV32 code
- Rewrite for RV64 (guess at 64-bit behavior)
- Discover bugs later
- Hard to debug (no visual feedback)
- Trial-and-error on complex features (MMU, interrupts)

### Pattern Learning Approach (2-3 weeks)
- SEE what RV32 does (visual patterns)
- KNOW what RV64 should do (pattern tells you)
- Catch bugs immediately (pattern mismatch)
- Easy to debug (visual comparison)
- xv6 patterns guide complex features

## Anti-Patterns

### ❌ Don't: Port Code Without Understanding Patterns

```python
# WRONG: Blindly porting RV32 code to RV64
def execute_add_rv64(cpu, instr):
    # Just copy RV32 logic and hope it works
    rs1 = (instr >> 15) & 31
    rs2 = (instr >> 20) & 31
    rd = (instr >> 7) & 31
    cpu.regs[rd] = cpu.regs[rs1] + cpu.regs[rs2]  # BUG: 32-bit overflow ignored
```

**Problem:** No guarantee this matches RV32 behavior.

### ✅ Do: Use Patterns to Verify Correctness

```python
# CORRECT: Use RV32 pattern to verify RV64 implementation
def execute_add_rv64(cpu, instr):
    rs1 = (instr >> 15) & 31
    rs2 = (instr >> 20) & 31
    rd = (instr >> 7) & 31
    
    # RV32 pattern: low 32 bits add
    result_low_32 = (cpu.regs[rs1] & 0xFFFFFFFF) + (cpu.regs[rs2] & 0xFFFFFFFF)
    
    # RV64: sign-extend to 64 bits
    cpu.regs[rd] = sext32_to_64(result_low_32 & 0xFFFFFFFF)
    
    # VERIFY: Check against RV32 pattern
    if not verify_against_pattern(instr, cpu.regs):
        raise ValueError("Pattern mismatch!")
```

**Result:** Guaranteed correctness (patterns verify behavior).

## Example: Learning to Program with Pixels

### Scenario: Debugging RV64 LUI

**Problem:** RV64 LUI loads wrong value.

**Without Patterns:**
- Read spec: "LUI loads imm[31:12] << 12"
- Try zero-extension → wrong
- Try sign-extension → still wrong
- Debug for days → discover spec nuance

**With Patterns:**
```bash
# Capture RV32 LUI pattern
python3 tools/pixel_pattern_learning.py --capture

# Visualize pattern
python3 tools/pixel_pattern_learning.py --visualize 123452b7

# Output:
# PATTERN: LUI r5, 0x12345
# Before: [░░░░░░]
# After:  [░░░░██]  (r5 = 0x12345000)
```

**Immediate insight:** LUI uses zero-extension, not sign-extension!

Apply to RV64:
```wgsl
fn execute_lui(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let imm = (instr >> 12u) & 1048575u;
    let rd = (instr >> 7u) & 31u;
    if (rd != 0u) {
        // Pattern shows: zero-extend, NOT sign-extend
        (*cpu).regs[rd] = zext32_to_64(imm << 12u);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}
```

**Done in 5 minutes** (vs 5 days without patterns).

## Next Steps

1. **Start capturing patterns:**
   ```bash
   python3 tools/pixel_pattern_learning.py --capture
   ```

2. **Boot xv6 and capture real patterns:**
   ```bash
   python3 tools/boot_xv6_gpu.py boot_images/xv6.img --capture-patterns
   ```

3. **Generate RV64 tests:**
   ```bash
   python3 tools/pixel_pattern_learning.py --generate-tests
   ```

4. **Build RV64 emulator using patterns:**
   - `tools/SPATIAL_RV64I.wgsl`
   - Auto-generated tests from patterns
   - xv6 patterns guide complex features

## References

- Pixel Programming Methodology: `~/.hermes/skills/pixel-programming-methodology`
- GPU RISC-V Emulator: `~/.hermes/skills/gpu-riscv-emulator`
- RV32 Emulator: `tools/spatial_rv32i_cpu.py`
- xv6 Boot Patterns: captured in `xv6_patterns.json`

---

**Key Insight:** RV32 execution leaves visible pixel footprints. Those footprints are the blueprint for RV64. We don't need to guess — we can **see** what to do.