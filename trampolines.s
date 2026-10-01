.text
.global unhandled_efi
unhandled_efi:
    li a0, -1
    slli a0, a0, 63
    addi a0, a0, 3
    ret

.global alloc_pool
alloc_pool:
    lui a7, 0x55454
    addi a7, a7, 0x649
    li a6, 5
    ecall
    ret
