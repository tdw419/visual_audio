OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    /* QEMU virt machine RAM starts at 0x80000000
     * OpenSBI occupies 0x80000000-0x80200000, so we start at 0x80200000 */
    RAM : ORIGIN = 0x80200000, LENGTH = 128M
}

SECTIONS
{
    . = 0x80200000;

    /* Text section — code */
    .text : {
        KEEP(*(.text.entry))
        *(.text .text.*)
    } > RAM

    /* Read-only data — constants */
    .rodata : {
        *(.rodata .rodata.*)
    } > RAM

    /* Data section — initialized variables */
    .data : {
        *(.data .data.*)
    } > RAM

    /* BSS section — zero-initialized variables */
    .bss : {
        *(.bss .bss.*)
        *(COMMON)
    } > RAM

    /* Stack — allocate 8KB */
    .stack (NOLOAD) : {
        . = ALIGN(16);
        . += 8K;
        _boot_stack_top = .;
    } > RAM

    /* Discard sections we don't need */
    /DISCARD/ : {
        *(.comment .note .note.* .eh_frame .eh_frame_hdr)
    }
}