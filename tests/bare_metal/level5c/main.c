#include <stdint.h>

#define UART_BASE_IDENTITY 0x10000000UL
volatile uint8_t *uart_identity = (uint8_t *)UART_BASE_IDENTITY;

#define PAGE_SIZE 4096

/* Non-identity mapping targets: code moved up by 0x40000000, UART moved
 * to an unrelated virtual address entirely (proves the walker is doing
 * real translation, not just passing PA through by coincidence). */
#define CODE_VA_BASE   0xC0000000UL
#define CODE_PA_BASE   0x80000000UL
#define UART_VA_REMAP  0x50000000UL
#define UART_PA_BASE   0x10000000UL

uint8_t l2_page[2 * PAGE_SIZE] __attribute__((aligned(PAGE_SIZE)));

void print_str_via(volatile uint8_t *uart, const char *s) {
    while (*s) *uart = *s++;
}

void print_hex64_via(volatile uint8_t *uart, uint64_t val) {
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

    print_str_via(uart_identity, "TRAP! mcause=");
    print_hex64_via(uart_identity, mcause);
    print_str_via(uart_identity, "      mepc=");
    print_hex64_via(uart_identity, mepc);

    asm volatile("csrw mepc, %0" :: "r"(mepc + 4));
}

/* Root (walker's L1, indexed by VPN[2]) and middle (walker's L2, indexed
 * by VPN[1]) tables, shared across all four mappings below - they all
 * happen to want VPN[1]=0 (code targets) or VPN[1]=128 (UART targets),
 * so one middle table with two leaf slots covers everything. */
void build_page_table(void) {
    uint64_t *root = (uint64_t *) l2_page;
    uint64_t *mid  = (uint64_t *)(l2_page + PAGE_SIZE);

    const uint64_t leaf_flags   = 0xCF;  /* V | X | W | R | A | D */
    const uint64_t branch_flags = 0x01;  /* V only (non-leaf) */

    uint64_t mid_ppn = ((uint64_t)mid) >> 12;

    /* VA            VPN[2]  VPN[1]  root idx  mid idx  -> PA          */
    /* 0x80000000    2       0       [2]       [0]      -> 0x80000000 (identity, M-mode safety) */
    /* 0xC0000000    3       0       [3]       [0]      -> 0x80000000 (non-identity code remap)  */
    /* 0x10000000    0       128     [0]       [128]    -> 0x10000000 (identity UART)             */
    /* 0x50000000    1       128     [1]       [128]    -> 0x10000000 (non-identity UART remap)   */
    root[0] = (mid_ppn << 10) | branch_flags;
    root[1] = (mid_ppn << 10) | branch_flags;
    root[2] = (mid_ppn << 10) | branch_flags;
    root[3] = (mid_ppn << 10) | branch_flags;

    /* PTE PPN field is always PA>>12 (page-number granularity), even for
     * a 2MB leaf - only the low 9 bits need to be zero for alignment.
     * (This is the exact bug 5b caught: PA>>21 here would be wrong.) */
    mid[0]   = ((CODE_PA_BASE >> 12) << 10) | leaf_flags;
    mid[128] = ((UART_PA_BASE >> 12) << 10) | leaf_flags;

    print_str_via(uart_identity, "Page table built (4 root entries, 2 shared leaves).\n");
}

/* Entered via mret with mstatus.MPP=S AND satp already active, at its
 * VIRTUAL address (CODE_VA_BASE + link-time offset) - so simply fetching
 * this function's first instruction already proves the walker completed
 * a non-identity instruction-fetch translation. */
void supervisor_main(void) {
    volatile uint8_t *uart_remap = (uint8_t *)UART_VA_REMAP;

    print_str_via(uart_identity, "supervisor_main reached via non-identity VA fetch: OK\n");

    print_str_via(uart_remap, "UART write via non-identity VA (0x50000000->0x10000000): OK\n");

    print_str_via(uart_identity, "Level 5c Complete.\n");

    while (1) {
        asm volatile("wfi");
    }
}

int main() {
    print_str_via(uart_identity, "Level 5c: Non-Identity SV39 Mapping\n");

    /* PMP: NAPOT covering all physical memory (S-mode has zero access
     * without this - see Level 5a). */
    asm volatile("csrw pmpaddr0, %0" :: "r"(0x3FFFFFFFFFFFFFULL));
    asm volatile("csrw pmpcfg0, %0" :: "r"(0x1FULL));

    build_page_table();

    uint64_t root_ppn = (uint64_t)l2_page >> 12;
    uint64_t satp_val = (8ULL << 60) | root_ppn;
    print_str_via(uart_identity, "satp value: ");
    print_hex64_via(uart_identity, satp_val);

    /* M-mode's own fetches bypass translation regardless (Level 5b fix),
     * so it's safe to program satp here before dropping privilege - the
     * S-mode fetch that follows mret is what actually gets translated. */
    asm volatile("csrw satp, %0" :: "r"(satp_val));
    asm volatile("sfence.vma");

    uint64_t mstatus;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus));
    mstatus &= ~(3ULL << 11);
    mstatus |= (1ULL << 11); /* MPP = S */
    asm volatile("csrw mstatus, %0" :: "r"(mstatus));

    /* Relocate supervisor_main's link-time address into the CODE_VA_BASE
     * window - this is the actual virtual PC mret will jump to. */
    uint64_t supervisor_va = (uint64_t)&supervisor_main - CODE_PA_BASE + CODE_VA_BASE;
    print_str_via(uart_identity, "supervisor_main virtual address: ");
    print_hex64_via(uart_identity, supervisor_va);
    asm volatile("csrw mepc, %0" :: "r"(supervisor_va));

    print_str_via(uart_identity, "Executing mret into S-mode at non-identity VA...\n");
    asm volatile("mret");

    print_str_via(uart_identity, "ERROR: mret returned to M-mode!\n");
    while (1) {
        asm volatile("wfi");
    }
}
