#include <stdint.h>

/* ─── Physical addresses ─────────────────────────────────────────── */
#define CODE_PA_BASE   0x80000000UL
#define UART_PA_BASE   0x10000000UL

/* ─── Virtual addresses (S-mode and U-mode) ──────────────────────── */
#define USER_CODE_VA   0x00010000UL   /* User trampoline (mapped U=1) */
#define USER_UART_VA   0x10000000UL   /* User UART    (mapped U=1)    */
#define S_UART_REMAP   0x50000000UL   /* S-mode UART  (from 5c)       */
#define S_CODE_VA      0x80000000UL   /* S-mode code identity          */

/* ─── UART access (S-mode uses 0x50000000, the non-identity remap) */
volatile uint8_t *uart = (uint8_t *)S_UART_REMAP;

/* ─── Globals for M-mode trap handler ────────────────────────────── */
volatile uint64_t last_mcause = 0xFFFFFFFFFFFFFFFFULL;
volatile int trap_count = 0;

/* ─── UART helpers ───────────────────────────────────────────────── */
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

/* ─── M-mode trap handler (c_trap_handler) ───────────────────────────
 * Called from entry.S's trap_vector when something faults before
 * we reach S-mode.  Just report and skip. */
void c_trap_handler(void) {
    uint64_t mcause, mepc;
    asm volatile("csrr %0, mcause" : "=r"(mcause));
    asm volatile("csrr %0, mepc" : "=r"(mepc));
    last_mcause = mcause;
    trap_count++;

    print_str("M-mode TRAP! mcause=");
    print_hex64(mcause);
    print_str("            mepc=");
    print_hex64(mepc);

    asm volatile("csrw mepc, %0" :: "r"(mepc + 4));
}

/* ─── U-mode trampoline ──────────────────────────────────────────────
 * Placed in .utext section (4KB-aligned, mapped U=1).
 * Self-contained: no external calls or data references.
 * Writes to UART then ecalls back to S-mode. */
__attribute__((section(".utext"), naked))
void u_trampoline(void) {
    asm volatile(
        "li t0, %[uart_va]\n"               /* UART user VA            */
        "li t1, 0x55\n"                      /* 'U'                     */
        "sb t1, 0(t0)\n"                     /* print 'U'               */
        "li t1, 0x0A\n"                      /* '\n'                    */
        "sb t1, 0(t0)\n"                     /* newline                 */
        "li a7, 42\n"                        /* cookie for S-mode       */
        "ecall\n"                            /* trap to S-mode stvec    */
        "1: wfi\n"
        "j 1b\n"                             /* halt (in case of sret)  */
        :: [uart_va] "i" (USER_UART_VA)
    );
}

/* ─── SV39 page table with U=1 entries ───────────────────────────────
 *
 * Memory layout (4 pages, 16KB, zeroed in BSS):
 *   Page 0: Root   table (512 × 8 B PTEs) — VPN[2] lookup
 *   Page 1: Code   mid  (512 × 8 B PTEs) — VPN[1] lookup, S-mode
 *   Page 2: User   mid  (512 × 8 B PTEs) — VPN[1] lookup, U-mode
 *   Page 3: User L3      (512 × 8 B PTEs) — VPN[0] lookup, 4KB pages
 *
 *      ┌──────────────────────────────────────────────────────┐
 *      │  Root          Code Mid      User Mid      User L3   │
 *      ├──────────────────────────────────────────────────────┤
 *      │ [0] → UserMid  [0]→*0x80000000 U=0 │ [0] → UserL3  │ [16]→*code_pa U=1 │
 *      │ [1] → CodeMid  [128]→*0x10000000 U=0│ [128]→*0x10000000 U=1│ [...invalid]    │
 *      │ [2] → CodeMid                       │               │                   │
 *      │ [3] → CodeMid                       │               │                   │
 *      └──────────────────────────────────────────────────────┘
 *
 *  User L2[0] is a *branch* at VPN[1]=0, pointing to L3.  Only
 *  L3[16] (VA 0x00010000) and L3[32] (VA 0x00020000, unused) are
 *  populated — the rest are invalid, so stray low-VA accesses
 *  from U-mode page-fault as expected.
 *
 *  User L2[128] is a 2MB leaf for UART at VA 0x10000000, U=1. */
#define PAGE_SIZE 4096
uint8_t pt_mem[4 * PAGE_SIZE] __attribute__((aligned(PAGE_SIZE)));

void build_page_table(void) {
    uint64_t *root     = (uint64_t *)pt_mem;                      /* Page 0 */
    uint64_t *code_mid = (uint64_t *)(pt_mem + 1 * PAGE_SIZE);    /* Page 1 */
    uint64_t *user_mid = (uint64_t *)(pt_mem + 2 * PAGE_SIZE);    /* Page 2 */
    uint64_t *user_l3  = (uint64_t *)(pt_mem + 3 * PAGE_SIZE);    /* Page 3 */

    const uint64_t leaf_flags     = 0xCF;    /* V|X|W|R|A|D, U=0 (S-mode)    */
    const uint64_t user_leaf_flags = 0xDF;   /* V|X|W|R|A|D, U=1 (U-mode)    */
    const uint64_t branch_flags   = 0x01;    /* V only (non-leaf)             */

    uint64_t mem_ppn = (uint64_t)pt_mem >> 12;

    /* ── Root table (VPN[2]) ─────────────────────────────────────── */
    root[0] = ((mem_ppn + 2) << 10) | branch_flags;   /* 0x00000000-0x3FFFFFFF → user_mid */
    root[1] = ((mem_ppn + 1) << 10) | branch_flags;   /* 0x40000000-0x7FFFFFFF → code_mid */
    root[2] = ((mem_ppn + 1) << 10) | branch_flags;   /* 0x80000000-0xBFFFFFFF → code_mid */
    root[3] = ((mem_ppn + 1) << 10) | branch_flags;   /* 0xC0000000-0xFFFFFFFF → code_mid */

    /* ── Code middle table (VPN[1], S-mode mappings) ──────────────── */
    code_mid[0]   = ((CODE_PA_BASE >> 12) << 10) | leaf_flags;    /* 2MB: code   */
    code_mid[128] = ((UART_PA_BASE >> 12) << 10) | leaf_flags;    /* 2MB: UART   */

    /* ── User middle table (VPN[1], U-mode mappings) ──────────────── */
    user_mid[0]   = ((mem_ppn + 3) << 10) | branch_flags;   /* 4KB leaf: user code   */
    user_mid[128] = ((UART_PA_BASE >> 12) << 10) | user_leaf_flags;  /* 2MB: user UART */

    /* ── L3 table (VPN[0], 4KB user pages) ────────────────────────── */
    uint64_t utramp_pa = (uint64_t)&u_trampoline & ~0xFFFULL;   /* Page-aligned */
    user_l3[16] = ((utramp_pa >> 12) << 10) | user_leaf_flags;  /* VA 0x00010000 → utramp page, U=1 */

    print_str("Page table built (4 pages, user code at PA ");
    print_hex64(utramp_pa);
    print_str(", mapped at VA 0x00010000, U=1).\n");
}

/* ─── S-mode trap handler ────────────────────────────────────────────
 * Called via stvec when U-mode ecalls.  Reports and returns via sret.
 * Uses __attribute__((interrupt("supervisor"))) so the compiler
 * generates sret and saves/restores all registers. */
__attribute__((interrupt("supervisor")))
void s_trap_handler(void) {
    uint64_t scause, sepc;
    asm volatile("csrr %0, scause" : "=r"(scause));
    asm volatile("csrr %0, sepc" : "=r"(sepc));

    if (scause == 8) {   /* ECALL from U-mode */
        uint64_t a7_val;
        asm volatile("mv %0, a7" : "=r"(a7_val));

        print_str("S-mode caught ecall from U-mode. a7=");
        print_hex64(a7_val);
        print_str("sepc=");
        print_hex64(sepc);

        /* Advance past the ecall instruction */
        asm volatile("csrw sepc, %0" :: "r"(sepc + 4));

        print_str("Level 6a Complete.\n");
    } else {
        print_str("S-mode unhandled trap! scause=");
        print_hex64(scause);
        print_str("sepc=");
        print_hex64(sepc);
        while (1) { asm volatile("wfi"); }
    }
}

/* ─── Main ────────────────────────────────────────────────────────────
 * 1) M-mode: set up PMP
 * 2) M-mode: build page table
 * 3) M-mode: enable SV39 MMU (safe — M-mode bypasses translation)
 * 4) M-mode: configure stvec + medeleg for ECALL_U → S-mode
 * 5) M-mode: drop to S-mode via mret
 * 6) S-mode: sret to U-mode at 0x00010000
 * 7) U-mode: print to UART via user page, ecall
 * 8) S-mode: catch ecall via stvec, print, done! */
int main(void) {
    print_str("Level 6a: S-mode → U-mode via sret\n");

    /* ── PMP: NAPOT covering all physical memory ── */
    asm volatile("csrw pmpaddr0, %0" :: "r"(0x3FFFFFFFFFFFFFULL));
    asm volatile("csrw pmpcfg0, %0" :: "r"(0x1FULL));

    /* ── Build page table (M-mode, MMU off) ── */
    build_page_table();

    /* ── Enable SV39 MMU (safe: M-mode bypasses translate_va) ── */
    uint64_t root_ppn = (uint64_t)pt_mem >> 12;
    uint64_t satp_val = (8ULL << 60) | root_ppn;
    asm volatile("csrw satp, %0" :: "r"(satp_val));
    asm volatile("sfence.vma");

    /* ── Configure S-mode trap delegation ── */
    asm volatile("csrw stvec, %0" :: "r"(&s_trap_handler));

    /* Delegate ECALL_U (cause 8) to S-mode */
    uint64_t medeleg_val;
    asm volatile("csrr %0, medeleg" : "=r"(medeleg_val));
    medeleg_val |= (1ULL << 8);
    asm volatile("csrw medeleg, %0" :: "r"(medeleg_val));

    print_str("stvec configured, medeleg[8]=1 for ECALL_U delegation.\n");

    /* ── Drop to S-mode via mret (same as 5a/5b/5c) ── */
    uint64_t mstatus;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus));
    print_str("mstatus before drop: ");
    print_hex64(mstatus);

    mstatus &= ~(3ULL << 11);
    mstatus |= (1ULL << 11);           /* MPP = S */
    asm volatile("csrw mstatus, %0" :: "r"(mstatus));

    /* Set mret target to S-mode main (at physical 0x80000000+offset;
     * M-mode doesn't translate, so physical PC is fine for mret). */
    extern void s_mode_main(void);
    asm volatile("csrw mepc, %0" :: "r"(&s_mode_main));

    print_str("mret into S-mode...\n");
    asm volatile("mret");

    print_str("ERROR: mret returned to M-mode!\n");
    while (1) { asm volatile("wfi"); }
    return 0;
}

/* ─── S-mode main ────────────────────────────────────────────────────
 * Called via mret from M-mode main().  By now we're in S-mode with
 * SV39 active.  Sets up the rest and srets to U-mode. */
void s_mode_main(void) {
    print_str("Now in S-mode (SV39 active).\n");

    /* ── Verify S-mode UART works through non-identity mapping ── */
    print_str("S-mode UART write via 0x50000000->0x10000000: OK\n");

    /* ── sret to U-mode ── */
    uint64_t sstatus;
    asm volatile("csrr %0, sstatus" : "=r"(sstatus));
    print_str("sstatus before sret: ");
    print_hex64(sstatus);

    sstatus &= ~(1ULL << 8);           /* SPP = 0 → U-mode          */
    sstatus |= (1ULL << 5);            /* SPIE = 1 → enable SIE on sret */
    sstatus |= (1ULL << 1);            /* SIE = 1 (already set)     */
    asm volatile("csrw sstatus, %0" :: "r"(sstatus));

    /* sepc = user trampoline virtual address */
    asm volatile("csrw sepc, %0" :: "r"((uint64_t)USER_CODE_VA));

    print_str("sret to U-mode at VA 0x00010000...\n");
    print_str("(expect: U-mode prints 'U', ecalls, S-mode catches it)\n");
    asm volatile("sret");

    /* Shouldn't reach here — user ecalls back to s_trap_handler */
    print_str("ERROR: sret returned to S-mode without ecall!\n");
    while (1) { asm volatile("wfi"); }
}
