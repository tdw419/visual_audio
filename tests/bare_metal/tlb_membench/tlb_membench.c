/*
 * tlb_membench.c — synthetic RV64I memory-path benchmark for the GPU emulator.
 *
 * Purpose: isolate the TLB / Sv39-walk / Hilbert-memory cost cleanly, WITHOUT
 * hunting through the Alpine boot trace. The host harness (tools/tlb_membench.py)
 * pre-populates an SV39 identity page table at 0x80400000; this program enables
 * satp (SV39), mret's into S-mode, then hammers a working set of W pages with
 * the selected access type:
 *
 *   -D ACCESS=ALU   register-only arithmetic loop (execute-path baseline)
 *   -D ACCESS=LOAD  one 64-bit load per page, accumulate
 *   -D ACCESS=STORE one 64-bit store per page
 *
 * Compile with -DW=<pages> (default 128) — the host measures steps/s and reads
 * the shader's tlb_hits/tlb_misses counters, so the guest never halts; the host
 * stops it at max_steps. R is deliberately huge.
 *
 * Build (see build.sh):
 *   riscv64-linux-gnu-gcc -march=rv64imac -mabi=lp64 -nostdlib -static -O2 \
 *       -DACCESS=LOAD -DW=128 -DR=1000000 -Ttext=0x80000000 -o tlb_bench_ld.elf
 */
#define ROOT_PT  0x80400000UL   /* host pre-populates Sv39 root table here      */
#define WORK_BASE 0x81000000UL  /* working-set region (identity-mapped)         */
#define PAGE_SIZE 4096UL
#define SYSCON_ADDR 0x11100000UL
#define UART_ADDR   0x10000000UL

#ifndef W
#define W 128
#endif
#ifndef R
#define R 1000000UL
#endif

#define STR2(x) #x
#define STR(x) STR2(x)

static void uart_write(char c) {
    volatile char *uart = (volatile char *)UART_ADDR;
    *uart = c;
}

static void uart_str(const char *s) {
    while (*s) uart_write(*s++);
}

__attribute__((noreturn)) void _s_main(void);

__attribute__((noreturn)) void _start(void) {
    /* Stack for safety (no calls in the hot loop, but keep it valid). */
    asm volatile("li sp, 0x83FFF000");

    /* Enable Sv39 with the host-pre-populated identity root. */
    unsigned long satp = (8UL << 60) | (ROOT_PT >> 12);
    asm volatile("csrw satp, %0" :: "r"(satp));

    /* mret into S-mode (mstatus.MPP = S). */
    unsigned long mstatus;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus));
    mstatus = (mstatus & ~(3UL << 11)) | (1UL << 11);
    asm volatile("csrw mstatus, %0" :: "r"(mstatus));
    asm volatile("csrw mepc, %0" :: "r"((unsigned long)_s_main));
    asm volatile("mret");
    for (;;) { /* not reached */ }
}

__attribute__((noreturn)) void _s_main(void) {
    volatile unsigned long *p;
    unsigned long i, pass;
    unsigned long acc = 0;

    uart_str("tlb_membench ACCESS="
#ifdef ACCESS_ALU
             "ALU"
#endif
#ifdef ACCESS_LOAD
             "LOAD"
#endif
#ifdef ACCESS_STORE
             "STORE"
#endif
             " W=" STR(W) "\r\n");

    for (pass = 0; pass < R; pass++) {
        for (i = 0; i < W; i++) {
#ifdef ACCESS_ALU
            /* Pure register work: no memory, no translate. */
            acc = acc + i;
            acc = acc ^ (i << 3);
            acc = acc - (i >> 1);
            acc = acc * 3UL;
#elif defined(ACCESS_LOAD)
            p = (volatile unsigned long *)(WORK_BASE + i * PAGE_SIZE);
            acc += *p;
#elif defined(ACCESS_STORE)
            p = (volatile unsigned long *)(WORK_BASE + i * PAGE_SIZE);
            *p = acc + i;
#endif
        }
    }

    uart_str("tlb_membench done acc=");
    /* Emit acc as hex so the compiler can't sink the loop. */
    char buf[20];
    for (int sh = 60; sh >= 0; sh -= 4) {
        buf[(60 - sh) / 4] = "0123456789abcdef"[(acc >> sh) & 0xF];
    }
    buf[16] = '\r';
    buf[17] = '\n';
    for (int k = 0; k < 18; k++) uart_write(buf[k]);

    /* syscon poweroff -> emulator halts. */
    *(volatile unsigned long *)SYSCON_ADDR = 0x5555UL;
    for (;;) { }
}
