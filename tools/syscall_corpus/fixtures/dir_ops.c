/* fixture: dir_ops — mkdirat/rename/unlinkat(AT_REMOVEDIR) on RV64.
 * Pins asm-generic syscall numbers (mkdirat=34, renameat=38, renameat2=276,
 * unlinkat=35) and directory semantics for the glyph POSIX-shim layer.
 *
 * MEASURED FINDING (2026-09-16, qemu-riscv64-static 8.2.2 / Ubuntu
 * 1:8.2.2+ds-0ubuntu1.18): syscall 38 (renameat) is UNIMPLEMENTED — QEMU
 * prints "Unknown syscall 38" and returns -ENOSYS. The fixture treats that
 * as the documented trigger for the renameat2(276) fallback, mirroring what
 * glibc's mv(1) does on real kernels (see corpus rename_probe record).
 *
 * AT_FDCWD=-100, AT_REMOVEDIR=0x200.
 */
typedef long slong;

static long sys4(long n, slong a0, slong a1, slong a2, slong a3) {
    register long r_a0 asm("a0") = a0;
    register long r_a1 asm("a1") = a1;
    register long r_a2 asm("a2") = a2;
    register long r_a3 asm("a3") = a3;
    register long r_a7 asm("a7") = n;
    asm volatile("ecall"
                 : "+r"(r_a0)
                 : "r"(r_a1), "r"(r_a2), "r"(r_a3), "r"(r_a7)
                 : "memory");
    return r_a0;
}

#define SYS_mkdirat 34
#define SYS_unlinkat 35
#define SYS_renameat 38
#define SYS_renameat2 276
#define SYS_write 64
#define SYS_exit_group 94

static long sys5(long n, slong a0, slong a1, slong a2, slong a3, slong a4) {
    register long r_a0 asm("a0") = a0;
    register long r_a1 asm("a1") = a1;
    register long r_a2 asm("a2") = a2;
    register long r_a3 asm("a3") = a3;
    register long r_a4 asm("a4") = a4;
    register long r_a7 asm("a7") = n;
    asm volatile("ecall"
                 : "+r"(r_a0)
                 : "r"(r_a1), "r"(r_a2), "r"(r_a3), "r"(r_a4), "r"(r_a7)
                 : "memory");
    return r_a0;
}

void _start(void) {
    const char d1[] = "d1";
    const char d2[] = "d2";
    const char ok[] = "OK\n";
    const char err[] = "ERR\n";

    if (sys4(SYS_mkdirat, -100, (slong)d1, 0755, 0) != 0)
        goto fail;

    /* rename d1 -> d2: try renameat(38); on -ENOSYS (qemu-user gap) fall
     * back to renameat2(276) with flags=0 EXPLICIT in a4 (5-arg ABI —
     * relying on a4's stale value is a latent landmine). */
    if (sys4(SYS_renameat, -100, (slong)d1, -100, (slong)d2) != 0) {
        if (sys5(SYS_renameat2, -100, (slong)d1, -100, (slong)d2, 0) != 0)
            goto fail;
    }

    if (sys4(SYS_unlinkat, -100, (slong)d2, 0x200, 0) != 0)  /* AT_REMOVEDIR */
        goto fail;

    sys4(SYS_write, 1, (slong)ok, 3, 0);
    sys4(SYS_exit_group, 0, 0, 0, 0);

fail:
    sys4(SYS_write, 1, (slong)err, 4, 0);
    sys4(SYS_exit_group, 1, 0, 0, 0);
    for (;;)
        ;
}
