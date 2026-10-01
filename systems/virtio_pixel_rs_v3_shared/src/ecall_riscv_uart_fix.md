# RISC-V SBI Console Output Fix

## Problem

RISC-V kernels use SBI (Supervisor Binary Interface) for I/O, calling `sbi_putchar(c)` which issues:
```c
register long a0 asm("a0") = c;
register long a7 asm("a7") = 1;  // SBI Extension 0x01 (Console I/O)
asm volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
```

The bootloader's trap handler intercepted the ecall but only logged trap metadata, never forwarding the character to UART. This is why no kernel-authored output appeared.

## Solution

Modified `trap_handler()` in `virtio_pixel_rs_v3_shared/src/ecall.rs` to implement SBI Extension 0x01:

```rust
if f.cause == CAUSE_USER_ECALL || f.cause == CAUSE_SUPERVISOR_ECALL {
    LAST_TRAP = TrapState { cause: f.cause, syscall: f.a7, arg0: f.a0, arg1: f.a1 };
    TRAP_COUNT += 1;

    // SBI Extension 0x01 (Console I/O)
    if f.a7 == 0x01 {
        // SBI console putchar: write character in a0 to UART
        let c = f.a0 as u8;
        super::uart::UART.putc(c);
    }

    (*frame).pc += 4;
}
```

## Remaining Compilation Issues

1. **Module visibility**: `trap_entry` is in `riscv_ecall` submodule but being accessed via `super::`. Fixed by making it `pub`.
2. **Module reference**: `super::uart::UART` won't work from nested module. Need to use `crate::uart::UART` or import it.

## Next Steps

1. Fix the uart reference path in the trap handler
2. Rebuild the RISC-V bootloader
3. Run QEMU test to verify kernel output appears on serial console