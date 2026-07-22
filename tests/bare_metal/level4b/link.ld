OUTPUT_ARCH( "riscv" )
ENTRY( _start )

SECTIONS
{
  . = 0x80000000;
  .text : {
    *(.text.init)
    *(.text)
  }
  .data : {
    *(.data)
  }
  . = ALIGN(0x1000);
  .bss : {
    *(.bss)
  }
  . = ALIGN(0x1000);
  stack_top = .;

  /* Static VirtQueue storage: desc ring, avail ring, used ring.
     Placed well above the stack so nothing overlaps. */
  . = ALIGN(0x1000);
  vq_desc_base = .;
  . += 0x1000;
  vq_avail_base = .;
  . += 0x1000;
  vq_used_base = .;
  . += 0x1000;
}
