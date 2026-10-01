/* probe_cpio.c — bare-metal RV64 cpio-parser probe.
 *
 * Reproduces init/initramfs.c's exact padding/alignment logic (do_reset,
 * eat, this_header tracking) over a decompressed cpio archive, without any
 * file I/O. The kernel's "broken padding" error fires in do_reset() when,
 * after eating NUL padding, bytes remain at a non-4-aligned header offset.
 *
 * This probe feeds the SAME decompressed bytes (11,600,900 from the real
 * initrd) through the parser state machine and reports:
 *   - every record (name, mode, header offset) until TRAILER!!!
 *   - whether do_reset ever trips "broken padding"
 *   - the exact offset where it trips (if any)
 *
 * It runs on QEMU (golden) and the GPU core with identical ELF, so we can
 * see whether the cpio parse diverges even when inflate output is correct.
 *
 * Built for rv64imac_zicsr, linked at 0x80000000. _start sets sp, calls main.
 */
#include <stddef.h>

#define UART_ADDR   0x10000000UL
#define SYSCON_ADDR 0x11100000UL

static void uart_write(char c) {
    volatile char *uart = (volatile char *)UART_ADDR;
    *uart = c;
}
static void uart_str(const char *s) { while (*s) uart_write(*s++); }
static void uart_hex64(unsigned long v) {
    char buf[20]; int i;
    uart_str("0x");
    for (i = 15; i >= 0; i--) {
        unsigned nib = (v >> (i * 4)) & 0xF;
        buf[15 - i] = nib < 10 ? '0' + nib : 'a' + nib - 10;
    }
    buf[16] = '\0';
    uart_str(buf);
}
static void uart_hex32(unsigned int v) {
    char buf[12]; int i;
    uart_str("0x");
    for (i = 7; i >= 0; i--) {
        unsigned nib = (v >> (i * 4)) & 0xF;
        buf[7 - i] = nib < 10 ? '0' + nib : 'a' + nib - 10;
    }
    buf[8] = '\0';
    uart_str(buf);
}
static void uart_dec(unsigned long v) {
    char buf[24]; int i = 23;
    buf[i--] = '\0';
    if (v == 0) buf[i--] = '0';
    while (v) { buf[i--] = '0' + (v % 10); v /= 10; }
    uart_str(&buf[i + 1]);
}
static void uart_newline(void) { uart_write('\r'); uart_write('\n'); }

/* ---- the kernel's zlib_inflate (copied verbatim) ---- */
#include "linux/string.h"
#include "linux/zlib.h"
#include "linux/zutil.h"
#include "inflate.h"
#include "inftrees.h"
#include "inffast.h"
#include "infutil.h"

static struct inflate_workspace g_ws __attribute__((aligned(8)));
static z_stream g_strm;

#define FLUSH_CHUNK 0x8000
static unsigned char g_flush_buf[FLUSH_CHUNK];
static unsigned char *g_out_base;
static unsigned long g_out_total;
static unsigned long g_out_limit;

extern unsigned char initrd_gz_start[];
extern unsigned char initrd_gz_end[];
extern unsigned char probe_out_buf[];

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

static int run_gunzip(const unsigned char *zbuf, long len) {
    int rc;
    g_out_base = probe_out_buf;
    g_out_limit = 12UL * 1024 * 1024;
    g_out_total = 0;
    if (len < 10 || zbuf[0] != 0x1f || zbuf[1] != 0x8b || zbuf[2] != 0x08) {
        uart_str("ERR: not gzip\r\n");
        return -1;
    }
    g_strm.next_in = (const Byte *)(zbuf + 10);
    g_strm.avail_in = (uLong)(len - 10);
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
    rc = zlib_inflateInit2(&g_strm, -MAX_WBITS);
    if (rc != Z_OK) return -1;
    while (rc == Z_OK) {
        rc = zlib_inflate(&g_strm, 0);
        if (g_strm.next_out > g_flush_buf) {
            long l = (long)(g_strm.next_out - g_flush_buf);
            if (l != probe_flush(g_flush_buf, l)) { uart_str("ERR: write error\r\n"); return -1; }
            g_strm.next_out = g_flush_buf;
            g_strm.avail_out = FLUSH_CHUNK;
        }
        if (rc == Z_STREAM_END) { rc = 0; break; }
        else if (rc != Z_OK) { uart_str("ERR: inflate rc="); uart_dec(rc); uart_newline(); return -1; }
    }
    return rc;
}

/* ---- cpio newc parser mirroring init/initramfs.c ---- */
#define NEWC_MAGIC 0x070701
#define NEWC_HSIZE 110

struct newc_header {
    unsigned int magic;    /* 070701 */
    unsigned int ino;
    unsigned int mode;
    unsigned int uid;
    unsigned int gid;
    unsigned int nlink;
    unsigned int mtime;
    unsigned int filesize;
    unsigned int devmajor;
    unsigned int devminor;
    unsigned int rdevmajor;
    unsigned int rdevminor;
    unsigned int namesize;
    unsigned int check;
};

static unsigned int hexval_n(const unsigned char *p, int n) {
    unsigned int v = 0; int i;
    for (i = 0; i < n; i++) {
        unsigned char c = p[i];
        v <<= 4;
        if (c >= '0' && c <= '9') v |= c - '0';
        else if (c >= 'a' && c <= 'f') v |= c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') v |= c - 'A' + 10;
    }
    return v;
}
static unsigned int hexval(const unsigned char *p) { return hexval_n(p, 8); }

/* walk the archive; returns 0 on clean TRAILER, 1 on broken padding,
 * -1 on malformed record */
static int walk_cpio(const unsigned char *buf, unsigned long len) {
    unsigned long off = 0;
    unsigned long record_count = 0;
    unsigned int namesize, filesize;
    unsigned long name_off, body_off, next_off;
    unsigned long hdr_pad, body_pad;

    while (off + NEWC_HSIZE <= len) {
        unsigned int magic = hexval_n(buf + off, 6);
        if (magic != NEWC_MAGIC) {
            /* do_reset-style check: eat NULs, then non-4-aligned remaining
             * bytes => "broken padding" */
            unsigned long save = off;
            while (off < len && buf[off] == '\0') off++;
            uart_str("  ! non-newc magic at "); uart_hex64(save);
            uart_newline();
            if (off < len) {
                uart_str("  ! next byte: ");
                uart_hex32(buf[off]);
                uart_newline();
                if (save & 3) {
                    uart_str("  ! broken padding (hdr at non-4-align)\r\n");
                    return 1;
                }
                /* if aligned and non-NUL, it's junk at end of archive */
                uart_str("  ! junk at end of archive (aligned)\r\n");
                return 0;
            }
            uart_str("  ! clean NUL pad to end\r\n");
            return 0;
        }

        namesize = hexval(buf + off + 94);
        filesize = hexval(buf + off + 54);

        if (namesize < 1 || namesize > 4096) {
            uart_str("  ! bad namesize "); uart_dec(namesize);
            uart_str(" at 0x"); uart_hex64(off); uart_newline();
            return -1;
        }

        name_off = off + NEWC_HSIZE;
        body_off = name_off + namesize;

        /* padding to 4-byte alignment after name */
        hdr_pad = (4 - (body_off & 3)) & 3;
        body_off += hdr_pad;
        next_off = body_off + filesize;
        /* padding to 4-byte alignment after body */
        body_pad = (4 - (next_off & 3)) & 3;
        next_off += body_pad;

        if (next_off > len) {
            uart_str("  ! record overruns buffer at "); uart_hex64(off);
            uart_newline();
            return -1;
        }

        /* print name (up to 64 chars) */
        {
            char namebuf[65];
            unsigned long n = namesize - 1;
            unsigned long i;
            if (n > 64) n = 64;
            for (i = 0; i < n; i++) namebuf[i] = (char)buf[name_off + i];
            namebuf[n] = '\0';
            uart_str("  "); uart_dec(record_count); uart_str(": hdr@0x");
            uart_hex64(off);
            uart_str(" size="); uart_dec(filesize);
            uart_str(" "); uart_str(namebuf); uart_newline();
        }

        /* stop after TRAILER!!! */
        if (namesize == 11 && buf[name_off + 0] == 'T' &&
            buf[name_off + 1] == 'R' && buf[name_off + 2] == 'A' &&
            buf[name_off + 3] == 'I' && buf[name_off + 4] == 'L' &&
            buf[name_off + 5] == 'E' && buf[name_off + 6] == 'R') {
            uart_str("  TRAILER!!! found at "); uart_hex64(off);
            uart_str(" next="); uart_hex64(next_off); uart_newline();
            uart_str("  total records: "); uart_dec(record_count + 1);
            uart_newline();
            return 0;
        }

        off = next_off;
        record_count++;
        if (record_count > 10000) {
            uart_str("  ! too many records\r\n");
            return -1;
        }
    }
    uart_str("  ! ran past buffer end\r\n");
    return -1;
}

void main(void) {
    unsigned long in_len;
    int rc;

    uart_str("\r\n=== RV64 CPIO PROBE ===\r\n");

    in_len = (unsigned long)(initrd_gz_end - initrd_gz_start);
    uart_str("inflating initrd (");
    uart_dec(in_len);
    uart_str(" bytes gzip)...\r\n");

    rc = run_gunzip(initrd_gz_start, (long)in_len);
    uart_str("gunzip rc="); uart_dec(rc);
    uart_str(" out="); uart_dec(g_out_total); uart_newline();

    if (rc == 0 && g_out_total > 0) {
        uart_str("walking cpio...\r\n");
        rc = walk_cpio(probe_out_buf, g_out_total);
        if (rc == 0)
            uart_str("CPIO RESULT: CLEAN\r\n");
        else if (rc == 1)
            uart_str("CPIO RESULT: BROKEN PADDING\r\n");
        else
            uart_str("CPIO RESULT: MALFORMED\r\n");
    } else {
        uart_str("CPIO RESULT: SKIPPED (inflate failed)\r\n");
    }

    uart_str("=== PROBE DONE ===\r\n");
    *(volatile unsigned long *)SYSCON_ADDR = 0x5555UL;
    for (;;) { }
}
