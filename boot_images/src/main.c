/* Minimal RISC-V kernel: prints via the SBI legacy console, then halts. */
static void sbi_putchar(int c) {
    register long a0 asm("a0") = c;
    register long a7 asm("a7") = 1;   /* SBI legacy console putchar */
    asm volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
}
void kmain(void) {
    const char *s =
        "\n*** HELLO FROM THE SPOKEN KERNEL ***\n"
        "Booted via a signed visual-audio boot manifest.\n";
    for (const char *p = s; *p; p++) sbi_putchar(*p);
    for (;;) asm volatile("wfi");
}
