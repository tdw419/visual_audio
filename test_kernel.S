// Simple RISC-V kernel that prints "Booted from pixels" to UART
// Uses SBI console_putchar for output (standard for RISC-V)

.section .text
.global _start

_start:
    // Call _main
    call _main

    // Halt via infinite loop with WFI
    halt_loop:
        wfi
        j halt_loop

_main:
    // Print message using SBI console_putchar
    // SBI extension ID: 0x01 (legacy console)
    // Function: 0x00 (console_putchar)
    // a7 = extension ID, a6 = function ID, a0 = character

    li a7, 0x01        // Legacy console extension
    li a6, 0x00        // console_putchar function

    // Print "Booted from pixels\n"
    la t0, message
print_loop:
    lb a0, 0(t0)
    beqz a0, print_done
    ecall              // SBI call to print character
    addi t0, t0, 1
    j print_loop

print_done:
    // Return to caller
    ret

message:
    .asciz "Booted from pixels\n"