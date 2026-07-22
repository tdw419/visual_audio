#include <stdint.h>

#define UART_BASE 0x10000000UL

static void uart_putc(char c) {
    volatile uint8_t *thr = (volatile uint8_t *)UART_BASE;
    *thr = (uint8_t)c;
}

static void uart_puts(const char *s) {
    while (*s) {
        uart_putc(*s++);
    }
}

void main(void) {
    uart_puts("Level 1: Hello from GPU RISC-V\n");
    for (;;) {
        /* halt in place */
    }
}
