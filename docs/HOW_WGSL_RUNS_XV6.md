# How WGSL Runs xv6

How a WebGPU compute shader executes the xv6-riscv kernel — the architecture of
the GPU RISC-V emulator, the buffers it uses, its main loop, and how it is
validated against QEMU.

**TL;DR:** `tools/RISCV_CPU_MMU.wgsl` is a RISC-V **interpreter** written in WGSL.
The GPU is not running RISC-V machine code and is not exploiting parallelism — it
runs a fetch/decode/execute loop over guest memory and a CPU-state struct, one
logical hart, serially. Same idea as QEMU's interpreter core, expressed as a
compute shader. The whole point of the project is that this interpreter agrees
with QEMU **register-for-register**, so a real OS boots on it.

---

## 1. The moving parts

| File | Role |
|------|------|
| `tools/RISCV_CPU_MMU.wgsl` | The emulator. ~3600 lines of WGSL: decoder, ALU, MMU (Sv39), traps, and MMIO devices (UART/CLINT/PLIC/virtio). |
| `tools/boot_xv6_gpu.py` | Host driver for a normal boot: loads the kernel, creates GPU buffers, dispatches the shader in large instruction batches, prints UART output, feeds console input. |
| `tools/boot_xv6_gpu_trace.py` | Host driver for **lockstep tracing**: dispatches the shader **one instruction at a time**, reads the CPU state back after each step, and writes a JSONL trace for diffing. |
| `tools/riscv_gpu_cpu.py` | `CPU_DTYPE` — the host-side NumPy mirror of the WGSL `RiscvCPU` struct. The two layouts must stay byte-identical. |
| `tools/qemu_cpu_trace.py` | Boots the same kernel under QEMU with instruction tracing and emits the **ground-truth** JSONL. |
| `tools/diff_qemu_gpu_traces.py` | Aligns the two traces at a start PC and compares them register-for-register; reports the first divergence. |

Downstream consumer: `~/.hermes/scripts/wgsl_generator.py` (the "WGSL Generator"
daemon) runs QEMU-trace → GPU-trace → diff in a loop and asks an LLM for a
targeted shader patch when a divergence appears.

---

## 2. Memory model: everything is a storage buffer

The shader binds five buffers (`@group(0)`):

| binding | name | type | contents |
|--------:|------|------|----------|
| 0 | `memory` | `array<InstructionPixel>` `read_write` | **Guest physical RAM.** 128 MB, physical base `0x8000_0000`. Each element is 16 bytes (a 4×u32 "pixel"), so RAM is addressed as `array<u32>` in disguise. |
| 1 | `cpus` | `array<RiscvCPU>` `read_write` | **CPU state.** One element = one hart. This path uses exactly one. |
| 2 | `output` | `array<u32>` `read_write` | **UART output ring.** First 16384 bytes reserved for console bytes the guest writes to the 16550 THR. |
| 3 | `max_instructions` | `u32` `uniform` | Per-dispatch instruction budget. |
| 4 | `uart_input` | `array<u32>` `read_write` | **Console input.** Host writes keystrokes / autonomous commands here; the shader drains them through the UART RHR. |

The host loads the kernel by walking the ELF's loadable segments and copying each
one to `p_vaddr - 0x8000_0000` in `memory`. `fs.img` (the xv6 disk image) is
copied to `0x8100_0000 - 0x8000_0000` when present.

### 64-bit values in a 32-bit language

WGSL has no `u64`. Every 64-bit quantity — `pc`, each of `x0..x31`, every CSR —
is a `vec2<u32>` of `(low, high)`. Arithmetic goes through helpers like `add64`,
`u64_add`, `u64_lt`, `sext32_to_64`. This is the single biggest source of subtle
bugs (sign-extension, carry, shift-by-≥32) and therefore the thing the QEMU diff
is most valuable at catching.

### The `RiscvCPU` struct (abridged)

```wgsl
struct RiscvCPU {
    pc: vec2<u32>,
    regs: array<vec2<u32>, 32>,   // x0 hardwired to 0
    running: u32,                 // 0 = halted
    instr_count: u32,             // diagnostic only
    priv_mode: u32,               // 3=M, 1=S, 0=U
    satp, mstatus, mtvec, mepc, mcause, mtval, mscratch, mie, mip: vec2<u32>,
    stvec, sepc, scause, stval, sscratch: vec2<u32>,
    medeleg, mideleg, menvcfg: vec2<u32>,
    // virtio-blk queue registers, PLIC pending/enable/claimed,
    // CLINT mtime / mtimecmp, current_instr_len (2 for RVC, else 4), ...
}
```

`tools/riscv_gpu_cpu.py:CPU_DTYPE` declares the identical field order and sizes so
the host can `write_buffer(cpu.tobytes())` and `np.frombuffer(readback, CPU_DTYPE)`.

---

## 3. The main loop

```wgsl
@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var cpu = cpus[global_id.x];

    for (var step = 0u; step < max_instructions; step = step + 1u) {
        if (cpu.running == 0u) { break; }

        // (a) advance time / devices
        //     - decrement uart_irq_delay, raise PLIC IRQ 10 on expiry
        //     - mtime += 1; edge-trigger MTIP/STIP when mtime >= mtimecmp
        //     - level-trigger UART RX IRQ while uart_input has unread bytes

        // (b) interrupt delivery
        //     compute mip & mie, split by mideleg into M- vs S-pending,
        //     honour mstatus.MIE / mstatus.SIE, and if something is
        //     pending+enabled: take_trap(cause | 0x8000_0000); continue;

        // (c) fetch  — fetch_instruction() runs the Sv39 page-table walk
        //     when satp enables paging; on failure:
        //     take_trap(INSTR_PAGE_FAULT); continue;

        // (d) decode — if fetch.len == 2, decompress_rvc() to a 32-bit form;
        //     opcode = instr & 0x7f

        // (e) execute — nested if/else on opcode / funct3 / funct7 dispatching
        //     to execute_addi, execute_add, execute_lui, execute_auipc,
        //     loads/stores, branches/jumps, CSR ops, AMOs, ecall/ebreak/sret,
        //     the *W RV64 word ops, and the M extension. Unknown → handle_illegal.

        cpus[global_id.x] = cpu;   // write back
    }
}
```

Key points:

- **`workgroup_size(1)`, one dispatched workgroup.** A single GPU invocation does
  all the work. The emulator is single-hart and serial; the GPU is just an
  unusual place to run the interpreter. (The `PARALLEL_*` / "spatial" SIMT shader
  experiments are a separate line of work and do not run xv6.)
- **The budget is the `for` bound**, re-granted every dispatch via the
  `max_instructions` uniform. (A prior bug compared lifetime `instr_count`
  against it and silently turned it into a one-shot ceiling — see the comment in
  `main`.)
- Each executed instruction updates `pc` and possibly `regs` / CSRs / `memory`
  in place; there is no separate register file or writeback stage.

---

## 4. Devices, in the shader

MMIO is handled by range-checking the physical address inside the load/store path:

| Device | Base | What the shader emulates |
|--------|------|--------------------------|
| **UART 16550** | `0x1000_0000` | THR write → append byte to `output`. LSR read → THRE always set, DR set while `uart_input` has bytes. RHR read → next `uart_input` byte. Raises PLIC IRQ 10. |
| **CLINT** | `0x0200_0000` | `mtime` at `0x0200_bff8` (incremented once per instruction), `mtimecmp` at `0x0200_4000`. Writing `mtimecmp` re-arms the edge-triggered timer. |
| **PLIC** | (range-checked) | `plic_pending` / `plic_enable` / `plic_claimed` bits; claim/complete handshake feeds the SEIP/MEIP lines. |
| **virtio-blk** | (range-checked) | Legacy virtqueue registers in the struct (`vq_desc_*`, `vq_avail_*`, `vq_used_*`, `vq_idx`, …); the shader walks descriptor rings and copies blocks between `memory` and the in-RAM `fs.img` region. |

There is no host-side device model in the boot path — the shader is a
self-contained SoC.

---

## 5. The host loop

### Trace mode (`boot_xv6_gpu_trace.py`)

1. Load kernel + `fs.img` into a NumPy `memory` array.
2. `make_cpu_state(entry, priv_mode=3)`; seed inbound registers from
   `/tmp/qemu_kernel_init_state.json` so the GPU starts from the **same** state
   QEMU's `-bios none` reset vector hands the kernel (`a0`=hartid, `a1`=DTB
   pointer, `mstatus` UXL/SXL = 64-bit, stray `t0`/`a2`). Without this the diff
   reports cosmetic mismatches until the kernel overwrites those regs.
3. Create the five buffers, `max_instructions = 1`, build the pipeline
   (`entry_point = "main"`).
4. Loop: encode a compute pass → `dispatch_workgroups(1)` → `queue.submit` →
   `read_buffer(cpu_buffer)` → decode `pc` + `x0..x31` + `mstatus/mepc/mcause`,
   recombining each `(low, high)` pair into an unsigned 64-bit int → write one
   JSONL line → repeat until `running == 0` or the instruction cap.

### Boot mode (`boot_xv6_gpu.py`)

Same setup, but `max_instructions` is large (millions) so each dispatch runs a
long batch. Between dispatches the host reads the `output` buffer for new console
bytes and writes `uart_input` for keystrokes / autonomous commands. This is how
xv6 reaches `init: starting sh` and an interactive `$`.

---

## 6. Validation: the QEMU oracle

```
qemu_cpu_trace.py  kernel  → qemu_trace.jsonl   (ground truth)
boot_xv6_gpu_trace.py kernel → gpu_trace.jsonl  (emulator under test)
diff_qemu_gpu_traces.py --qemu-trace … --gpu-trace … --start-pc 0x80000004
        → "Compared N instructions - all matched!"
        or "First mismatch at instruction K (PC=…): x15 QEMU=… GPU=…"
```

`diff_qemu_gpu_traces.py` aligns both traces at `--start-pc`, then walks them in
lockstep comparing `pc` and every integer register (ignoring `mhartid` and
poisoning the destination of `rdtime`/`rdcycle`/`rdinstret` reads, which
legitimately differ). The first register that disagrees is the bug, localized to
one instruction.

As of 2026-08-28 the emulator matches QEMU register-for-register across the full
captured xv6 boot trace (~9500 instructions), and separately runs clean through
100k+ instructions in the WGSL Generator's escalation runs. See
`RV64_LOCKSTEP_HARNESS_RECEIPT.md`.

---

## 7. Why this is useful

Booting xv6 on the GPU is a **correctness oracle** for the WGSL, not a code
generator:

- **Free ground truth.** QEMU says exactly what every register should be; the
  diff says exactly where the shader is wrong.
- **Realistic coverage.** Boot exercises ADDI/AUIPC, loads/stores, CSR ops,
  traps, Sv39 walks, AMOs (spinlocks), and the M extension in real sequences and
  corner cases nobody would hand-write tests for.
- **Regression gate.** Re-run after any shader edit; if divergence moves earlier,
  you broke something. (Injecting a one-token `execute_addi` bug diverges at
  instruction 4.)
- **Structured LLM input.** "At PC X, QEMU set x15=A, GPU set x15=B, instruction
  was `addi`" is exactly the context needed to propose a targeted patch.

### Limits

- Only covers what xv6 actually executes; unused opcodes/edge cases stay untested.
- One boot trace is minutes of wall time; deep traces are large (disk pressure).
- Single hart, no SMP, no real wall-clock timing.
- `vec2<u32>` 64-bit math is where bugs hide — the diff is essential, not optional.

---

## 8. Pointers

- `tools/RISCV_CPU_MMU.wgsl` — the emulator (`struct RiscvCPU` ~line 24, `fn main` ~line 3305).
- `tools/riscv_gpu_cpu.py` — `CPU_DTYPE`, the host mirror of the struct.
- `tools/boot_xv6_gpu.py`, `tools/boot_xv6_gpu_trace.py` — host drivers.
- `tools/qemu_cpu_trace.py`, `tools/diff_qemu_gpu_traces.py` — the oracle.
- `docs/GPU_RISCV_XV6_BOOT_RECEIPT.md` — first boot-to-shell milestone (2026-07-20).
- `RV64_LOCKSTEP_HARNESS_RECEIPT.md` — current QEMU-agreement status.
- `RV64_DEVELOPMENT_GUIDE.md` — pattern-guided workflow for adding RV64 instructions.
- `docs/HOW_THE_TRANSPILER_BOOTS_XV6.md` — the native spatial alternative: transpiling xv6 C to native Glyph ISA v2 assembly.
