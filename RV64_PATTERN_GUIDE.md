# Using xv6 and RV32 Patterns to Build the RV64 Emulator

## The Core Idea

Instead of guessing what 64-bit instructions should do, we:
1. **Capture** actual execution patterns from the working RV32 emulator
2. **Save** those patterns as ground truth (JSON traces)
3. **Verify** that RV64 produces identical low-32-bit results
4. **Infer** 64-bit behavior from the 32-bit patterns

## Quick Start

### Step 1: Capture RV32 Execution Traces

```bash
# Capture boot sequence (10K instructions)
python3 tools/capture_rv32_traces.py \
    --kernel boot_images/xv6.img \
    --boot-sequence \
    -o tools/rv32_boot_trace.json

# Capture memory access patterns (page table walks)
python3 tools/capture_rv32_traces.py \
    --kernel boot_images/xv6.img \
    --trace-execve \
    -o tools/rv32_memory_trace.json
```

### Step 2: Analyze Traces for RV64 Development

```bash
python3 tools/capture_rv32_traces.py \
    --analyze tools/rv32_boot_trace.json
```

Output shows:
```
=== RV64 DEVELOPMENT ANALYSIS ===

Phase: boot_sequence
  Instructions: 10,000

  Key patterns for RV64:
    Arithmetic operations: 2,341
      Sample: add x5, x10, x11
        Before: x5=0, x10=0x80001000, x11=0x20
        After:  x5=0x80001020

    Memory operations: 1,892
      Sample: lw x6, 0(x10)

    CSR operations: 234
      Sample: csrrw x5, mstatus, x0
        SATP before: 0x0
        SATP after:  0x80000000

    Privilege transitions: 3
      Sample: 3 → 1 (M-mode to S-mode)
```

### Step 3: Use Traces in RV64 Implementation

```python
import json

# Load RV32 ground truth
with open('tools/rv32_boot_trace.json') as f:
    rv32_traces = json.load(f)

# For each instruction in the trace
for instr in rv32_traces['phases'][0]['instructions'][:100]:  # First 100
    pc = instr['pc']
    rv32_before = instr['registers_before']
    rv32_after = instr['registers_after']

    # Execute on RV64 emulator
    rv64_before = get_rv64_registers()
    execute_rv64_instruction(instr['instruction'])
    rv64_after = get_rv64_registers()

    # VERIFY: Low 32 bits must match
    for reg in rv32_before.keys():
        rv32_val = rv32_after[reg]
        rv64_low = rv64_after[reg] & 0xFFFFFFFF

        if rv32_val != rv64_low:
            print(f"✗ MISMATCH at PC={hex(pc)}: {reg}")
            print(f"  RV32: {hex(rv32_val)}")
            print(f"  RV64: {hex(rv64_low)}")
            raise Exception("RV64 behavior incorrect")
```

## Pattern Types Most Useful for RV64

### 1. Arithmetic Operations (ADD, SUB, AND, OR, XOR)

**RV32 pattern:**
```json
{
  "pc": 0x80001000,
  "decoded": "add x5, x10, x11",
  "registers_before": {"x5": 0, "x10": 0x80001000, "x11": 0x20},
  "registers_after": {"x5": 0x80001020, "x10": 0x80001000, "x11": 0x20}
}
```

**RV64 implementation:**
```python
def execute_add_rv64(cpu, instr):
    rs1 = (instr >> 15) & 31
    rs2 = (instr >> 20) & 31
    rd = (instr >> 7) & 31

    # RV64: Full 64-bit add
    cpu.regs[rd] = cpu.regs[rs1] + cpu.regs[rs2]

    # But low 32 bits must match RV32
    # (This is automatically true for ADD)
```

**Verification:**
```python
# Low 32 bits of RV64 result must equal RV32 result
assert (cpu.regs[rd] & 0xFFFFFFFF) == rv32_trace['registers_after']['x5']
```

### 2. Memory Operations (LW, SW, LB, SB)

**RV32 pattern (Sv32):**
```json
{
  "pc": 0x80001020,
  "decoded": "lw x6, 0(x10)",
  "registers_before": {"x6": 0, "x10": 0x80002000},
  "registers_after": {"x6": 0x00000017, "x10": 0x80002000},
  "page_table_walk": {
    "vaddr": 0x80002000,
    "paddr": 0x84002000,
    "vpn": [0x100, 0x100, 0x2],
    "ppn": [0x210, 0x100, 0x2]
  }
}
```

**RV64 implementation (Sv39):**
```python
def execute_lw_rv64(cpu, instr):
    rs1 = (instr >> 15) & 31
    rd = (instr >> 7) & 31

    vaddr = cpu.regs[rs1] & 0xFFFFFFFF  # RV32 address fits in 32 bits

    # RV64 Sv39 page table walk
    paddr, fault = cpu.translate_address_sv39(vaddr, access_type='read')

    if fault:
        cpu.raise_page_fault(fault)
        return

    # Load 32-bit value
    value = cpu.read_mem_word(paddr)

    # Sign-extend to 64 bits
    cpu.regs[rd] = sext32_to_64(value)
```

**Verification:**
```python
# Physical address translation must match
assert paddr == rv32_trace['page_table_walk']['paddr']

# Low 32 bits of loaded value must match
assert (cpu.regs[rd] & 0xFFFFFFFF) == rv32_trace['registers_after']['x6']
```

### 3. CSR Operations (CSRRW, CSRRS, CSRRC)

**RV32 pattern:**
```json
{
  "pc": 0x80000050,
  "decoded": "csrrw x5, mstatus, x0",
  "csr_before": {"mstatus": 0x00001800, "satp": 0x00000000},
  "csr_after": {"mstatus": 0x00000000, "satp": 0x00000000},
  "privilege_before": 3,
  "privilege_after": 3
}
```

**RV64 implementation:**
```python
def execute_csrrw_rv64(cpu, instr):
    csr = (instr >> 20) & 0xFFF
    rs1 = (instr >> 15) & 31
    rd = (instr >> 7) & 31

    # Read old value
    old_val = cpu.read_csr(csr)

    # Write new value (low 32 bits for RV32 CSRs)
    new_val = cpu.regs[rs1] & 0xFFFFFFFF

    # Write CSR
    cpu.write_csr(csr, new_val)

    # Write old value to destination
    if rd != 0:
        cpu.regs[rd] = sext32_to_64(old_val)
```

**Verification:**
```python
# CSR after must match RV32
assert cpu.read_csr(csr) == rv32_trace['csr_after']['mstatus']
```

### 4. Privilege Transitions (ECALL, MRET, SRET)

**RV32 pattern:**
```json
{
  "pc": 0x80000010,
  "decoded": "ecall",
  "privilege_before": 1,
  "privilege_after": 3,
  "pc_after": 0x80000000,
  "mcause": 0x0000000B,
  "mepc": 0x80000010
}
```

**RV64 implementation:**
```python
def execute_ecall_rv64(cpu):
    # Trap to M-mode
    cpu.mepc = cpu.pc
    cpu.mcause = 0x8000000B  # Environment call from S-mode
    cpu.mstatus = (cpu.mstatus & ~0x80) | ((cpu.privilege << 3) & 0x80)
    cpu.privilege = 3  # M-mode
    cpu.pc = cpu.mtvec  # Jump to trap handler
```

**Verification:**
```python
# Trap handling must be identical
assert cpu.privilege == rv32_trace['privilege_after']
assert cpu.mepc == rv32_trace['csr_after']['mepc']
assert cpu.mcause == rv32_trace['csr_after']['mcause']
```

## Complete RV64 Development Workflow

### Phase 1: Capture Ground Truth

```bash
# Boot xv6 on RV32 emulator and capture traces
python3 tools/capture_rv32_traces.py \
    --kernel boot_images/xv6.img \
    --full-boot \
    -o tools/rv32_golden_trace.json
```

This creates a comprehensive trace including:
- Boot sequence (OpenSBI → kernel → shell)
- Page table walks during execve
- CSR state transitions
- Privilege mode changes
- All memory accesses

### Phase 2: Implement RV64 Instructions

Start with base ISA, use traces to verify:

```python
import json

# Load golden trace
with open('tools/rv32_golden_trace.json') as f:
    golden = json.load(f)

# Get boot sequence trace
boot_trace = golden['phases'][0]['instructions']

# Test RV64 ADD implementation
test_add = [i for i in boot_trace if 'add' in i['decoded']][0]

# Execute on RV64
rv64_cpu = RV64Core()
rv64_cpu.regs = {f"x{i}": test_add['registers_before'][f"x{i}"] for i in range(32)}
rv64_cpu.execute_instruction(test_add['instruction'])

# Verify
rv64_result = rv64_cpu.regs[5] & 0xFFFFFFFF
rv32_result = test_add['registers_after']['x5']

if rv64_result == rv32_result:
    print("✓ ADD implementation correct")
else:
    print(f"✗ ADD mismatch: {hex(rv64_result)} != {hex(rv32_result)}")
```

### Phase 3: Verify Page Table Walks

```python
# Find memory accesses in trace
mem_ops = [i for i in boot_trace if any(op in i['decoded'] for op in ['lw', 'sw'])]

for op in mem_ops[:10]:  # Test first 10
    vaddr = op['registers_before']['x10']  # Assuming base in x10

    # Execute on RV64
    paddr_rv64, fault = rv64_cpu.translate_address_sv39(vaddr, 'read')

    # Get RV32 physical address (if captured)
    if op.get('page_table_walk'):
        paddr_rv32 = op['page_table_walk']['paddr']

        if paddr_rv64 == paddr_rv32:
            print(f"✓ Page walk correct: {hex(vaddr)} → {hex(paddr_rv64)}")
        else:
            print(f"✗ Page walk mismatch: {hex(vaddr)}")
            print(f"  RV32: {hex(paddr_rv32)}")
            print(f"  RV64: {hex(paddr_rv64)}")
```

### Phase 4: Boot xv6 on RV64

Once all critical patterns pass:

```bash
# Boot xv6 on RV64 emulator
python3 tools/boot_xv6_rv64.py \
    --kernel boot_images/xv6.img \
    --max-instructions 100000

# Verify it matches RV32 traces
python3 tools/verify_rv64_traces.py \
    --trace tools/rv32_golden_trace.json \
    --rv64-output rv64_boot_output.json
```

## Advantages of This Approach

### 1. Ground Truth, Not Guessing

```
Without patterns: "I think ADD should sign-extend..."
With patterns:    "RV32 ADD produced 0x80001020, so RV64 must too"
```

### 2. Automated Verification

```python
def verify_rv64_instruction(rv32_trace, rv64_cpu):
    """Automatically verify RV64 matches RV32."""
    rv64_result = rv64_cpu.regs[5] & 0xFFFFFFFF
    rv32_result = rv32_trace['registers_after']['x5']

    return rv64_result == rv32_result
```

### 3. Early Bug Detection

```bash
# Find first mismatch in 10K instructions
python3 tools/verify_rv64_traces.py \
    --trace tools/rv32_golden_trace.json

# Output:
# ✗ Mismatch at instruction 2,341
#   PC: 0x80001234
#   Instruction: 00000097  (auipc ra, 0)
#   RV32 result: ra=0x80001238
#   RV64 result: ra=0x00001238  ← BUG: Missing sign-extension!
```

### 4. Confidence Through Reproducibility

```bash
# Every developer can verify against the same ground truth
git checkout main
python3 tools/capture_rv32_traces.py --boot-sequence -o golden.json
git checkout my-rv64-branch
python3 tools/verify_rv64_traces.py --trace golden.json
```

## Next Steps

1. **Capture initial traces:**
   ```bash
   python3 tools/capture_rv32_traces.py --boot-sequence
   ```

2. **Implement RV64 ADD:**
   Use captured traces to verify low-32-bit behavior.

3. **Implement RV64 Sv39 MMU:**
   Use page table walk patterns from traces.

4. **Iterate:**
   Capture more traces → implement more instructions → verify → repeat.

5. **Full boot:**
   Once all patterns pass, attempt full xv6 boot on RV64.

## Files Reference

| File | Purpose |
|------|---------|
| `tools/capture_rv32_traces.py` | Capture execution traces from RV32 |
| `tools/rv32_golden_trace.json` | Ground truth traces (generated) |
| `PATTERN_LEARNING_COMPLETE_GUIDE.md` | Full pattern learning methodology |
| `CAPTURING_XV6_PATTERNS.md` | How to capture xv6 patterns |
| `tools/rv64_verify_traces.py` | Verify RV64 against RV32 traces (TODO) |

---

**Bottom line:** The pattern learning approach transforms RV64 development from "guessing at 64-bit behavior" to "verifying against proven 32-bit behavior." The captured traces are ground truth — they're what RV32 ACTUALLY does, so RV64 must produce identical low-32-bit results for correctness.