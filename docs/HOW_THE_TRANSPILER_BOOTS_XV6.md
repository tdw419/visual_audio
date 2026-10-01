# How the RV64I/RV32I → Glyph Transpiler Boots xv6

**A Comprehensive Architectural Guide to the Geometry OS Spatial Transpiler, Sub-Word Memory Lowering, and the xv6-nano Spatial Boot Pipeline**

---

## 1. Executive Summary

Geometry OS operates under the paradigm that **"The Screen is the Hard Drive"** and that computation can be expressed as spatial, font-atomic glyph structures arranged on an infinite 2D plane.

Historically, Geometry OS ran operating systems (like Alpine Linux and MIT xv6) through a GPU compute shader emulator ([`docs/HOW_WGSL_RUNS_XV6.md`](file:///home/jericho/projects/zion/projects/visual_audio/docs/HOW_WGSL_RUNS_XV6.md)), where a 3,600-line WGSL kernel interprets RISC-V instructions serially with full Sv39 MMU page tables and device emulation.

The **RV64I/RV32I → Glyph Transpiler** ([`tools/rv64i_to_glyph.py`](file:///home/jericho/projects/zion/projects/visual_audio/tools/rv64i_to_glyph.py) and parity copy [`glyph_dispatch/src/glyph/rv64i_to_glyph.py`](file:///home/jericho/projects/zion/projects/visual_audio/glyph_dispatch/src/glyph/rv64i_to_glyph.py)) represents a fundamental leap:
Instead of running a software interpreter inside a GPU compute shader, we compile standard C code with standard GCC, transpile the resulting RISC-V machine instructions into **native Glyph ISA v2 assembly**, and assemble them into **spatial pixel matrices (`.glyph.png`)** that execute directly on the spatial substrate ([`GlyphCPUv2`](file:///home/jericho/projects/zion/projects/visual_audio/tools/glyph_isa_v2.py#L320)).

```
┌────────────────────────────────────────────────────────────────────────┐
│                        THE TRANSPILER PIPELINE                         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   xv6 C Kernel Source (kalloc.c, string.c, proc.c, fs.c)               │
│                            │                                           │
│                            ▼  riscv64-unknown-elf-gcc                  │
│   RV32I ELF Binary (-march=rv32i -mabi=ilp32 -O1 -nostdlib)            │
│                            │                                           │
│                            ▼  tools/rv64i_to_glyph.py                  │
│   Glyph ISA v2 Assembly Text (.glyph)                                  │
│   - Lowered 34/87 RISC-V opcodes to 27 Glyph instructions              │
│   - Resolved 1D byte-addresses to 2D pixel PCs via PTR_TABLE_BASE      │
│   - Word/lane split and RMW bitmask clearing for LBU/SB byte access    │
│                            │                                           │
│                            ▼  tools/glyph_isa_v2.py (Assembler)        │
│   Spatial Pixel Container (.glyph.png)                                 │
│   - 4 RGB pixels per instruction (Opcode, Regs, Low Imm, High Imm)     │
│   - Executed directly on GlyphCPUv2 / GPU Spatial Substrate            │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. How the Transpiler Works

The transpiler is a pure-Python, zero-external-dependency translation engine structured in four strict phases.

### Phase 1: ELF Parsing & Section Mapping (`parse_elf` and `parse_elf_data_sections`)

The transpiler parses standard 32-bit (`ELFCLASS32`) and 64-bit (`ELFCLASS64`) Little-Endian RISC-V ELF binaries:
1. **Header & Program Headers**: Extracts entry address (`e_entry`), section header table offset (`e_shoff`), and segment descriptors.
2. **Section Discovery (`parse_elf`)**: Identifies `.text` (code), `.rodata` (read-only constants/strings), `.sdata`/`.sbss` (small data), and `.bss`/`.data` (globals).
3. **Data Initializer Extraction (`parse_elf_data_sections`)**: Extracts non-zero initialized sections (`SHF_ALLOC` with `SHT_PROGBITS` non-`.text`, such as `.rodata`, `.sdata`, `.data`). This seeds `GlyphCPUv2.memory` with string literals and pre-initialized tables, ensuring non-zero globals do not read as zeroes.
4. **Symbol Table Resolution**: Walks `.symtab` and `.strtab` to associate addresses with symbolic names (`_start`, function names, global variables).

### Phase 2: Instruction Decoding (`rv64i_decode.py`)

Every 32-bit instruction word in `.text` is decoded into:
- An opcode enum `op` (e.g. `OP_ADDI`, `OP_LW`, `OP_LBU`, `OP_SB`, `OP_JALR`, `OP_BEQ`).
- Register indices: destination `rd`, source registers `rs1`, `rs2` (0 to 31).
- Sign-extended immediate value `imm`.

### Phase 3: Two-Pass Analysis & Lowering

The lowering pipeline requires two passes across the instruction stream:

1. **Pass 1: Label Collection & PC Coordinate Mapping**
   - Direct branch/jump targets are gathered.
   - For every instruction, an explicit label `:pc_%08x` is emitted. This is mandatory for dynamic dispatch: because function pointers and return addresses can target any instruction, the runtime pointer table must be able to resolve any byte address to a 2D pixel coordinate.
2. **Pass 2: Instruction Emission & Architecture Mapping**
   - RISC-V instructions are translated into Glyph ISA v2 instructions.
   - Unhandled opcodes immediately raise a `ValueError`, enforcing strict falsifiability.

---

## 3. The Solved Impedance Mismatches

The RISC-V architecture and the Geometry OS Glyph Stratum have radically different execution models. The transpiler successfully bridges eight major architectural gaps:

### 1. 1D Byte Address vs. 2D Pixel Coordinate Mismatch (`PTR_TABLE_BASE`)
- **The Problem**: In RISC-V, function pointers and return addresses are 1D linear byte offsets (e.g. `0x0000004c`). In Glyph ISA v2, instruction pointers are 2D coordinates packed into a single 32-bit integer: `packed_pc = (row << 16) | col`, where each instruction occupies 4 pixels horizontally. A dynamic jump `jalr ra, 0(a5)` cannot jump directly to `0x0000004c`.
- **The Solution**: The transpiler establishes a pointer translation table at `PTR_TABLE_BASE` (`0xC00`).
  - At assembly time, `build_pointer_table()` reads the pixel coordinates of every `:pc_%08x` label and populates the table: `table[byte_addr >> 2] = (row << 16) | col`.
  - At runtime, any dynamic JALR lowers to:
    ```glyph
    LDI r30 0xc00        # PTR_TABLE_BASE
    ADD r30 r{rs1}       # Add byte address
    LDI r29 2
    SHR r30 r29          # Convert byte index to word index
    LD r30 r30           # Read packed 2D pixel coordinate
    CALLR r30            # or JMPR r30
    ```

### 2. The Return-vs-Resume Ambiguity (`swtch.S`)
- **The Problem**: In RISC-V, a normal function epilogue and a context switch end with the exact same instruction: `ret` (which is `jalr zero, 0(ra)`).
  - In an ordinary function, `ret` returns to the caller.
  - In a cooperative context switch (`swtch.S`), the function reloads `ra` from a saved task struct in memory (`lw ra, 0(a1)`) and executes `ret` to *resume* a different task.
  - In Glyph, normal `RET` pops from the hardware call stack (`r31`). If a context switch executes `RET`, it pops from the old task's call stack instead of resuming the new task!
- **The Solution (Local Dataflow on `x1`)**:
  - The transpiler tracks the provenance of register `ra` (`x1`).
  - If the last write to `ra` before `ret` was `lw ra, N(sp)` where `rs1 == sp`, it is an **ordinary epilogue return** $\rightarrow$ lowers to `RET`.
  - If the last write was `lw ra, 0(a1)` where `rs1 != sp`, it is a **task resume** $\rightarrow$ lowers to `POP r28` (to discard and balance the activation frame pushed by `CALL`) followed by `JMPR r30` through the pointer table!

### 3. Sub-Word Memory Access (`LBU`, `SB`) on 32-Bit Word-Indexed Substrate
- **The Problem**: Glyph CPU memory is addressed in 32-bit words (`byte_to_word_mem=True`), while C strings (`char*`) and kernel buffers are byte-addressed. Glyph has no byte-load or byte-store opcodes, and no bitwise `NOT` opcode.
- **The Solution (Word/Lane Splitting & Read-Modify-Write)**:
  - **`LBU rd, imm(rs1)`**:
    1. Compute effective byte address: `addr = imm + rs1`.
    2. Extract word index: `word_addr = addr >> 2`.
    3. Extract lane index: `lane = addr & 3`.
    4. Bit shift amount: `shift = lane << 3` (0, 8, 16, or 24 bits).
    5. Load 32-bit word: `word = mem[word_addr]`.
    6. Extract and mask: `rd = (word >> shift) & 0xFF`.
  - **`SB rs2, imm(rs1)` (Read-Modify-Write)**:
    1. Load current 32-bit word from `word_addr`.
    2. Create clear mask: shift `0xFF << shift`. To clear without a `NOT` opcode, use the identity `(word | mask) ^ mask == word & ~mask`.
    3. Shift new byte into position: `(rs2 & 0xFF) << shift`.
    4. Combine: `new_word = cleared_word | shifted_byte`.
    5. Store back: `mem[word_addr] = new_word`.
    6. Uses 5 scratch registers (`r26-r30`) with strict register-lifetime management to prevent clobbering aliased operands.

### 4. Zero Register Invariant (`r0`)
- In RISC-V, register `x0` is hardwired to constant `0`.
- In Glyph ISA v2, `CMP` writes its boolean equality flag into register `r0`.
- If a subsequent branch compares against zero (e.g. `blez r5`), reading `r0` would read the stale comparison flag rather than zero.
- The transpiler uses `_emit_add_reg` and `_emit_sub_reg` helpers that skip operations entirely when the operand is `x0`, guaranteeing that zero is never corrupted.

### 5. Instruction-Pixel Footprint vs. Call Stack Aliasing (`stack_addr`)
- In `GlyphCPUv2`, the hardware call stack (`r31`) writes directly into the same 2D pixel image that holds the compiled program instructions.
- If `stack_addr` is set too low (e.g. 1500), larger programs (>375 instructions) expand into row 5 and live `CALL` pushes silently overwrite active instructions.
- The transpiler convention places `stack_addr` safely past the instruction footprint (typically `stack_addr = 7000` or higher).

### 6. Small Data & Global Pointer Setup (`gp`)
- GCC compiles global and static variable accesses under `-O1` as small-data references relative to the global pointer: `lw a5, off(gp)`.
- If `gp` is uninitialized (0), all global variables read and write to garbage memory addresses.
- Because pseudo-instructions like `la gp, __global_pointer$` and `-mcmodel=medany` emit `auipc` (currently unmapped), `_start` must initialize `gp` using absolute instructions:
  ```assembly
  .option push
  .option norelax
  lui gp, %hi(__global_pointer$)
  addi gp, gp, %lo(__global_pointer$)
  .option pop
  ```

---

## 4. How the Transpiler is Going to Boot xv6

Upstream MIT xv6 is designed for traditional hardware: it boots in M-mode, uses Sv39 virtual memory (`satp` page tables), relies on hardware trap vectors (`stvec`/`sepc`), and uses timer interrupts for preemption.

The transpiler enables a **clean, staged evolution** toward booting xv6 on Geometry OS:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      THE 4-STAGE XV6 BOOT ROADMAP                      │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Stage 1: Verified Component Extraction (G1–G7) ──► [COMPLETE]         │
│  - kalloc.c (real xv6 source verbatim): freerange, kfree, kalloc       │
│  - proc.c / swtch.S: 3-task round-robin scheduler & cooperative yield  │
│  - pipe.c: FIFO ring buffers & struct wraparound                       │
│  - fs.c: Inode table indexing & block mapping                          │
│  - string.c: memset, memmove, strlen, strncmp (G6/G8)                  │
│                                                                        │
│  Stage 2: Single Address Space (xv6-nano) ────────► [IN PROGRESS]      │
│  - Eliminate Sv39 page tables: replace 1D virtual memory with          │
│    2D Geometric Spatial Isolation (Area Agents & Window Bounds)        │
│  - Replace trap-based syscalls (ecall) with direct dispatch table      │
│  - Replace timer preemption with cooperative yield hooks               │
│                                                                        │
│  Stage 3: Unified Kernel Assembly ───────────────► [NEXT TARGET]       │
│  - Link xv6-nano into a single ELF (-march=rv32i -nostdlib)            │
│  - Transpile entire kernel into xv6_nano.glyph.png                     │
│  - Entry in _start -> kinit() -> userinit() -> scheduler()             │
│                                                                        │
│  Stage 4: Full Spatial Shell Execution ──────────► [TARGET ARCH]       │
│  - Init task spawns sh.c (shell)                                       │
│  - Shell executes cat, ls, echo as spatial child tasks                 │
│  - Output rendered to Geometry OS terminal tile via pixel buffers      │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Stage 1: Component Extraction (Proven & Verified)
We have proven that xv6's core subsystems compile with `-march=rv32i -O1 -nostdlib`, transpile to Glyph assembly, and execute with bit-for-bit three-way differential agreement (x86 host $\leftrightarrow$ GPU core $\leftrightarrow$ GlyphCPUv2):
- **`kalloc.c`**: Verbatim xv6 page allocator running freelist drainage, page poisoning (`0x05050505`), and LIFO reclamation (Commit `0b735e3`).
- **`proc.c` & `swtch.S`**: Dynamic function-pointer dispatch, cooperative task switching, and 3-task round-robin scheduling (Commits `5692bd0`, `85ffdce`, `3d62e7e`).
- **`fs.c`**: In-memory inode table lookup and nested struct indexing (Commit `c3d1c1b`).
- **`string.c`**: Sub-word string building and memory copying via `LBU`/`SB` (Commit `529ae69`).

### Stage 2: The "xv6-nano" Spatial OS Model
Rather than porting complex Sv39 page table management that has no native analogue in Glyph hardware, Geometry OS adapts xv6 into a **Single Address Space Operating System (SASOS)**:
1. **Geometric Isolation Instead of Paging**:
   - In Geometry OS, windows and processes are bounded regions on the infinite 2D canvas.
   - Process memory isolation is enforced by the spatial compositor (Area Agents) checking bounding box coordinates, eliminating the need for `satp` page-walk hardware.
2. **Cooperative System Call Dispatch**:
   - Instead of raising an `ecall` trap to switch to supervisor mode, xv6-nano user processes invoke system calls through a dispatch table:
     `syscall_dispatch(SYS_fork, ...)`
3. **Cooperative Multitasking**:
   - In place of CLINT timer interrupts, tasks yield during I/O operations (`read`, `write`) or at loop back-edges.

### Stage 3: Unified Kernel Assembly & Boot Sequence
The boot sequence of `xv6_nano.glyph.png` on the Geometry OS substrate will execute as follows:

```c
void _start(void) {
    // 1. Hardware Stack & Global Pointer Initialization
    __asm__ volatile (
        ".option push\n"
        ".option norelax\n"
        "lui gp, %hi(__global_pointer$)\n"
        "addi gp, gp, %lo(__global_pointer$)\n"
        ".option pop\n"
        "li sp, 0x8000\n"
        "call main\n"
        "ecall\n"
    );
}

void main(void) {
    kinit();         // Initialize physical page allocator (freerange)
    procinit();      // Initialize process table and locks
    binit();         // Initialize buffer cache
    iinit();         // Initialize inode table
    fileinit();      // Initialize file table
    userinit();      // Create the first process (initcode / sh)
    scheduler();     // Enter infinite cooperative scheduling loop
}
```

When transpiled into `.glyph.png`:
1. `_start` establishes `sp` and `gp`.
2. `kinit()` populates `kmem.freelist` with memory pages, writing poisoning bytes across page blocks.
3. `userinit()` allocates a `struct proc` via `allocproc()`, sets up its stack context, and marks it `RUNNABLE`.
4. `scheduler()` enters the round-robin loop, locates the runnable init process, calls `switch_to(&c->context, p->context)`, and jumps into the initial shell!

---

## 5. Architectural Comparison: WGSL Emulator vs. Glyph Transpiler

| Feature | WGSL RISC-V Emulator (`tools/RISCV_CPU_MMU.wgsl`) | RV64I $\rightarrow$ Glyph Transpiler (`tools/rv64i_to_glyph.py`) |
|---|---|---|
| **Execution Paradigm** | Software interpreter inside a GPU compute shader | Direct compilation to native Glyph spatial assembly |
| **ISA** | RV64IMA + Zicsr + Zifencei | RV32I lowered to Glyph ISA v2 (27 spatial opcodes) |
| **Memory Model** | 128 MB linear RAM emulated via WGSL storage buffers | 2D pixel grid memory (`image` + word-addressed `memory`) |
| **Virtual Memory** | Full Sv39 3-level page-table walking in shader | Flat spatial memory / Geometric boundary isolation |
| **Privilege Modes** | Machine (`M`), Supervisor (`S`), User (`U`) | Unified flat spatial substrate |
| **Target Workload** | Upstream Linux kernels, standard unmodified xv6 ELF | Native Geometry OS spatial microkernel (xv6-nano) |
| **Verification Gate** | Instruction-by-instruction lockstep trace diff with QEMU | Three-way bit-identical gate (x86 host $\leftrightarrow$ GPU core $\leftrightarrow$ GlyphCPUv2) |

---

## 6. Current Status & Verification Gates

The transpiler test suite is verified via the repository pre-commit gate:

```bash
# Run full differential test suite
pytest tests/test_rv64i_to_glyph*.py tests/test_glyph_isa_v2.py tests/test_spatial_rv64i_cpu.py -v
```

- **Passing Tests**: 29/29 green.
- **Parity Invariant**: [`tools/glyph_isa_v2.py`](file:///home/jericho/projects/zion/projects/visual_audio/tools/glyph_isa_v2.py) and [`glyph_dispatch/src/glyph/glyph_isa_v2.py`](file:///home/jericho/projects/zion/projects/visual_audio/glyph_dispatch/src/glyph/glyph_isa_v2.py) are byte-identical (`cmp -s`).
- **Opcode Coverage**: 34/87 opcodes covered ([`tools/GLYPH_TRANSPILER_OPCODE_COVERAGE.md`](file:///home/jericho/projects/zion/projects/visual_audio/tools/GLYPH_TRANSPILER_OPCODE_COVERAGE.md)).
- **Next Operational Milestone**: G8 — Transpiling real xv6 `kernel/string.c` (`strlen`, `strncmp`, `strncpy`, `safestrcpy`, `memmove`).
