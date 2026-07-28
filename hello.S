.section .text
.global _start
_start:
    # UART is at PA 0x10000000. Let's write 'H', 'i', '\n'
    li t0, 0x10000000
    
    li t1, 72 # 'H'
    sb t1, 0(t0)
    
    li t1, 105 # 'i'
    sb t1, 0(t0)
    
    li t1, 10 # '\n'
    sb t1, 0(t0)
    
    # Halt/Loop
1:
    j 1b
