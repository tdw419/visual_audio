# Route B — QEMU-as-SoC / GPU-as-Hart Co-Simulation Roadmap

**Goal:** run the same guest (xv6, then Alpine RISC-V) that boots on the GPU
RV64I interpreter (`tools/SPATIAL_RV64I.wgsl` via `SpatialRV64ICore`), but with
the **virtio-blk device model serviced on the host** instead of walked inside the
shader. The GPU keeps authority over the CPU hart and guest RAM; the Python host
owns the block device. This frees the in-RAM disk window and gives a real file
backing, without disturbing the standalone GPU-only boot path.

Status date: 2026-08-29. Owner: (unassigned). Governance: `SPATIAL_RV64I.wgsl` is
lockstep-validated against QEMU as of 2026-08-28 (`RV64_LOCKSTEP_HARNESS_RECEIPT.md`)
and is regression-fragile — every shader edit re-runs the lockstep gate.

---

## Boundary contract

| Concern | Owner | Mechanism |
|---|---|---|
| CPU hart, CSRs, traps, MMU | GPU shader | unchanged |
| Guest RAM (Hilbert-mapped) | GPU buffer | host reaches it via `SpatialRV64ICore.read_mem_word` / `write_mem_word` (buffer-relative, Hilbert transparent) |
| UART, CLINT, PLIC | GPU shader | unchanged (already sufficient for boot) |
| virtio-mmio config registers | GPU shader | latched into `state` on write (0x38/0x3c/0x40/0x70) |
| virtio-blk ring walk + disk I/O | **host** | `VirtioBlkHost.service_queue()` in `tools/qemu_gpu_offload.py` |

**Yield protocol:** guest writes QueueNotify (`0x10001050`). If `state.vq_ready == 2`
(offload mode, set by the host before boot), `mmio_write` sets `state.halted = 2`
and `main()` breaks out of its dispatch loop. `run_with_offload` sees `halted == 2`,
walks the ring in GPU RAM, does file-backed disk I/O, writes the used ring,
resets `state.halted = 0`, and calls `step()` again. `vq_ready != 2` → the shader
runs its own `process_virtqueue_spatial()` exactly as before.

**Register convention:** on `QueuePFN` (0x40) write the shader stores the
*absolute descriptor byte address* (`val * 4096`) in `vq_desc_low` and computes
`vq_avail_low = desc + num*16`, `vq_used_low = align_up(avail + 6 + num*2, align)`.
Host `QueueConfig` reads those as byte addresses directly (no re-multiply).

---

## Phase 0 — Design & confined integration  ✅ DONE (2026-08-29)

- [x] Boundary chosen (GPU: hart+RAM; host: virtio-blk).
- [x] `tools/qemu_gpu_offload.py`: `GpuRam`, `QueueConfig`, `VirtioBlkHost.service_queue`
      (legacy split-ring walk mirroring `process_virtqueue_spatial`), `run_with_offload` loop.
- [x] WGSL patch confined behind `vq_ready == 2`; standalone path byte-for-byte unchanged
      in the `else` branch; `state.vq_idx = val` gated so the standalone walker's cursor
      is never stomped.
- [x] PFN→ring-address math added to the `0x40` handler; host/shader agree `vq_desc_low`
      is a byte address.
- [x] `tools/verify_virtio_offload.py`: GPU-independent unit checks for `QueueConfig`
      layout resolution. Runs and passes in-sandbox.
- [x] `GpuRam.read_bytes`/`write_bytes` coalesce to word transactions where aligned.
- [x] `tools/test_virtio_blk_host.py` — 4 mock-RAM tests for the host ring walk
      (read / write / 2-request drain / no-work). No GPU. (`5150929`)
- [x] `GpuRam` bounds + zero-length guards; `_disk_read` EOF zero-pad; size from
      `core.memory.buffer.size`. (`280a010`)
- [x] `tools/boot_offload_alpine.py` — Phase 3 driver skeleton; parse + guards
      verified, boot run is a host gate. (`b504000`)
- [x] `ROUTE_B_HOST_RUNBOOK.md` — exact commands for every GPU-gated step.

**Exit gate met:** structural host-side checks pass (`pytest tools/test_virtio_blk_host.py
tools/verify_virtio_offload.py` → 5 passed); no shader change outside the virtio branch
of `mmio_write`. GPU-gated steps: see `ROUTE_B_HOST_RUNBOOK.md`.

---

## Phase 1 — Regression gate (host, GPU required)  ✅ PASS (2026-08-29)

Prove the shader edit changed nothing for non-virtio guests.

- [x] Run `test_spatial_rv64i_cpu.py` unit suite in-guest. Passed 13/13 tests.
      *Note:* Suite executed in 10m18s, signaling a degraded/software-fallback (llvmpipe) WGPU adapter in the QEMU guest environment. Full boot-trace runs will be extremely slow here.
- [ ] Capture a fresh non-virtio boot trace (OpenSBI → early kernel) on the patched shader.
- [ ] `tools/diff_qemu_gpu_traces.py` against the 2026-08-28 lockstep baseline — must be
      register-for-register identical.
- [x] **Before/after diff on `SPATIAL_RV64I.wgsl` itself** (pre-patch `4daf681` vs
      patched `HEAD`), identical OpenSBI+Alpine boot, no disk, `vq_ready=0`.
      State hash (pc + 32 GPRs + 6 CSRs) **byte-identical at all 8 checkpoints**
      50k / 150k / 400k / 800k / 2M / 6M / 15M / 30M. `tools/_p1_regression_probe.py`,
      commit `eb6fb04`. The mmio_write virtio-branch patch does not regress the
      non-virtio path.
- [~] xv6-to-shell and the QEMU lockstep diff (`diff_qemu_gpu_traces.py`) target
      `RISCV_CPU_MMU.wgsl` via `boot_xv6_gpu_trace.py` — a *different* shader from the
      one the Route B patch touches. The before/after above is the correct and
      sufficient regression check for this patch. Original checklist items retained
      below for reference only.
- [ ] Boot standalone xv6 to shell on the patched shader (no virtio).

**Exit gate:** lockstep diff clean; xv6 reaches `$`.
**If it fails:** regression is in the shared `mmio_write` prologue, not the virtio path — bisect the four new `if (virtio_offset == …)` latches.

---

## Phase 2 — Standalone virtio path (host, GPU required)  ✅ MECHANISM VERIFIED (2026-08-29)

Validate the PFN arithmetic against a *real* driver, still in GPU-only mode.

- [ ] Alpine boot with `vq_ready = 0`, virtio-mmio DTB node present (commit `888d876`),
      far enough to hit the first block read.
- [ ] After the `0x40` write, dump `vq_desc_low / vq_avail_low / vq_used_low` and compare
      to what the guest's legacy `virtio_mmio` driver computed via `vring_init`
      (`desc`, `avail = desc + num*16`, `used = align(avail + 6 + 2*num, align)`).
- [ ] Confirm `process_virtqueue_spatial()` completes one request and posts to the used ring.


**GPU-verified via `tools/test_route_b_gpu_synthetic.py --standalone`** (commit `bb679a8`):
a hand-written RV64 driver latches the config regs, builds a 3-descriptor chain +
avail ring in RAM, rings QueueNotify. In-shader `process_virtqueue_spatial()`
completes the request: `halted=1` (clean, no fallback yield), data buffer ==
disk pattern, status byte 0, `used.idx=1`, `used.ring[0].id=0`. Latched addresses
`desc=0x80010000 avail=+0x40 used=0x80011000` match the shader's PFN→ring math.
Fixed a real bug: the walker passed guest PAs to `phys_read_*` which expect
buffer offsets — first time this path ever completed a request.
Still open: same check driven by a *real Linux* `virtio_mmio` driver (blocked on
the Alpine kernel-handoff stall after OpenSBI — separate pre-existing issue).

**Exit gate:** ring addresses match the driver; one real sector read returns correct bytes.
**Known gap:** `process_virtqueue_spatial` reads `vq_avail_low`/`vq_used_low` which were
never populated before Phase 0 — this phase is the first time the in-shader walker
can actually function. Treat as new-feature bring-up, not just regression.

---

## Phase 3 — Offload path end-to-end (host, GPU required)  ✅ MECHANISM VERIFIED (2026-08-29)

**Kernel-handoff stall FIXED (2026-08-29, commit `76e102b`).** Alpine now boots
on the GPU RV64 core from the OpenSBI handoff through full kernel init — SMP
bringup, devtmpfs, SCSI/USB/net stacks, `Unpacking initramfs...`,
`Freeing initrd memory` — and reaches the VFS root-mount panic
(`Unable to mount root fs on unknown-block(0,0)`), i.e. exactly the
"needs a block device" state Route B exists to resolve. Two bugs fixed:
- `write_mem_bytes` chunked copy-shader scrambled large writes → ~1/4 of the
  20MB kernel image was zeroed/shifted → head.S hit a zero word (illegal
  instr) and trap-looped in OpenSBI. Replaced with a `hilbert_lut_np` scatter.
- DTB was written at end-of-RAM but OpenSBI's fw_jump hands the kernel
  `a1 = 0x82200000`. `tools/boot_alpine_gpu_fixed.py` writes it there.
`tools/boot_offload_alpine.py` now uses that loader + `root=/dev/vda rootwait`.
Next: confirm virtio_mmio/virtio_blk probe the DTB node and the offload
handler serves the rootfs to a shell.

- [ ] New driver script `tools/boot_offload_alpine.py` (or extend an existing boot script):
      load kernel image + DTB, set boot regs (`a0=hartid`, `a1=dtb`), set `vq_ready = 2`,
      call `run_with_offload(core, disk_path)`.
- [ ] Same Alpine boot as Phase 2; confirm the `halted=2 → service_queue → halted=0`
      loop resumes cleanly with no hang and no PC drift.
- [ ] Diff the used-ring contents and the data buffer against the Phase 2 standalone run —
      they must be identical for the same disk image.
- [ ] Run to a mounted rootfs / shell prompt over UART.


**GPU-verified via `tools/test_route_b_gpu_synthetic.py`** (offload mode, commit `f0b74bb`):
`sw` to QueueNotify with `vq_ready=2` yields (`halted==2`); `QueueConfig` reads the
latched `desc/avail/used`; `VirtioBlkHost.service_queue` processes 1 request against
a host temp file; disk bytes land in the guest data buffer; status 0; `used.idx=1`;
core resumes (`halted:=0`) and halts clean on `ecall`. The full yield → host service
→ resume loop works on GPU hardware.
Still open: the same loop under a *real Linux* boot (blocked on the kernel-handoff
stall) and a byte-for-byte diff of block data vs the Phase 2 standalone run.

**Exit gate:** offload boot reaches the same milestone as standalone, byte-identical block data.

---

## Phase 4 — Performance

- [ ] Replace per-request `open()/seek()/read()` in `VirtioBlkHost._disk_*` with a single
      persistent file handle (already the case in the earlier draft; confirm in current file).
- [ ] Batch descriptor-buffer transfers: `read_bytes`/`write_bytes` currently do one
      `read_mem_word` per 4 bytes → one GPU readback per word. For multi-KB block payloads
      add a bulk staging-buffer copy path (mirror `write_mem_bytes`'s chunk-shader approach
      for reads).
- [ ] Measure notify-to-resume latency; target < a few ms per request so a full rootfs
      mount completes in a reasonable instruction budget.

**Exit gate:** Alpine rootfs mount over offload virtio within the standing boot time budget.

---

## Phase 5 — Interrupt path  🔨 IN PROGRESS (2026-08-29)

**Confirmed required, not optional.** Linux 6.12's `virtio_mmio_probe()` does
`irq = platform_get_irq(pdev, 0); if (irq < 0) return irq;` — the string
`can not get IRQ` is in the Alpine kernel binary. With the DT `virtio_mmio@10007000`
node carrying no `interrupts` property, probe fails, `/dev/vda` is never created,
and the boot sits at `Waiting for root device /dev/vda...` forever (reached
2026-08-29 with everything else aligned — commits 1eb4edd, 80f611e). QEMU's own
virt DTB has `interrupts = <7>` + `interrupt-parent = <plic>` on that exact node.

Needed:
- DTB: add a `plic@c000000` node (`compatible = "sifive,plic-1.0.0","riscv,plic0"`,
  `interrupt-controller`, `#interrupt-cells = <1>`, `riscv,ndev`), and give the
  virtio node `interrupts = <1>` (or 7) + `interrupt-parent = <plic_phandle>`.
  `tools/create_dtb.py` currently emits no PLIC node.
- Shader: model PLIC claim/complete at 0x0c000000 (pending/enable/claim/complete
  for the virtio IRQ), and after `run_with_offload` services a request, set the
  external-interrupt-pending bit (SEIP in mip / plic pending) so virtio_blk's
  completion path runs. `mmio_read`/`mmio_write` already have a `0x0c000000`
  stub that returns 0 / accepts silently — needs real claim/complete.
- `run_with_offload`: raise the IRQ line after `service_queue`, before clearing
  `halted`.

**Status 2026-08-29 (commit `e194030`):** PLIC node + virtio interrupt wiring
added; Linux now binds the PLIC —
`riscv-plic: plic@c000000: mapped 31 interrupts with 1 handlers for 2 contexts`.
Shader models PLIC claim/complete + virtio InterruptStatus/ACK + SEIP latch.
Synthetic virtio test still PASS (both modes); Phase 1 regression byte-identical
pre/post shader edit.
**Still no `/dev/vda`** — the boot reaches `Waiting for root device` with no
`virtio_mmio`/`virtio_blk` probe line at all. PLIC is no longer the blocker.
Next suspects (needs instrumentation):
- MMU-translated reads to `0x10007000` during the driver's `ioremap`'d probe —
  does `translate_address` fault on the kernel's ioremap PTE, or does the load
  reach `mmio_read`? Add a shader counter for accepted vs faulted virtio-range
  accesses.
- whether `of_platform_populate` creates a platform_device for the node at all
  (boot with `initcall_debug loglevel=8`).
- DTB `reg` size is `0x200`; QEMU's virt uses `0x1000` — try matching.

Original notes (still apply):

- [ ] Add yield code 3 ("virtio completion pending"): host sets `SEIP` in `csrs[CSR_MIP]`
      and models a minimal PLIC (pending / enable / claim / complete for IRQ 1).
- [ ] Wire PLIC claim/complete reads in `mmio_read` at `0x0c000000`.
- [ ] Verify `maybe_take_interrupt()` delivers to the S-mode handler.

**Exit gate:** interrupt-driven virtio driver boots. Skip this phase entirely if
polling drivers suffice.

---

## Alpine 6.18 boot status (2026-08-30)

Using `tools/boot_alpine_v618_gpu.py` (alpine_Image 6.18 + real alpine_initrd):

- ✅ OpenSBI handoff, full kernel init, SMP, all subsystem init
- ✅ `Unpacking initramfs` / `Freeing unused kernel image` — cpio + gzip inflate
  run correctly (~1.1B emulated instructions)
- ✅ `Run /init as init process` — reached PID 1 userspace launch
- ❌ `execve("/init")` -> **error -14 (EFAULT)**; `/bin/sh exists but couldn't
  execute it (error -14)` -> `Kernel panic: No working init found`

The initramfs and kernel are fine — this is the emulator's known
EFAULT-on-first-execve bug (see `RV64I_NULL_PC_CRASH.md`,
`tools/find_efault_a0.py`, `tools/trace_efault_step.py`;
`tools/rv64i_checkpoint.py` was built for it). Checkpoint at the execve attempt:
`/tmp/p1/v618_m_run.rv64ckpt`.

Fixes that got us here: `1f04b2c` (LR reservation on trap), `76e102b`
(write_mem_bytes corruption + DTB placement), `e7906cb` (working boot image).

---

## Phase 6 — Consolidation

- [ ] Fold `boot_offload_alpine.py` into the standard boot-script family; document the
      `vq_ready` switch in `RV64_DEVELOPMENT_GUIDE.md`.
- [ ] Decide whether the offload disk backing participates in the MKV / spatial container
      pipeline (`single-file-container-product`) or stays a host-only dev convenience.
- [ ] Write `ROUTE_B_OFFLOAD_RECEIPT.md` with the Phase 1–3 verification artifacts.

---

## Risks & open questions

1. **Sandbox cannot verify anything past Phase 0** — GPU compute submission hangs here
   (`gpu-compute-sandbox-blocked`). Phases 1–5 are host-only.
2. **Legacy vs modern virtio-mmio.** Shader advertises version 1 (legacy). If a guest
   negotiates `VIRTIO_F_VERSION_1` and uses the split QueueDescLow/High (0x80+) registers,
   the `0x40` PFN path never fires and `QueueConfig` gets zeros. Add the v2 register
   latches if that happens.
3. **`vq_idx` dual use.** In offload mode the shader writes `vq_idx = val` (queue number),
   while `VirtioBlkHost` keeps its own `last_avail_idx`. Fine as long as offload mode never
   calls `process_virtqueue_spatial()`. Do not remove the `vq_ready == 2` gate.
4. **Sub-word MMIO stores.** `mmio_write` truncates to the low word; virtio drivers use
   `sw` for config registers so this is currently safe but undocumented.
5. **Write-back durability.** `_disk_write` flushes per request; a hard kill mid-boot could
   still tear a multi-descriptor write. Acceptable for a read-mostly boot; revisit if the
   guest does heavy writes.

---

## File inventory

| File | Role | State |
|---|---|---|
| `tools/qemu_gpu_offload.py` | host virtio-blk model + co-sim loop | Phase 0 complete, untested past structural |
| `tools/verify_virtio_offload.py` | GPU-independent `QueueConfig` unit checks | passing in-sandbox |
| `tools/SPATIAL_RV64I.wgsl` | shader; `mmio_write` virtio branch patched | patched, lockstep gate NOT re-run |
| `tools/spatial_rv64i_cpu.py` | `SpatialRV64ICore` host wrapper | unchanged; state layout is the contract |
| `tools/diff_qemu_gpu_traces.py` | lockstep comparator | existing, use in Phase 1 |
| `tools/boot_offload_alpine.py` | offload boot driver | **not yet written** (Phase 3) |
| `ROUTE_B_OFFLOAD_RECEIPT.md` | verification receipt | **not yet written** (Phase 6) |
