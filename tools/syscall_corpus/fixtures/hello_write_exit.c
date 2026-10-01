/* fixture: hello_write_exit — smallest meaningful corpus entry.
 * Exercises: write(64), exit(93). Ground truth: qemu -strace line-per-syscall.
 * _start is pure inline-asm-friendly (no libc prologue): entry ABI is bare.
 */
typedef unsigned long ulong;

static long sys3(long n, long a0, long a1, long a2) {
    register long r_a0 asm("a0") = a0;
    register long r_a1 asm("a1") = a1;
    register long r_a2 asm("a2") = a2;
    register long r_a7 asm("a7") = n;
    asm volatile("ecall"
                 : "+r"(r_a0)
                 : "r"(r_a1), "r"(r_a2), "r"(r_a7)
                 : "memory");
    return r_a0;
}

void _start(void) {
    const char msg[] = "hello glyph\n";
    /* write(1, msg, sizeof(msg)-1) */
    sys3(64, 1, (ulong)msg, sizeof(msg) - 1);
    /* exit(7) — non-zero so a stuck exit path is visible in traces */
    sys3(93, 7, 0, 0);
    for (;;)
        ;
}
