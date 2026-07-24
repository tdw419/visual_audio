#include <stdint.h>

#define UART_BASE      0x10000000UL
#define CLINT_MTIME    0x0200bff8UL
#define CLINT_MTIMECMP 0x02004000UL

volatile uint8_t *uart = (uint8_t *)UART_BASE;

/* Delta (in mtime ticks) between now and the scheduled interrupt. The
 * emulator advances mtime by 1 per instruction dispatch, so this just
 * needs to be comfortably larger than the instruction count in the
 * spin loop below. */
#define TIMER_DELTA 5000UL

#define SBI_EXT_TIME 0x54494D45UL

volatile int trap_count = 0;
volatile uint64_t last_scause = 0xFFFFFFFFFFFFFFFFULL;
volatile int timer_fired = 0;

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

/* M-mode trap handler. On real hardware an S-mode `ecall` is a genuine
 * trap to M-mode (cause 9) that must be serviced by SBI firmware - there
 * is no OpenSBI here, so this function IS the firmware for the one SBI
 * call this test needs (sbi_set_timer). */
void c_trap_handler(void) {
    uint64_t mcause, mepc;
    asm volatile("csrr %0, mcause" : "=r"(mcause));
    asm volatile("csrr %0, mepc" : "=r"(mepc));

    if (mcause == 0x8000000000000007ULL) { /* Machine timer interrupt (MTIP) */
        /* There is no hardware path from MTIP to STIP - mideleg does not
         * apply to the machine timer at all (it only ever sets MTIP).
         * Real SBI firmware must catch this in M-mode and manually relay
         * it to S-mode by setting sip.STIP, then mask mie.MTIE so MTIP
         * (which stays pending until mtimecmp is rewritten) doesn't
         * immediately re-trap M-mode on the way back down. */
        asm volatile("csrc mie, %0" :: "r"(1UL << 7));
        asm volatile("csrs mip, %0" :: "r"(1UL << 5));
        return; /* mepc is already correct for an async interrupt - no +4 */
    }

    if (mcause == 9) { /* ECALL from S-mode */
        uint64_t a7, a6, a0;
        asm volatile("mv %0, a7" : "=r"(a7));
        asm volatile("mv %0, a6" : "=r"(a6));
        asm volatile("mv %0, a0" : "=r"(a0));

        if (a7 == SBI_EXT_TIME && a6 == 0) { /* sbi_set_timer */
            volatile uint32_t *mtimecmp = (volatile uint32_t *)CLINT_MTIMECMP;
            mtimecmp[0] = (uint32_t)(a0 & 0xFFFFFFFFu);
            mtimecmp[1] = (uint32_t)(a0 >> 32);
            /* STIP is read-only through sip - only M-mode can clear it
             * (via mip). Real SBI rearms the timer AND clears STIP in
             * the same call, which is exactly what real xv6/OpenSBI
             * rely on: S-mode never clears STIP itself, it just calls
             * sbi_set_timer again to ask for the next tick. */
            asm volatile("csrc mip, %0" :: "r"(1UL << 5));
            asm volatile("csrs mie, %0" :: "r"(1UL << 7)); /* re-arm MTIE */
            asm volatile("li a0, 0"); /* SBI_SUCCESS */
        }
        asm volatile("csrw mepc, %0" :: "r"(mepc + 4));
        return;
    }

    print_str("M-mode TRAP! mcause=");
    print_hex64(mcause);
    print_str("            mepc=");
    print_hex64(mepc);
    asm volatile("csrw mepc, %0" :: "r"(mepc + 4));
}

/* S-mode trap handler - catches the supervisor timer interrupt
 * (scause=5, with the interrupt bit set: 0x8000000000000005). */
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

    if (scause == 0x8000000000000005ULL) { /* Supervisor timer interrupt */
        print_str("  -> Supervisor Timer Interrupt confirmed.\n");
        timer_fired = 1;

        /* STIP is read-only through sip - S-mode can't clear it itself.
         * Ask M-mode (via SBI, same as scheduling any other tick) to
         * rearm mtimecmp far into the future, which is where the real
         * STIP-clearing (via mip) actually happens. */
        register uint64_t a7 asm("a7") = SBI_EXT_TIME;
        register uint64_t a6 asm("a6") = 0;
        register uint64_t a0 asm("a0") = 0xFFFFFFFFFFFFFFFFULL;
        asm volatile("ecall" : "+r"(a0) : "r"(a7), "r"(a6));
    } else {
        print_str("  UNEXPECTED scause, halting.\n");
        while (1) { asm volatile("wfi"); }
    }
}

void s_mode_main(void) {
    print_str("Now in S-mode (no MMU - identity physical addressing).\n");

    asm volatile("csrw stvec, %0" :: "r"(&s_trap_handler));

    /* Enable STIE (sie bit 5) and SIE (sstatus bit 1). */
    asm volatile("csrs sie, %0" :: "r"(1UL << 5));
    asm volatile("csrs sstatus, %0" :: "r"(1UL << 1));

    volatile uint32_t *mtime = (volatile uint32_t *)CLINT_MTIME;
    uint64_t now = ((uint64_t)mtime[1] << 32) | mtime[0];
    print_str("Current mtime: ");
    print_hex64(now);

    uint64_t target = now + TIMER_DELTA;
    print_str("Scheduling timer via SBI at: ");
    print_hex64(target);

    register uint64_t a7 asm("a7") = SBI_EXT_TIME;
    register uint64_t a6 asm("a6") = 0; /* fid = sbi_set_timer */
    register uint64_t a0 asm("a0") = target;
    asm volatile("ecall" : "+r"(a0) : "r"(a7), "r"(a6));

    print_str("Timer scheduled. Spinning on wfi until it fires...\n");

    int spins = 0;
    while (!timer_fired) {
        asm volatile("wfi");
        spins++;
        /* On real hardware `wfi` genuinely blocks until the interrupt, so
         * this loop iterates once or twice. On the GPU emulator `wfi` is
         * a NOP (no interrupt-wake modeling yet), so this spins through
         * real instruction dispatch until mtime reaches the target -
         * needs enough headroom for that, not just a hardware sanity cap. */
        if (spins > 1000000) {
            print_str("FAIL: timer did not fire after many wfi spins.\n");
            while (1) { asm volatile("wfi"); }
        }
    }

    print_str("PASS: timer_fired=1, trap_count=");
    print_hex64((uint64_t)trap_count);
    print_str("Level 7a Complete.\n");

    while (1) { asm volatile("wfi"); }
}

int main(void) {
    print_str("Level 7a: Timer Interrupt (mtime/mtimecmp -> STIP -> S-mode)\n");

    /* PMP: NAPOT covering all physical memory (S-mode convention from
     * Level 5a onward, even though this emulator doesn't yet enforce
     * PMP on the no-MMU physical path). */
    asm volatile("csrw pmpaddr0, %0" :: "r"(0x3FFFFFFFFFFFFFULL));
    asm volatile("csrw pmpcfg0, %0" :: "r"(0x1FULL));

    /* Delegate the supervisor timer interrupt (bit 5) so STIP traps
     * directly to stvec without M-mode intervention. */
    uint64_t mideleg_val;
    asm volatile("csrr %0, mideleg" : "=r"(mideleg_val));
    mideleg_val |= (1ULL << 5);
    asm volatile("csrw mideleg, %0" :: "r"(mideleg_val));

    /* mtimecmp defaults to 0 at reset, which is already <= mtime the
     * instant execution starts - disarm it first so enabling mie.MTIE
     * below doesn't immediately consume a spurious timer interrupt
     * before the real SBI-scheduled one ever gets a chance. */
    volatile uint32_t *mtimecmp_init = (volatile uint32_t *)CLINT_MTIMECMP;
    mtimecmp_init[0] = 0xFFFFFFFFu;
    mtimecmp_init[1] = 0xFFFFFFFFu;

    /* Enable the machine timer interrupt so M-mode actually receives
     * MTIP while the CPU is executing in S-mode (M-level interrupts
     * always preempt lower privilege modes regardless of mstatus.MIE -
     * only mie.MTIE gates them). */
    asm volatile("csrs mie, %0" :: "r"(1UL << 7));

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
