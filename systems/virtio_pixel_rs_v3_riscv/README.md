# virtio_pixel_rs_v3_riscv — RISC-V Bare-Metal Bootloader

**Status:** Compiles and links for RISC-V, but targets `riscv64gc-unknown-none-elf` (bare-metal), not UEFI.

**Why not UEFI?**
- Rust-std does not have a `riscv64gc-unknown-uefi` target yet (only x86_64/i686/aarch64 UEFI targets exist)
- RISC-V UEFI support in QEMU is still experimental and requires custom firmware
- OpenSBI is the standard RISC-V boot firmware, not UEFI

**What works:**
- ✅ Compiles clean for RISC-V
- ✅ Stack pointer set to 0x80100000 (OpenSBI convention)
- ✅ `check_machine()` accepts EM_RISCV (0xf3) kernels
- ✅ RISC-V handoff assembly implemented (mv sp, jr a0)

**What's blocked:**
- ❌ No UEFI runtime — cannot use `uefi::prelude::*`, BlockIO protocol
- ❌ Cannot boot from real hardware or QEMU UEFI
- ❌ PNG decode stubbed out (miniz_oxide not integrated yet)

**Alternative path:**
Use the x86_64 UEFI bootloader (`virtio_pixel_rs_v3`) with a QEMU RISC-V vhost-user backend to boot RISC-V kernels indirectly.

**Integration path:**
For now, the RISC-V crate exists as a reference implementation. The practical boot path remains:
1. Encode RISC-V kernel as PXC1 visual container
2. Boot via x86_64 UEFI bootloader → decode → handoff to RISC-V VM

**Next steps:**
- Extract shared code (media.rs, elf64.rs, handoff.rs) into `virtio_pixel_rs_v3_shared`
- Wire PNG decode into boot flow (decoder.rs → bootloader_uefi.rs)
- Test with RISC-V test kernel (920-byte HANDOFF-OK) in QEMU

**Build command:**
```bash
cargo build --target riscv64gc-unknown-none-elf
```

**Output:** `target/riscv64gc-unknown-none-elf/debug/bootloader_uefi_riscv` (6MB)