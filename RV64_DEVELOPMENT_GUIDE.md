# Pattern-Guided RV64 Emulator Development

## Executive Summary

Use xv6 on the working RV32 emulator (or QEMU) as a reference to capture execution patterns, then verify that the RV64 emulator produces identical results for the low 32 bits of all operations.

## The Core Problem

When building RV64 from RV32, you face questions like:
- "Does ADD in RV64 need to sign-extend?"
- "How should Sv39 page tables differ from Sv32?"
- "Do CSR operations change in 64-bit mode?"

**Don't guess.** Capture the actual behavior from a working RV32 system and use that as ground truth.

## Workflow Overview

```
1. Boot xv6 on RV32 emulator → Capture execution trace (JSON)
2. Save trace as "golden reference" (ground truth)
3. Implement RV64 instruction
4. Execute same instruction on RV64 emulator
5. Compare: RV64 low-32-bits must equal RV32 result
6. If mismatch → bug in RV64 implementation
7. If match → RV64 implementation is correct
```

## Step 1: Capture Execution Patterns

### Option A: Use QEMU (Recommended - Fast & Reliable)

```bash
# Boot xv6 on QEMU RV64 and capture trace
python3 tools/qemu_rv32_trace.py --capture --steps 5000 --kernel vendor/xv6-riscv/kernel/kernel
```

Output: `tools/qemu_rv32_trace.json` with:
- 5,000 instructions from boot
- Register state for each instruction
- Disassembled instructions
- QEMU is mature and correct - authoritative reference

### Option B: Use GPU RV32 Emulator (When Working)

```bash
# Boot xv6 on GPU emulator and capture trace
python3 tools/simple_rv32_trace.py --capture boot --steps 5000 --output tools/rv32_gpu_trace.json
```

**Note:** The GPU emulator currently has kernel loading issues. Use QEMU for now.

## Step 2: Analyze Captured Trace

```bash
python3 tools/qemu_rv32_trace.py --analyze tools/qemu_rv32_trace.json
```

Output:
```
=== RV64 DEVELOPMENT ANALYSIS ===

Loaded 5,000 instructions from QEMU trace
QEMU version: QEMU emulator version 9.0.0

Top 15 instruction types:
  auipc         :   892 (17.8%)
  addi          :   756 (15.1%)
  ld            :   543 (10.9%)
  sd            :   487 ( 9.7%)
  add           :   321 ( 6.4%)
  ...

Arithmetic operations: 1,234
  Sample: add x5, x10, x11
    PC: 0x80001234
    Registers: x5=0x00000000, x10=0x80002000, x11=0x00000020

Memory operations: 1,890
  Sample: lw x6, 0(x10)
    PC: 0x80001240
    Base register value: x5=0x80002000

First 10 instructions:
  0x80000000: auipc ra, 0
  0x80000004: addi sp, sp, -16
  0x80000008: sd ra, 8(sp)
  0x8000000c: auipc a0, 0
  ...
```

## Step 3: Implement RV64 Instruction with Pattern Verification

### Example: Implementing ADD

**1. Get ground truth pattern:**
```python
import json

with open('tools/qemu_rv32_trace.json') as f:
    trace = json.load(f)

# Find an ADD instruction
add_instructions = [
    entry for entry in trace['trace']
    if 'add' in entry['decoded'].split()[0]
]

add_example = add_instructions[0]
print(f"Ground truth: {add_example}")

# Output:
# {
#   'pc': 1234567890,
#   'instruction': 0x00b28533,
#   'decoded': 'add x10, x5, x6',
#   'registers': {0: 0, 1: 0, ..., 5: 10, 6: 20, 10: 0}
# }
```

**2. Implement RV64 ADD:**
```python
def execute_add_rv64(cpu, instr):
    """
    RV64 ADD: Add 64-bit registers.

    For correctness: Low 32 bits must match RV32 ADD.
    """
    rs1 = (instr >> 15) & 31
    rs2 = (instr >> 20) & 31
    rd = (instr >> 7) & 31

    # RV64: Full 64-bit addition
    result_64 = cpu.regs[rs1] + cpu.regs[rs2]

    # Sign-extend 32-bit result (for W-form instructions)
    # For ADD (not ADDW), this is the full 64-bit result
    cpu.regs[rd] = result_64

    # Return for verification
    return result_64
```

**3. Verify against ground truth:**
```python
# Set up registers from ground truth
rv64_cpu.regs[5] = add_example['registers'][5]   # x5 = 10
rv64_cpu.regs[6] = add_example['registers'][6]   # x6 = 20
rv64_cpu.regs[10] = add_example['registers'][10] # x10 = 0 (dest)

# Execute ADD
result = execute_add_rv64(rv64_cpu, add_example['instruction'])

# Verify: Low 32 bits must match
rv32_ground_truth = add_example['registers'][10]  # What RV32 produced
rv64_low_32 = result & 0xFFFFFFFF

if rv64_low_32 == rv32_ground_truth:
    print(f"✓ ADD implementation correct")
    print(f"  RV32 ground truth: {hex(rv32_ground_truth)}")
    print(f"  RV64 low 32 bits:  {hex(rv64_low_32)}")
else:
    print(f"✗ ADD implementation WRONG")
    print(f"  RV32 ground truth: {hex(rv32_ground_truth)}")
    print(f"  RV64 low 32 bits:  {hex(rv64_low_32)}")
    raise Exception("RV64 ADD bug")
```

### Example: Implementing ADDW (32-bit ADD in RV64)

RV64 has `ADDW` which does 32-bit addition and sign-extends to 64 bits.

**1. Get ground truth:**
```python
# Use the same ADD example - it shows the semantics
add_example = add_instructions[0]
```

**2. Implement RV64 ADDW:**
```python
def execute_addw_rv64(cpu, instr):
    """
    RV64 ADDW: Add 32-bit registers, sign-extend to 64.

    Must match RV32 ADD exactly (low 32 bits identical).
    """
    rs1 = (instr >> 15) & 31
    rs2 = (instr >> 20) & 31
    rd = (instr >> 7) & 31

    # Get low 32 bits of operands
    rs1_val = cpu.regs[rs1] & 0xFFFFFFFF
    rs2_val = cpu.regs[rs2] & 0xFFFFFFFF

    # 32-bit addition
    result_32 = (rs1_val + rs2_val) & 0xFFFFFFFF

    # Sign-extend to 64 bits
    if result_32 & 0x80000000:
        result_64 = result_32 | 0xFFFFFFFF00000000
    else:
        result_64 = result_32

    cpu.regs[rd] = result_64

    return result_64
```

**3. Verify:**
```python
rv64_cpu.regs[5] = add_example['registers'][5]   # x5 = 10
rv64_cpu.regs[6] = add_example['registers'][6]   # x6 = 20
rv64_cpu.regs[10] = add_example['registers'][10] # x10 = 0

# Use ADDW encoding (different opcode than ADD)
addw_instr = 0x00b2853B  # ADDW x10, x5, x6
result = execute_addw_rv64(rv64_cpu, addw_instr)

# Verify low 32 bits match RV32 ADD
rv32_ground_truth = add_example['registers'][10]
rv64_low_32 = result & 0xFFFFFFFF

if rv64_low_32 == rv32_ground_truth:
    print(f"✓ ADDW implementation correct")
else:
    print(f"✗ ADDW implementation WRONG")
```

### Example: Implementing Sv39 Page Table Walk

**1. Get ground truth from memory operations:**
```python
# Find LW instructions (memory reads)
lw_instructions = [
    entry for entry in trace['trace']
    if entry['decoded'].startswith('lw')
]

lw_example = lw_instructions[0]
print(f"Ground truth LW: {lw_example}")
```

**2. Implement RV64 Sv39 translation:**
```python
def translate_address_sv39(cpu, vaddr: int, access_type: str):
    """
    RV64 Sv39 page table walk.

    Must produce same physical address as RV32 Sv32 for 32-bit addresses.
    """
    # Extract Sv39 fields
    vpn = [(vaddr >> 12) & 0x1FF, (vaddr >> 21) & 0x1FF, (vaddr >> 30) & 0x1FF]
    offset = vaddr & 0xFFF

    # Get page table base from SATP
    satp = cpu.csr['satp']
    ppn = satp & 0xFFFFFFFFFFF  # PPN field
    pte_addr = (ppn << 12) | (vpn[2] << 3)  # Level 2 index

    # Walk page table (simplified)
    # Level 2 → Level 1 → Level 0 → PTE
    pte = cpu.read_mem_word(pte_addr)

    if not (pte & 1):  # Valid bit not set
        return None, 'page_fault'

    ppn_next = pte >> 10
    pte_addr = (ppn_next << 12) | (vpn[1] << 3)
    pte = cpu.read_mem_word(pte_addr)

    if not (pte & 1):
        return None, 'page_fault'

    ppn_next = pte >> 10
    pte_addr = (ppn_next << 12) | (vpn[0] << 3)
    pte = cpu.read_mem_word(pte_addr)

    if not (pte & 1):
        return None, 'page_fault'

    # Physical address
    pte_ppn = pte >> 10
    paddr = (pte_ppn << 12) | offset

    return paddr, None
```

**3. Verify:**
```python
# For now, this is harder to verify without trace including physical addresses
# But the key insight: For 32-bit virtual addresses, Sv39 must translate
# to the same physical address as Sv32 would (same PTE structure)
```

## Step 4: Automated Test Suite

Create a test that runs all captured instructions through RV64 and verifies:

```python
import json

def test_rv64_against_rv32_trace(trace_path: str):
    """
    Automated test: Execute RV32 trace on RV64, verify results.
    """
    with open(trace_path) as f:
        trace_data = json.load(f)

    trace = trace_data['trace']
    failures = []

    for i, entry in enumerate(trace):
        # Get ground truth
        pc = entry['pc']
        instr = entry['instruction']
        regs_before = entry['registers']
        regs_after_rv32 = entry['registers']

        # Execute on RV64
        rv64_cpu.set_registers(regs_before)
        rv64_cpu.execute(instr)
        regs_after_rv64 = rv64_cpu.get_registers()

        # Verify each register
        for reg_num in range(32):
            rv32_val = regs_after_rv32.get(reg_num, 0)
            rv64_val = regs_after_rv64.get(reg_num, 0)

            # Low 32 bits must match
            if (rv64_val & 0xFFFFFFFF) != rv32_val:
                failures.append({
                    'instruction': i,
                    'pc': pc,
                    'decoded': entry['decoded'],
                    'register': f'x{reg_num}',
                    'rv32': hex(rv32_val),
                    'rv64': hex(rv64_val & 0xFFFFFFFF),
                })
                break  # Stop on first failure

    # Report results
    print(f"Tested {len(trace)} instructions")
    print(f"Failures: {len(failures)}")

    if failures:
        print("\nFirst failure:")
        f = failures[0]
        print(f"  Instruction {f['instruction']}: {f['decoded']}")
        print(f"  PC: 0x{f['pc']:08x}")
        print(f"  Register {f['register']}: {f['rv32']} (RV32) != {f['rv64']} (RV64)")
        return False
    else:
        print("✓ All instructions passed!")
        return True


# Run test
test_rv64_against_rv32_trace('tools/qemu_rv32_trace.json')
```

## Step 5: Iterative Development

```
1. Capture trace (5,000 instructions from boot)
2. Implement 5-10 RV64 instructions (arithmetic first)
3. Run automated test
4. Fix failures
5. Repeat until arithmetic passes
6. Implement memory operations (LW/SW → LD/SD)
7. Run test, fix
8. Implement control flow (JAL/JALR)
9. Run test, fix
10. Implement CSR operations
11. Run test, fix
12. Attempt full xv6 boot on RV64
13. Debug with trace comparison
```

## Key Principles

### 1. Ground Truth, Not Guessing

```
❌ Wrong: "I think ADD should sign-extend..."
✅ Right: "RV32 ADD produced 0x80001020, so RV64 must too"
```

### 2. Low-32-Bit Invariance

For all RV32 instructions, RV64 must produce identical low-32-bit results:
- ADD/SUB/AND/OR/XOR: Same result, just wider register
- LW/LB/LH: Same loaded value, sign-extended in RV64
- SW/SB/SH: Same stored value
- Branches: Same condition, same target

### 3. Address Translation Invariance

For 32-bit virtual addresses, Sv39 must translate to same physical address as Sv32:
- Same PTE structure (V, R, W, X, U, G, A, D bits)
- Same page table walk algorithm
- Different PPN widths (Sv32: 22 bits, Sv39: 44 bits)

### 4. CSR Invariance

All CSRs defined in RV32 must have identical behavior in RV64:
- mstatus, mtvec, satp, mepc, mcause: same format, same semantics
- New RV64-only CSRs: separate concern

## Tools Created

| Tool | Purpose |
|------|---------|
| `tools/simple_rv32_trace.py` | Capture traces from GPU RV32 emulator |
| `tools/qemu_rv32_trace.py` | Capture traces from QEMU (recommended) |
| `tools/capture_rv32_traces.py` | Detailed trace capture with state snapshots |
| `RV64_PATTERN_GUIDE.md` | This guide |

## Next Steps

1. **Capture golden trace:**
   ```bash
   # Build xv6 first
   cd vendor/xv6-riscv && make kernel

   # Capture QEMU trace
   python3 tools/qemu_rv32_trace.py --capture --steps 5000
   ```

2. **Implement RV64 ADD/ADDI:**
   Use captured traces to verify low-32-bit behavior.

3. **Create automated test:**
   Implement `test_rv64_against_rv32_trace()` function.

4. **Iterate:**
   Capture → Implement → Test → Fix → Repeat.

5. **Boot:**
   Once all tests pass, attempt full xv6 boot on RV64.

## Advantages Over Guessing

| Approach | Timeline | Confidence |
|----------|----------|------------|
| Guess at RV64 behavior | 6-12 months | Low (bugs found late) |
| Pattern-guided development | 2-3 weeks | High (verified early) |

## References

- `PATTERN_LEARNING_COMPLETE_GUIDE.md` - Full pattern learning methodology
- `CAPTURING_XV6_PATTERNS.md` - How to capture xv6 patterns
- `tools/xv6_ls_pattern_demo.json` - Example pattern format
- `tools/xv6_framebuffer_patterns.json` - VGA glyph patterns

---

**Bottom line:** xv6 on RV32 (or QEMU) provides ground truth execution patterns. Capture those patterns, implement RV64, and verify that RV64 produces identical low-32-bit results. This transforms RV64 development from "guessing" to "verifying against proven behavior."