#include <stdint.h>

#define UART_BASE 0x10000000
#define CLINT_BASE 0x02000000
#define MTIMECMP (CLINT_BASE + 0x4000)
#define MTIME    (CLINT_BASE + 0xBFF8)

volatile uint8_t *uart = (uint8_t *)UART_BASE;

void print_str(const char *str) {
    while (*str) {
        *uart = *str++;
    }
}

uint64_t get_mtime() {
    return *(volatile uint64_t *)MTIME;
}

void set_mtimecmp(uint64_t val) {
    *(volatile uint64_t *)MTIMECMP = val;
}

// Enable Machine Timer Interrupt (MTIE)
void enable_timer_interrupt() {
    uint64_t mie;
    __asm__ volatile("csrr %0, mie" : "=r"(mie));
    mie |= (1ULL << 7); // MTIE is bit 7
    __asm__ volatile("csrw mie, %0" : : "r"(mie));
}

// Enable global interrupts (MIE)
void enable_interrupts() {
    uint64_t mstatus;
    __asm__ volatile("csrr %0, mstatus" : "=r"(mstatus));
    mstatus |= (1ULL << 3); // MIE is bit 3
    __asm__ volatile("csrw mstatus, %0" : : "r"(mstatus));
}

void handle_trap() {
    print_str("Tick\n");
    // Schedule next tick
    set_mtimecmp(get_mtime() + 1000);
}

int main() {
    print_str("Level 2: Init\n");
    
    // Set first timer interrupt
    set_mtimecmp(get_mtime() + 1000);
    
    enable_timer_interrupt();
    enable_interrupts();
    
    print_str("Waiting for Tick...\n");
    
    while(1) {
        __asm__ volatile("wfi"); // Wait for interrupt
    }
    return 0;
}
