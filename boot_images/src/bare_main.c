/* Bare M-mode RISC-V kernel for `-bios none`: writes straight to the qemu virt
   NS16550 UART (no SBI firmware present), then halts. Mirrors how xv6-riscv
   carries its own boot code instead of relying on OpenSBI. */
#define UART0 0x10000000UL
static void uart_putc(char c) {
    *(volatile unsigned char *)UART0 = (unsigned char)c;
}
void kmain(void) {
    const char *s =
        "\n*** HELLO FROM THE BARE-METAL SPOKEN KERNEL ***\n"
        "Booted with -bios none (no OpenSBI) via signed boot manifest.\n";
    for (const char *p = s; *p; p++) uart_putc(*p);
    for (;;) asm volatile("wfi");
}
