.section .text.init
.global _start
_start:
    la sp, stack_top
    j main
