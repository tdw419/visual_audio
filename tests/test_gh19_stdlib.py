#!/usr/bin/env python3
"""GH-19 stdlib tile pack — the adversarial matrix gate.

Per systems/GLYPH_SELF_HOSTING_ROADMAP.md GH-19: ten C leaf routines
compiled rv32i, transpiled, IR-verified, ingest()-admitted (IRContract:
clobbers ⊆ {scratch, return_reg}, r31 preserved), each with the full
adversarial matrix, WORD-EXACT vs the native host GCC C reference.

Matrix (roadmap row, verbatim coverage):
  strlen/strcmp   empty "", 1-byte, max-length-64 boundary,
                  mismatched suffix
  memcpy/memmove  0-length, 1-word, unaligned offsets, overlapping
                  src/dst (dst=src+1 AND src=dst+1)
  divmod          divide by 1, by self, negative dividend/divisor
                  (C99 truncation toward zero), zero divisor
                  (0xFFFFFFFF status, no crash)
  atoi/itoa       negative "-12345", 0, INT32_MAX, INT32_MIN

Every golden value flows from executing the SAME C source on the host
(native_run); the glyph oracle must match it word-exactly, register by
register, with r31 preserved. Zero model calls anywhere.
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "tools"))

from tools.gh19_stdlib import (                       # noqa: E402
    Case, TILES, build_tile, ingest_leg, ir_leg, native_run, oracle_leg,
    pack_bytes, words_of,
    STR_A_BYTE, STR_B_BYTE, DST_BYTE, ITOA_BUF_BYTE,
)

TILE_TEXTS = {}


def tile(name: str) -> str:
    """Build (once per session) and return the transpiled tile text."""
    if name not in TILE_TEXTS:
        TILE_TEXTS[name] = build_tile(name)
    return TILE_TEXTS[name]


def gate(name, cases):
    """The full four-leg gate for one tile.

    cases: list of (Case, native_call, native_prints). Each case runs:
      leg 1 NATIVE  cc-compiled host run produces the golden words
      leg 2 ORACLE  GlyphCPUv2 word-exact vs the golden, r31 preserved
    Then once per tile:
      leg 3 IR GATE raise + StaticVerifier, IRContract assertions
      leg 4 INGEST  autoatlas.ingest() admission, byte-equal text
    """
    spec = TILES[name]
    text = tile(name)
    for case, native_call, native_prints in cases:
        golden = native_run(spec.c_source, native_call, native_prints)
        oracle_leg(name, text, case, golden)
    ir_leg(name, text)
    case0, call0, prints0 = cases[0]
    golden0 = native_run(spec.c_source, call0, prints0)[0]
    arg0 = case0.args[0] if case0.args else 0
    ingest_leg(name, text, spec.contract, golden0, arg0)


def c_string_literal(data: bytes) -> str:
    assert data.endswith(b"\x00")
    body = data[:-1].decode("ascii")
    body = body.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{body}"'


def c_byte_array(data: bytes) -> str:
    return ("{" + ",".join(str(b) for b in data) + "}")

S_EMPTY = b"\x00"
S_ONE = b"Q\x00"
S_MAX = b"a" * 64 + b"\x00"
S_MIX = b"hello!\x00"
S_DIFF = b"hellp!\x00"


def test_strlen_matrix():
    """strlen: empty, 1-byte, max-length-64 boundary, unaligned base."""
    cases = [
        (Case("empty", [STR_A_BYTE], pack_bytes(S_EMPTY), []),
         f'const char *s = {c_string_literal(S_EMPTY)};',
         ["strlen_c(s)"]),
        (Case("one_byte", [STR_A_BYTE], pack_bytes(S_ONE), []),
         f'const char *s = {c_string_literal(S_ONE)};',
         ["strlen_c(s)"]),
        (Case("max_len_64", [STR_A_BYTE], pack_bytes(S_MAX), []),
         f'static const char s[] = {c_string_literal(S_MAX)};',
         ["strlen_c(s)"]),
        (Case("mixed", [STR_A_BYTE], pack_bytes(S_MIX), []),
         f'const char *s = {c_string_literal(S_MIX)};',
         ["strlen_c(s)"]),
        (Case("unaligned_base", [STR_A_BYTE + 1],
              pack_bytes(S_MIX, STR_A_BYTE + 1), []),
         f'const char *s = {c_string_literal(S_MIX)};',
         ["strlen_c(s)"]),
    ]
    gate("strlen_c", cases)


def test_strcmp_matrix():
    """strcmp: empty vs empty, equal, mismatched suffix (both orders),
    prefix, max-length-64 equal."""
    a64 = b"m" * 64 + b"\x00"
    b64 = b"m" * 64 + b"\x00"

    def dual(a_bytes, b_bytes):
        return {**pack_bytes(a_bytes),
                **pack_bytes(b_bytes, STR_B_BYTE)}

    def native_row(a_lit, b_lit):
        return (f'const char *a = {a_lit}; const char *b = {b_lit};',
                ["strcmp_c(a, b)"])

    cases = [
        (Case("empty_vs_empty", [STR_A_BYTE, STR_B_BYTE],
              dual(S_EMPTY, S_EMPTY), []),
         *native_row(c_string_literal(S_EMPTY),
                     c_string_literal(S_EMPTY))),
        (Case("equal", [STR_A_BYTE, STR_B_BYTE],
              dual(S_MIX, S_MIX), []),
         *native_row(c_string_literal(S_MIX),
                     c_string_literal(S_MIX))),
        (Case("mismatched_suffix", [STR_A_BYTE, STR_B_BYTE],
              dual(S_MIX, S_DIFF), []),
         *native_row(c_string_literal(S_MIX),
                     c_string_literal(S_DIFF))),
        (Case("mismatched_suffix_reversed", [STR_A_BYTE, STR_B_BYTE],
              dual(S_DIFF, S_MIX), []),
         *native_row(c_string_literal(S_DIFF),
                     c_string_literal(S_MIX))),
        (Case("prefix", [STR_A_BYTE, STR_B_BYTE],
              dual(S_ONE, S_MIX), []),
         *native_row(c_string_literal(S_ONE),
                     c_string_literal(S_MIX))),
        (Case("max_len_64_equal", [STR_A_BYTE, STR_B_BYTE],
              dual(a64, b64), []),
         f'static const char a[] = {c_string_literal(a64)}; '
         f'static const char b[] = {c_string_literal(b64)};',
         ["strcmp_c(a, b)"]),
    ]
    gate("strcmp_c", cases)


# ══ batch 2: memcpy + memmove ════════════════════════════════════════

COPY_SRC = b"PACKED-PAYLOAD-009\x00"


def test_memcpy_matrix():
    """memcpy: 0-length, 1-word, unaligned offsets, word-spanning."""
    spec = TILES["memcpy_c"]
    text = tile("memcpy_c")
    data = COPY_SRC + b"#" * 16
    dst = DST_BYTE

    def one(cname, src_off, n):
        src_addr = STR_A_BYTE + 4 + src_off
        loads = words_of(dst, max(n, 1))[:3]
        # data is seeded at the window base (STR_A_BYTE+4) so data[src_off]
        # lands exactly at src_addr — what the tile reads and what the
        # native driver's `s + src_off` indexes.
        case = Case(cname, [dst, src_addr, n],
                    pack_bytes(data, STR_A_BYTE + 4), loads,
                    ret_override=dst)
        driver = (f"static const unsigned char s[] = {c_byte_array(data)};"
                  " unsigned char buf[64] = {0};"
                  f" memcpy_c(buf, s + {src_off}, {n});")
        prints = [f"*(const unsigned *)(buf + {4 * i})"
                  for i in range(len(loads))]
        return case, driver, prints

    cases = [
        one("zero_len", 0, 0),
        one("one_word", 0, 4),
        one("unaligned_src", 1, 6),
        one("unaligned_src_word_span", 3, 9),
    ]
    for case, native_call, prints in cases:
        golden = native_run(spec.c_source, native_call, prints)
        oracle_leg("memcpy_c", text, case, golden)
    ir_leg("memcpy_c", text)
    case0, call0, prints0 = cases[0]
    golden0 = native_run(spec.c_source, call0, prints0)[0]
    ingest_leg("memcpy_c", text, spec.contract, golden0,
               case0.args[0])


def test_memmove_matrix():
    """memmove: 0-length, 1-word, unaligned — plus overlap in
    test_memmove_overlap_matrix."""
    spec = TILES["memmove_c"]
    text = tile("memmove_c")
    data = COPY_SRC + b"#" * 16
    dst = DST_BYTE

    def one(cname, src_off, n):
        src_addr = STR_A_BYTE + 4 + src_off
        loads = words_of(dst, max(n, 1))[:3]
        # same seed-base rule as memcpy (data[src_off] must land at src_addr)
        case = Case(cname, [dst, src_addr, n],
                    pack_bytes(data, STR_A_BYTE + 4), loads,
                    ret_override=dst)
        driver = (f"static const unsigned char s[] = {c_byte_array(data)};"
                  " unsigned char buf[64] = {0};"
                  f" memmove_c(buf, s + {src_off}, {n});")
        prints = [f"*(const unsigned *)(buf + {4 * i})"
                  for i in range(len(loads))]
        return case, driver, prints

    cases = [
        one("zero_len", 0, 0),
        one("one_word", 0, 4),
        one("unaligned_src", 2, 7),
    ]
    for case, native_call, prints in cases:
        golden = native_run(spec.c_source, native_call, prints)
        oracle_leg("memmove_c", text, case, golden)
    ir_leg("memmove_c", text)
    case0, call0, prints0 = cases[0]
    golden0 = native_run(spec.c_source, call0, prints0)[0]
    ingest_leg("memmove_c", text, spec.contract, golden0,
               case0.args[0])


@pytest.mark.parametrize("delta", [1, -1])
@pytest.mark.parametrize("n", [4, 12])
def test_memmove_overlap_matrix(delta, n):
    """memmove overlap: dst=src+1 AND src=dst+1 (dst > src / src > dst),
    1-word and multi-word — dst buffer words checked word-exact."""
    spec = TILES["memmove_c"]
    text = tile("memmove_c")
    src = b"ABCDEFGHIJKLMNOP"
    base = STR_A_BYTE + 4                    # word-aligned window
    dst_addr = base + delta
    loads = words_of(base, n)[:3]
    case = Case(f"overlap_{delta}_n{n}", [dst_addr, base, n],
                pack_bytes(src, base), loads,
                ret_override=dst_addr)
    driver = (f"static const unsigned char s[] = {c_byte_array(src)};"
              " unsigned char buf[32] = {0};"
              f" for (int i = 0; i < {len(src)}; i++) buf[i] = s[i];"
              f" memmove_c(buf + {delta}, buf, {n});")
    prints = [f"*(const unsigned *)(buf + {4 * i})"
              for i in range(len(loads))]
    golden = native_run(spec.c_source, driver, prints)
    oracle_leg("memmove_c", text, case, golden)


# ══ batch 3: divmod ══════════════════════════════════════════════════

DIVMOD_REGS = [10, 11]          # small-struct return: q in a0, r in a1


def test_divmod_matrix():
    """divmod: /1, /self, negative dividend, negative divisor, both
    negative (C99 truncation toward zero), zero divisor (0xFFFFFFFF
    status quotient, no crash)."""
    spec = TILES["divmod_c"]
    text = tile("divmod_c")
    INT32_MIN = -0x80000000

    def one(cname, a, d):
        case = Case(cname, [a, d])
        driver = (f"volatile int A = {a}; volatile int D = {d};",
                  ["divmod_c(A, D).q", "divmod_c(A, D).r"])
        return case, driver

    cases = [
        one("by_one", 12345, 1),
        one("by_self", 12345, 12345),
        one("neg_dividend", -100, 7),
        one("neg_divisor", 100, -7),
        one("both_negative", -100, -7),
        one("neg_dividend_neg_divisor_exact", -81, -9),
        one("c99_truncation", -7, 2),          # q=-3 (not -4), r=-1
        one("int32_min_by_one", INT32_MIN, 1),
    ]
    for case, (driver, native_prints) in cases:
        golden = native_run(spec.c_source, driver, native_prints)
        oracle_leg("divmod_c", text, case, golden,
                   golden_regs=DIVMOD_REGS)
    ir_leg("divmod_c", text)

    # zero divisor: status leg — no crash, q == 0xFFFFFFFF, r == 0
    case = Case("zero_divisor", [12345, 0])
    driver = "volatile int A = 12345; volatile int D = 0;"
    golden = native_run(spec.c_source, driver,
                        ["divmod_c(A, D).q", "divmod_c(A, D).r"])
    assert golden == [0xFFFFFFFF, 0], \
        f"zero-divisor contract: native returned {golden}"
    oracle_leg("divmod_c", text, case, golden, golden_regs=DIVMOD_REGS)
    case0 = cases[0][0]
    golden0 = native_run(spec.c_source, cases[0][1][0],
                         cases[0][1][1])[0]
    ingest_leg("divmod_c", text, spec.contract, golden0, case0.args[0])


# ══ batch 4: itoa + atoi ═════════════════════════════════════════════

def test_itoa_matrix():
    """itoa: "-12345", 0, INT32_MAX, INT32_MIN. The length golden comes
    from the host run; the buffer words are checked word-exact against
    the host's printed buffer words (12 bytes = 3 words, zero-filled)."""
    spec = TILES["itoa_c"]
    text = tile("itoa_c")
    loads = words_of(ITOA_BUF_BYTE, 12)[:3]

    def one(cname, value):
        case = Case(cname, [value, ITOA_BUF_BYTE], {}, loads)
        driver = (f"volatile int V = {value};"
                  " char buf[16] = {0}; int n = itoa_c(V, buf);"
                  " (void)n;")
        prints = (["n"]
                  + [f"*(const unsigned *)(buf + {4 * i})"
                     for i in range(3)])
        return case, driver, prints

    INT32_MAX = 0x7FFFFFFF
    INT32_MIN = -0x80000000
    cases = [
        one("negative", -12345),
        one("zero", 0),
        one("int32_max", INT32_MAX),
        one("int32_min", INT32_MIN),
        one("positive", 987654),
    ]
    for case, native_call, prints in cases:
        golden = native_run(spec.c_source, native_call, prints)
        # golden[0] = length (return), golden[1:] = the buffer words;
        # ret_override=golden[0] is already the natural expectation.
        oracle_leg("itoa_c", text, case, golden)
    ir_leg("itoa_c", text)
    case0, call0, prints0 = cases[0]
    golden0 = native_run(spec.c_source, call0, prints0)[0]
    ingest_leg("itoa_c", text, spec.contract, golden0, case0.args[0])


def test_itoa_string_content():
    """itoa end-to-end: the glyph-written buffer must decode to the
    same decimal STRING the host C produced (not just equal words by
    construction) — compare against Python's str()."""
    spec = TILES["itoa_c"]
    text = tile("itoa_c")
    for value, expect_str in ((-12345, "-12345"), (0, "0"),
                              (0x7FFFFFFF, "2147483647"),
                              (-0x80000000, "-2147483648")):
        loads = words_of(ITOA_BUF_BYTE, 12)[:3]
        case = Case(f"content_{value}", [value, ITOA_BUF_BYTE], {},
                    loads)
        golden = native_run(
            spec.c_source,
            f"volatile int V = {value};"
            " char buf[16] = {0}; int n = itoa_c(V, buf); (void)n;",
            ["n"] + [f"*(const unsigned *)(buf + {4 * i})"
                     for i in range(3)])
        oracle_leg("itoa_c", text, case, golden)
        # decode what the TILE actually wrote: pack the golden words'
        # bytes and compare with C's canonical decimal
        raw = b"".join(v.to_bytes(4, "little") for v in golden[1:])
        assert raw.decode().split("\x00")[0] == expect_str, \
            f"itoa({value}) wrote {raw!r}, want {expect_str!r}"


def test_atoi_matrix():
    """atoi: "-12345", "0", INT32_MAX, INT32_MIN, plus/unary edge,
    trailing garbage stops the scan (C semantics)."""
    spec = TILES["atoi_c"]
    text = tile("atoi_c")

    def one(cname, s_repr):
        case = Case(cname, [STR_A_BYTE], pack_bytes(s_repr), [])
        driver = (f"const char *s = {c_string_literal(s_repr)};",
                  ["atoi_c(s)"])
        return case, driver

    cases = [
        one("negative", b"-12345\x00"),
        one("zero", b"0\x00"),
        one("int32_max", b"2147483647\x00"),
        one("int32_min", b"-2147483648\x00"),
        one("leading_zeroes", b"00042\x00"),
        one("stops_at_nondigit", b"12ab\x00"),
    ]
    for case, (native_call, prints) in cases:
        golden = native_run(spec.c_source, native_call, prints)
        oracle_leg("atoi_c", text, case, golden)
    ir_leg("atoi_c", text)
    case0, (call0, prints0) = cases[0]
    golden0 = native_run(spec.c_source, call0, prints0)[0]
    ingest_leg("atoi_c", text, spec.contract, golden0, case0.args[0])


# ══ batch 5: popcount + rotr32 + rotl32 ══════════════════════════════

def test_popcount_matrix():
    """popcount: 0, all-ones, alternating, single bit."""
    spec = TILES["popcount_c"]
    text = tile("popcount_c")
    vectors = [(0, "0"), (0xFFFFFFFF, "-1"), (0xF0F0F0F0, "-252645136"),
               (1, "1"), (0x80000000, "-2147483648"),
               (0xDEADBEEF, "-559038737")]
    cases = []
    for i, (v, _label) in enumerate(vectors):
        case = Case(f"pop_{i}", [int(v) & 0xFFFFFFFF])
        driver = f"volatile unsigned X = {v}U;"
        cases.append((case, driver, ["popcount_c(X)"]))
    for case, native_call, prints in cases:
        golden = native_run(spec.c_source, native_call, prints)
        oracle_leg("popcount_c", text, case, golden)
    ir_leg("popcount_c", text)
    case0, call0, prints0 = cases[0]
    golden0 = native_run(spec.c_source, call0, prints0)[0]
    ingest_leg("popcount_c", text, spec.contract, golden0, case0.args[0])


@pytest.mark.parametrize("x,n", [
    (0xF0F0F0F0, 4), (1, 1), (0xDEADBEEF, 8), (0xFFFFFFFF, 16),
    (0x00000001, 31), (0x12345678, 0), (0x80000000, 7),
])
def test_rotr32_matrix(x, n):
    spec = TILES["rotr32_c"]
    text = tile("rotr32_c")
    case = Case(f"rotr_{n}_{x & 0xFFFFFFFF:08x}", [x, n])
    driver = f"volatile unsigned X = {x}U; volatile int N = {n};"
    golden = native_run(spec.c_source, driver, ["rotr32_c(X, N)"])
    oracle_leg("rotr32_c", text, case, golden)
    if n == 0:      # one-time IR + ingest legs (cheap, deterministic)
        ir_leg("rotr32_c", text)
        ingest_leg("rotr32_c", text, spec.contract, golden[0], x)


@pytest.mark.parametrize("x,n", [
    (0xF0F0F0F0, 4), (1, 1), (0xDEADBEEF, 8), (0xFFFFFFFF, 16),
    (0x00000001, 31), (0x12345678, 0), (0x80000000, 7),
])
def test_rotl32_matrix(x, n):
    spec = TILES["rotl32_c"]
    text = tile("rotl32_c")
    case = Case(f"rotl_{n}_{x & 0xFFFFFFFF:08x}", [x, n])
    driver = f"volatile unsigned X = {x}U; volatile int N = {n};"
    golden = native_run(spec.c_source, driver, ["rotl32_c(X, N)"])
    oracle_leg("rotl32_c", text, case, golden)
    if n == 0:
        ir_leg("rotl32_c", text)
        ingest_leg("rotl32_c", text, spec.contract, golden[0], x)
