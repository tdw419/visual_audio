.section .text.start
.global _start
_start:
    la   sp, stack_top
    call kmain
hang:
    wfi
    j    hang
.section .bss
.align 12
stack:
    .skip 4096
stack_top:
