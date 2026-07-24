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
}
