/* probe_main.c — bare-metal RV64 inflate probe.
 *
 * Reproduces the kernel's initramfs gzip path (lib/decompress_inflate.c
 * __gunzip with flush=flush_buffer) as a standalone RV64 program so the same
 * ELF runs on BOTH the GPU emulator and QEMU (golden reference).
 *
 * Prints over UART (0x10000000):
 *   - input region checksum (verifies the memory READ path delivers the same
 *     bytes the loader wrote)
 *   - inflate return code, total_out, avail_in after stream end, adler
 *   - a rolling checksum of the decompressed output (byte-identity check)
 *
 * The kernel's "broken padding" error is emitted by the CPIO parser
 * (init/initramfs.c do_reset) when, after eating NUL padding, bytes remain
 * at a non-4-aligned header offset. That only happens if the decompressed
 * stream is truncated/corrupted/misaligned — so this probe's output length
 * + checksum + adler tell us whether the inflate itself diverges.
 *
 * Built for rv64imac_zicsr, linked at 0x80000000. _start sets sp, calls main.
 */
#include <stddef.h>

typedef unsigned long ulg;
typedef unsigned int uInt;
typedef unsigned char Byte;

/* ---- minimal UART + syscon ---- */
#define UART_ADDR   0x10000000UL
#define SYSCON_ADDR 0x11100000UL

static void uart_write(char c) {
    volatile char *uart = (volatile char *)UART_ADDR;
    *uart = c;
}

static void uart_str(const char *s) {
    while (*s) uart_write(*s++);
}

static void uart_hex64(unsigned long v) {
    char buf[20];
    int i;
    uart_str("0x");
    for (i = 15; i >= 0; i--) {
        unsigned nib = (v >> (i * 4)) & 0xF;
        buf[15 - i] = nib < 10 ? '0' + nib : 'a' + nib - 10;
    }
    buf[16] = '\0';
    uart_str(buf);
}

static void uart_hex32(unsigned int v) {
    char buf[12];
    int i;
    uart_str("0x");
    for (i = 7; i >= 0; i--) {
        unsigned nib = (v >> (i * 4)) & 0xF;
        buf[7 - i] = nib < 10 ? '0' + nib : 'a' + nib - 10;
    }
    buf[8] = '\0';
    uart_str(buf);
}

static void uart_dec(unsigned long v) {
    char buf[24];
    int i = 23;
    buf[i--] = '\0';
    if (v == 0) buf[i--] = '0';
    while (v) { buf[i--] = '0' + (v % 10); v /= 10; }
    uart_str(&buf[i + 1]);
}

static void uart_newline(void) { uart_write('\r'); uart_write('\n'); }

/* simple FNV-1a 64-bit rolling checksum */
static unsigned long fnv1a(const unsigned char *p, unsigned long n) {
    unsigned long h = 0xcbf29ce484222325UL;
    while (n--) { h ^= *p++; h *= 0x100000001b3UL; }
    return h;
}

/* ---- the kernel's zlib_inflate (copied verbatim) ---- */
#include "linux/zlib.h"
#include "linux/zutil.h"
#include "inflate.h"
#include "inftrees.h"
#include "inffast.h"
#include "infutil.h"

/* workspace for zlib_inflateInit2: inflate_state + 32KB window */
static struct inflate_workspace g_ws __attribute__((aligned(8)));
static z_stream g_strm;

/* output sink state */
static unsigned long g_out_total = 0;
static unsigned long g_out_limit = 12UL * 1024 * 1024;
static unsigned char *g_out_base = 0;

extern unsigned char initrd_gz_start[];
extern unsigned char initrd_gz_end[];
extern unsigned char small_gz_start[];
extern unsigned char small_gz_end[];
extern unsigned char probe_out_buf[];
extern unsigned char small_out_buf[];

/* 32KB flush chunk, exactly like the kernel's __gunzip(flush) path:
 * inflate writes into a 32KB scratch; each time it fills, the flush
 * callback copies it to the sink. This exercises the window-copy /
 * cross-chunk LZ77 path the real boot uses (wsize stays 32768). */
#define FLUSH_CHUNK 0x8000
static unsigned char g_flush_buf[FLUSH_CHUNK];

static long probe_flush(void *buf, unsigned long len) {
    unsigned long copy = len;
    const unsigned char *src = (const unsigned char *)buf;
    unsigned char *dst;
    unsigned long i;
    if (g_out_total + copy > g_out_limit)
        copy = g_out_limit - g_out_total;
    dst = g_out_base + g_out_total;
    for (i = 0; i < copy; i++) dst[i] = src[i];
    g_out_total += copy;
    return (long)copy;
}

/* Replicates __gunzip()'s loop (flush mode) with a 32KB flush chunk,
 * matching the kernel's real initramfs path byte-for-byte.
 * Returns: 0 == Z_STREAM_END reached cleanly, -1 == error. */
static int run_gunzip(const unsigned char *zbuf, long len,
                      unsigned char *out_base, unsigned long out_limit) {
    int rc;
    long fill_rc;

    g_out_base = out_base;
    g_out_limit = out_limit;
    g_out_total = 0;

    /* verify gzip header */
    if (len < 10 || zbuf[0] != 0x1f || zbuf[1] != 0x8b || zbuf[2] != 0x08) {
        uart_str("ERR: not gzip\r\n");
        return -1;
    }

    g_strm.next_in = (const Byte *)(zbuf + 10);
    g_strm.avail_in = (uLong)(len - 10);

    /* skip asciz filename if FNAME set */
    if (zbuf[3] & 0x8) {
        while (g_strm.avail_in && *g_strm.next_in) {
            g_strm.avail_in--;
            g_strm.next_in++;
        }
        if (g_strm.avail_in) { g_strm.avail_in--; g_strm.next_in++; }
    }

    g_strm.next_out = g_flush_buf;
    g_strm.avail_out = FLUSH_CHUNK;
    g_strm.workspace = &g_ws;

    rc = zlib_inflateInit2(&g_strm, -MAX_WBITS);  /* raw deflate, like kernel */
    if (rc != Z_OK) {
        uart_str("ERR: inflateInit2 rc="); uart_dec(rc); uart_newline();
        return -1;
    }

    /* kernel's no-flush branch zeroes window; the boot path uses flush, so we
     * keep the window enabled to exercise the same memcpy path. */

    while (rc == Z_OK) {
        if (g_strm.avail_in == 0) {
            /* nofill like the kernel (fill=NULL): no more input available */
            fill_rc = -1;
            if (fill_rc < 0) {
                uart_str("ERR: read error (avail_in hit 0)\r\n");
                return -1;
            }
        }
        rc = zlib_inflate(&g_strm, 0);

        /* flush any produced bytes (kernel's flush_buffer semantics) */
        if (g_strm.next_out > g_flush_buf) {
            long l = (long)(g_strm.next_out - g_flush_buf);
            if (l != probe_flush(g_flush_buf, l)) {
                uart_str("ERR: write error\r\n");
                return -1;
            }
            g_strm.next_out = g_flush_buf;
            g_strm.avail_out = FLUSH_CHUNK;
        }

        if (rc == Z_STREAM_END) {
            rc = 0;
            break;
        } else if (rc != Z_OK) {
            uart_str("ERR: inflate rc="); uart_dec(rc); uart_newline();
            return -1;
        }
    }

    return rc;
}

static void run_case(const char *name,
                     const unsigned char *gz_start, const unsigned char *gz_end,
                     unsigned char *out_buf, unsigned long out_limit) {
    unsigned long in_len = (unsigned long)(gz_end - gz_start);
    unsigned long in_cksum;
    int rc;

    uart_str("--- "); uart_str(name); uart_str(" ---\r\n");
    uart_str("gzip bytes: ");
    uart_dec(in_len);
    uart_newline();

    /* checksum the INPUT region as seen through the emulator's read path */
    in_cksum = fnv1a(gz_start, in_len);
    uart_str("input fnv1a: ");
    uart_hex64(in_cksum);
    uart_newline();

    rc = run_gunzip(gz_start, (long)in_len, out_buf, out_limit);

    uart_str("inflate rc: ");
    uart_dec(rc);
    uart_newline();
    uart_str("total_out: ");
    uart_dec(g_out_total);
    uart_newline();
    uart_str("total_in: ");
    uart_dec(g_strm.total_in);
    uart_newline();
    uart_str("avail_in after: ");
    uart_dec(g_strm.avail_in);
    uart_newline();
    uart_str("adler: ");
    uart_hex32((unsigned int)g_strm.adler);
    uart_newline();

    if (g_out_total > 0) {
        uart_str("out fnv1a: ");
        uart_hex64(fnv1a(out_buf, g_out_total));
        uart_newline();
        uart_str("out[0..7]: ");
        uart_hex64(*(unsigned long *)out_buf);
        uart_newline();
        uart_str("out[-8..]: ");
        uart_hex64(*(unsigned long *)(out_buf + g_out_total - 8));
        uart_newline();
    }
}

void main(void) {
    uart_str("\r\n=== RV64 INFLATE PROBE ===\r\n");

    /* fast small payload first */
    run_case("small", small_gz_start, small_gz_end,
             small_out_buf, 256 * 1024);

    /* then the real Alpine initrd (large) */
    run_case("initrd", initrd_gz_start, initrd_gz_end,
             probe_out_buf, 12 * 1024 * 1024);

    uart_str("=== PROBE DONE ===\r\n");

    /* syscon poweroff -> emulator halts; QEMU also honors this on virt */
    *(volatile unsigned long *)SYSCON_ADDR = 0x5555UL;
    for (;;) { }
}
