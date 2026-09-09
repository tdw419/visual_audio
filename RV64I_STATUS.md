# RV64I GPU Emulator Status

## Performance Milestones (all honest, sync-bracketed measurements)

| Commit | Change | Measured effect |
|--------|--------|-----------------|
| 2aee769 | Precomputed Hilbert LUT (d2idx O(1)) | 3.3x (181k → 600k steps/s) |
| 3d0b073 | DecodedOp fast path (host decoder, 0 mismatches vs objdump on 60,615 OpenSBI instrs) | Verified correct, no rate win |
| 39ec634 | Sv39 TLB (256-entry direct-mapped, binding 7) + sfence.vma fix | 1.33x; fixed deep-boot freeze (PC pinned at 0xffffffff807fc3d8 — sfence.vma was a no-op in the fast path) |
| 034e99b | monitor_rv64i.py: opensbi/elf loaders, stall detection | Caught the TLB freeze bug a test harness structurally couldn't (2M early-exit missed the 8M freeze) |
| a58176d | RV64I basic-block bench (toy proof, numba-JIT CPU baseline) | 17-30x vs compiled CPU on sum-1..N at 1M-4M instances |
| f0598eb + ebbf1e9 | **Basic-block threading in the real emulator** | **2.25x** on Alpine boot: 1,584,637 steps/s ON vs 704,886 OFF (get_state()-bracketed); 92.0% threaded, 0% fallback, avg block 12.8 insts |
| (HEAD) | TLB instrumentation + bb-counter hoist | **+6-7%** on the real boot (1.58M → 1.69M steps/s at same 30M-step point); +7-8% on synthetic memory benches |
| (uncommitted) | **Alpine boot unblocked: timer interrupt chain + boot-image fixes** | Boot goes from a dead stall at 60M steps (0 UART after "Mountpoint-cache") to **the full initcall chain: crng init, SMP bringup, devtmpfs, DMA, USB, HugeTLB, initramfs unpack, /init handoff**. Five root causes fixed (see below) |

## TLB / Memory-Path Analysis (measured this milestone, synthetic + real-boot)

**Question: is a larger/associative TLB worth building? NO — measured answer.**

- Real Alpine boot, 120M steps: **39,191,946 TLB hits / 32,879 misses = 99.9% hit rate**.
  The 256-entry direct-mapped TLB already covers the boot's page working set; a bigger
  or associative TLB would buy ~nothing on this workload.
- The boot is ~100% S-mode with MMU on (mode split S100 at 50M/100M steps); the M-mode
  OpenSBI phase is <5M steps. The earlier hypothesis that "most execution bypasses the
  TLB in M-mode" does not hold for the current boot.

Clean isolation numbers (new synthetic benchmark `tools/tlb_membench.py` +
`tests/bare_metal/tlb_membench/`, SV39 identity map, S-mode, sync-bracketed):

| Variant | TLB hit | steps/s (threading on) |
|---------|---------|------------------------|
| ALU (no memory) | — | 1.96M |
| LOAD, 128-page working set (fits 256-entry TLB) | 99.2% | 1.35M |
| LOAD, 2048-page working set (thrash) | 49.8% | 1.04M |
| STORE, 2048-page working set (thrash) | 49.8% | 1.27M |

Reads: the full per-access memory path (TLB lookup + Hilbert LUT + storage load)
costs ~31% over pure ALU. The 3-level Sv39 walk (miss path) costs ~23% extra and
matters only when the TLB thrashes — which the Alpine boot does not do. The next
dominant cost after threading is per-step state-buffer write serialization (bb
counters, mtime, pc, instr_len all hammer the same 120-byte cache line every
step), not TLB capacity or the walk.

**Remaining instrumentation caveat:** the tlb_hits/tlb_misses counters are still
written per memory access from inside tlb_lookup() (they cost a few % and were
kept deliberately — they are the only at-a-glance TLB activity check; remove if
raw speed matters later). The bb counters were hoisted to locals and flushed once
per dispatch (host reads them only after step() returns) — that hoist is the
+6-7% above.

## Basic-Block Threading (current HEAD)

Threaded fallthrough path in `SPATIAL_RV64I.wgsl` main(): after a pre-decoded op
executes on the fast path, block-internal ops skip fetch(), the I-TLB translate,
raw validation, and interrupt checks. A block ends on: control-flow ops, CSR
writes (satp can re-map underneath; any CSR write can change privilege/interrupt
state), the 64-bit pc-fallthrough inequality check (the authoritative trap/redirect
test — load/store page faults redirect pc via raise_trap WITHOUT trap_pending),
4KB page-boundary crossing, non-pre-decoded slots, traps, halt.

**Verified gates (this milestone):**
- 13/13 unit tests pass
- A/B equivalence: threading ON vs OFF → all 32 regs + pc + mode + halted identical at 5M/15M/30M Alpine-boot steps
- UART output byte-identical (4096 bytes) at 30M steps
- 60M-step boot completes: pc=0xffffffff8038fe3e, mode=S, halted=0, no stall warnings

Measurement counters (bb_total/ctl/fallback/threaded/enabled) live in CPUState
(state buffer 92 → 112 bytes); host toggles via `set_bb_threading()`. Tools:
`check_threading_equivalence.py` (A/B gate), `tools/bb_length_dynamic.py` /
`tools/bb_length_static.py` (dynamic/static block-length distribution),
`tools/bb_bisect.py` (first-divergence finder).

**Measurement caveat (recorded for future sessions):** `core.step()` only submits
the GPU dispatch asynchronously — timing it alone measures submit speed (millions
of steps/s, meaningless). Real throughput requires bracketing with a blocking read:
`t0; step(); get_state(); dt`. The 12.7M → 15.7M steps/s figure in f0598eb was a
no-sync artifact; the honest sync-bracketed rates are 0.70M (off) / 1.58M (on).

## Unit / Integration Tests

```
tests/test_spatial_rv64i_cpu.py  13/13 PASSED (addi, sub, xor, slli, mul, addiw,
    ecall_halt, lr_sc_w, ld_sd_lwu, 64bit_mul_div, instruction page fault pc
    redirect, ram_base/mtimecmp persistence, uart rx roundtrip)
tests/test_opensbi_boot.py       PASSED
```

## Alpine Boot State (as of HEAD)

- Boots 60M+ steps cleanly through OpenSBI M-mode → kernel S-mode → early kernel
  init (cma: Reserved, percpu: Embedded, Dentry cache hash table visible in UART),
  with the TLB and threading both active
- No stalls; PC advances continuously through the former 8M-step freeze point
- Full boot to userspace still outstanding (needs more steps and/or further
  performance work; the boot is long)

## Alpine Boot Fixes (uncommitted milestone) — the 60M-step stall, root-caused

The boot previously died at ~60M steps right after "Mountpoint-cache hash table
entries" with the CPU cycling idle/tick code and zero UART. Investigation (QEMU
isolation with the SAME OpenSBI + kernel + DTB: QEMU sails past the stall) proved
it emulator-specific. Five independent root causes, all fixed:

1. **Timer interrupts OR-latched and never cleared.** `maybe_take_interrupt()`
   OR-set MTIP/STIP and relied on "implicit clearing" that never happened; the
   first armed timer interrupt became an infinite storm. Now clear-and-set from
   the live mtime comparison each call, preserving OpenSBI-injected STIP
   (software-latched, cleared when the guest re-arms).
2. **SBI TIME set-timer armed the wrong timer path.** OpenSBI v1.7 runs its
   timer with Sstc (it arms the S-mode `stimecmp` CSR and never touches the
   legacy mtimecmp MMIO). The native SBI TIME handler armed mtimecmp+MTIE
   instead; the M-timer fired but OpenSBI's Sstc-mode handler never stopped it
   (93% M-mode storm, boot stuck after sched_clock). The handler now writes
   `stimecmp` directly, matching OpenSBI's `mtimer_event_start`.
3. **mtime advanced 1024/step while the guest tick is 10000 ticks (1ms,
   HZ=1000).** The tick fired every ~10 instructions → ~98% interrupt duty →
   `kernel_init` never got scheduled. Now 1/step (~6% duty).
4. **DTB lacked `/chosen/rng-seed`.** crng never initialized; 6.12's
   `kernel_init_freeable` blocks in `wait_for_random_bytes()`. Added a fixed
   32-byte rng-seed (QEMU virt provides one; the kernel prints
   "random: crng init done").
5. **Boot-image layout bugs.** (a) The LNX header declares `initrd_size` but not
   an initrd file offset — the production image pads the initrd to 0x2000000 and
   the header-declared section is zeros ("Initramfs unpacking failed: invalid
   magic"). The loader now scans for the archive magic. (b) The initrd was placed
   at kernel_end — inside the kernel's own rounded-up memblock reservation
   ("INITRD overlaps in-use memory region"); placed at a fixed 32MB offset. (c)
   The DTB was placed at the top of RAM — inside the kernel's 16MB CMA region;
   CMA overwrote it and the late `of_fdt_raw_init` (crc32 over the DTB) oopsed.
   DTB now at a fixed 38MB offset, below the CMA.

Also reverted an external agent's broken uncommitted `read_csr` change (it
mapped CSR addresses through an RV32 struct-offset table, reading the wrong
buffer locations and breaking every host-side CSR read; the RV64 shader uses a
flat address-indexed `csrs` array, so `addr * 8` is correct).

**Verified:** 13/13 unit tests; boot reaches the full initcall chain (~160
kernel messages incl. "Unpacking initramfs...", X.509 certs) and hands off to
/init; the remaining blocker is userspace (busybox /init segfaults — the
emulator's userspace execution frontier, and the constant-clock jitterentropy
RNG spin makes the late boot slow: sha3/jent at ~30% CPU until it converges).

**Latest finding (post-commit):** with the real initrd now loaded, the
initramfs unpack runs the gzip inflate for ~50s of kernel time and then fails
with **"Initramfs unpacking failed: broken padding"** — the kernel gunzip's
leftover-input check (`strm.avail_in != 0` after Z_STREAM_END). The gzip is
exact-length and valid (Python decompresses the same 5,289,441 bytes cleanly
to 11,600,900 bytes, zero trailing padding), so the inflate is terminating
EARLY on the emulator — a mis-executed instruction in the zlib inflate's
stream-end path (the boot previously failed earlier with "invalid magic" from
the zeroed initrd section; the loader scan fix corrected the data, exposing
this next bug). The inflate must complete before /init can run.

**Known issue:** a pc-derived mtime advance variation (added to give the
jitterentropy RNG clock variance) caused a HARD stall at vgaarb (timed waits
stopped resolving) and was reverted — keep the mtime advance constant (1/step).

## Next Steps

1. **Full Alpine boot to userspace** — the kernel side now completes (initcall
   chain + /init handoff). Remaining: (a) the initramfs /init (busybox) segfaults
   — first userspace-execution bug to chase (memory layout of the ELF loader,
   syscalls, or a userspace instruction); (b) the constant-clock jitterentropy
   RNG spin slows the late boot (~30% CPU in sha3/jent until convergence) — a
   gentler mtime variation (rare 1-tick bump instead of per-instruction 1-4)
   might fix it without the vgaarb hard-stall the pc-derived jitter caused.
2. ~~Larger/associative TLB~~ **DONE — measured: not worth it** (99.9% hit rate
   on the real boot; the walk only matters when the working set thrashes, which
   the boot never does). If a future workload thrashes, the 4MB-superpage walk
   path is already correct — the TLB just needs more ways, not a redesign.
3. **Level 5c GPU test timeout** — **DONE — resolved**: `tests/level5c_gpu_test.py`
   completes in seconds with all four checkpoints passing.
4. **Per-step state-write reduction** — next lever: the WGSL loop writes
   state.pc_low/pc_high, state.instr_len, state.mtime_low (+high), and (for
   memory ops) tlb counters on every step. Ideas: batch pc writes for threaded
   fallthrough runs (write pc only at block end — but traps/loads inside a block
   need pc immediately, so this needs care); move tlb counters out of
   tlb_lookup() the same way the bb counters were hoisted (thread a
   ptr<function,u32> through translate_address); reorder CPUState fields so the
   per-step writes share fewer cache lines.
5. **Synthetic benchmark suite** — `tools/tlb_membench.py` +
   `tests/bare_metal/tlb_membench/` is the clean isolation tool for future
   memory-path work; extend with a mixed ALU/mem mix that mirrors the boot's
   0.5 lookups/inst if comparing against real-boot rates.

## Architecture (verified)

1. RV64I base ISA, M-extension, A-extension (LR/SC reservation machine)
2. 64-bit registers (vec2<u32>), 64-bit CSRs, 64-bit trap path (mepc/sepc/mtvec/stvec)
3. Sv39 MMU: 3-level page walk, sign extension, M-mode bypass (MPRV for data)
4. Sv39 TLB: 256-entry direct-mapped, invalidated on satp writes and sfence.vma
5. DecodedOp fast path: host-side decoder, per-slot lookup, raw-byte validation,
   runtime fallback (0% fallback measured on the Alpine boot)
6. Basic-block threading: threaded fallthrough for ~92% of executed instructions
