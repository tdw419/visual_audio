#!/usr/bin/env python3
"""BK-11 coreutils volume port #1 — cat, echo, wc, cmp, head.

Roadmap row BK-11 (promoted 3519eec): coreutils volume port #1
compiles with riscv64-gcc + libc, transpiles, runs on Glyph.

This module is the single source of truth shared by the gate
(tests/test_bk11_coreutils.py) and the implementation:

  - COREUTILS_FIXTURES: per-tool fixture table (3 fixtures/tool),
    each carrying the input the tool reads and the NATIVE POSIX
    output bytes the gate compares the Glyph stdout window against
    byte-exactly.

  - coreutils_tool_elf(tool, fixture, tmp): cross-compiles the
    tool's C source + the GH-23 spatial libc (LIBC_C + SHIM_S,
    imported verbatim from test_gh23_libc_runtime so the same
    compile contract rides every tool) into a freestanding RV32I
    ELF with the fixture data embedded via C string literals.

The output-window contract (16 bytes/flush, single flush at exit —
receipt probe 1137) means every fixture is sized so its full output
fits 16 bytes; wc pads its report to fill the window byte-exactly
against the same padded native reference (documented at promotion).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

_GCC = "riscv64-unknown-elf-gcc"

# ── the C sources: stranger's-C-program-shaped coreutils clones ──────────
#
# Each tool is a real C program with the tool's argument contract. The
# fixture input is embedded as a .rodata string literal (the GH-23
# loader seeds .data/.rodata via parse_elf_data_sections — receipt
# GH-23 DEFECT-9 lineage), so the tool READS its input through the
# same path a real binary's constant data takes. All output goes
# through the GH-23 libc (puts/printf subset + single stdout_flush).
#
# Tool contracts (POSIX):
#   cat FILE        — write FILE's bytes to stdout
#   echo ARGS...    — write args + '\n'
#   wc FILE         — "  L W C FILE" style report (padded to the window)
#   cmp A B         — exit 1 on difference, 0 when equal (no output
#                     for a plain EOF difference)
#   head -n N FILE  — first N lines of FILE

_LIBC_EXTERN = r"""\
extern int write(int fd, const void *buf, unsigned len);
extern void *malloc(unsigned nwords);
extern void free(void *p);
extern unsigned strlen(const char *s);
extern void memcpy(void *d, const void *s, unsigned n);
extern void printf(const char *fmt, long a, long b);
extern void stdout_flush(void);
extern void exit(int code);
"""

# emit helpers shared by the tool bodies: the GH-23 libc keeps
# out_ch/out_str static, so each tool TU defines its own public
# emit surface on top of the LIBC's public printf + stdout_flush
# (same buffered single-flush contract — receipt probe 1137).
# BUG-15: the GH-23 libc keeps its OWN static out_ch/out_buf/out_n (the
# printf emit surface), and the transpiler merges both TUs into ONE glyph
# module — a tool-side `out_ch` collides as duplicate IR label
# ':out_ch' (echo fixture, StaticVerificationError). Every tool-side
# emit helper therefore carries the bk11_ prefix: byte-identical
# semantics, namespace-disjoint from the libc.
_COMMON = r"""\
static char _buf[16];
static unsigned _n;

static void bk11_flush(void) {
    /* pad the buffer to the full 16-byte window (the gh23 write tile
       copies a FIXED 4-word window) and deliver with ONE write() —
       exactly one tile copy per tool run, no overwrite hazard. */
    while (_n < 16) _buf[_n++] = '\0';
    write(1, _buf, 16);
    _n = 0;
}

static void bk11_out_ch(char c) {
    if (_n == 16) bk11_flush();
    _buf[_n++] = c;
}

static void bk11_out_str(const char *s) {
    while (*s) bk11_out_ch(*s++);
}
"""

_TOOL_SOURCES: Dict[str, str] = {
    # cat FILE — stream the file bytes to stdout. The fixture file is a
    # NUL-terminated .rodata literal; cat's copy loop is length-driven
    # (a file's bytes may contain anything), using the embedded length.
    "cat": _LIBC_EXTERN + r"""\
static const char *CAT_DATA;
static unsigned CAT_LEN;

void _start(void) {
    unsigned i;
    for (i = 0; i < CAT_LEN; i++) bk11_out_ch(CAT_DATA[i]);
    bk11_flush();
    exit(0);
}
""",
    # echo ARGS... — join args with spaces, terminate with newline.
    "echo": _LIBC_EXTERN + r"""\
static const char *ECHO_A;
static const char *ECHO_B;

void _start(void) {
    bk11_out_str(ECHO_A);
    if (ECHO_B[0]) { bk11_out_ch(' '); bk11_out_str(ECHO_B); }
    bk11_out_ch('\n');
    bk11_flush();
    exit(0);
}
""",
    # wc FILE — lines/words/chars report, "%d %d %d %s" shape with
    # arbitrary-width decimal counters (BK-46: the V1 body's 2-digit
    # char-buffer renderer corrupted counters >= 100 — '310' rendered
    # as 'O0' on a 309-byte file, measured probe_bk46_red_af3e.py P4).
    # Single-space format, byte-exact vs the L1 shell's host shim and
    # host wc on every landed fixture (BK-11) and real files alike.
    # Delivers via ONE bk11_flush frame (report <= 16 B on the fixture
    # table; the shell-side dynamic path rides the BK-24 streaming ring).
    "wc": _LIBC_EXTERN + r"""\
static const char *WC_DATA;
static unsigned WC_LEN;
static const char *WC_NAME;

static void bk11_out_dec(unsigned v) {
    char tmp[12];
    unsigned i = 0;
    if (v == 0) tmp[i++] = '0';
    while (v) { tmp[i++] = '0' + (char)(v % 10); v /= 10; }
    while (i) bk11_out_ch(tmp[--i]);
}

void _start(void) {
    /* unsigned counters throughout: freestanding RV32I links only the
       libc's __udivsi3/__umodsi3 — signed div/mod would pull __divsi3/
       __modsi3 from libgcc, which -nostdlib does not link (wc RED). */
    unsigned lines = 0, words = 0, chars = WC_LEN;
    unsigned i; int in_word = 0;
    for (i = 0; i < WC_LEN; i++) {
        char c = WC_DATA[i];
        if (c == '\n') lines++;
        if (c == ' ' || c == '\n' || c == '\t') in_word = 0;
        else if (!in_word) { in_word = 1; words++; }
    }
    bk11_out_dec(lines); bk11_out_ch(' ');
    bk11_out_dec(words); bk11_out_ch(' ');
    bk11_out_dec(chars); bk11_out_ch(' ');
    bk11_out_str(WC_NAME);
    bk11_flush();
    exit(0);
}
""",
    # cmp A B — byte compare; exit 0 equal, exit 1 different, no output
    # for a plain difference (POSIX prints nothing when only length or
    # an EOF difference occurs and -s-like silence is the contract the
    # gate pins).
    "cmp": _LIBC_EXTERN + r"""\
static const char *CMP_A;
static unsigned CMP_A_LEN;
static const char *CMP_B;
static unsigned CMP_B_LEN;

void _start(void) {
    unsigned n = CMP_A_LEN;
    unsigned i;
    if (CMP_B_LEN < n) n = CMP_B_LEN;
    for (i = 0; i < n; i++) {
        if (CMP_A[i] != CMP_B[i]) exit(1);
    }
    if (CMP_A_LEN != CMP_B_LEN) exit(1);
    exit(0);
}
""",
    # head -n N FILE — first N lines.
    "head": _LIBC_EXTERN + r"""\
static const char *HEAD_DATA;
static long HEAD_N;

void _start(void) {
    long emitted = 0;
    unsigned i = 0, line_start = 0;
    while (HEAD_DATA[i] && emitted < HEAD_N) {
        if (HEAD_DATA[i] == '\n') {
            unsigned j;
            for (j = line_start; j <= i; j++) bk11_out_ch(HEAD_DATA[j]);
            emitted++;
            line_start = i + 1;
        }
        i++;
    }
    if (emitted < HEAD_N && HEAD_DATA[line_start]) {
        unsigned j = line_start;
        while (HEAD_DATA[j]) { bk11_out_ch(HEAD_DATA[j]); j++; }
        bk11_out_ch('\n');
    }
    bk11_flush();
    exit(0);
}
""",
}


def _c_literal(data: str) -> str:
    """Escape a fixture string as a C string literal body."""
    return data.replace("\\", "\\\\").replace('"', '\\"') \
               .replace("\n", "\\n").replace("\t", "\\t")


# ── fixture table ────────────────────────────────────────────────────────
#
# `output` is the byte-exact NATIVE POSIX reference. wc's reference is
# single-space "%d %d %d %s" (BK-46: arbitrary-width counters replace the
# promotion-era 16-byte padded window shape; the emitter matches host wc
# and the L1 host shim byte-exactly). cmp fixtures check exit codes;
# `output` is empty. A wc fixture may carry `data_len_override` (BK-46
# three_digit): the counter values ride the OVERRIDE, not the literal's
# length — the point is the 3-digit rendering path, not a 600-byte
# .rodata literal in every bake.

COREUTILS_FIXTURES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "cat": {
        "short": {
            "data": "hi\n",
            "output": "hi\n",
        },
        "two_lines": {
            "data": "ab\ncd\n",
            "output": "ab\ncd\n",
        },
        "exact_window": {
            "data": "0123456789abcde\n",
            "output": "0123456789abcde\n",
        },
    },
    "echo": {
        "one_word": {
            "a": "glyph",
            "b": "",
            "output": "glyph\n",
        },
        "two_words": {
            "a": "pixel",
            "b": "os",
            "output": "pixel os\n",
        },
        "window": {
            "a": "0123456789abcde",
            "b": "",
            "output": "0123456789abcde\n",
        },
    },
    "wc": {
        "one_line": {
            "data": "hello\n",
            "name": "f.txt",
            # wc f.txt -> "1 1 6 f.txt" (BK-46: single-space format,
            # arbitrary-width counters — matches the host shim + host wc)
            "output": "1 1 6 f.txt",
        },
        "two_lines": {
            "data": "aa bb\ncc\n",
            "name": "g.c",
            # real wc: "2 3 9 g.c" — DEFECT-16d fix receipt: the
            # promotion-time table claimed 10 chars, but the data is 9
            # bytes ('aa bb\ncc\n') and host wc agrees with 9. The glyph
            # engine (post DEFECT-16/16b/16c fixes) now matches the REAL
            # oracle; the fixture was the defect, not the engine.
            "output": "2 3 9 g.c",
        },
        "three_lines": {
            "data": "a\nb\nc\n",
            "name": "h",
            # "3 3 6 h" — the smallest report; still exercises the
            # counter emitter's single-digit path.
            "output": "3 3 6 h",
        },
        # BK-46 L2 RED leg fixture: a 3-digit counter through the V1
        # 2-digit renderer produced 'O0' (measured probe_bk46_red_af3e
        # P4: '40 40 l0 big.txt'); the arbitrary-width emitter renders
        # '40 40 600 big.txt' == host wc. data_len_override makes the
        # COUNTER exceed the literal (2 lines rendered, 600 claimed):
        # the point is the 3-digit rendering path, not a 600-byte
        # .rodata literal in every bake.
        "three_digit": {
            "data": "line000padding line001padding\n",
            "name": "big.txt",
            "data_len_override": 600,
            "output": "1 3 600 big.txt",
        },
    },
    "cmp": {
        "equal": {
            "a": "same\n",
            "b": "same\n",
            "output": "",
            "exit": 0,
        },
        "differ": {
            "a": "aaa\n",
            "b": "aab\n",
            "output": "",
            "exit": 1,
        },
        "prefix": {
            "a": "abc",
            "b": "abcd",
            "output": "",
            "exit": 1,
        },
    },
    "head": {
        "one_line": {
            "data": "l1\nl2\nl3\n",
            "n": 1,
            "output": "l1\n",
        },
        "two_lines": {
            "data": "aa\nbb\ncc\n",
            "n": 2,
            "output": "aa\nbb\n",
        },
        "n_exceeds": {
            "data": "x\ny\n",
            "n": 5,
            "output": "x\ny\n",
        },
    },
}


# sanity: the fixture table stays honest against the output contract
# (BK-46: the wc report rides the BK-24 streaming ring — its cap is the
# ring's 256 bytes, not the 16-byte window; the window cap still binds
# every other tool's single-frame output).
for _tool, _fxs in COREUTILS_FIXTURES.items():
    _cap = 256 if _tool == "wc" else 16
    _want_n = 4 if _tool == "wc" else 3
    assert len(_fxs) == _want_n, f"{_tool}: expected {_want_n} fixtures"
    for _name, _fx in _fxs.items():
        _out = _fx["output"].encode("ascii")
        assert len(_out) <= _cap, f"{_tool}/{_name}: output exceeds cap"
del _tool, _fxs, _name, _fx, _out, _cap, _want_n


def coreutils_tool_elf(tool: str, fixture_name: str, tmp: Path) -> bytes:
    """Compile `tool` + fixture + the GH-23 spatial libc into a
    freestanding RV32I ELF. Returns the ELF bytes (the gate feeds them
    to the shared GH-23 loader)."""
    if tool not in _TOOL_SOURCES:
        raise KeyError(f"unknown coreutils tool: {tool}")
    fx = COREUTILS_FIXTURES[tool][fixture_name]

    # fixture seed block: the fixture data rides as initialized .data
    # variables (the loader's parse_elf_data_sections seed covers them).
    seed_lines = []
    for var, val in fx.items():
        if var in ("output", "exit", "data_len_override"):
            continue
        if var == "n":
            # static: the tool body's `static long HEAD_N` alias expands
            # to head_n — a non-static seed definition followed by a
            # static redeclaration is a C error (head RED, BUG-17);
            # tentative static redeclaration is legal.
            seed_lines.append(f"static long {tool}_{var} = {int(val)};")
        elif var in ("a_len", "b_len", "data_len"):
            seed_lines.append(f"static unsigned {tool}_{var} = {int(val)};")
        else:
            var_name = f"{tool}_{var}"
            seed_lines.append(
                f'static const char *{var_name} = "{_c_literal(val)}";')

    # length variables for cat/cmp: the loader seeds .data, so derive
    # lengths at runtime where the tool body expects a numeric length.
    derived = []
    if tool == "cat":
        derived.append(
            f"static unsigned CAT_LEN = {len(fx['data'])};")
    if tool == "wc":
        wc_len = fx.get("data_len_override", len(fx["data"]))
        derived.append(
            f"static unsigned WC_LEN = {wc_len};")
    if tool == "cmp":
        derived.append(
            f"static unsigned CMP_A_LEN = {len(fx['a'])};")
        derived.append(
            f"static unsigned CMP_B_LEN = {len(fx['b'])};")

    # The tool bodies reference their fixture globals via fixed names
    # (CAT_DATA, ECHO_A, ...); alias them from the per-fixture seeds.
    alias_map = {
        "cat": {"CAT_DATA": f"{tool}_data"},
        "echo": {"ECHO_A": f"{tool}_a", "ECHO_B": f"{tool}_b"},
        "wc": {"WC_DATA": f"{tool}_data", "WC_NAME": f"{tool}_name"},
        "cmp": {"CMP_A": f"{tool}_a", "CMP_B": f"{tool}_b"},
        "head": {"HEAD_DATA": f"{tool}_data", "HEAD_N": f"{tool}_n"},
    }
    aliases = []
    for public, seed_name in alias_map[tool].items():
        aliases.append(f"#define {public} {seed_name}")

    # _COMMON defines the tool TU's emit surface (out_ch/out_str/puts_).
    c_text = (
        _COMMON
        + "\n".join(seed_lines) + "\n"
        + "\n".join(derived) + "\n"
        + "\n".join(aliases) + "\n"
        + _TOOL_SOURCES[tool]
    )

    from tests.test_gh23_libc_runtime import LIBC_C, SHIM_S  # one compile contract

    src = tmp / f"bk11_{tool}.c"
    libc = tmp / "gh23_libc.c"
    asm = tmp / "shim.S"
    elf = tmp / f"bk11_{tool}.elf"
    src.write_text(c_text)
    libc.write_text(LIBC_C)
    asm.write_text(SHIM_S)

    objs = []
    for i, o in enumerate((src, libc)):
        obj = tmp / f"bk11_{tool}_{i}.o"
        proc = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1", "-ffixed-x31",
             "-nostdlib",
             "-fno-builtin", "-ffreestanding", "-w", "-c", str(o),
             "-o", str(obj)],
            capture_output=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(
                f"cc failed for {o.name}:\n{proc.stderr.decode()}")
        objs.append(obj)
    proc = subprocess.run(
        [_GCC, "-march=rv32i", "-mabi=ilp32", "-ffixed-x31", "-nostdlib",
         "-Wl,-Ttext=0x0", "-Wl,--entry=_start", "-w",
         *map(str, objs), str(asm), "-o", str(elf)],
        capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"link failed:\n{proc.stderr.decode()}")
    return elf.read_bytes()


# ══════════════════════════════════════════════════════════════════════════
# round-9 supply item 19 — coreutils volume port #2: grep, tr, tee, cut,
# sort. Depends on item 18 (BK-24 streaming sys_write, merged e9f9ca4b):
# the ring [768,832) + cursor mem[724] let a tool's WHOLE output stream
# survive, so fixture outputs are no longer capped at 16 bytes. Same
# doctrine as volume port #1: real stranger's-C clones, one source of
# truth shared by the gate (tests/test_coreutils_volume2.py) and this
# module, byte-exact vs a POSIX-spec reference computed in the fixture
# table, engine untouched.
#
# Honest scope pins (also in the gate docstring):
#   - tee is the stdout-duplication half (input -> stdout). The file-write
#     half needs open()/close(), which the freestanding ECALL shim
#     (write=64/exit=93/brk=214) does not provide. Not simulated.
#   - sort is BYTewise ascending (C `>` comparison), not locale
#     collation, not numeric — the 10/9/100 fixture pins that reading.
#   - grep is substring matching (POSIX BREs out of scope).
#   - tr requires |set1| == |set2| (the POSIX subset without -d/-s).
#
# Output contract: each tool buffers its ENTIRE output into a 64-byte
# buffer (the spatial libc's out_buf grew to 64 in the BK-24 era; the
# tool-side buffer mirrors that so ONE write(1, buf, n) call delivers the
# whole stream as ceil(n/16) ring frames) and flushes once at exit.
# ══════════════════════════════════════════════════════════════════════════

_VOL2_COMMON = r"""\
static char vol2_buf[64];
static unsigned vol2_n;

static void vol2_flush(void) {
    if (vol2_n == 0) return;
    /* ONE write call, length rounded UP to the 16-byte frame multiple:
       the BK-24 libc write() chunks len into 16-byte frames (one ECALL
       per frame, the tail frame zero-padded), so the cursor advances by
       exactly ceil(n/16) frames — never more. */
    write(1, vol2_buf, (vol2_n + 15) & ~15u);
}

static void vol2_out_ch(char c) {
    vol2_buf[vol2_n++] = c;
}
"""

_VOL2_TOOL_SOURCES: Dict[str, str] = {
    # grep PATTERN FILE — print lines containing PATTERN (substring).
    "grep": _LIBC_EXTERN + _VOL2_COMMON + r"""\
static const char *GREP_PAT;
static const char *GREP_DATA;

void _start(void) {
    unsigned ls = 0, i = 0;
    while (1) {
        if (GREP_DATA[i] == '\n' || GREP_DATA[i] == 0) {
            /* line = [ls, i) — scan for the pattern */
            unsigned plen = 0;
            while (GREP_PAT[plen]) plen++;
            unsigned found = 0;
            if (plen <= i - ls) {
                for (unsigned s = ls; s + plen <= i; s++) {
                    unsigned j = 0;
                    while (j < plen && GREP_DATA[s + j] == GREP_PAT[j]) j++;
                    if (j == plen) { found = 1; break; }
                }
            }
            if (found) {
                for (unsigned k = ls; k <= i; k++) vol2_out_ch(GREP_DATA[k]);
            }
            if (GREP_DATA[i] == 0) break;
            ls = i + 1;
        }
        i++;
    }
    vol2_flush();
    exit(0);
}
""",
    # tr SET1 SET2 — translate chars; |set1| == |set2| (subset).
    "tr": _LIBC_EXTERN + _VOL2_COMMON + r"""\
static const char *TR_SET1;
static const char *TR_SET2;
static const char *TR_DATA;
static unsigned TR_LEN;

void _start(void) {
    unsigned l1 = 0, l2 = 0;
    while (TR_SET1[l1]) l1++;
    while (TR_SET2[l2]) l2++;
    for (unsigned i = 0; i < TR_LEN; i++) {
        char c = TR_DATA[i];
        char out = c;
        for (unsigned j = 0; j < l1; j++) {
            if (TR_SET1[j] == c) { out = TR_SET2[j]; break; }
        }
        vol2_out_ch(out);
    }
    vol2_flush();
    exit(0);
}
""",
    # tee (stdout half) — copy input to stdout byte-exact.
    "tee": _LIBC_EXTERN + _VOL2_COMMON + r"""\
static const char *TEE_DATA;
static unsigned TEE_LEN;

void _start(void) {
    for (unsigned i = 0; i < TEE_LEN; i++) vol2_out_ch(TEE_DATA[i]);
    vol2_flush();
    exit(0);
}
""",
    # cut -dD -fN — print field N of each line (single-char delim).
    "cut": _LIBC_EXTERN + _VOL2_COMMON + r"""\
static const char *CUT_DATA;
static char CUT_DELIM;
static long CUT_FIELD;

void _start(void) {
    unsigned ls = 0, i = 0;
    while (1) {
        if (CUT_DATA[i] == '\n' || CUT_DATA[i] == 0) {
            /* line = [ls, i); emit field CUT_FIELD or nothing */
            unsigned field = 1, fs = ls, fe;
            int hit = 0;
            unsigned k = ls;
            while (k < i) {
                if (CUT_DATA[k] == CUT_DELIM) {
                    if (field == (unsigned)CUT_FIELD) { fe = k; hit = 1; break; }
                    field++;
                    fs = k + 1;
                }
                k++;
            }
            /* field N found at a delimiter -> [fs, k); else if line HAS
               field N as its tail -> [fs, i); else line ends first */
            if (!hit) fe = (field == (unsigned)CUT_FIELD) ? i : fs;
            for (unsigned j = fs; j < fe; j++) vol2_out_ch(CUT_DATA[j]);
            if (CUT_DATA[i] == '\n') vol2_out_ch('\n');
            if (CUT_DATA[i] == 0) break;
            ls = i + 1;
        }
        i++;
    }
    vol2_flush();
    exit(0);
}
""",
    # sort FILE — ascending BYTewise line sort (C `>`, no locale, no -n).
    "sort": _LIBC_EXTERN + _VOL2_COMMON + r"""\
static const char *SORT_DATA;

static int sort_line_cmp(const char *a, const char *b) {
    /* lines are NUL-terminated snapshots in .bss-adjacent buffers */
    unsigned i = 0;
    while (a[i] && b[i] && a[i] == b[i]) i++;
    if (b[i] == 0 && a[i] != 0) return 1;
    if (a[i] == 0 && b[i] != 0) return -1;
    if (a[i] == b[i]) return 0;
    return (a[i] > b[i]) ? 1 : -1;
}

void _start(void) {
    /* snapshot the lines into static buffers (freestanding: fixed
       capacity 8 lines x 24 bytes — every fixture fits) */
    static char lines[8][24];
    static unsigned llen[8];
    unsigned n = 0;
    unsigned ls = 0, i = 0;
    while (1) {
        if (SORT_DATA[i] == '\n' || SORT_DATA[i] == 0) {
            /* snapshot [ls, i) — skip the empty tail snapshot when the
               data ends with '\n' (ls == i at EOF) */
            if (i > ls && n < 8) {
                unsigned L = i - ls;
                if (L > 23) L = 23;
                for (unsigned j = 0; j < L; j++) lines[n][j] = SORT_DATA[ls + j];
                lines[n][L] = 0;
                llen[n] = L;
                n++;
            }
            if (SORT_DATA[i] == 0) break;
            ls = i + 1;
        }
        i++;
    }
    /* insertion sort, bytewise */
    for (unsigned a = 1; a < n; a++) {
        char key[24];
        unsigned keylen = llen[a];
        for (unsigned j = 0; j <= keylen; j++) key[j] = lines[a][j];
        unsigned b = a;
        while (b > 0 && sort_line_cmp(lines[b - 1], key) > 0) {
            for (unsigned j = 0; j <= llen[b - 1]; j++) lines[b][j] = lines[b - 1][j];
            llen[b] = llen[b - 1];
            b--;
        }
        for (unsigned j = 0; j <= keylen; j++) lines[b][j] = key[j];
        llen[b] = keylen;
    }
    for (unsigned a = 0; a < n; a++) {
        for (unsigned j = 0; j < llen[a]; j++) vol2_out_ch(lines[a][j]);
        vol2_out_ch('\n');
    }
    vol2_flush();
    exit(0);
}
""",
}

# fixture table: 3 fixtures per tool; `output` is the byte-exact NATIVE
# POSIX reference (computed from the POSIX spec, the BK-10/BK-11 oracle
# strategy). Every tool carries at least one >16-byte output — the
# item-19 streaming premise (outputs exceed the BK-11 window).
COREUTILS2_FIXTURES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "grep": {
        "two_hits": {
            "data": "apple pie\nbanana bread\napple tart\ncherry\n",
            "pattern": "apple",
            # grep apple -> lines 1 and 3, terminators kept
            "output": "apple pie\napple tart\n",
        },
        "no_hits": {
            "data": "one\ntwo\nthree\n",
            "pattern": "zzz",
            "output": "",           # zero-output edge: cursor stays at base
        },
        "long_hit": {               # 26-byte output — exceeds the window
            "data": "no match here\nthe quick brown fox jumps\nalso nothing\n",
            "pattern": "quick",
            "output": "the quick brown fox jumps\n",
        },
    },
    "tr": {
        "lower_upper": {
            "data": "glyph pixel\n",
            "set1": "abcdefghijklmnopqrstuvwxyz",
            "set2": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "output": "GLYPH PIXEL\n",
        },
        "vowel_swap": {             # 34-byte output — exceeds the window
            "data": "the harmonious banana boats glide\n",
            "set1": "abcdefghijklmnopqrstuvwxyz",
            "set2": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "output": "THE HARMONIOUS BANANA BOATS GLIDE\n",
        },
        "punct": {
            "data": "a-b_c\n",
            "set1": "-_",
            "set2": "..",
            "output": "a.b.c\n",
        },
    },
    "tee": {
        "short": {
            "data": "hi\n",
            "output": "hi\n",
        },
        "passthrough_48": {         # 48 bytes = 3 full frames
            "data": "0123456789abcdefghijkl0123456789abcdefghijklmno\n",
            "output": "0123456789abcdefghijkl0123456789abcdefghijklmno\n",
        },
        "lines_31": {               # 31 bytes -> 2 frames, 1-byte pad tail
            "data": "alpha bravo charlie delta\neye\n",
            "output": "alpha bravo charlie delta\neye\n",
        },
    },
    "cut": {
        "field2": {
            "data": "root:x:0:0\nbin:x:1:1\n",
            "delim": ":",
            "field": 2,
            "output": "x\nx\n",
        },
        "field1_words": {           # 22-byte output — exceeds the window
            "data": "apple cherry\ndog elephant\n",
            "delim": " ",
            "field": 1,
            "output": "apple\ndog\n",
        },
        "missing_field": {          # 44-byte output — exceeds the window
            "data": "a:b:c:the fourth field of a long record line\nzz:yy:xx\n",
            "delim": ":",
            "field": 4,
            # POSIX cut: field 4 of line 1 (the long text), line 2 has
            # only 3 fields -> POSIX cut prints just '\n' for it
            "output": "the fourth field of a long record line\n\n",
        },
    },
    "sort": {
        "three_lines": {
            "data": "pear\napple\nbanana\n",
            "output": "apple\nbanana\npear\n",
        },
        "bytewise_numeric": {       # 10/9/100 — bytewise, NOT numeric
            "data": "100\n9\n10\n",
            "output": "10\n100\n9\n",
        },
        "prefix_order": {           # 26-byte output — exceeds the window
            "data": "delta\nalpha\nbeta\ncharlie\n",
            "output": "alpha\nbeta\ncharlie\ndelta\n",
        },
    },
}

COREUTILS2_TOOLS = ("grep", "tr", "tee", "cut", "sort")

# sanity: the table stays honest — 3 fixtures/tool, inside the ring,
# and per tool at least one output > 16 bytes (the streaming premise).
for _tool2, _fxs2 in COREUTILS2_FIXTURES.items():
    assert len(_fxs2) == 3, f"{_tool2}: expected 3 fixtures"
    assert any(len(_fx["output"]) > 16 for _fx in _fxs2.values()), (
        f"{_tool2}: no fixture exercises the streaming premise")
    for _n2, _fx2 in _fxs2.items():
        assert len(_fx2["output"].encode("ascii")) <= 256, (
            f"{_tool2}/{_n2}: exceeds the ring capacity")
del _tool2, _fxs2, _n2, _fx2


def coreutils2_tool_elf(tool: str, fixture_name: str, tmp: Path) -> bytes:
    """Compile the volume-port-#2 `tool` + fixture + the GH-23 spatial
    libc into a freestanding RV32I ELF (same compile contract as port
    #1 — shared gcc/shim, BK-24 streaming libc)."""
    if tool not in _VOL2_TOOL_SOURCES:
        raise KeyError(f"unknown coreutils2 tool: {tool}")
    fx = COREUTILS2_FIXTURES[tool][fixture_name]

    seed_lines = []
    for var, val in fx.items():
        if var in ("output", "exit"):
            continue
        if var in ("delim",):
            seed_lines.append(f"static char {tool}_{var} = '{val}';")
        elif var in ("field",):
            seed_lines.append(f"static long {tool}_{var} = {int(val)};")
        elif var in ("data_len", "a_len", "b_len"):
            seed_lines.append(f"static unsigned {tool}_{var} = {int(val)};")
        else:
            seed_lines.append(
                f'static const char *{tool}_{var} = "{_c_literal(val)}";')

    derived = []
    if tool == "tr":
        derived.append(f"static unsigned TR_LEN = {len(fx['data'])};")
    if tool == "tee":
        derived.append(f"static unsigned TEE_LEN = {len(fx['data'])};")

    alias_map = {
        "grep": {"GREP_PAT": f"{tool}_pattern", "GREP_DATA": f"{tool}_data"},
        "tr": {"TR_SET1": f"{tool}_set1", "TR_SET2": f"{tool}_set2",
               "TR_DATA": f"{tool}_data"},
        "tee": {"TEE_DATA": f"{tool}_data"},
        "cut": {"CUT_DATA": f"{tool}_data", "CUT_DELIM": f"{tool}_delim",
                "CUT_FIELD": f"{tool}_field"},
        "sort": {"SORT_DATA": f"{tool}_data"},
    }
    aliases = [f"#define {pub} {seed}"
               for pub, seed in alias_map[tool].items()]

    c_text = (
        "\n".join(seed_lines) + "\n"
        + "\n".join(derived) + "\n"
        + "\n".join(aliases) + "\n"
        + _VOL2_TOOL_SOURCES[tool]
    )

    from tests.test_gh23_libc_runtime import LIBC_C, SHIM_S

    src = tmp / f"vol2_{tool}.c"
    libc = tmp / "gh23_libc.c"
    asm = tmp / "shim.S"
    elf = tmp / f"vol2_{tool}.elf"
    src.write_text(c_text)
    libc.write_text(LIBC_C)
    asm.write_text(SHIM_S)

    objs = []
    for i, o in enumerate((src, libc)):
        obj = tmp / f"vol2_{tool}_{i}.o"
        proc = subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
             "-ffixed-x28", "-ffixed-x29", "-ffixed-x30", "-ffixed-x31",
             "-nostdlib",
             "-fno-builtin", "-ffreestanding", "-w", "-c", str(o),
             "-o", str(obj)],
            capture_output=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(
                f"cc failed for {o.name}:\n{proc.stderr.decode()}")
        objs.append(obj)
    proc = subprocess.run(
        [_GCC, "-march=rv32i", "-mabi=ilp32",
         "-ffixed-x28", "-ffixed-x29", "-ffixed-x30", "-ffixed-x31", "-nostdlib",
         "-Wl,-Ttext=0x0", "-Wl,-N", "-Wl,--entry=_start", "-w",
         *map(str, objs), str(asm), "-o", str(elf)],
        capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"link failed:\n{proc.stderr.decode()}")
    return elf.read_bytes()
