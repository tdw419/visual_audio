# RISC-V Boot Path Blocker — OpenSBI Integration Required

## Current Status

| Architecture | Boot Firmware | Trap Mechanism | Phase 3 Status |
|--------------|---------------|----------------|----------------|
| x86_64 | ✅ UEFI (OVMF) | ✅ IDT + syscall int 0x80 | ✅ Implemented & Verified |
| RISC-V | ❌ OpenSBI | ⏸️ CSR (stvec) | ⏸️ Blocked |

## Why RISC-V is Blocked

### 1. No UEFI Target for RISC-V

Rust-std does not have `riscv64gc-unknown-uefi`:

```bash
$ rustc --print target-list | grep uefi
aarch64-unknown-uefi
i686-unknown-uefi
x86_64-unknown-uefi
# No RISC-V UEFI target
```

### 2. Different Boot Firmware Conventions

| x86_64 UEFI | RISC-V OpenSBI |
|-------------|---------------|
| Entry: `extern "efiapi" efi_main(Handle, SystemTable) -> Status` | Entry: `_start` in assembly (no parameters) |
| BlockIO protocol | SBI console (SBI_CALL_0x01) + SBI firmware |
| Memory map via `get_memory_map()` | Memory regions hardcoded or via SBI |
| Resource discovery via UEFI protocols | Device tree (DTB) or hardcode |

### 3. Different Trap Mechanism

| x86_64 | RISC-V |
|--------|--------|
| IDT (Interrupt Descriptor Table) | CSR registers (`stvec`, `scause`, `stval`) |
| `syscall` instruction → int 0x80 | `ecall` instruction → CSR trap |
| Kernel mode: ring 0 | Kernel mode: S-mode (Supervisor) |
| User mode: ring 3 | User mode: U-mode (User) |

## What Works Now

### x86_64 (Complete)

**Verified implementation:**
```rust
// ecall.rs (x86_64_ecall module)
static mut IDT: [IdtEntry; 256] = [const { IdtEntry::missing() }; 256];

pub fn setup_trap_table() {
    IDT[0x80].set_handler(syscall_entry as u64, 0x08); // syscall vector
    lidt(&IdtPtr { base: &IDT as *const _ as u64, limit: ... });
}
```

**End-to-end verification:**
- BEFORE-ECALL → int 0x80 trap → Rust handler → clean return → AFTER-ECALL
- Real syscall numbers captured
- Both boot paths verified (raw ELF, PXC1 Hilbert PNG)

## What Needs RISC-V OpenSBI Integration

### 1. Assembly Entry Point

```assembly
# start.S
.global _start
_start:
    # OpenSBI passes: a0 = hartid, a1 = device_tree_addr
    # We need to save these, then jump to Rust entry
    la sp, _stack_top
    call rust_main

rust_main:
    # Rust code takes over here
```

### 2. CSR Trap Vector Setup

```rust
// ecall.rs (riscv_ecall module)
pub fn setup_trap_table() {
    // Write trap handler address to stvec
    // stvec = {trap_handler_function} << 2
    unsafe {
        core::arch::asm!("csrw stvec, {0}", in(reg) trap_handler);
    }
}

#[unsafe(naked)]
pub extern "C" fn trap_handler() -> ! {
    naked_asm!(
        "addi sp, sp, -16",
        "sd ra, 0(sp)",
        "sd a0, 8(sp)",
        "call handle_ecall",
        "ld ra, 0(sp)",
        "ld a0, 8(sp)",
        "addi sp, sp, 16",
        "sret",  // Supervisor-mode return (not iret like x86_64)
    );
}
```

### 3. SBI Console for Logging

RISC-V uses SBI (Supervisor Binary Interface) for firmware services:

```rust
// SBI function numbers
const SBI_EXT_BASE: usize = 0x10;
const SBI_EXT_0_1_CONSOLE_PUTCHAR: usize = 0x01;

pub fn sbi_put_char(c: u8) {
    unsafe {
        let a0 = c as usize;
        core::arch::asm!(
            "ecall",
            in("a7") SBI_EXT_0_1_CONSOLE_PUTCHAR,
            in("a0") a0,
            lateout("a0") _,
            lateout("a1") _,
        );
    }
}
```

## Decision Point

### Option A: Full OpenSBI Rewrite Now (4-6 hours)

Implement complete RISC-V bare-metal boot path:
- Assembly entry point
- CSR trap vector
- SBI console logging
- Device tree parsing
- Memory region setup

**Pros:**
- Complete RISC-V support
- Same Phase 3 experience as x86_64

**Cons:**
- High initial effort
- Unknowns in SBI integration
- Delays Phase 3 syscall analysis

### Option B: Delay RISC-V Until x86_64 Syscall Analysis Complete (Recommended)

Use x86_64 to:
1. Capture real syscall numbers from hello.img/xv6.img
2. Determine which syscalls are actually needed
3. Implement functional handlers for common syscalls
4. Then port to RISC-V with proven patterns

**Pros:**
- Faster Phase 3 completion
- Proven syscall handling patterns
- Lower risk

**Cons:**
- RISC-V support delayed
- Need to redo some work for RISC-V

## Recommendation

**Proceed with Option B:**

1. Capture syscall traces from x86_64 hello.img/xv6.img
2. Implement functional handlers for common syscalls (`write`, `read`, `exit`)
3. Document which syscalls each kernel actually uses
4. Port proven patterns to RISC-V OpenSBI later

## Next Steps

### Immediate (x86_64)

1. **Capture syscall traces** from hello.img/xv6.img:
   ```bash
   cargo build --target x86_64-unknown-uefi
   qemu-system-x86_64 -bios OVMF.fd -drive file=hello.img -serial stdio
   ```

2. **Analyze traces** — which syscall numbers? Which registers?

3. **Implement functional handlers** for:
   - `sys_write` (serial output)
   - `sys_exit` (graceful shutdown)
   - `sys_read` (if needed)

### Deferred (RISC-V OpenSBI)

4. **Rewrite RISC-V boot path** for OpenSBI:
   - Assembly entry point
   - CSR trap vector
   - SBI console
   - Device tree parsing

5. **Port proven syscall handlers** from x86_64 to RISC-V

6. **Test with RISC-V hello.img/xv6.img**

---

**Status:** RISC-V blocked on OpenSBI boot path rewrite. x86_64 Phase 3 ready for syscall trace capture.