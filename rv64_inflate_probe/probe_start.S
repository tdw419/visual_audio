/* probe_start.S — pure assembly entry point: set sp BEFORE any C code runs.
 * QEMU's bare-metal loader jumps to the load base (0x80000000), not e_entry,
 * so this section must be the first thing in .text.
 */
.section .text._start, "ax"
.globl _start
.type _start, @function
_start:
    li   sp, 0x83FFF000      /* top of 64MB RAM */
    call main
1:  wfi
    j    1b
.size _start, .-_start
