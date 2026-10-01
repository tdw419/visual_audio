# Pixel Emulator RV64 Implementation Roadmap

**Phase 2 Complete**: Skeleton scaffolding with explicit interfaces and stub bodies.

## Pre-Test Checklist

Before running integration tests:

- [x] All side effects defined (memory read/write, CSR access, exceptions)
- [x] Runtime data structures mapped (PixelContainer backing, PixelTracer integration)
- [x] Memory boundary conditions explicit (check_bounds, check_alignment)
- [x] Skeleton compiles without missing dependencies
- [x] Address to pixel mapping placeholder exists (Hilbert to be implemented)

## Phase 3: Implementation Order

### Round 3a: Memory Layer (Priority 1)
**Goal**: PixelContainer-backed flat memory with Hilbert mapping

1. Implement `addr_to_pixel()` using `geos_pixel::hilbert::hilbert_d2xy`
2. Wire up `read_u8/write_u8` to PixelContainer `read_region/write_region`
3. Implement `read_u16/u32/u64` and `write_u16/u32/u64` using byte primitives
4. Add unit tests for address mapping (Hilbert coherence)
5. Add unit tests for multi-byte reads/writes (endianness)
6. Verify with simple test: write bytes, read back, compare

**Verification gate**:
```bash
cargo test rv64_memory::tests
```

### Round 3b: Instruction Decoder (Priority 2)
**Goal**: Full RV64I base ISA decoding

1. Complete `decode()` opcode dispatch
2. Implement I-type decoding (ADDI, SLTI, ANDI, ORI, XORI, SLLI, SRLI, SRAI)
3. Implement S-type decoding (SB, SH, SW, SD)
4. Implement B-type decoding (BEQ, BNE, BLT, BGE, BLTU, BGEU)
5. Implement U-type decoding (LUI, AUIPC)
6. Implement J-type decoding (JAL, JALR)
7. Implement R-type decoding (ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND)
8. Implement RV64W extensions (ADDIW, SLLIW, SRLIW, SRAIW, ADDW, SUBW, SLLW, SRLW, SRAW)
9. Implement system instructions (ECALL, EBREAK, CSR*)
10. Add unit tests per instruction category

**Verification gate**:
```bash
cargo test rv64_decode::tests
```

### Round 3c: ALU Operations (Priority 3)
**Goal**: Execute arithmetic/logic instructions

1. Implement `execute_addi` (immediate add)
2. Implement `execute_lui`/`execute_auipc` (upper immediate)
3. Implement ALU ops (ADD, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU)
4. Implement RV64W ops (ADDIW, ADDW, SUBW, SLLW, SRLW, SRAW)
5. Add unit tests for each operation (edge cases: overflow, shift counts)

**Verification gate**:
```bash
cargo test alu_ops
```

### Round 3d: Memory Operations (Priority 4)
**Goal**: Load/store execution

1. Implement `execute_lb/lh/lw/ld` (sign-extending loads)
2. Implement `execute_lbu/lhu/lwu` (zero-extending loads)
3. Implement `execute_sb/sh/sw/sd` (stores)
4. Wire memory reads/writes to `RV64Memory`
5. Add unit tests for loads/stores with misaligned access checks

**Verification gate**:
```bash
cargo test memory_ops
```

### Round 3e: Branch/Control Flow (Priority 5)
**Goal**: Conditional and unconditional jumps

1. Implement `execute_beq/bne/blt/bge/bltu/bgeu` (conditional branches)
2. Implement `execute_jal` (unconditional jump)
3. Implement `execute_jalr` (register indirect jump)
4. Update PC correctly for taken vs not-taken branches
5. Add unit tests for branch conditions and PC updates

**Verification gate**:
```bash
cargo test branch_ops
```

### Round 3f: System Instructions (Priority 6)
**Goal**: ECALL/EBREAK and CSR access

1. Implement `execute_ecall` (environment call - halt)
2. Implement `execute_ebreak` (breakpoint - halt)
3. Implement `execute_csrrw/csrrs/csrrc` (CSR read/write)
4. Implement `execute_csrrwi/csrrsi/csrcci` (CSR immediate variants)
5. Wire CSR operations to `RV64CPU::read_csr/write_csr`
6. Add unit tests for CSR access and exception handling

**Verification gate**:
```bash
cargo test system_ops
```

### Round 3g: Execution Loop (Priority 7)
**Goal**: Complete fetch-decode-execute cycle

1. Implement `RV64VM::step()` (single instruction)
2. Implement `RV64VM::run()` (until halt)
3. Update statistics on each instruction
4. Wire trace adapter to record operations
5. Add integration test: run small binary (e.g., simple ADD loop)

**Verification gate**:
```bash
cargo test execution_loop
cargo run --example simple_program
```

### Round 3h: Trace Integration (Priority 8)
**Goal**: Pixel-aware operation recording

1. Complete `addr_to_pixel()` Hilbert mapping in `TraceAdapter`
2. Wire memory read/write traces in `RV64VM::step()`
3. Wire instruction execution traces
4. Verify trace output JSON format
5. Add test: load binary, execute, verify trace JSON

**Verification gate**:
```bash
cargo test trace_integration
# Verify output in ./pixel_traces/
```

### Round 3i: End-to-End Verification (Priority 9)
**Goal**: Boot simple RV64 program

1. Compile minimal RV64 ELF binary (C program: add two numbers)
2. Load binary into RV64VM via `load_binary()`
3. Run to completion via `run()`
4. Check final register state (x0=0, result in x1)
5. Compare trace output with expected memory access pattern

**Verification gate**:
```bash
cargo run --example minimal_boot
# Verify exit code 0 and register state
```

## Acceptance Criteria

- [ ] Round 3a-3i all complete
- [ ] All unit tests pass
- [ ] Integration test boots simple binary
- [ ] Trace JSON generated and valid
- [ ] Memory mapping Hilbert coherent (visual inspection)
- [ ] No dead code warnings after Phase 3
- [ ] Cargo check passes with no errors

## Rollback Criteria

Stop implementation and return to Phase 2 if:
- 3+ consecutive test failures requiring signature changes
- PixelContainer API incompatible with RV64Memory abstraction
- Hilbert mapping incoherent (breaks visual consistency)
- Performance impossible (< 1K instructions/sec baseline)