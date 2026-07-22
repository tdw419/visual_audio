#include <stdint.h>

#define UART_BASE 0x10000000
volatile uint8_t *uart = (uint8_t *)UART_BASE;

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

/* Any trap while in S-mode without delegation lands here in M-mode.
 * We use this purely as a safety net / observability tool: if the
 * privilege-drop or a CSR access misbehaves, we see exactly what
 * trapped instead of the GPU silently hanging or corrupting state. */
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

    /* Skip past the faulting instruction (assume 4-byte, non-compressed)
     * so a deliberately-illegal CSR read doesn't just refault forever. */
    asm volatile("csrw mepc, %0" :: "r"(mepc + 4));
}

/* Entered via `mret` with mstatus.MPP = S, so this body executes with
 * priv_mode == PRIV_S (1), not PRIV_M (3). Never returns - execution
 * ends in the wfi loop at the bottom. */
void s_mode_entry(void) {
    print_str("Now executing in S-mode.\n");

    print_str("UART MMIO write from S-mode: OK (you're reading this)\n");

    /* sstatus is the S-mode-legal alias of mstatus - this read should
     * succeed under the emulator's CSR privilege gating. */
    uint64_t sstatus;
    asm volatile("csrr %0, sstatus" : "=r"(sstatus));
    print_str("sstatus (S-mode read, should succeed): ");
    print_hex64(sstatus);

    /* mstatus itself is M-mode-only. From S-mode this must trap illegal
     * instruction (cause 2) if the emulator's privilege gating actually
     * works - this is the real thing 5a is testing. */
    print_str("Attempting to read mstatus from S-mode (expect trap)...\n");
    uint64_t mstatus_from_s;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus_from_s));
    print_str("If you see this, the read did NOT trap: ");
    print_hex64(mstatus_from_s);

    print_str("trap_count after mstatus read: ");
    print_hex64((uint64_t)trap_count);

    print_str("Level 5a Complete.\n");

    while (1) {
        asm volatile("wfi");
    }
}

int main() {
    print_str("Level 5a: Privilege Escalation M -> S\n");

    /* With zero PMP regions configured, M-mode has implicit full memory
     * access but S/U-mode have NONE by default (RISC-V priv spec) - any
     * S-mode fetch/load/store would instruction/load/store-access-fault
     * immediately. Open one NAPOT region covering all of physical memory
     * with R/W/X so S-mode can actually run. */
    asm volatile("csrw pmpaddr0, %0" :: "r"(0x3FFFFFFFFFFFFFULL));
    asm volatile("csrw pmpcfg0, %0" :: "r"(0x1FULL)); /* A=NAPOT(3<<3), R|W|X */

    uint64_t mstatus;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus));
    print_str("mstatus before drop: ");
    print_hex64(mstatus);

    /* MPP lives in mstatus[12:11]. Clear it, then set to S (1). */
    mstatus &= ~(3ULL << 11);
    mstatus |= (1ULL << 11);
    asm volatile("csrw mstatus, %0" :: "r"(mstatus));

    /* mepc is where mret will jump; set it to the S-mode entry point. */
    asm volatile("csrw mepc, %0" :: "r"(&s_mode_entry));

    print_str("Executing mret into S-mode...\n");
    asm volatile("mret");

    /* Unreachable: mret never returns here. */
    print_str("ERROR: mret returned to M-mode code, privilege drop failed!\n");
    while (1) {
        asm volatile("wfi");
    }
}
