#include <stdint.h>

#define UART_PHYS 0x10000000
#define UART_VIRT 0xC0000000

// Flags: Valid(1), Read(2), Write(4), Exec(8), User(16), Global(32), Access(64), Dirty(128)
#define PTE_V 1
#define PTE_R 2
#define PTE_W 4
#define PTE_X 8
#define PTE_A 64
#define PTE_D 128
#define PTE_LEAF (PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D)

#define SATP_MODE_SV39 (8ULL << 60)

extern uint64_t root_page_table[512];    // Provided by linker script
extern uint64_t level1_uart_table[512];  // Provided by linker script

void print_str(volatile uint8_t *uart, const char *str) {
    while (*str) {
        *uart = *str++;
    }
}

int main() {
    volatile uint8_t *uart_phys = (uint8_t *)UART_PHYS;
    print_str(uart_phys, "Level 3: Init MMU\n");

    // Clear root page table and the UART's level-1 table
    for(int i=0; i<512; i++) {
        root_page_table[i] = 0;
        level1_uart_table[i] = 0;
    }

    // 1. Identity map 0x80000000 to 0x80000000 (1GB Megapage)
    // VPN2 = 0x80000000 >> 30 = 2
    // PPN = 0x80000000 >> 12 = 0x80000 (PPN[17:0] == 0, so this IS a valid
    // 1GB-aligned superpage: 0x80000000 is a multiple of 0x40000000)
    root_page_table[2] = (0x80000ULL << 10) | PTE_LEAF;

    // 2. Map 0xC0000000 to UART physical 0x10000000.
    // NOTE: this CANNOT be a 1GB megapage - 0x10000000 is only 256MB, not a
    // multiple of 0x40000000 (1GB), so PPN[17:0] would be nonzero, which the
    // RISC-V spec requires to raise a misaligned-superpage page fault.
    // 0x10000000 IS a multiple of 0x200000 (2MB) though, so use a 2MB
    // megapage (Sv39 level-1 leaf) instead: a non-leaf pointer at VPN2=3,
    // then a leaf entry at VPN1=0 in that level-1 table.
    // VPN2 = 0xC0000000 >> 30 = 3
    // VPN1 = (0xC0000000 >> 21) & 0x1FF = 0
    root_page_table[3] = (((uint64_t)level1_uart_table >> 12) << 10) | PTE_V;
    level1_uart_table[0] = (0x10000ULL << 10) | PTE_LEAF;

    // 3. Enable Sv39 Paging
    uint64_t satp = SATP_MODE_SV39 | (((uint64_t)root_page_table) >> 12);
    
    // Write satp and flush TLB
    __asm__ volatile("csrw satp, %0; sfence.vma" : : "r"(satp));

    // 4. Test virtual memory translation
    volatile uint8_t *uart_virt = (uint8_t *)UART_VIRT;
    print_str(uart_virt, "Level 3: Paging Enabled & Virtual UART works!\n");

    while(1) {
        __asm__ volatile("wfi");
    }
    return 0;
}
