# Regression incident, 2026-08-21 (post-rename to virtio_pixel_rs_v3_x86)

A "Phase 3 COMPLETE and VERIFIED" status report was inaccurate. On inspection, the
codebase (renamed from `virtio_pixel_rs_v3` to `virtio_pixel_rs_v3_x86` without
mention, alongside a new `virtio_pixel_rs_v3_riscv`) had regressed three previously
verified milestones simultaneously:

1. **PXC1 Hilbert PNG boot silently dead.** `bootloader_uefi.rs`'s PNG branch had
   been reverted to the pre-decode stub ("pixel-decode path not implemented yet,
   skipping"). Separately, `decoder.rs` had PNG decode gated behind a `png_decode`
   Cargo feature, default-off and not enabled anywhere — a second, independent way
   to break the same thing.
2. **x86_64 ecall trap caused a full reboot loop.** The replacement `ecall.rs`'s
   `x86_64_setup_idt()` never masked interrupts (`cli`) after installing the IDT,
   and was called *before* the BlockIO disk read. With 255/256 IDT vectors absent,
   any stray interrupt (most likely UEFI's own timer tick, firing mid-read)
   triple-faulted the machine. Confirmed via QEMU serial log: the boot banner
   repeated in an infinite loop, never reaching "Read N bytes from disk." The
   "builds cleanly" claim was true; "verified" was not — it never survived first
   real use.
3. **The replacement `int_0x80_handler` corrupted register state on return.** It
   pushed rax/rdi/rsi/rdx but then discarded them with `add rsp, N` before `iretq`
   instead of popping them back, so any kernel that actually reached a working
   trap would have had its registers clobbered afterward. Never exercised in
   practice due to #2.
4. Separately, `media.rs` (UEFI-specific — imports `uefi::proto::media::block::BlockIO`)
   had been moved into the supposedly-portable `virtio_pixel_rs_v3_shared` crate,
   which broke the build outright once `uefi`/`log` were pulled out of that crate's
   `Cargo.toml` as part of restoring it.

## Fix

- Restored the verified `ecall.rs`: `cli` after `lidt`, correct 4-register
  save/restore before `iretq`, `setup_trap_table()` called right before handoff
  (after all BlockIO work), not before.
- Restored unconditional (non-feature-gated) PNG/Hilbert decode in `decoder.rs`
  and re-wired `bootloader_uefi.rs`'s PNG branch to call it.
- Moved `media.rs` back into `virtio_pixel_rs_v3_x86` (UEFI-specific code belongs
  in the UEFI-specific crate, not the architecture-portable shared one).

## Re-verified in QEMU (all pass)

- Raw ELF handoff → `HANDOFF-OK`
- PXC1 Hilbert PNG → decode → handoff → `HANDOFF-OK`
- `int 0x80` ecall trap: `BEFORE-ECALL` → trap → `AFTER-ECALL`

## Process note

This is not an isolated incident — see the earlier `xy2d` fix being silently
reverted twice, and a fabricated "RISC-V crate created" claim from earlier in
this project's history. **"Builds cleanly" and "verified" are not the same
claim.** A clean build here still triple-faulted on first real boot. Before
trusting a status report on this codebase, rebuild from scratch and boot it in
QEMU against the three test payloads above — don't take a written summary at
face value, including this one.
