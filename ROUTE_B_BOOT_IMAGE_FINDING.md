# Route B: the shell blocker is the boot image, not the emulator (2026-08-29)

## Finding

`boot_images/alpine_riscv64.lnx.bin` — the image every GPU boot script has been
using — cannot reach userspace on *any* emulator:

- **Kernel 6.12.31 has no built-in virtio.** `strings` finds only
  `virtio_ring` / `virtio` core symbols; no `virtio_blk` / `virtio_mmio`
  driver strings. Those configs are `=m`, not `=y`.
- **The LNX container's initrd section is 5.2 MB of zeroes.** cpio parse: 0
  entries, no `/init`. The kernel prints `Freeing initrd memory: 5164K` and
  then falls straight through `populate_rootfs` → `prepare_namespace` →
  `mount_root` with nothing loaded.
- Net: no virtio driver, no initramfs `/init` → `Waiting for root device
  /dev/vda...` forever (or `unknown-block(0,0)` panic without `rootwait`).

**Cross-check:** `qemu-system-riscv64 -machine virt -kernel <this kernel>
-drive file=…,if=none,id=hd0 -device virtio-blk-device,drive=hd0
-append "root=/dev/vda rootwait"` — QEMU also hangs at `Waiting for root
device`, also no `virtio_blk` probe line. Confirms the image, not the GPU
emulator.

## Correct materials (already in repo)

- `boot_images/alpine_Image` — 22 MB, PE32+ RISC-V 64, kernel **6.18.35**
- `boot_images/alpine_initrd` — 6.6 MB gzip → 16 MB cpio, real initramfs:
  has `init`, and
  `usr/lib/modules/6.18.35-0-lts/kernel/drivers/virtio/virtio_mmio.ko`,
  `.../block/virtio_blk.ko`, `virtio.ko`, `virtio_ring.ko` (247 entries).
  Kernel and modules are version-matched.

## Next step to a shell

Swap the boot: load `alpine_Image` (raw PE, entry 0x80200000) + `alpine_initrd`
(separate gzip blob at the DTB's `initrd_addr`/`initrd_size`) instead of parsing
the `.lnx.bin` LNX header. Then the initramfs `/init` insmods `virtio_mmio.ko` +
`virtio_blk.ko`, they probe `virtio_mmio@10007000`, Route B's offload handler
services the ring, `/dev/vda` appears, `switch_root`, shell.

Risks: kernel 6.18 vs 6.12 may exercise emulator paths the 6.12 boot didn't
(new CSRs, instructions, timer behaviour) — expect a round of the same
QEMU-oracle diagnosis. But the Route B mechanism itself (host virtio-blk
offload, PLIC, interrupt delivery) is already verified on GPU via
`tools/test_route_b_gpu_synthetic.py`.

## What is proven working (this session)

- Kernel-handoff stall fixed — Alpine 6.12 boots through full kernel init
  (`ALPINE_GPU_BOOT_RECEIPT.md`, commit 76e102b).
- `write_mem_bytes` large-write corruption fixed (LUT scatter).
- Route B offload: synthetic RV64 driver → shader yield → host `service_queue`
  → data in guest RAM → clean resume. PASS on GPU.
- PLIC + virtio completion interrupt wired; Linux binds the PLIC
  (`riscv-plic: mapped 31 interrupts`). commit e194030.
- Phase 1 regression clean across every shader change.
