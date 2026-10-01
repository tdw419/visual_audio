/* probe.ld — bare-metal RV64 probe linker script */
OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 64M
}

SECTIONS
{
    . = 0x80000000;
    .text : {
        *(.text._start)
        *(.text*)
    } > RAM

    .rodata : {
        *(.rodata*)
    } > RAM

    .data : {
        *(.data*)
        *(.sdata*)
    } > RAM

    .bss : {
        __bss_start = .;
        *(COMMON)
        *(.bss*)
        *(.sbss*)
        __bss_end = .;
    } > RAM

    .got : {
        *(.got*)
    } > RAM

    /DISCARD/ : {
        *(.note*)
        *(.eh_frame*)
        *(.riscv.attributes)
        *(.comment)
    }
}
