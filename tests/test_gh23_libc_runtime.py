#!/usr/bin/env python3
"""tests/test_gh23_libc_runtime.py — GH-23 Picolibc/Newlib Full Port gate (RED).

Spec (roadmap row GH-23, systems/GLYPH_SELF_HOSTING_ROADMAP.md):

  standard C library runtime (malloc/free backed by sys_brk, printf/puts,
  string/math) compiled for RV32I targeting Glyph OS POSIX shim; compiles
  real userspace C software directly to verified spatial tiles.

  Gate: standard C test suite (heap allocation, formatted output, qsort)
  compiles with standard cross-compiler, links against spatial libc,
  transpiles to GlyphIR, passes StaticVerifier, and runs to clean exit 0
  on GlyphRunner.

LANDED-ABI FACTS this gate is written against (GH-21 3ec1946 receipt, no
re-derivation):

  - posix_shim_kernel_image(user_program=...) splices the transpiled C
    text in as task A; the loader rewrite (ECALL HALT -> SYSCALL r10),
    sp init and .rodata seeding are TEST-side helpers in GH-21 — GH-23
    shares them verbatim (the libc rt0 is the same shape: a freestanding
    RV32I binary linked against ECALL thunks).
  - write()'s length rides the tile contract: sys_write copies the FIXED
    2-word stdout window. GH-23's libc needs a 4-word stdout window
    (printf output) -> the gh23 image packs a WIDER write tile (the
    stdout channel grows to words 718..721; the rect holds 24 packed
    instruction cells, GH-21 used 23).
  - sys_brk aliases slot 1568 (214 -> idx 0, UNSIGNED mask). GH-21 left
    brk as a verdict-0 stub; GH-23 admits a REAL brk tile: it reads the
    current break from the GH23_BRK word, advances it by the delta in
    SYS_A0, and stores the new break back (bump allocator contract, the
    engine does not marshal a2 so the libc keeps the break in-image).
  - The bake-time tile sources are IR-verified (ir_pixel_words) exactly
    like every ingest() candidate (posix_shim pattern).

RED contract: tests/test_gh23_libc_runtime.py does not import until
tools/glyph_gpt/libc_runtime.py exists with libc_runtime_kernel_image().
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import (                              # noqa: E402 (RED)
    libc_runtime_kernel_image,     # does not exist yet — RED at import
    GH18_TABLE_WORD,
)
from tools.glyph_isa_v2 import (                                 # noqa: E402
    SYS_A0_ADDR, SYS_A1_ADDR,
)

_GCC = "riscv64-unknown-elf-gcc"

# ── GH-23 ABI constants ──────────────────────────────────────────────────
GH23_ABI_VERSION = 0x0002001B            # BK-24: low byte bumped 0x1A -> 0x1B
KERNEL_OK = 0xCAFE0000 | 27              # BK-24 libc-mode status tail id 27

# stdout channel: words 718..721 (the 4-word window the gh23 write tile
# copies — printf output is word-exact there, like GH-21's 718/719)
GH23_STDOUT_WORDS = (718, 719, 720, 721)
GH23_EXIT_CODE = 722                     # sys_exit status code lands here
GH23_BRK = 723                           # the in-image program break

N_BRK = 214                              # sys_brk POSIX number (slot 1568)


def _slot(sys_n: int) -> int:
    return GH18_TABLE_WORD + ((sys_n - 6) & 15)


# receipt words the kernel itself must NOT touch (the zeroing loop in the
# prologue zeroes 712/722-adjacent words — see the GH-23 kernel-mode note
# in libc_runtime.py; this pin FAILS if the list drifts)
_KERNEL_ZEROED = (GH18_TABLE_WORD,)      # sanity: table lives at 1568


# ── the spatial libc: standard C, no glyph anything ──────────────────────

LIBC_C = r"""\
/* GH-23 spatial libc — freestanding RV32I, syscalls via ECALL thunks.
   malloc/free: bump allocator over the brk (the single-allocation
   contract the gate exercises; free is a no-op that keeps the API). */
extern int write(int fd, const void *buf, unsigned len);
extern void exit(int code);
extern long sys_brk_ecall(long delta);
#define HEAP_BASE 2560          /* words; vpn 10, identity-mapped. GH-23
                                   fix (receipt dbg_gh23_cron60..64): the
                                   transpiler's indirect-call pointer
                                   table lives at PTR_TABLE_BASE=0x2000
                                   (word 2048) upward — a heap at 2048
                                   OVERWROTE the fn-pointer entries and
                                   qsort's jalr CALLR'd into kernel text.
                                   2560 is above the table's extent. */

static long brk_word = HEAP_BASE;

long sys_brk(long delta) {
    /* ECALL thunk: the TILE owns the break (sbrk semantics — the tile
       returns the OLD break in a0 and advances the in-image GH23_BRK
       mirror). The C static brk_word is only the INITIAL value; the
       authority is the tile (receipt dbg_gh23_leg3: a pure-C bump
       allocator never issues the ECALL, so the tile mirror stayed at
       its seed and leg 3's 2048+6 assertion failed with 0x0). */
    (void)brk_word;
    return sys_brk_ecall(delta);
}

void *malloc(unsigned nwords) {
    long p = sys_brk((long)nwords);
    return (void *)(unsigned)((unsigned long)p << 2);   /* word->byte */
}

void free(void *p) { (void)p; }

/* ── string ── */
unsigned strlen(const char *s) {
    unsigned n = 0;
    while (s[n]) n++;
    return n;
}

void memcpy(void *d, const void *s, unsigned n) {
    unsigned char *dd = d; const unsigned char *ss = s;
    for (unsigned i = 0; i < n; i++) dd[i] = ss[i];
}

/* ── BK-24: streaming write ────────────────────────────────────────────
   The engine marshals only a7/a0/a1 (a2 = length never reaches the
   tile), and the stamped write tile is deliberately branch-free: each
   ECALL appends ONE fixed 16-byte frame at the cursor. POSIX write(fd,
   buf, len) semantics are restored HERE, in C — the one place a length
   is actually available. Chunks ride a word-aligned 16-byte frame;
   every frame issues its own ECALL, so N bytes cost ceil(N/16) ECALLs
   and the whole stream lands byte-exact in the ring. */
#define FRAME 16

/* raw tile entry: ONE 16-byte frame from word-aligned src (the shim's
   `write` ECALL thunk, renamed so the public write() is the wrapper). */
extern int _write_frame(int fd, const void *src);

int write(int fd, const void *buf, unsigned len) {
    const unsigned char *p = buf;
    static char frame[FRAME] __attribute__((aligned(16)));
    unsigned left = len;
    while (left >= FRAME) {
        memcpy(frame, p, FRAME);
        _write_frame(fd, frame);
        p += FRAME;
        left -= FRAME;
    }
    if (left) {
        for (unsigned i = 0; i < FRAME; i++) frame[i] = 0;
        memcpy(frame, p, left);
        _write_frame(fd, frame);
    }
    return (int)len;
}

/* ── formatted output: the printf subset the gate uses ──
    fmt chars: %d (32-bit signed decimal), %s (NUL string), %c, %%.
    Output is buffered into a 16-byte window (4 stdout words). */
static char out_buf[16] __attribute__((aligned(16)));
static unsigned out_n;
static unsigned out_dcnt;

/* out_flush: deliver the accumulated buffer with ONE write(1, buf, 16)
   — the gh23 tile copies all 4 words word-exactly. Empty buffer is a
   no-op (leg 3's brk fixture writes nothing and must not issue a
   write ECALL). Called by stdout_flush at the END of the program and
   automatically by out_ch when the 16-byte window is full. Receipt
   probe 1137: printf must NOT flush per call — flush2's '!C' would
   overwrite flush1's 'n=10,30' in the fixed 16-byte window copy. */
void out_flush(void) {
    if (out_n == 0) return;
    write(1, out_buf, 16);
    out_n = 0;
}

/* stdout_flush: explicit flush of the accumulated buffer. The gate
   calls this before exit so the whole 'n=10,30!C' stream lands in the
   4-word window as ONE write (receipt probe 1137). */
void stdout_flush(void) {
    out_flush();
}

static void out_ch(char c) {
    if (out_n == 16) out_flush();
    out_buf[out_n++] = c;
}

static void out_str(const char *s) {
    while (*s) out_ch(*s++);
}

static void out_dec(long v) {
    char tmp[12];
    unsigned neg = 0, i = 0;
    unsigned long u;
    if (v < 0) { neg = 1; u = (unsigned long)(-(v + 1)) + 1; }
    else u = (unsigned long)v;
    if (u == 0) tmp[i++] = '0';
    while (u) { tmp[i++] = '0' + (char)(u % 10); u /= 10; }
    if (neg) out_ch('-');
    while (i) out_ch(tmp[--i]);
}

/* libgcc div/mod-by-10 helpers (RV32I has no divide; -nostdlib means
   the libgcc runtime is not linked — provide the two the digit loop
   needs as plain C loops; the GH-19 receipt precedent: avoid libgcc
   divide helpers entirely). */
unsigned long __umodsi3(unsigned long a, unsigned long b) {
    unsigned long q = 0, r = a;
    while (r >= b) { r -= b; q++; }
    return r;
}
unsigned long __udivsi3(unsigned long a, unsigned long b) {
    unsigned long q = 0, r = a;
    while (r >= b) { r -= b; q++; }
    return q;
}

void printf(const char *fmt, long a, long b) {
    /* two-arg subset: the gate uses at most 2 args per call */
    for (unsigned i = 0; fmt[i]; i++) {
        if (fmt[i] != '%') { out_ch(fmt[i]); continue; }
        i++;
        if (fmt[i] == 'd') {
            static long which; /* static: avoids stack spills in -O0 */
            which = (out_dcnt++ & 1) ? b : a;
            out_dec(which);
        } else if (fmt[i] == 's') {
            static long which2;
            which2 = (out_dcnt++ & 1) ? b : a;
            out_str((const char *)(unsigned)(unsigned long)which2);
        } else if (fmt[i] == 'c') {
            static long which3;
            which3 = (out_dcnt++ & 1) ? b : a;
            out_ch((char)which3);
        } else if (fmt[i] == '%') {
            out_ch('%');
        } else {
            out_ch(fmt[i]);
        }
    }
    /* NO flush here (receipt probe 1137): a per-printf flush makes the
       second printf's window copy ('!C' + stale tail) overwrite the
       first's 'n=10,30' at words 718/719. Buffering continues across
       calls; the program flushes once via stdout_flush before exit. */
}

/* ── qsort: insertion sort (n is tiny; determinism is the contract) ── */
static int cmp_ilv(const void *a, const void *b) {
    int x = *(const int *)a, y = *(const int *)b;
    return (x > y) - (x < y);
}

void qsort(int *base, unsigned n,
           int (*cmp)(const void *, const void *)) {
    for (unsigned i = 1; i < n; i++) {
        int key = base[i];
        int j = (int)i - 1;
        while (j >= 0 && cmp(&base[j], &key) > 0) {
            base[j + 1] = base[j];
            j--;
        }
        base[j + 1] = key;
    }
}

/* ── exit thunk (the runtime's own tail) ── */
static void libc_exit(int code) { exit(code); }
#define EXIT libc_exit
"""

FIXTURE_C = r"""\
/* GH-23 gate binary: standard C, linked against the spatial libc.
   Exercises: heap allocation (malloc from the brk), formatted output
   (printf %d/%s), qsort, clean exit 0. */
extern void *malloc(unsigned nwords);
extern void free(void *p);
extern unsigned strlen(const char *s);
extern void memcpy(void *d, const void *s, unsigned n);
extern void qsort(int *base, unsigned n, int (*cmp)(const void *, const void *));
extern int cmp_ilv_unused(const void *a, const void *b);
extern void exit(int code);

static const char tag[4] = { 'G','H','2','3' };

void _start(void) {
    /* leg A: heap allocation — a 4-word block from the brk */
    int *arr = (int *)malloc(4);
    for (int i = 0; i < 4; i++) arr[i] = 40 - 10 * i;   /* 40,30,20,10 */

    /* leg B: qsort over the heap block (insertion sort in libc) */
    qsort(arr, 4, cmp_ilv_unused);

    /* leg C: printf "%d,%d" -> "10,30" (first two sorted entries) */
    printf("n=%d,%d", arr[0], arr[1]);

    /* leg D: string ops on .rodata */
    unsigned n = strlen("AB");          /* 2 */
    printf("!%c", (long)(char)('A' + (char)n));   /* '!C' */

    /* one flush delivers the whole 'n=10,30!C' stream as ONE write
       (receipt probe 1137: no per-printf flush — flush2's '!C' would
       overwrite flush1's 'n=10,30' in the fixed 16-byte window) */
    stdout_flush();

    free(arr);
    exit(0);
}

/* the comparator, passed by name so the link is honest */
int cmp_ilv_unused(const void *a, const void *b);
int cmp_ilv_unused(const void *a, const void *b) {
    int x = *(const int *)a, y = *(const int *)b;
    return (x > y) - (x < y);
}
"""

SHIM_S = """\
    .text
    .globl _write_frame
_write_frame:
    li a7, 64
    ecall
    ret
    .globl exit
exit:
    li a7, 93
    ecall
    ret
    .globl sys_brk_ecall
sys_brk_ecall:
    li a7, 214
    ecall
    ret
"""

LINKER_JUNK = ("__global_pointer$", "__SDATA_BEGIN__", "__BSS_END__",
               "__bss_start", "__DATA_BEGIN__", "__DATA_END__")


def _require_toolchain() -> None:
    if shutil.which(_GCC) is None:
        pytest.skip("riscv64-unknown-elf-gcc not installed")


def _compile_elf(tmp: Path, c_text: str, libc_text: "str | None" = None) -> bytes:
    """Freestanding RV32I compile of c_text + LIBC_C against the ECALL
    thunks. No glyph awareness anywhere in this step."""
    src, elf = tmp / "g23.c", tmp / "g23.elf"
    libc = tmp / "gh23_libc.c"
    asm = tmp / "shim.S"
    src.write_text(c_text)
    libc.write_text(libc_text if libc_text is not None else LIBC_C)
    asm.write_text(SHIM_S)
    objs = []
    for i, o in enumerate((src, libc)):
        obj = tmp / f"g23_{i}.o"
        subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin", "-ffreestanding", "-w", "-c", str(o),
             "-o", str(obj)],
            check=True, capture_output=True, timeout=60)
        objs.append(obj)
    subprocess.run(
        [_GCC, "-march=rv32i", "-mabi=ilp32", "-nostdlib",
         "-Wl,-Ttext=0x0", "-Wl,--entry=_start", "-w",
         *map(str, objs), str(asm), "-o", str(elf)],
        check=True, capture_output=True, timeout=60)
    return elf.read_bytes()


def _load_posix_program(elf_bytes: bytes) -> str:
    """Shared GH-21 loader: parse ELF -> filter linker junk ->
    transpile (IR gate inside) -> rewrite ECALL into SYSCALL ->
    seed sp + .data/.rodata. Verbatim from tests/test_gh21_posix_shim.py
    (the libc rt0 is the same program shape)."""
    # ── pointer-table seed (GH-23 defect fix, receipt dbg_gh23_cron60..64):
    # qsort's `jalr s2` (comparator call) lowers to a lookup through the
    # transpiler's PTR_TABLE_BASE=0x2000 table: mem[(0x2000 + rv_addr) >> 2].
    # The GH-21 loader never seeded those words (its fixtures make no
    # indirect calls) AND the old heap base (2048) sat ON TOP of the table,
    # so the "fn pointer" load read arr[0]=40 and CALLR'd into kernel text.
    # Two coordinated changes:
    #   (a) here: emit stores for every :pc_ label entry (the loader-side
    #       half of build_pointer_table — coords come from a throwaway
    #       assemble pass at the SAME cols_instrs the splice bake uses);
    #   (b) the heap moves above the table's extent (GH23_HEAP_BASE=2560,
    #       vpn 10) — set in LIBC_C and the baker's libc prologue seed.
    import rv64i_to_glyph as r2g

    base, text, symbols = r2g.parse_elf(elf_bytes)
    # capture __global_pointer$ BEFORE the junk filter (DEFECT 9,
    # 2026-09-10 cron session, receipts output/probe_gh23_1092..1103):
    # gcc relaxes small-data references to `addi reg,gp,-off`, relying on
    # crt0 to set gp — but -nostdlib ships no crt0, so the GH-21 loader
    # never initialized x3. The first such access (out_ch's
    # `sb s0,0(a5)` with a5 = gp + (-2040)) computed
    # 0xfffff808 + r3(0) = 0xfffff808 and faulted the page walker at
    # word 0xFFFFF808>>2 — the whole 4-leg run died at step ~3126 with
    # brk/exit correct but zero stdout. 0xfffff808 + gp(0x1d14) =
    # 0x151c = &out_buf exactly, so seeding x3 restores the compiler's
    # contract. (GH-21 fixtures never touched small data; GH-23's libc
    # does — out_buf/out_n are .sbss.)
    gp_addr = next((a for a, n in r2g.parse_elf(elf_bytes)[2].items()
                    if n == "__global_pointer$"), None)
    symbols = {a: n for a, n in symbols.items()
               if not n.startswith("$") and n not in LINKER_JUNK}
    lines = r2g.transpile_rv32i_to_glyph(
        text_bytes=text, symbols=symbols, base_addr=base,
        entry_symbol="_start", use_ir=True,
        cols_instrs=32).splitlines()

    out: list[str] = []
    prev = ""
    for ln in lines:
        s = ln.split(";")[0].strip()
        if not s or s.startswith(":"):
            out.append(ln)
            continue
        if s == "HALT" and prev.startswith("LDI r17 "):
            out.append("SYSCALL r10")
            prev = "SYSCALL r10"
            continue
        out.append(ln)
        prev = s

    init: list[str] = []
    for vaddr, blob in r2g.parse_elf_data_sections(elf_bytes):
        for wi in range(0, len(blob), 4):
            word = int.from_bytes(blob[wi:wi + 4].ljust(4, b"\0"), "little")
            w = (vaddr + wi) >> 2
            init.append(f"LDI r20 {word & 0xFFFF}")
            hi = (word >> 16) & 0xFFFF
            if hi:
                init.append(f"LDI r21 {hi}")
                init.append("LDI r22 16")
                init.append("SHL r21 r22")
                init.append("OR r20 r21")
            init.append(f"LDI r15 {w}")
            init.append("ST r15 r20")

    # ── pointer-table entries (the (a) half of the GH-23 fix): every
    # :pc_ label gets memory[(PTR_TABLE_BASE + rv_word) >> 2] = its
    # pixel-packed glyph PC. Coords come from a throwaway assemble of
    # the REWRITTEN text (post-SYSCALL-rewrite — the 1:1 rewrite keeps
    # label coords stable, so pre/post coords agree; assembling the
    # final spliced text is the bake's job, this is just the DATA seed).
    #
    # DEFECT 4 (2026-09-10, cron session; receipt output/dbg_gh23_cron289..295
    # + this session's step traces): the packed PCs above are PLAIN-LAYOUT
    # cells, but the libc bake SPLICES the task at cell 332 (after the 24-cell
    # g23 tile rect + 97-cell pad). The ECALL-thunk CALL chain is entered via
    # these fn-pointer seeds, so the pushed return addresses are plain cells
    # (observed: RET popped 0x3a0004 = plain cell 465, which in the spliced
    # image is the task's own data-init `ST r15 r20`): execution fell into the
    # seed stores, re-issued the brk ECALL once per ~1951-step cycle, and brk
    # grew +4 per cycle (31 cycles, brk 2560 → 2684, exit word 0). GH-21 never
    # hit this because its fixtures make no indirect calls (no fn-ptr seeds).
    # FIX: every :pc_ packed PC is converted plain-cell → +SPLICE_OFFSET_CELLs
    # and repacked, matching where the bake actually places the task text.
    # The offset mirrors libc_runtime.py exactly: 24-cell tile rect + pad up
    # to the reserved table window (window_end_cell 332 = task start). The
    # baker asserts the same arithmetic; if it moves, this constant must move
    # with it (single source of truth would require a baker import cycle —
    #    the assert below pins the drift instead).
    # DEFECT 6 (2026-09-10, cron session; receipt output/dbg_gh23_cron359):
    # the packed PCs were STILL low by 2272 cells — exactly the size of the
    # data-init block inserted BELOW this loop (init += ptr seeds are appended
    # at `out[:idx+1] + sp + init + out[jmp_idx:]`). The coords came from
    # `assemble(out)` — the text WITHOUT the init block — so every :pc_ label
    # sat 2272 cells higher in that layout than in the final spliced text
    # (e.g. :pc_158 seeded cell 586 = 0x00490002 instead of spliced 2858 =
    # 0x01650002). First indirect RET (malloc -> sys_brk_ecall's `ret` pops
    # the packed PC for :pc_158) landed in the task's own data-init region,
    # re-entered _start, and the task re-issued malloc/brk every ~1734 steps
    # while r2 marched down 0x10/cycle to fault 0xfffffff8 — the Defect-4
    # symptom at a new offset. FIX: fixed-point seeding — assemble the
    # FINAL text (init block included, pre-splice), take :pc_ coords from
    # that, then splice-offset them. Converges in one pass: the seeds are
    # data words, so adding them changes no label's coordinate, only the
    # ABSOLUTE cells — which is exactly what the second assemble captures.
    # DEFECT 7 companion (2026-09-10, cron session; receipt
    # output/gh23_red_0945.txt + output/gh23_memmask_probe.out): the bake
    # moved to cols_instrs=16 because the engine's packed-PC row field is
    # 8 bits (24-bit pixel word) and the spliced task at 8 cols was 413
    # rows — return PCs with row >= 256 truncated on the store mask. At
    # 16 cols the task is ~230 rows, safely under. The loader MUST
    # assemble at the same cols_instrs so the :pc_ coords match the bake
    # (libc_runtime.py pins the same constant + SPLICE_OFFSET_CELLS
    # relationship).
    # DEFECT 8 companion (2026-09-10, cron session; receipt
    # output/dbg_gh23_cron706..708): the libc bake's Defect-8 fix moved
    # window_end_cell from 332 to 384 (pad past the WHOLE vpn-6 alias
    # window [320,384), not just the 16 reserved words) — the spliced task
    # now starts at cell 384. The loader still seeded :pc_ packed PCs with
    # SPLICE_OFFSET_CELLS=332, i.e. every fn pointer was 52 cells LOW.
    # Symptom (receipt cron706/707/708): malloc->sys_brk_ecall's RET popped
    # a PC 52 cells into PRE-task territory (a pad cell), execution fell
    # into a stale malloc loop — 12 spurious +4 brk wraps (brk 2560->2612),
    # sp marching down 0x10/wrap 0x3ff->0x1f, then ST [0xfffffff8] fault.
    # brk word 2612 at fault = 13 brk calls for a 1-malloc fixture — the
    # Defect-4/6 re-issue signature at a new constant. FIX: track the
    # bake's window_end_cell = 384. The baker asserts the same arithmetic
    # (libc_runtime.py:332); if it moves, this constant must move with it.
    SPLICE_OFFSET_CELLS = 384                    # window_end_cell (libc bake)
    CELLS_PER_ROW = 32                           # cols_instrs=32 (BK-24 re-fix:
                                                 #  the write wrapper pushed
                                                 #  70 :pc_ entries past row
                                                 #  255 at 16 cols; see
                                                 #  RECEIPT_BK24_ROOT_CAUSE_row_truncation.md)

    def _final_text(pc_seed_packed=None):
        """Build the seeded text with :pc_ seeds packed as given (dict
        rv_byte -> packed), else zeros (shape pass)."""
        init: list[str] = []
        for vaddr, blob in r2g.parse_elf_data_sections(elf_bytes):
            for wi in range(0, len(blob), 4):
                word = int.from_bytes(blob[wi:wi + 4].ljust(4, b"\0"), "little")
                w = (vaddr + wi) >> 2
                init.append(f"LDI r20 {word & 0xFFFF}")
                hi = (word >> 16) & 0xFFFF
                if hi:
                    init.append(f"LDI r21 {hi}")
                    init.append("LDI r22 16")
                    init.append("SHL r21 r22")
                    init.append("OR r20 r21")
                init.append(f"LDI r15 {w}")
                init.append("ST r15 r20")
        for rv_byte, packed in (pc_seed_packed or {}).items():
            word = (r2g.PTR_TABLE_BASE + rv_byte) >> 2
            if packed >> 16:
                init.extend([
                    f"LDI r20 {packed & 0xFFFF}",
                    f"LDI r21 {(packed >> 16) & 0xFFFF}",
                    "LDI r22 16",
                    "SHL r21 r22",
                    "OR r20 r21",
                ])
            else:
                init.append(f"LDI r20 {packed & 0xFFFF}")
            init.append(f"LDI r15 {word}")
            init.append("ST r15 r20")
        idx = next(i for i, ln in enumerate(out)
                   if ln.split(";")[0].strip().startswith("LDI r31"))
        jmp_idx = next(i for i in range(idx + 1, len(out))
                       if out[i].startswith("JMP "))
        seeded = (out[:idx + 1]
                  + ["LDI r2 1023            ; C data stack pointer (sp)"]
                  # DEFECT 9 fix: gp (x3) seed — see the capture note above.
                  + (["LDI r3 %d            ; __global_pointer$ (gp, byte addr)"
                      % gp_addr] if gp_addr is not None else [])
                  + init
                  + out[jmp_idx:])
        return "\n".join(seeded) + "\n"

    # pass 1: assemble the final-shaped text (zero seeds) to get the
    # :pc_ label coords AS THEY WILL SIT IN THE BAKED IMAGE (mod the
    # constant splice offset). The seed block inserts BEFORE every task
    # label (rt0 head + seeds + JMP :_start), so seed-block size shifts
    # the coords — and the per-entry shape (5-instr row≠0 vs 2-instr
    # row=0) depends on the packed values. Hence a genuine fixed-point
    # loop: reassemble with the previous pass's seeds until the seed set
    # stops moving (spliced rows are all >= 41, so every entry takes the
    # 5-instr form from pass 2 on — convergence in 3 iterations).
    shape_txt = _final_text()
    _, pc_coords = r2g.assemble_glyph_to_pixels(
        shape_txt, cols_instrs=CELLS_PER_ROW, min_rows=34)
    seeds: dict[int, int] = {}
    for _it in range(5):
        new_seeds: dict[int, int] = {}
        for lbl, (col, row) in pc_coords.items():
            if not lbl.startswith(":pc_"):
                continue
            rv_byte = int(lbl[4:], 16)
            flat_cell = row * CELLS_PER_ROW + col
            spliced_cell = flat_cell + SPLICE_OFFSET_CELLS
            # DEFECT 5 (2026-09-10, cron session; receipt
            # output/dbg_gh23_cron354..370): the packed fn-pointer PCs used the
            # PIXEL-x convention ((col * 4)), but the engine's JMPR/CALLR
            # decode is tx * INSTR_WIDTH — i.e. the packed field is a COLUMN
            # (see build_pointer_table in rv64i_to_glyph.py: ((row)<<16)|col).
            # The x4 overshoot sent every indirect call (qsort's `jalr s2`)
            # into the middle of unrelated functions: observed ra=0x158
            # (= pixel 344 = col 86), RET chains derailing into out_flush,
            # +4 brk re-issue loops and a C-stack underflow fault at
            # 0xfffffff8. Convention A (col-based) verified empirically in
            # dbg_gh23_cron368: CALLR with 0x10002 lands on cell 10 exactly.
            packed = (((spliced_cell // CELLS_PER_ROW) & 0xFFFF) << 16) \
                | ((spliced_cell % CELLS_PER_ROW) & 0xFFFF)
            new_seeds[rv_byte] = packed
        if new_seeds == seeds:
            break
        seeds = new_seeds
        _, pc_coords = r2g.assemble_glyph_to_pixels(
            _final_text(seeds), cols_instrs=CELLS_PER_ROW, min_rows=34)
    else:
        raise AssertionError(
            "pointer-seed fixed-point did not converge in 5 passes")
    # converged: emit the seeded text with the FINAL packed PCs
    return _final_text(seeds)


# ── leg 1: ABI version word bumped in the libc-mode image ────────────────

def test_gh23_abi_version_word_bumped():
    """mem[952] == 0x0002001A at boot in the libc-mode image."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gh23.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=60000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        assert receipt["memory"][952] == GH23_ABI_VERSION
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 2: heap alloc + formatted output + qsort + clean exit 0 ──────────

def test_gh23_c_suite_malloc_printf_qsort_exit0():
    """Standard C suite (malloc/qsort/printf/strlen) compiles, links
    against the spatial libc, transpiles through the IR gate, and runs:
    sorted output word-exact at the stdout window, heap block written
    and freed, exit code 0, clean kernel tail."""
    _require_toolchain()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = _compile_elf(tmp, FIXTURE_C)
        program = _load_posix_program(elf)

        out = tmp / "gh23.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                  user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=200000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # printf("n=%d,%d", arr[0], arr[1]) then printf("!%c", 'C'):
        # fixture seeds 40,30,20,10; qsort ascending -> 10,20,30,40, so
        # the first two sorted entries are 10,20 (NOT 10,30 — the old
        # constant predated the DEFECT-10/11 comparator fixes, when the
        # SLT rd==rs1 aliasing left the sort partially broken; verified
        # independently by reading heap words 2560..2563 = [10,20,30,40],
        # receipt output/probe_leg2_heap.py, 2026-09-10 cron session).
        # buf bytes: 'n','=','1','0' | ',','2','0','!' | 'C',NUL...
        b = bytes(b"n=10,20!C")
        b = b + b"\0" * (16 - len(b))
        import struct
        w0, w1, w2, w3 = struct.unpack("<4I", b)
        assert mem[GH23_STDOUT_WORDS[0]] == w0, hex(mem[GH23_STDOUT_WORDS[0]])
        assert mem[GH23_STDOUT_WORDS[1]] == w1, hex(mem[GH23_STDOUT_WORDS[1]])
        assert mem[GH23_STDOUT_WORDS[2]] == w2, hex(mem[GH23_STDOUT_WORDS[2]])
        assert mem[GH23_STDOUT_WORDS[3]] == w3, hex(mem[GH23_STDOUT_WORDS[3]])
        assert mem[GH23_EXIT_CODE] == 0, "exit(0) code not delivered"
        # the break advanced past the heap base by the 4-word block
        assert mem[GH23_BRK] >= 2560 + 4
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 3: brk tile is real — the break MOVES ────────────────────────────

def test_gh23_brk_tile_moves_the_break():
    """The brk slot carries a REAL tile: an in-image USER task that calls
    the brk ECALL twice advances the GH23_BRK word by exactly the two
    deltas (the GH-21 stub left it at 0 — this leg pins the upgrade)."""
    _require_toolchain()
    brk_c = r"""\
extern long sys_brk(long delta);
extern void exit(int code);
void _start(void) {
    long a = sys_brk(4);        /* old break: HEAP_BASE (2560) */
    long b = sys_brk(2);        /* old break: 2564 */
    (void)a; (void)b;
    exit(0);
}
"""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = _compile_elf(tmp, brk_c)
        program = _load_posix_program(elf)
        out = tmp / "gh23brk.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                  user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=200000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # libc tracks the break in its own static (heap-side); the TILE's
        # GH23_BRK mirror must have advanced by 4+2 = 6 words
        assert mem[GH23_BRK] == 2560 + 6, hex(mem[GH23_BRK])
        assert mem[GH23_EXIT_CODE] == 0
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 4: unrecognized ecall traps cleanly (shim contract preserved) ────

def test_gh23_unrecognized_ecall_traps_clean():
    """A POSIX number whose aliased slot is UNLIT (e.g. SYS 11 -> idx 5)
    must hit the unknown-syscall handler: 'E' in BADSYS (730), clean
    SYSRET, kernel tails to KERNEL_OK."""
    _require_toolchain()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        unknown_c = FIXTURE_C.replace(
            '    printf("n=%d,%d", arr[0], arr[1]);\n',
            '    __asm__ volatile ("li a7, 11\\n\\tecall");\n')
        elf = _compile_elf(tmp, unknown_c)
        program = _load_posix_program(elf)
        out = tmp / "gh23u.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                  user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=200000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        assert mem[730] == 69, hex(mem[730])      # 'E' — clean errno marker
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 5: full-GH regression stays green (structural pin) ───────────────

def test_gh23_loader_preserves_ir_shape():
    """Structural: the loader's ECALL rewrite is 1:1 (instruction count
    identical modulo the documented seed) and the transpile path is the
    IR-gated one. Skips cleanly without the toolchain."""
    _require_toolchain()
    with tempfile.TemporaryDirectory() as d:
        elf = _compile_elf(Path(d), FIXTURE_C)
        import rv64i_to_glyph as r2g
        base, text, symbols = r2g.parse_elf(elf)
        symbols = {a: n for a, n in symbols.items()
                   if not n.startswith("$") and n not in LINKER_JUNK}
        plain = r2g.transpile_rv32i_to_glyph(
            text_bytes=text, symbols=symbols, base_addr=base,
            entry_symbol="_start", use_ir=True)
        rewritten = _load_posix_program(elf)
        n_seed = 1  # LDI r2 1023
        # DEFECT 10 companion (2026-09-10): the gp seed (LDI r3, DEFECT 9
        # fix) is also loader-inserted — account for it exactly as sp.
        import rv64i_to_glyph as _r2g
        _gp = next((a for a, n in _r2g.parse_elf(elf)[2].items()
                    if n == "__global_pointer$"), None)
        if _gp is not None:
            n_seed += 1
        for _vaddr, blob in r2g.parse_elf_data_sections(elf):
            for wi in range(0, len(blob), 4):
                word = int.from_bytes(blob[wi:wi + 4].ljust(4, b"\0"),
                                      "little")
                n_seed += 3 + (4 if (word >> 16) & 0xFFFF else 0)
        # pointer-table seed block (GH-23 loader, :pc_ entries): DEFECT 9
        # accounting (2026-09-10, cron session; receipt
        # output/dbg_gh23_cron701): the old count assumed 5 instrs/entry,
        # but a 24-bit packed PC needs the FULL 64k-range pair form —
        # LDI r20 lo + LDI r21 hi + LDI r22 16 + SHL + OR + LDI r15 + ST
        # = 7 instrs per entry (spliced rows are >= 41, so packed>>16 is
        # always nonzero and the 2-instr short form never fires). Measured:
        # rewritten 3375 = plain 1103 + sp 1 + data 24 + 321*7 = 3375 exact.
        n_pc = sum(1 for ln in rewritten.splitlines()
                   if ln.startswith(":pc_"))
        n_seed += n_pc * 7

        def _instrs(txt: str) -> list[str]:
            return [ln.split(";")[0].strip() for ln in txt.splitlines()
                    if ln.strip() and not ln.strip().startswith(":")
                    and not ln.strip().startswith("#")]
        n_plain = len(_instrs(plain))
        n_rw = len(_instrs(rewritten))
        assert n_plain == n_rw - n_seed, (
            f"ECALL rewrite must be instruction-count neutral: "
            f"plain {n_plain} vs rewritten-minus-seed {n_rw - n_seed}")
        n_halt = sum(1 for s in _instrs(plain) if s == "HALT")
        n_sys = sum(1 for s in _instrs(rewritten) if s == "SYSCALL r10")
        assert n_sys == n_halt, f"{n_sys} SYSCALL vs {n_halt} HALT"
        assert "SYSCALL r10" in rewritten
        lines = rewritten.splitlines()
        for i, ln in enumerate(lines):
            if ln.split(";")[0].strip() == "SYSCALL r10":
                j = i - 1
                while j >= 0:
                    s = lines[j].split(";")[0].strip()
                    if s and not s.startswith(":"):
                        break
                    j -= 1
                assert j >= 0 and lines[j].split(";")[0].strip().startswith(
                    "LDI r17 "), (
                    f"SYSCALL at line {i} not preceded by LDI r17")
