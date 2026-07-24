#include <stdint.h>

/* ─── Physical addresses ─────────────────────────────────────────── */
#define CODE_PA_BASE   0x80000000UL
#define UART_PA_BASE   0x10000000UL
#define S_UART_REMAP   0x50000000UL

/* ─── Virtual addresses for the two test pages ───────────────────────
 * Both hang off code_mid[1] (a new VPN[1]=1 branch under root[2], which
 * already routes 0x80000000-0xBFFFFFFF), pointing at a dedicated 4KB
 * L3 table so each page is a precisely 4KB-aligned leaf - no megapage
 * alignment ambiguity to worry about. */
#define MISC_VA_BASE     0x80200000UL   /* VPN[2]=2, VPN[1]=1 */
#define USER_DATA_VA     (MISC_VA_BASE + 0x0000)  /* VPN[0]=0: U=1 data page   */
#define XONLY_VA         (MISC_VA_BASE + 0x1000)  /* VPN[0]=1: U=0 X-only page */

volatile uint8_t *uart = (uint8_t *)S_UART_REMAP;

volatile int trap_count = 0;
volatile uint64_t last_scause = 0xFFFFFFFFFFFFFFFFULL;

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

/* M-mode trap handler - only fires if something faults before we reach
 * S-mode (shouldn't happen in this test, but keeps us observable if it does). */
void c_trap_handler(void) {
    uint64_t mcause, mepc;
    asm volatile("csrr %0, mcause" : "=r"(mcause));
    asm volatile("csrr %0, mepc" : "=r"(mepc));
    print_str("M-mode TRAP! mcause=");
    print_hex64(mcause);
    print_str("            mepc=");
    print_hex64(mepc);
    asm volatile("csrw mepc, %0" :: "r"(mepc + 4));
}

/* S-mode trap handler: catches load-page-faults (scause=13) from the
 * SUM/MXR tests below. Skips past the single faulting `lb` and srets. */
__attribute__((interrupt("supervisor")))
void s_trap_handler(void) {
    uint64_t scause, sepc;
    asm volatile("csrr %0, scause" : "=r"(scause));
    asm volatile("csrr %0, sepc" : "=r"(sepc));
    last_scause = scause;
    trap_count++;

    print_str("  TRAP caught: scause=");
    print_hex64(scause);
    print_str("  sepc=");
    print_hex64(sepc);

    if (scause == 13) { /* Load page fault - expected path */
        asm volatile("csrw sepc, %0" :: "r"(sepc + 4));
    } else {
        print_str("  UNEXPECTED scause, halting.\n");
        while (1) { asm volatile("wfi"); }
    }
}

/* Single faulting-or-succeeding load, isolated to one instruction so the
 * trap handler's sepc+4 skip lands cleanly past it either way. */
static uint8_t try_lb(volatile uint8_t *p) {
    uint8_t v = 0;
    asm volatile("lb %0, 0(%1)" : "=r"(v) : "r"(p));
    return v;
}

/* ─── SV39 page table ─────────────────────────────────────────────────
 * Page 0: root      (VPN[2])
 * Page 1: code_mid  (VPN[1], under root[1..3]) - S-mode code + UART, as in 5c/6a
 * Page 2: misc_l3   (VPN[0], under code_mid[1]) - the two test pages
 * Page 3: user_data (backing page for the U=1 data test)
 * Page 4: xonly     (backing page for the execute-only/MXR test)        */
#define PAGE_SIZE 4096
uint8_t pt_mem[5 * PAGE_SIZE] __attribute__((aligned(PAGE_SIZE)));

void build_page_table(void) {
    uint64_t *root     = (uint64_t *)pt_mem;
    uint64_t *code_mid = (uint64_t *)(pt_mem + 1 * PAGE_SIZE);
    uint64_t *misc_l3  = (uint64_t *)(pt_mem + 2 * PAGE_SIZE);
    uint8_t  *user_data_page = pt_mem + 3 * PAGE_SIZE;
    uint8_t  *xonly_page     = pt_mem + 4 * PAGE_SIZE;

    const uint64_t leaf_flags       = 0xCF; /* V|X|W|R|A|D, U=0 - normal S-mode code/UART */
    const uint64_t branch_flags     = 0x01; /* V only */
    const uint64_t user_data_flags  = 0xD7; /* V|R|W|A|D|U, no X - readable/writable data */
    const uint64_t xonly_flags      = 0xC9; /* V|X|A|D, no R, no W, U=0 - exec-only */

    uint64_t mem_ppn = (uint64_t)pt_mem >> 12;

    /* Known bytes to load back and verify. */
    user_data_page[0] = 0xAB;
    xonly_page[0]      = 0xCD;

    root[0] = ((mem_ppn + 1) << 10) | branch_flags;   /* unused range -> code_mid, harmless */
    root[1] = ((mem_ppn + 1) << 10) | branch_flags;
    root[2] = ((mem_ppn + 1) << 10) | branch_flags;   /* 0x80000000-0xBFFFFFFF -> code_mid */
    root[3] = ((mem_ppn + 1) << 10) | branch_flags;

    code_mid[0]   = ((CODE_PA_BASE >> 12) << 10) | leaf_flags;  /* 2MB: S-mode code   */
    code_mid[128] = ((UART_PA_BASE >> 12) << 10) | leaf_flags;  /* 2MB: UART          */
    code_mid[1]   = ((mem_ppn + 2) << 10) | branch_flags;       /* branch -> misc_l3  */

    misc_l3[0] = (((uint64_t)user_data_page >> 12) << 10) | user_data_flags; /* VA MISC_VA_BASE+0x0    */
    misc_l3[1] = (((uint64_t)xonly_page     >> 12) << 10) | xonly_flags;    /* VA MISC_VA_BASE+0x1000 */

    print_str("Page table built: U=1 data page + U=0 X-only page under 0x80200000.\n");
}

void s_mode_main(void) {
    print_str("Now in S-mode (SV39 active).\n");

    uint64_t sstatus;

    /* ── SUM test ─────────────────────────────────────────────────── */
    print_str("\n--- SUM test ---\n");
    asm volatile("csrr %0, sstatus" : "=r"(sstatus));
    sstatus &= ~(1ULL << 18); /* SUM = 0 */
    asm volatile("csrw sstatus, %0" :: "r"(sstatus));
    print_str("SUM=0, attempting lb from U=1 data page (expect fault)...\n");

    int before = trap_count;
    uint8_t v1 = try_lb((volatile uint8_t *)USER_DATA_VA);
    (void)v1;
    if (trap_count == before + 1 && last_scause == 13) {
        print_str("PASS: SUM=0 correctly faulted (Load Page Fault).\n");
    } else {
        print_str("FAIL: SUM=0 did NOT fault as expected!\n");
    }

    asm volatile("csrr %0, sstatus" : "=r"(sstatus));
    sstatus |= (1ULL << 18); /* SUM = 1 */
    asm volatile("csrw sstatus, %0" :: "r"(sstatus));
    print_str("SUM=1, attempting lb from U=1 data page (expect success)...\n");

    before = trap_count;
    uint8_t v2 = try_lb((volatile uint8_t *)USER_DATA_VA);
    if (trap_count == before) {
        print_str("PASS: SUM=1 read succeeded, value=");
        print_hex64((uint64_t)v2);
    } else {
        print_str("FAIL: SUM=1 still faulted!\n");
    }

    /* ── MXR test ─────────────────────────────────────────────────── */
    print_str("\n--- MXR test ---\n");
    asm volatile("csrr %0, sstatus" : "=r"(sstatus));
    sstatus &= ~(1ULL << 18); /* SUM = 0, cleanliness */
    sstatus &= ~(1ULL << 19); /* MXR = 0 */
    asm volatile("csrw sstatus, %0" :: "r"(sstatus));
    print_str("MXR=0, attempting lb from X-only page (expect fault)...\n");

    before = trap_count;
    uint8_t v3 = try_lb((volatile uint8_t *)XONLY_VA);
    (void)v3;
    if (trap_count == before + 1 && last_scause == 13) {
        print_str("PASS: MXR=0 correctly faulted (Load Page Fault).\n");
    } else {
        print_str("FAIL: MXR=0 did NOT fault as expected!\n");
    }

    asm volatile("csrr %0, sstatus" : "=r"(sstatus));
    sstatus |= (1ULL << 19); /* MXR = 1 */
    asm volatile("csrw sstatus, %0" :: "r"(sstatus));
    print_str("MXR=1, attempting lb from X-only page (expect success)...\n");

    before = trap_count;
    uint8_t v4 = try_lb((volatile uint8_t *)XONLY_VA);
    if (trap_count == before) {
        print_str("PASS: MXR=1 read succeeded, value=");
        print_hex64((uint64_t)v4);
    } else {
        print_str("FAIL: MXR=1 still faulted!\n");
    }

    print_str("\nLevel 6b Complete. Total traps caught: ");
    print_hex64((uint64_t)trap_count);

    while (1) { asm volatile("wfi"); }
}

int main(void) {
    print_str("Level 6b: SUM / MXR Fault Isolation\n");

    asm volatile("csrw pmpaddr0, %0" :: "r"(0x3FFFFFFFFFFFFFULL));
    asm volatile("csrw pmpcfg0, %0" :: "r"(0x1FULL));

    build_page_table();

    uint64_t root_ppn = (uint64_t)pt_mem >> 12;
    uint64_t satp_val = (8ULL << 60) | root_ppn;
    asm volatile("csrw satp, %0" :: "r"(satp_val));
    asm volatile("sfence.vma");

    asm volatile("csrw stvec, %0" :: "r"(&s_trap_handler));

    /* Delegate load-page-fault (cause 13) to S-mode. */
    uint64_t medeleg_val;
    asm volatile("csrr %0, medeleg" : "=r"(medeleg_val));
    medeleg_val |= (1ULL << 13);
    asm volatile("csrw medeleg, %0" :: "r"(medeleg_val));

    uint64_t mstatus;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus));
    mstatus &= ~(3ULL << 11);
    mstatus |= (1ULL << 11); /* MPP = S */
    asm volatile("csrw mstatus, %0" :: "r"(mstatus));

    extern void s_mode_main(void);
    asm volatile("csrw mepc, %0" :: "r"(&s_mode_main));

    print_str("mret into S-mode...\n");
    asm volatile("mret");

    print_str("ERROR: mret returned to M-mode!\n");
    while (1) { asm volatile("wfi"); }
    return 0;
}
