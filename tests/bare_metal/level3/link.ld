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
  .bss : {
    *(.bss)
  }
  . = ALIGN(0x1000);
  /* We need a 4KB aligned page for the root page table */
  root_page_table = .;
  . += 0x1000;
  /* Level-1 table for the UART's 2MB megapage (0x10000000 isn't 1GB-aligned,
     so it can't be mapped as a Level-2 1GB superpage - see main.c) */
  level1_uart_table = .;
  . += 0x1000;
  /* CRITICAL: without a real gap here, the stack (growing down from
     stack_top) sits immediately adjacent to level1_uart_table. main()'s
     stack frame then physically overlaps the tail of that table, so the
     table-clearing loop's own writes (as i approaches 511) stomp on its
     own loop counter and saved ra/s0 mid-loop. 16KB of dedicated stack
     space closes that gap. */
  . += 0x4000;
  stack_top = .;
}
