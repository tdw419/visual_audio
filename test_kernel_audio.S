// Simple RISC-V kernel that prints "Booted from audio" and halts
// This will be encoded as audio and loaded by audio_boot.rs

.section .text
.global _start

_start:
    // Write "Booted from audio" to UART (0x10000000)
    la a0, message
    jal print_string

    // Write newline
    li a0, '\n'
    sb a0, 0x10000000(t0)

    // Halt via infinite loop
    halt_loop:
        wfi
        j halt_loop

print_string:
    // a0 = pointer to null-terminated string
    mv t0, a0
print_loop:
    lb a1, 0(t0)
    beqz a1, print_done
    sb a1, 0x10000000(t0)
    addi t0, t0, 1
    j print_loop
print_done:
    ret

message:
    .asciz "Booted from audio"