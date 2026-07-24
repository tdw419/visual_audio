# RVC Test - Quadrant 0: Stack-relative memory (C.ADDI4SPN, C.LW, C.LD, C.SW, C.SD)
# This test uses patterns that encourage RVC instruction emission

.option rvc  # Enable RVC encoding preferences

.section .text.init
.globl _start
_start:
    # Initialize stack (boot args in t0)
    la sp, stack_top
    j main

.section .text
.globl main
main:
    # Print test banner
    li t1, 0x10000000  # UART base
    li t0, 'R'
    sb t0, 0(t1)
    li t0, 'V'
    sb t0, 0(t1)
    li t0, 'C'
    sb t0, 0(t1)
    li t0, ' '
    sb t0, 0(t1)
    

        # C.ADDI4SPN x8, sp, 32
        # Encoding: 0000_1000_0010_0000  (addi x8, sp, 32 may emit C.ADDI4SPN)
        addi x8, sp, 32
        
        # C.LW x9, 0(x8)
        lw x9, 0(x8)
        
        # C.SW x10, 4(x8)
        sw x10, 4(x8)
        

    # Success - print success code in a0
    # Output each nibble of a0
    mv t2, a0
    li t0, ' '
    sb t0, 0(t1)
    
    li t3, 4
output_loop:
    slli t4, t2, 28
    srli t4, t4, 28
    li t0, '0'
    ble t4, t0, skip_hex
    li t0, '9'
    ble t4, t0, is_digit
    addi t4, t4, -10
    li t0, 'A'
    add t4, t4, t0
    j output_char
is_digit:
    li t0, '0'
    add t4, t4, t0
output_char:
    sb t4, 0(t1)
    addi t3, t3, -1
    bnez t3, output_loop
    
    li t0, '
'
    sb t0, 0(t1)
    
    j done

skip_hex:
    # Value is 0-9, just add '0' and output
    add t4, t4, t0
    sb t4, 0(t1)
    addi t3, t3, -1
    bnez t3, output_loop
    
    li t0, '
'
    sb t0, 0(t1)
    
    j done

# Jump targets
target1:
    # Return from C.JAL
    ret

target2:
    # Return from C.JR
    j done

target3:
    # C.BEQZ taken correctly
    j done

target4:
    # C.BNEZ taken correctly
    j done

fail:
    # Failure case
    li a0, 0x4641494C  # "FAIL"

done:
    # Halt with wfi loop
halt_loop:
    wfi
    j halt_loop

# Stack allocation
.section .bss
.align 16
stack_bottom:
    .skip 0x4000  # 16KB stack
stack_top:
