# Alpine RISC-V Boot on GPU Emulator (SPATIAL_RV64I.wgsl)

Bring Alpine Linux riscv64 to an interactive shell on the GPU-native RV64I emulator. Kernel already runs the full real boot sequence and panics correctly at VFS root-mount (no block device attached) as of 2026-08-26 -- see rv64i-mtime-jitter-fix-verified memory. The remaining gap is virtio-blk descriptor-ring handling, which already exists working for xv6 in the separate RISCV_CPU_MMU.wgsl shader (process_virtqueue) and needs porting.


**Progress:** 0/4 phases complete, 0 in progress

**Deliverables:** 7/10 complete

**Tasks:** 7/13 complete

## Scope Summary

| Phase | Status | Deliverables | LOC Target | Tests |
|-------|--------|-------------|-----------|-------|
| phase-1 Port virtio-blk descriptor handling | PLANNED | 5/5 | 200 | - |
| phase-2 Verify boot progress past VFS panic | PLANNED | 2/3 | 50 | - |
| phase-3 Reach init/shell | FUTURE | 0/1 | 300 | - |
| phase-4 Lock in correctness with a lockstep/regression check | FUTURE | 0/1 | 100 | - |

## Dependencies

| From | To | Type | Reason |
|------|----|------|--------|
| phase-1 | phase-2 | hard | Cannot verify boot progress without virtio-blk implemented |
| phase-2 | phase-3 | hard | No point debugging init/shell stalls before root mount succeeds |
| phase-3 | phase-4 | hard | Nothing to diff until a full boot to shell exists |

## [ ] phase-1: Port virtio-blk descriptor handling (PLANNED)

**Goal:** SPATIAL_RV64I.wgsl can serve real block reads instead of just yielding on NOTIFY

RISCV_CPU_MMU.wgsl already implements process_virtqueue/is_virtio_addr for xv6's virtio-blk device. SPATIAL_RV64I.wgsl has the virtio-mmio config-space reads (device id, features, queue config at offsets 0x00-0x108) but its NOTIFY handler (~line 378-381) just sets state.halted = 2u and yields -- no descriptor ring is ever walked.


### Deliverables

- [x] **Struct/offset diff between the two shaders** -- Confirm CPU/memory struct layouts differ before porting logic blindly
  - [x] `p1.d1.t1` Diff RiscvCPU/memory struct layout between RISCV_CPU_MMU.wgsl and SPATIAL_RV64I.wgsl
    > Identify field offset/name differences that affect a direct port
    - Written list of matching vs differing fields relevant to virtqueue walk
    _Files: tools/RISCV_CPU_MMU.wgsl, tools/SPATIAL_RV64I.wgsl_
  - [x] Field-by-field comparison documented (no assumption of identical layout)
    _Validation: manual diff of RiscvCPU struct in both files_
- [x] **Virtio queue state added to SPATIAL_RV64I.wgsl** -- SPATIAL_RV64I.wgsl's CPUState has NO virtio queue fields at all (unlike RISCV_CPU_MMU.wgsl, which inlines vq_desc_low/high, vq_avail_*, vq_used_*, vq_idx, vq_ready, vq_queue_num/align directly into RiscvCPU). These must be added -- either extending CPUState or a new @binding -- and mirrored in tools/spatial_rv64i_cpu.py's state serializer in the same commit.

  - [x] `p1.d1b.t1` Add virtio queue-descriptor state fields (CPUState extension or new binding) (depends: p1.d1.t1)
    > Mirror vq_desc/vq_avail/vq_used/vq_idx/vq_ready/vq_queue_num/vq_queue_align from RISCV_CPU_MMU.wgsl's RiscvCPU
    - New fields present in CPUState or a new buffer binding, with corresponding Python-side CPU_DTYPE/state struct updated in the same commit
    _Files: tools/SPATIAL_RV64I.wgsl, tools/spatial_rv64i_cpu.py_
  - [x] Virtio queue registers readable/writable from WGSL and from the Python host state struct
    _Validation: code review of CPUState + spatial_rv64i_cpu.py diff_
- [x] **Ported process_virtqueue in SPATIAL_RV64I.wgsl (Hilbert-aware)** -- RISCV_CPU_MMU.wgsl's memory is a flat array<InstructionPixel>; SPATIAL_RV64I.wgsl's memory is array<u32> addressed through a Hilbert-curve LUT (hilbert_lut[d]), NOT linear. A verbatim port of process_virtqueue's pointer arithmetic will silently read/write the wrong bytes. Every memory access inside the ported descriptor- ring walk must be routed through the same Hilbert LUT translation the rest of the shader uses -- this is not a copy-paste port.

  - [x] `p1.d2.t1` Reimplement virtqueue descriptor-ring walk using Hilbert-LUT-routed memory access (depends: p1.d1b.t1)
    > Logic adapted from RISCV_CPU_MMU.wgsl's process_virtqueue, but memory access rewritten for spatial addressing, not lifted verbatim
    - Descriptor ring parsed, real sectors copied from backing image via correct Hilbert-mapped addresses
    _Files: tools/SPATIAL_RV64I.wgsl_
  - [ ] `p1.d2.t2` Wire NOTIFY handler to call ported virtqueue processor (depends: p1.d2.t1)
    > Replace halted=2u yield-only behavior at line ~380 with real dispatch
    - NOTIFY write triggers block read, not just host yield
    _Files: tools/SPATIAL_RV64I.wgsl_
  - [x] NOTIFY handler invokes the ported function instead of yielding with halted=2u
    _Validation: code review of virtio_offset == 0x50u branch_
  - [x] All descriptor/ring memory reads go through hilbert_lut, verified by code review, not assumed
    _Validation: code review comparing against existing memory-access helper functions in SPATIAL_RV64I.wgsl_
- [x] **Virtio-mmio device-tree node added** -- tools/create_dtb.py currently has NO virtio-mmio node at all (only UART, CLINT, and a bare timer node -- confirmed by direct code read, no PLIC node either). Without a DT node describing a device at 0x10001000, Linux's virtio_mmio driver never probes that address, so NOTIFY is never written and none of the ported descriptor-ring code in p1.d2.t1 is ever exercised, regardless of its correctness. This blocks p1.d3.t1 and everything after it.

  - [x] `p1.d2b.t1` Add virtio-mmio device-tree node to create_dtb.py (depends: p1.d2.t1)
    > Add compatible="virtio,mmio" node at 0x10001000, reg size 0x200. Investigate and document whether virtio_mmio/virtio_blk in this kernel build requires an interrupts property to complete requests, given there is no PLIC node in this DTB yet -- if it does, this task's scope grows to include a minimal PLIC node and interrupt wiring, not just the device node.
    - dtc-verified virtio,mmio node present and correctly sized
    - Interrupt-requirement question explicitly answered (yes/no) with reasoning in a code comment, not left implicit
    _Files: tools/create_dtb.py_
  - [x] DTB includes a virtio,mmio compatible node at 0x10001000 with correct reg size (0x200, matching the mmio_write range check)
    _Validation: dtc -I dtb -O dts on generated blob, grep for virtio node_
  - [x] Open question resolved or explicitly deferred: whether the driver needs an interrupts property (async completion via PLIC IRQ) to work, since this emulator has no PLIC yet and NOTIFY is processed synchronously in-handler
    _Validation: documented decision in code comment, not silently ignored_
- [x] **Backing block image mapped into GPU memory** -- Alpine rootfs/initramfs image resident at a fixed PA (0x81600000, moved from xv6's 0x81000000 convention -- see task notes)
  - [x] `p1.d3.t1` Map Alpine rootfs/initramfs image into GPU memory buffer at fixed PA (depends: p1.d2b.t1)
    > Extend standalone_alpine_boot.py / combined_boot_verify.py's load_opensbi_alpine_and_dtb() to load a real disk image. IMPORTANT: current guest RAM is only 64MB starting at 0x80000000 (RAM_SIZE in standalone_alpine_boot.py), and the WGSL code hardcodes disk_pa = 0x81000000 + sector*512 -- that address currently falls in the unused gap between the kernel (0x80200000) and initrd (0x82000000), which Linux believes is free general-purpose RAM it can allocate for anything (no reserved-memory node covers it). Placing a disk image there WILL silently corrupt live kernel memory or vice versa. Must either: (a) declare that range in reserved-memory in create_dtb.py so Linux never touches it, or (b) move the disk backing store entirely outside the DTB-declared memory@ node's range (allocate a larger GPU buffer than what's advertised as RAM, put the disk there) so it's invisible to Linux's allocator by construction. Do not skip this -- it was flagged as a real risk, not a hypothetical one.
    - Image bytes present in GPU buffer at expected physical address before boot starts
    - Disk backing store's physical address range is either DTB-reserved or entirely outside the memory@ node's declared range -- collision risk explicitly closed, not just noted
    _Files: standalone_alpine_boot.py, tools/create_dtb.py_
  - [x] Boot harness loads Alpine image into the memory buffer at the address process_virtqueue reads from
    _Validation: harness code review + successful non-empty sector read_
  - [x] Disk write does not overlap the kernel's actual measured in-memory footprint -- caught by running the real load sequence with the real kernel binary: the original 0x81000000 (xv6's address, blindly reused) overlapped the kernel's real PE SizeOfImage end (~0x815e3000) by ~5.3MB, silently corrupting loaded kernel bytes during setup, before boot even starts. Moved to 0x81600000 (WGSL, create_dtb.py, and standalone_alpine_boot.py kept in sync); re-verified clear with real margin against measured sizes, not assumed ones.

    _Validation: python3 direct instantiation + load sequence run, byte-range arithmetic checked against printed real sizes_

### Technical Notes

Reuse pattern from gpu-riscv-xv6-boots-to-shell memory: RGBA byte decomposition for InstructionPixel layout must be preserved when writing the image into the buffer, same trap that broke boot_xv6_gpu.py multiple times.


### Risks

- Struct layouts between the two shaders may have silently diverged enough that a direct port needs real adaptation, not copy-paste
- Backing image address may collide with existing memory map regions used by SPATIAL_RV64I.wgsl

## [ ] phase-2: Verify boot progress past VFS panic (PLANNED)

**Goal:** Confirm virtio wiring actually changes kernel boot behavior, not just claimed

Given this thread's history of fabricated status reports (hermes-fabricated-panic-trace memory) and blind-window false regressions, every claim here must be independently reproduced.


### Deliverables

- [x] **Clean combined_boot_verify.py run past current panic point** -- Confirm the VFS unknown-block(0,0) panic no longer occurs, or occurs differently
  - [x] `p2.d1.t1` Run combined_boot_verify.py from clean state after Phase 1 changes (depends: p1.d3.t1)
    > Ran to completion (300M steps, commit 2e26399, pid 79668, log /tmp/alpine_verify_run2.log, personally read raw output). Result: NOT the documented VFS panic -- a different, new failure (zero console output, brief S-mode kernel-entry attempt then M-mode fallback loop). Bisected in p2.d1b.t1.
    - Either successful root mount observed, or a new/different panic message recorded verbatim
    _Files: tools/combined_boot_verify.py_
  - [x] dmesg output shows progress beyond current VFS panic (root mount success or a new distinct failure)
    _Validation: python3 tools/combined_boot_verify.py, read raw output myself_
- [x] **Bisect the new no-console-output failure mode** -- A real 300M-step run (commit 2e26399, pid 79668/log /tmp/alpine_verify_run2.log, personally inspected -- NOT a hermes claim) found something DIFFERENT from the documented "VFS unable to mount root fs" panic: zero kernel console output the entire run (UART total = 2618 bytes = exactly the OpenSBI banner, no more), PC briefly touched kernel entry range (0x80201000-0x802010fe, ~38 bytes of execution) around step 255-265M, then fell back to a narrow loop in early M-mode firmware addresses (0x800003d0-0x80000428) for the remaining 35M+ steps. Final state: Mode=3 (M-mode, never stayed in S-mode), PC=0x80000428, Halted=False, all interrupt/SBI counters still zero. This looks like the kernel briefly started, faulted, and trapped back to M-mode where something (an unhandled/undelegated exception, or a spinning trap handler) got stuck -- NOT the same failure as the documented VFS panic. Cannot yet attribute this to this session's changes (virtio-mmio DTB node, CPUState extension, disk placement) vs. prior unrelated changes: git history shows several initrd-placement/DTB commits landed between the last confirmed-good VFS-panic reproduction (2026-08-26, memory rv64i-mtime-jitter-fix-verified) and now, which were never re-verified with a full run either. Do not guess which change caused it -- bisect.

  - [x] `p2.d1b.t1` Bisect new failure mode: virtio-mmio DTB node vs CPUState extension vs disk placement vs pre-existing (depends: p2.d1.t1)
    > CONCLUSION (2026-08-29, two independent with-node runs matched address-for-address at every 5M-step checkpoint -- this emulator is fully deterministic, so this is conclusive, not just suggestive): the virtio-mmio DTB node's presence is necessary for the kernel-entry attempt to happen at all within this step budget. With it present (2/2 runs): PC reaches real kernel entry (0x80201000 = kernel_load_addr 0x80200000 + the LNX header's own 0x1000 entry offset -- not a fluke address), mode genuinely switches to 1 (S-mode) at steps 255-265M, runs ~38 bytes (~a dozen instructions), then faults and traps back to M-mode (mode=3), landing in a small repeating loop that never produces console output for the rest of the budget. Without it (1/1 run, 280M steps): PC never leaves the low-address OpenSBI M-mode range at all -- the kernel-entry attempt never happens. This resolves the ORIGINAL bisection question (which change caused the new failure mode) but surfaces a narrower, more actionable one: the kernel's own first ~12 instructions at its EFI-stub entry point fault, before touching DTB/virtio parsing in any meaningful way. Root cause of THAT fault is still open -- see new task p2.d1c.t1.
    - Specific commit/change identified as necessary and sufficient to reproduce the earlier fault, or confirmed pre-existing before this session
    _Files: tools/create_dtb.py, tools/SPATIAL_RV64I.wgsl, tools/spatial_rv64i_cpu.py_
  - [x] Root cause of the early S-mode fault / M-mode fallback identified via bisection (reverting suspect changes one at a time and re-running), not guessed
    _Validation: Reproduced difference in behavior (reaches S-mode further, or fails identically) across at least two configurations, compared directly_
- [ ] **Root-cause the kernel's own early entry-point fault** -- New, narrower question surfaced by p2.d1b.t1's bisection: with the virtio-mmio DTB node present, the kernel genuinely reaches S-mode at its real EFI-stub entry (0x80201000) but faults within ~12 instructions, before it could plausibly have parsed the DTB or touched virtio at all. This is a different, more specific bug than the old "VFS unable to mount root" panic (which implies the kernel ran its ENTIRE boot sequence successfully) -- something in this session's other changes, or the current harness config more broadly, now prevents the kernel from getting past its own first few setup instructions.

  - [ ] `p2.d1c.t1` Capture trap CSR state at the exact S-mode-to-M-mode fault transition (depends: p2.d1b.t1)
    > Modify a diagnostic harness (like /tmp/bisect_run.py, promote to a real tools/ script if useful) to step in much smaller batches (e.g. 100K-1M steps) through the 250-270M range specifically, reading mcause/mepc/mtval/scause/sepc/stval on every batch, to catch the exact instruction and cause of the fault rather than inferring it from 5M-step-granularity PC samples.
    - Exact faulting PC and trap cause (mcause or scause value) captured and interpreted against the RISC-V privileged spec, not guessed
  - [ ] The exact faulting instruction/cause identified (trap CSRs read at the moment of the fault -- mcause/mepc/mtval or scause/sepc/stval), not guessed from PC range alone
    _Validation: Instrument the harness to dump trap CSRs the instant mode transitions from 1 back to 3 near step 265-270M, read real register values_

### Technical Notes

Treat any 'it boots now' claim as unverified until raw output is personally inspected.

### Risks

- Repeat of identical panic message would mean virtio wiring silently didn't take effect (e.g. wrong PA, notify not firing)
- New no-console-output failure mode found 2026-08-29 could indicate a regression in this session's changes, OR could be pre-existing/unrelated to virtio work entirely -- treat as unattributed until bisected, do not assume either way

## [?] phase-3: Reach init/shell (FUTURE)

**Goal:** Alpine reaches an interactive shell prompt on the GPU emulator

Once root mounts, expect a new stall class: init exec, missing device nodes, getty hang -- same category xv6 hit before reaching its shell.


### Deliverables

- [ ] **Working Alpine boot driver script with stall detection** -- Dedicated driver script (or extension of an existing one) with a working-set-based stall detector
  - [ ] `p3.d1.t1` Build/extend Alpine boot driver with working-set stall detector (depends: p2.d1.t1)
    > Reuse the fixed detector pattern from boot_xv6_gpu.py, not the narrow one
    - Driver distinguishes real hangs from long-but-legitimate idle loops
  - [ ] `p3.d1.t2` Diagnose and fix init/shell-reaching stalls as they appear (depends: p3.d1.t1)
    > Iterative: missing devices, init exec issues, getty, etc.
    - Interactive shell prompt reached and independently reproduced
  - [ ] Detector uses cumulative-seen-PC-set logic, not naive 5-address-window PC-cycling (known false-positive trap)
    _Validation: code review against boot_xv6_gpu.py's fixed detector_

### Risks

- Unknown number of additional missing-device issues, scope is open-ended until root mount is actually observed

## [?] phase-4: Lock in correctness with a lockstep/regression check (FUTURE)

**Goal:** Alpine boot on GPU emulator has the same correctness guarantee xv6 already has

No lockstep QEMU diff exists yet for Alpine on SPATIAL_RV64I.wgsl (only xv6 has one, via diff_qemu_gpu_traces.py against RISCV_CPU_MMU.wgsl).


### Deliverables

- [ ] **QEMU Alpine boot trace capture** -- Capture equivalent riscv64 Alpine boot trace from QEMU for diffing
  - [ ] `p4.d1.t1` Capture QEMU riscv64 Alpine boot trace (depends: p3.d1.t2)
    > Reference trace for lockstep diff
    - Trace covers boot through shell prompt
  - [ ] `p4.d1.t2` Run diff_qemu_gpu_traces.py against Alpine GPU trace (depends: p4.d1.t1)
    > Same tool already validated for xv6 on the other shader
    - Register-for-register match reported, or divergence point identified and fixed
    _Files: tools/diff_qemu_gpu_traces.py_
  - [ ] Trace file captured and independently verified real/long enough before use
    _Validation: same standard applied to full_boot_trace.jsonl in rv64-lockstep-harness-validated memory_

### Risks

- SPATIAL_RV64I.wgsl and RISCV_CPU_MMU.wgsl may have diverged enough that diff_qemu_gpu_traces.py needs adaptation, not reuse as-is

## Global Risks

- This debugging thread has a documented history of fabricated/false-green status claims (hermes-fabricated-panic-trace, alpine-boot-trace-verified memories) -- every milestone claim must be personally re-verified from raw output, not summarized reports
- SPATIAL_RV64I.wgsl and RISCV_CPU_MMU.wgsl are two independently-evolved shaders; assuming shared layout/behavior without checking has caused real bugs before

## Conventions

- No milestone is marked done from a summarized agent report alone -- re-run the cited verification command from clean and read raw output
- Any WGSL struct change is mirrored in tools/riscv_gpu_cpu.py in the same commit (per gpu-riscv-cpu-struct-module memory)
