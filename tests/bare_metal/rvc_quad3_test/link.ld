OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS
{
    . = 0x80000000;
    .text : { *(.text .text.*) }
    . = ALIGN(8);
    .data : { *(.data .data.*) }
    . = ALIGN(8);
    .bss : { *(.bss .bss.*) }
    /DISCARD/ : { *(.comment) *(.note*) }
}
