# Phase 3: Ecall/Syscall Handler Stubs — Architecture Review

## Problem Statement

After successful kernel handoff (HANDOFF-OK confirmed), the kernel will immediately crash on its first ecall/syscall instruction because the bootloader provides no handler infrastructure.

**From Phase 0 inventory:**

| Kernel | Syscall method | Location |
|--------|----------------|----------|
| xv6.img | Internal `syscall` function | `syscall+0x58` |
| xv6-riscv.img | Internal `syscall` function | `syscall+0x5c`, `syscall+0x7c` |
| hello.img | Direct RISC-V `ecall` instruction | Code segment |

## Architectural Approaches

### Option A: Minimal Stub Handlers (Recommended)

Create a trap table with stub handlers that:
1. Log the syscall number to serial console
2. Return a dummy value (0 or -1)
3. Prevent immediate crash

**Pros:**
- Minimal implementation (~50 lines)
- Lets kernel boot to user space
- Serial output reveals which syscalls are actually called
- Non-breaking — can extend later

**Cons:**
- Dummy returns may confuse kernel logic
- Doesn't actually handle I/O

### Option B: Proxy to Host OS

Hook ecall/syscall and forward to QEMU vhost-user backend.

**Pros:**
- Real I/O possible
- Kernel gets correct behavior

**Cons:**
- Requires host daemon
- Massive complexity (vhost-user protocol)
- Defeats bare-metal goal

### Option C: Embedded OS Services

Implement actual syscalls in bootloader:
- `read()`: Read from BlockIO
- `write()`: Write to serial console
- `exit()`: Halt QEMU

**Pros:**
- Self-contained
- Kernel gets functional I/O

**Cons:**
- Significant implementation effort
- Bloated bootloader
- Not Phase 3 scope

## Recommended Implementation: Option A

### File Structure

```
systems/virtio_pixel_rs_v3_shared/src/
  ecall.rs          # Trap table + stub handlers
```

### Trap Table Design

```rust
// ecall.rs
use core::arch::naked_asm;

#[cfg(target_arch = "x86_64")]
const SYSCALL_VECTOR: u64 = 0x80;

#[cfg(target_arch = "riscv64")]
const SYSCALL_VECTOR: u64 = 0x0;

pub fn setup_trap_table() {
    #[cfg(target_arch = "riscv64")]
    {
        // Write trap vector to stvec
        // stvec = {trap_handler_function} << 2
    }
}

#[cfg(target_arch = "riscv64")]
#[unsafe(naked)]
pub extern "C" fn trap_handler() -> ! {
    naked_asm!(
        "addi sp, sp, -16",    // Allocate stack frame
        "sd ra, 0(sp)",         // Save return address
        "sd a0, 8(sp)",         // Save syscall number
        "call handle_ecall",    // Call Rust handler
        "ld ra, 0(sp)",         // Restore return address
        "ld a0, 8(sp)",         // Restore/return value
        "addi sp, sp, 16",      // Free stack frame
        "sret",                 // Return to kernel
    );
}

#[cfg(target_arch = "riscv64")]
pub fn handle_ecall(syscall_num: u64) -> u64 {
    use uefi::println;
    uefi::println!("ECALL: syscall={}", syscall_num);

    match syscall_num {
        1 => { uefi::println!("  sys_write (stub)"); 0 }
        2 => { uefi::println!("  sys_open (stub)"); -1 }
        3 => { uefi::println!("  sys_close (stub)"); 0 }
        _ => { uefi::println!("  unknown syscall"); -1 }
    }
}
```

### Integration into Bootloader

```rust
// bootloader_uefi.rs (after segment loading)

// Set up trap table before handoff
virtio_pixel_rs_v3_shared::ecall::setup_trap_table();

uefi::println!("Trap table configured. Handing off to entry {:#x}...", header.e_entry);

unsafe {
    handoff::handoff_to_kernel(header.e_entry, &state);
}
```

## Verification Steps

1. **Build:** `cargo build --target x86_64-unknown-uefi`
2. **Boot:** QEMU with hello.img (RISC-V) or test kernel
3. **Expected output:**
   ```
   Handing off to entry 0x80200000...
   Ecall: syscall=1
     sys_write (stub)
   Ecall: syscall=10
     unknown syscall
   ```
4. **Success:** Kernel doesn't immediately crash; serial logs reveal syscalls

## Next Steps After Phase 3

Once stub handlers are verified and kernel boots to user space:

1. **Analyze serial logs** — Which syscalls does the kernel actually need?
2. **Priority syscalls first** — `write()` (serial output), `read()` (if needed), `exit()` (cleanup)
3. **Implement functional handlers** — Return real values, handle I/O

## Blockers

- RISC-V trap vector setup details (stvec register)
- QEMU RISC-V ecall routing to our trap handler
- Serial output from kernel (may need `write()` to serial)

## Questions for Kernel Payload

- Does the kernel expect specific return values for each syscall?
- Is there a specific syscall number convention (POSIX, xv6, custom)?
- Should we redirect `write()` to serial console or to QEMU debugcon?

---

**Recommendation:** Start with Option A stub handlers, verify with hello.img, then extend based on actual syscall traces.