# Virtual Pixel RS v3 — Dual-Architecture Bootloaders

Dual-architecture bootloader family for x86_64 (UEFI) and RISC-V (OpenSBI) with PXC1 Hilbert PNG boot and ecall interception.

## Architecture

```
virtio_pixel_rs_v3_x86/     # x86_64 UEFI bootloader
├── src/
│   ├── bootloader_uefi.rs  # Main UEFI entry point
│   └── media.rs            # UEFI BlockIO device abstraction
├── Cargo.toml

virtio_pixel_rs_v3_riscv/   # RISC-V OpenSBI bootloader
├── src/
│   └── main.rs             # Main entry point
├── hello.img               # Embedded test kernel
├── Cargo.toml

virtio_pixel_rs_v3_shared/  # Shared portable code (used by x86_64)
├── src/
│   ├── decoder.rs          # PXC1 Hilbert PNG decoder
│   ├── ecall.rs            # IDT (x86_64) / stvec (RISC-V) trap handling
│   ├── elf64.rs            # ELF64 loader
│   └── handoff.rs          # CPU state handoff
├── Cargo.toml

geos_pixel/                # Pixel decoding primitives (Hilbert curve)
└── src/
    ├── lib.rs
    ├── hilbert.rs
    └── decoder.rs
```

## Build

```bash
cd systems

# x86_64
cargo build -p virtio_pixel_rs_v3_x86 --bin bootloader_uefi_x86 --target x86_64-unknown-uefi

# RISC-V
cargo build -p virtio_pixel_rs_v3_riscv --release --target riscv64gc-unknown-none-elf
```

## Test

```bash
cd systems

# x86_64 with test kernel
qemu-system-x86_64 \
  -bios /usr/share/edk2/x64/OVMF_CODE.fd \
  -drive file=test.img,format=raw,if=virtio \
  -nographic

# RISC-V with embedded hello.img
qemu-system-riscv64 \
  -machine virt \
  -bios default \
  -kernel target/riscv64gc-unknown-none-elf/release/bootloader_riscv \
  -nographic
```

## Verification

See `PXC1_BOOTLOADER_VERIFIED_STATUS.md` for independent test results.

All four scenarios verified:
1. Raw ELF handoff (x86_64)
2. PXC1 Hilbert PNG boot (x86_64)
3. int 0x80 ecall trap (x86_64)
4. Full Phase 4 parity: 97-trap message + ACPI shutdown (x86_64)

RISC-V verified:
1. OpenSBI handoff → S-mode
2. 88 ecall traps intercepted
3. Clean SBI shutdown on illegal instruction

## Key Features

### x86_64
- UEFI boot environment (OVMF)
- BlockIO protocol for disk access
- IDT with vector 0x80 for syscall interception
- Interrupt masking (cli) during critical sections to prevent triple faults
- Clean ACPI shutdown via #UD → port 0x604

### RISC-V
- OpenSBI firmware handoff (M-mode → S-mode)
- S-mode trap table (stvec) for ecall interception
- SIE (supervisor interrupt enable) masking
- Clean SBI shutdown on unhandled traps

### Shared
- PXC1 Hilbert PNG decoder
- ELF64 loader with architecture verification
- CPU state handoff with privilege drop