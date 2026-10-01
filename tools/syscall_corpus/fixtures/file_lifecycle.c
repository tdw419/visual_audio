/* fixture: file_lifecycle — openat/write/fsync/close/openat+read/close/unlinkat/exit_group.
 * Semantic ground truth for POSIX-shim ordering tests (cf. test_gh21_posix_shim.py):
 *   create -> write -> fsync -> close -> reopen+read -> verify -> unlink.
 * All raw syscalls (no libc): AT_FDCWD=-100, O_CREAT|O_WRONLY|O_TRUNC=0x241,
 * O_RDONLY=0, mode 0644.
 * Every call goes through sys4 with exactly 4 args (pad with 0) — no arity drift.
 */
typedef unsigned long ulong;
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

#define SYS_openat 56
#define SYS_close 57
#define SYS_read 63
#define SYS_write 64
#define SYS_fsync 82
#define SYS_unlinkat 35
#define SYS_exit_group 94
#define SYS_brk 214

static slong slen(const char *s) {
    slong n = 0;
    while (s[n])
        n++;
    return n;
}

void _start(void) {
    const char path[] = "corpus_file.bin";
    const char payload[] = "PXC1-persist-0123456789";
    const char ok[] = "OK\n";
    const char no[] = "BAD\n";
    const char err[] = "ERR\n";
    char rbuf[32];
    slong fd, n, i, bad;

    /* openat(AT_FDCWD, path, O_CREAT|O_WRONLY|O_TRUNC, 0644) */
    fd = sys4(SYS_openat, -100, (slong)path, 0x241, 0644);
    if (fd < 0)
        goto fail;

    /* write(fd, payload, len) */
    n = sys4(SYS_write, fd, (slong)payload, slen(payload), 0);
    if (n != (slong)slen(payload))
        goto fail;

    /* fsync(fd) */
    if (sys4(SYS_fsync, fd, 0, 0, 0) != 0)
        goto fail;

    /* close(fd) */
    if (sys4(SYS_close, fd, 0, 0, 0) != 0)
        goto fail;

    /* openat(AT_FDCWD, path, O_RDONLY, 0) */
    fd = sys4(SYS_openat, -100, (slong)path, 0, 0);
    if (fd < 0)
        goto fail;

    /* read(fd, rbuf, sizeof(rbuf)) */
    n = sys4(SYS_read, fd, (slong)rbuf, (slong)sizeof(rbuf), 0);
    if (n != (slong)slen(payload))
        goto fail;

    bad = 0;
    for (i = 0; i < slen(payload); i++)
        bad |= (rbuf[i] != payload[i]);

    sys4(SYS_close, fd, 0, 0, 0);

    /* unlinkat(AT_FDCWD, path, 0) */
    if (sys4(SYS_unlinkat, -100, (slong)path, 0, 0) != 0)
        goto fail;

    /* brk probe: in-place extension; QEMU handles without tracing */
    sys4(SYS_brk, 0, 0, 0, 0);

    if (bad) {
        sys4(SYS_write, 1, (slong)no, 3, 0);
        sys4(SYS_exit_group, 9, 0, 0, 0);
    } else {
        sys4(SYS_write, 1, (slong)ok, 3, 0);
        sys4(SYS_exit_group, 0, 0, 0, 0);
    }

fail:
    sys4(SYS_write, 1, (slong)err, 4, 0);
    sys4(SYS_exit_group, 1, 0, 0, 0);
    for (;;)
        ;
}
