# RECEIPT — GO-6 Layer 1: virtio-mmio transport alive on the GPU-native RV32 guest

**Date:** 2026-09-15 · **Seat:** orchestrator cron `af3e62239ce2` (implements directly — delegation retired 2026-09-15)
**Branch:** `go6-virtio-l1` (worktree `/home/jericho/projects/zion/worktrees/go6-virtio-l1`, based on `ce87f3e`)
**Commits:** `81c71a3` (engine + host), `f2dfe97` (gate + evidence artifacts)
**Authorization:** GO-6 gate opened by Jericho, explicit, in-channel 2026-09-15 ("activate at Layer 1") — `systems/GPU_OS_ROADMAP.md:414-420`; precondition GO-5 green+committed verified this tick before pickup.

## What landed

1. **`tools/SPATIAL_RV32I.wgsl`** — virtio-mmio transport register surface at
   `VIRTIO_BASE=0x10007000` (0x200 window), ported from `SPATIAL_RV64I.wgsl:324-450`
   (reads) and `:410-450` (writes):
   - reads: magic `0x74726976` ('virt'), version 1 (legacy), deviceID 2 (block),
     vendor `0x1AF4`, hostFeatures (RO bit only), queueNumMax 256, plus readback of
     queueNum/queueAlign/queuePFN/deviceStatus from state.
   - writes: queueNum (0x38), queueAlign (0x3C), queuePFN (0x40 → desc/avail/used
     derivation identical to the RV64 port, `vq_ready=2` armed), deviceStatus (0x70);
     QueueNotify/feature-select writes accepted, no action — **enumeration only, by design**.
   - `CPUState` widened by 8 words: `virtio_status, vq_desc, vq_avail, vq_used,
     vq_queue_num, vq_queue_align, vq_ready, vq_pfn`.
   - No PLIC/IRQ path: measured against this exact kernel family —
     `virtio_mmio_probe()` (`/home/jericho/projects/zion/linux-rv32/drivers/virtio/virtio_mmio.c:616-698`)
     reads only magic/version/deviceID (+DMA mask); `platform_get_irq` lives in
     `vm_find_vqs` (`:493`), which is the driver-bind path (Layer 2+).
2. **`tools/spatial_rv32i_cpu.py`** — state buffer 13→21 words; `get_state`/`load_program`
   extended; **`step()` now writes back the full state** (it previously truncated after
   `ram_base` — with the wider struct that would have reset fields 11-20 on every dispatch;
   even pre-port this was a latent trap for `uart_rx_*` and is now closed).
3. **`output/go6_l1/make_virtio_dtb.py`** → `sixtyfourmb_virtio.dtb` — derived from the
   shipped `sixtyfourmb.dtb` with exactly two additive changes: bootargs
   `virtio_mmio.device=64K@0x10007000:1` (cmdline transport device) and
   `/soc/virtio_mmio@10007000` node (`compatible "virtio,mmio"`, no interrupts — the
   create_dtb.py:275 no-PLIC lesson holds for 6.1.14's probe too). dtc round-trip verified
   in-script.

## Gate — the row's clause, run by the seat

```
python3 output/go6_l1/boot_virtio_gate.py   (worktree go6-virtio-l1)
→ [    6.845526] virtio-mmio: Registering device virtio-mmio.0 at 0x10007000-0x10016fff, IRQ 1.
→ GATE: GREEN — virtio-mmio transport enumerated by the 6.1.14 kernel
  10.28M steps, 21.2s wall, 10.28M-step early exit; UART evidence:
  output/go6_l1/l1_boot_uart.txt (committed)
```

RED before the fix (measured): first boot attempt used `virtio_mmio.device=0x10007000`
→ kernel printed `device: '0x10007000' invalid for parameter 'virtio_mmio.device'`
(virtio_mmio.c:42-50 requires `memparse` size `@base:irq`). Fixed to `64K@0x10007000:1`
→ GREEN above. Both tails are in this receipt and the commit body.

## Non-vacuity (the gate can fail)

`output/go6_l1/nonvacuity_prefix.sh`: the identical probe run against the PRE-port shader
(`git show ce87f3e:tools/SPATIAL_RV32I.wgsl`, pinned copy committed) → **T1-T4 RED,
PROBE: RED**; ported shader restored, md5 `608a7d80e24d08047c78f4e521eafb08` before == after.

## In-gate probe (transport semantics, all orchestrator-run)

`output/go6_l1/probe_transport_regs.py` → **T1-T5 GREEN**: magic read (T1), version/deviceID/
vendor (T2), queueNumMax + queueNum writeback + PFN=2 → `vq_desc=0x2000`/`vq_avail=0x2200`
(T3), deviceStatus write visible guest-side AND host-side in state (T4), window is device-
not-RAM (T5).

## No-regression

`tests/test_spatial_rv32i_cpu.py` → **19 passed** on the modified tree (both before commit
and re-run after).

## Scope

`git status` clean after commits; only `tools/SPATIAL_RV32I.wgsl`,
`tools/spatial_rv32i_cpu.py` (+artifacts under `output/go6_l1/`) changed. Worktree isolation
per AGENTS.md (WGSL shader = core codec component). No roadmap/backlog row was opened or
marked: GPU_OS_ROADMAP.md carries GO-6 as prose-layered row and Layer 1's own gate is
"transport alive in dmesg" — this receipt is the Layer 1 evidence; row-level ✅ stays
Jericho's call (Layers 2-3 remain open by design).

## What this PASS does NOT prove

- **No device driver binds.** The shipped Image has zero virtio_blk (strings-verified:
  `vd%c`/virtio_blk absent) — `/dev/vda` cannot appear until Layer 2's kernel rebuild.
  The `IRQ 1` in the dmesg line is the cmdline-declared irq number, and `vm_find_vqs`
  will `request_irq` on it at driver bind — untested here (no driver).
- **DTB-node-only enumeration path not separately observed on UART.** A cmdline-free DTB
  (`sixtyfourmb_dtbonly.dtb`, committed) was booted 40M steps: no virtio line before
  `/init` — 6.1.14's late-`of_platform_default_populate` for this node lands after the
  point this kernel's initramfs init takes over, so the node's probe (if any) is not
  observable as a boot-time dmesg line in this build. Layer 1's gate is satisfied by the
  cmdline-device leg (which DID probe the emulated window: `Registering … 0x10007000`
  with no `Wrong magic value`); the DTB node is committed for Layer 2.
- **Queue notify is accepted-and-ignored** (no descriptor walk, no SEIP). A guest writing
  0x50 gets silent acceptance.
- **No WGSL-twin differential vs the RV64 port** (different ISA/state layout — not
  byte-comparable); single seed, single run (n=1, not a rate).
- The CLINT-window note in `SPATIAL_RV64I.wgsl` about `phys_read_*` byte-offset semantics
  does not apply yet — the RV32 port reads/writes only its register window; the descriptor
  walk (which must subtract `ram_base` for `memory[]` access) is future work and this
  receipt's pointer math (`desc = pfn*4096`, guest-PA) has not been exercised end-to-end.
