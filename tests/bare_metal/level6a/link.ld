OUTPUT_ARCH( "riscv" )
ENTRY( _start )

SECTIONS
{
  . = 0x80000000;
  .text : {
    *(.text.init)
    *(.text)
  }
  . = ALIGN(0x1000);
  __utext_start = .;
  .utext : { *(.utext) }
  __utext_end = .;
  .data : {
    *(.data)
  }
  . = ALIGN(0x1000);
  .bss : {
    *(.bss)
  }
  . = ALIGN(0x1000);
  stack_top = .;
}
