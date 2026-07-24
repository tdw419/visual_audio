#include <stdint.h>

#define UART_BASE 0x10000000
volatile uint8_t *uart = (uint8_t *)UART_BASE;
#define PAGE_SIZE 4096

/* 4KB-aligned page table storage (2 pages: L2 root + L1 table). */
uint8_t l2_page[2 * PAGE_SIZE] __attribute__((aligned(PAGE_SIZE)));

void print_str(const char *s) {
    while (*s) *uart = *s++;
}

void print_hex64(uint64_t val) {
    const char hex[] = "0123456789ABCDEF";
    *uart = '0'; *uart = 'x';
    for (int i = 15; i >= 0; i--) {
        *uart = hex[(val >> (i * 4)) & 0xF];
    }
    *uart = '\n';
}

volatile uint64_t last_mcause = 0xFFFFFFFFFFFFFFFFULL;
volatile int trap_count = 0;

void c_trap_handler(void) {
    uint64_t mcause, mepc;
    asm volatile("csrr %0, mcause" : "=r"(mcause));
    asm volatile("csrr %0, mepc" : "=r"(mepc));
    last_mcause = mcause;
    trap_count++;

    print_str("TRAP! mcause=");
    print_hex64(mcause);
    print_str("      mepc=");
    print_hex64(mepc);

    /* Skip past the faulting instruction (assume 4-byte) */
    asm volatile("csrw mepc, %0" :: "r"(mepc + 4));
}

/* ─── SV39 identity-map page table ────────────────────────────────────────
 *
 * Identity-map 2MB pages for code (0x80000000) and UART (0x10000000).
 * ──────────────────────────────────────────────────────────────────────── */

void build_page_table(void) {
    uint64_t *l2 = (uint64_t *) l2_page;
    uint64_t *l1 = (uint64_t *)(l2_page + PAGE_SIZE);

    const uint64_t leaf_flags   = 0xCF;  /* V | X | W | R | A | D — S-mode only */
    const uint64_t branch_flags = 0x01;  /* V only (non-leaf)     */

    uint64_t l1_ppn = ((uint64_t)l1) >> 12;

    /* Address      VPN[2]  VPN[1]  L2 idx  L1 idx */
    /* 0x80000000   2       0       [2]     [0]    */
    /* 0x10000000   0       128     [0]     [128]  */
    l2[2] = (l1_ppn << 10) | branch_flags;
    l2[0] = (l1_ppn << 10) | branch_flags;

    /* PTE PPN field is always PA>>12 (page-number granularity), even for
     * a megapage leaf - only the low 9 bits of PPN must be zero for the
     * mapping to be 2MB-aligned. PA>>21 here was off by 9 bits, pointing
     * translations at a physical address ~512x too low. */
    l1[0]   = ((0x80000000ULL >> 12) << 10) | leaf_flags;
    l1[128] = ((0x10000000ULL >> 12) << 10) | leaf_flags;

    print_str("Page table built (2 pages, 2MB leaf entries).\n");
}

/* Entered via mret with mstatus.MPP=S-mode */
void s_mode_entry(void) {
    print_str("Now executing in S-mode.\n");

    /* Enable SV39 MMU */
    uint64_t root_ppn = (uint64_t)l2_page >> 12;
    uint64_t satp_val = (8ULL << 60) | root_ppn;

    print_str("satp value: ");
    print_hex64(satp_val);

    asm volatile("fence iorw, iorw");
    asm volatile("csrw satp, %0" :: "r"(satp_val));
    asm volatile("sfence.vma");

    print_str("satp written, MMU active.\n");

    /* Verify identity mapping works — UART at 0x10000000 */
    print_str("UART write via identity-mapped SV39: OK\n");

    print_str("Level 5b Complete.\n");

    while (1) {
        asm volatile("wfi");
    }
}

int main() {
    print_str("Level 5b: Identity-Mapped SV39\n");

    /* ── PMP: NAPOT covering all physical memory (matching level5a) ── */
    asm volatile("csrw pmpaddr0, %0" :: "r"(0x3FFFFFFFFFFFFFULL));
    asm volatile("csrw pmpcfg0, %0" :: "r"(0x1FULL)); /* A=NAPOT(3), R|W|X */

    /* Build page table in M-mode */
    build_page_table();

    /* Configure mstatus for S-mode, then mret */
    uint64_t mstatus;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus));
    print_str("mstatus before drop: ");
    print_hex64(mstatus);

    mstatus &= ~(3ULL << 11);
    mstatus |= (1ULL << 11);         /* MPP = S-mode */
    asm volatile("csrw mstatus, %0" :: "r"(mstatus));
    asm volatile("csrw mepc, %0" :: "r"(&s_mode_entry));

    print_str("Executing mret into S-mode...\n");
    asm volatile("mret");

    print_str("ERROR: mret returned to M-mode!\n");
    while (1) {
        asm volatile("wfi");
    }
}
