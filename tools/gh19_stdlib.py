#!/usr/bin/env python3
"""gh19_stdlib.py — GH-19 stdlib tile pack: the in-image libc leaf set.

Ten C leaf routines (strlen, strcmp, memcpy, memmove, divmod, itoa, atoi,
popcount, rotr32, rotl32) compiled with riscv64-unknown-elf-gcc
(-march=rv32i -mabi=ilp32), transpiled to Glyph ISA v2, IR-verified
(autoatlas lane policy: r31 preserved, scratch ⊆ {r26..r30}), and
admitted through autoatlas.ingest() (family 'ingested_c'). Every tile
ships an oracle receipt per the roadmap's ADVERSARIAL MATRIX, word-exact
against the native host GCC C reference.

Memory model (G6): RAM is word-indexed; the transpiler lowers byte
addresses via byte_to_word_mem (addr >> 2) with byte lanes decoded
in-tile (LBU/SB RMW). Fixtures therefore pack bytes into seed words
little-endian per lane — pack_bytes() does that packing so fixtures read
as C.

Verification legs per tile (deterministic, zero model calls):

  1. NATIVE   the same C source compiled and run on the host (cc).
              Every golden value in the matrix flows from this
              execution — the native run IS the reference.
  2. ORACLE   the transpiled tile run on GlyphCPUv2 via run_oracle,
              every result register word-exact vs NATIVE, r31
              preserved (== the harness callstack value at HALT).
  3. IR GATE  raise_lines_to_ir with the autoatlas policy +
              StaticVerifier.verify(); asserts preserves == ['r31'],
              scratch_pool ∩ preserves == ∅, callstack r31. The tile
              body raises with the leading :atlas_<name> alias label
              stripped (the raiser fuses the FIRST label into the
              entry block; the transpiler emits the entry pc label
              immediately after the function label, so the alias never
              carries code and is not part of the verified body).
              Atlas-storage tiles are verified for contract/shape; the
              24-instr window budget is the GH-9 mailbox lane's, not
              the atlas's (roadmap throughput-levers note).
  4. INGEST   autoatlas.ingest() (runner=None) with a deterministic
              stub escalate that returns the transpiled tile — the
              whitelist -> verification -> admission loop with zero
              model calls. res.code == 'OK' and the admitted text
              byte-equals the transpiled artifact; atlas.register()
              then persists it (gate 2: register runs the tile).

Batch order (one commit per batch, smallest risk first):
  (1) strlen+strcmp, (2) memcpy+memmove, (3) divmod,
  (4) itoa+atoi, (5) popcount+rotr32+rotl32.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_TOOLS = Path(__file__).resolve().parent
_REPO = _TOOLS.parent
for _p in (str(_REPO), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from glyph_ir import StaticVerificationError            # noqa: E402
from rv64i_to_glyph import (                            # noqa: E402
    PTR_TABLE_BASE, assemble_glyph_to_pixels,
    transpile_elf_to_glyph)
from tools.glyph_gpt.autoatlas import (                 # noqa: E402
    _autoatlas_policy, ingest)
from tools.glyph_gpt.oracle import run_oracle           # noqa: E402

RV_GCC = "riscv64-unknown-elf-gcc"

# ── glyph word map used by every fixture (clear of reserved ranges) ──
# Reserved: 750-760 argv, 800-896 mailbox, 950-968 status, 1024-1280 FS.
# Fixture buffers live at WORDS 200..749 (byte addresses 0x320..0xBB8),
# spaced 256 bytes apart so byte-lane packing can never collide: the
# max fixture string is 65 bytes (64 chars + NUL), and a colliding word
# would silently overwrite the other buffer's NUL lane (this exact bug
# bit the max-length-64 strcmp fixture during development).
STR_A_BYTE = 0x400                       # string/buffer A (word 256)
STR_B_BYTE = 0x500                       # string/buffer B (word 320)
DST_BYTE = 0x600                         # copy destination   (word 384)
ITOA_BUF_BYTE = 0x700                    # itoa scratch       (word 448)
CALLSTACK = 30000                        # harness r31 seed
STACK_TOP_BYTE = 0x1C00                  # RV sp seed (word 1792): above the
# fixture buffers (bytes 0x320..0xBB8), below the pointer table (0x2000);
# frames grow DOWN and the largest tile frame is 32 bytes, so the stack
# can never collide with either. Without a valid sp the prologue's
# `addi sp, sp, -32` starts at 0, wraps to 0xffffffe0, and the first
# `sw ra, 28(sp)` lowers to an out-of-bounds store (0x3fffffff) — the
# CPU faults with no-halt/"faulted" and the oracle hangs to its cap.


def pack_bytes(data: bytes, base_byte: int = STR_A_BYTE) -> Dict[int, int]:
    """Pack bytes into the little-endian byte lanes of glyph words,
    exactly how the transpiled LBU/SB machinery reads/writes them."""
    words: Dict[int, int] = {}
    for i, b in enumerate(data):
        addr = base_byte + i
        w = addr >> 2
        shift = (addr & 3) * 8
        words[w] = (words.get(w, 0) | (b << shift)) & 0xFFFFFFFF
    return words


def words_of(byte_addr: int, nbytes: int) -> List[int]:
    """The glyph word indices covering [byte_addr, byte_addr + nbytes)."""
    first = byte_addr >> 2
    last = (byte_addr + max(nbytes, 1) - 1) >> 2
    return list(range(first, last + 1))


def lit(v: int) -> str:
    """A 32-bit literal the glyph assembler accepts (decimal, or hex for
    the negative/high half where two's complement matters)."""
    return str(v & 0xFFFFFFFF) if 0 <= v <= 0x7FFFFFFF \
        else f"0x{v & 0xFFFFFFFF:x}"


# ── leg 1: native host reference (the oracle's oracle) ───────────────
def native_run(c_source: str, call: str,
               prints: List[str]) -> List[int]:
    """Compile C for the host, run it, return the printed words.

    `call` is the C statement invoking the function; `prints` are the C
    expressions printed one per line AFTER the call (the return value
    and any buffer words the fixture checks). Every golden in the
    matrix comes from this execution.
    """
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # ONE translation unit: the tile C text, then the driver's
        # main() appended (prototypes are not needed — main comes after
        # the definitions). The compiled artifact thus executes exactly
        # the tile source as the reference run.
        main_c = (c_source + "\n"
                  "#include <stdio.h>\n"
                  "int main(void) {\n"
                  f"    {call}\n"
                  + "".join(f'    printf("%ld\\n", (long)(unsigned)({e}));\n'
                            for e in prints)
                  + "    return 0;\n}\n")
        (tdp / "main.c").write_text(main_c)
        subprocess.run(["cc", "-w", str(tdp / "main.c"),
                        "-o", str(tdp / "host")],
                       check=True, capture_output=True, timeout=60)
        out = subprocess.run([str(tdp / "host")], capture_output=True,
                             check=True, timeout=60)
        return [int(line) & 0xFFFFFFFF
                for line in out.stdout.decode().split()]


# ── legs 2-4 inputs: rv32i compile + transpile ───────────────────────
def compile_and_transpile(c_source: str, func_symbol: str,
                          name: str, cols_instrs: int = 64) -> str:
    """The SB-2 pipeline: rv32i compile -> transpile -> slice the target
    function -> namespace labels -> :atlas_<name> tile text."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "f.c").write_text(c_source)
        subprocess.run([RV_GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
                        "-nostdlib", "-fno-builtin", "-ffreestanding",
                        "-w", "-c", str(tdp / "f.c"), "-o",
                        str(tdp / "f.o")], check=True, capture_output=True,
                       timeout=60)
        # -lgcc: pure-rv32i targets have no M extension, so / and % lower
        # to __divsi3/__modsi3 libgcc calls; -nostdlib alone leaves them
        # undefined at link. -lgcc supplies them as pure rv32i code (no
        # M-extension instructions in the linked output — verified with
        # objdump), keeping the tile 100% rv32i.
        subprocess.run([RV_GCC, "-march=rv32i", "-mabi=ilp32", "-nostdlib",
                        "-Wl,-Ttext=0x0", f"-Wl,--entry={func_symbol}",
                        "-w", str(tdp / "f.o"), "-o", str(tdp / "f.elf"),
                        "-lgcc"],
                       check=True, capture_output=True, timeout=60)
        glyph = transpile_elf_to_glyph((tdp / "f.elf").read_bytes(),
                                       entry_symbol=func_symbol,
                                       byte_to_word_mem=True,
                                       cols_instrs=cols_instrs)
    lines = glyph.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines)
                     if ln.strip() == f":{func_symbol}")
    except StopIteration:
        raise ValueError(f"transpiler emitted no ':{func_symbol}' label")
    body = "\n".join(lines[start + 1:]).rstrip("\n")
    body = re.sub(r":(pc_[0-9a-fA-F]+|__[A-Za-z0-9_]+)", rf":{name}_\1",
                  body)
    return f":atlas_{name}\n{body}\n"


def tile_body(tile_text: str) -> List[str]:
    """The tile text without the leading :atlas_<name> alias label —
    exactly what the IR gate raises (see module docstring)."""
    lines = tile_text.splitlines()
    assert lines and lines[0].startswith(":atlas_"), "tile must be labeled"
    return lines[1:]


def instr_count(tile_text: str) -> int:
    return len([ln for ln in tile_text.splitlines()
                if ln.strip() and not ln.strip().startswith(":")
                and not ln.strip().startswith("#")])


# ── leg 2: oracle (word-exact vs the native goldens) ─────────────────
# ── leg 2: oracle (word-exact vs the native goldens) ─────────────────
def _pointer_table_seeds(harness_text: str, name: str,
                         func_symbol: str) -> Dict[int, int]:
    """Seed words for the transpiler's dynamic-jump pointer table.

    GCC lowers computed jumps (libgcc __divsi3/__modsi3 tail-calls,
    switch tables) to `jr`; the transpiler routes those through JMPR +
    a table at PTR_TABLE_BASE mapping RV word index -> packed glyph PC.
    The table is DATA the run harness must seed (same pattern as
    tests/test_rv64i_to_glyph_printf.py) — without it the `LD` reads 0
    and GlyphCPUv2 jumps to (0,0) forever ("no-halt: N steps").

    Mechanism: re-assemble the FULL harness+tile text; the tile's
    renamed pc labels (:<name>_pc_<rvpc>) resolve to their glyph
    coordinates; the label's embedded rvpc gives the RV word index, so
    no ELF round-trip is needed.
    """
    _, coords = assemble_glyph_to_pixels(harness_text, cols_instrs=64,
                                         min_rows=16)
    seeds: Dict[int, int] = {}
    prefix = f":{name}_pc_"
    for lbl, (col, row) in coords.items():
        if not lbl.startswith(prefix):
            continue
        try:
            rv_pc = int(lbl[len(prefix):], 16)
        except ValueError:
            continue
        packed = (row & 0xFFFF) << 16 | (col & 0xFFFF)
        seeds[(PTR_TABLE_BASE >> 2) + (rv_pc >> 2)] = packed
    return seeds



@dataclass
class Case:
    """One adversarial vector.

    args         a0..a2 as C would receive them (ints; masked to 32 bits)
    seed_words   glyph words preloaded into RAM before step 0
    load_words   glyph word addresses the harness loads into r12, r13,
                 r15 (in order) after the CALL — buffer fixtures check
                 memory through registers because the oracle's contract
                 surface is registers.
    ret_override when set, replaces golden[0] as the expected r10 (used
                 by the copy tiles: C mandates memcpy/memmove return
                 dst, so the fixture layout — not the host's heap
                 addresses — is the reference for that register).
    """
    name: str
    args: List[int] = field(default_factory=list)
    seed_words: Dict[int, int] = field(default_factory=dict)
    load_words: List[int] = field(default_factory=list)
    ret_override: Optional[int] = None


def oracle_leg(name: str, tile_text: str, case: Case,
               golden: List[int], golden_regs: Optional[List[int]] = None
               ) -> None:
    """Run one vector on GlyphCPUv2; every checked register must match
    its golden word-exactly, and r31 must be preserved.

    golden      the values, in order (return first, then loaded words)
    golden_regs the register for each golden (default r10 then
                r12/r13/r15 for each loaded word); divmod's struct
                return uses (r10, r11). A shorter golden list is
                accepted: only the first len(golden) registers are
                checked (e.g. zero-length copies load an all-zero word
                that is constant anyway — checking r10 alone is exact).
    """
    regs = golden_regs or [10] + [12, 13, 15][:len(case.load_words)]
    assert len(golden) <= len(regs), \
        f"{name}/{case.name}: golden {golden} vs regs {regs}"
    if case.ret_override is not None:
        # PREPEND, not replace: golden[0:] are the loaded-word goldens;
        # the copy tiles' return register (dst) is an EXTRA expectation.
        golden = [case.ret_override] + list(golden)
    regs = regs[:len(golden)]
    lines = [f"LDI r31 {CALLSTACK}",
             # RV ABI: sp must be valid on entry. Tiles with stack frames
             # (divmod's spills, libgcc saves) compute slots as sp - k;
             # an unseeded sp=0 wraps negative and the byte-lane `>> 2`
             # turns the wrapped address into an OOB word.
             f"LDI r2 {STACK_TOP_BYTE}"]
    for i, a in enumerate(case.args):
        lines.append(f"LDI r{10 + i} {lit(a)}")
    lines.append(f"CALL :atlas_{name}")
    for out_reg, waddr in zip((12, 13, 15), case.load_words):
        lines.append(f"LDI r14 {waddr}")
        lines.append(f"LD r{out_reg} r14")
    lines.append("HALT")
    expect = {r: v for r, v in zip(regs, golden)}
    text = ":__entry\n" + "\n".join(lines) + "\n" + tile_text
    # computed jumps (jr) need the dynamic-jump pointer table seeded
    # (libgcc division tail-calls, switch tables). Tiles with no
    # computed jumps simply produce no seeds — table stays empty.
    seeds = dict(case.seed_words)
    seeds.update(_pointer_table_seeds(text, name, name))
    res = run_oracle(text, cols_instrs=64,
                     expect_registers=expect,
                     seed_memory=seeds)
    assert res.passed, f"{name}/{case.name}: {res.error}"
    r31 = (res.registers or [0] * 32)[31]
    assert r31 == CALLSTACK, \
        f"{name}/{case.name}: r31 clobbered: {r31:#x}"


# ── leg 3: the IR gate (contract/shape) ──────────────────────────────
def ir_leg(name: str, tile_text: str) -> None:
    """Raise the tile body with the autoatlas policy and run the
    StaticVerifier; assert the IRContract (r31 preserved, clobber set
    ⊆ scratch ∪ {return reg}). Raises StaticVerificationError on a
    shape violation."""
    import glyph_ir as gi
    body = tile_body(tile_text)
    window = max(instr_count(tile_text), 1)   # atlas storage, not mailbox
    mod = gi.raise_lines_to_ir(body, name=f"gh19_{name}",
                               policy=_autoatlas_policy(64),
                               window_max_words=window)
    gi.StaticVerifier(mod).verify()
    clobbers = set(mod.lowering.scratch_pool)
    assert mod.contract.preserves == ["r31"], mod.contract.preserves
    assert not (clobbers & set(mod.contract.preserves)), \
        "scratch pool clobbers a preserved register"
    assert mod.lowering.callstack_reg == "r31"


# ── leg 4: ingest admission (deterministic, model-free) ──────────────
def ingest_leg(name: str, tile_text: str, contract: str,
               golden0: int, arg0: int) -> None:
    """autoatlas.ingest() with the IRContract admission path: whitelist
    ('ingested_c') -> escalate (stubbed with the transpiled tile — zero
    model calls) -> verified -> OK. The admitted text must byte-equal
    the transpiled artifact, and atlas.register() must accept it."""
    from tools.glyph_gpt import autoatlas as aa
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.escalate import EscalationResult, OracleResult

    def _stub(*_a, **_k):
        return EscalationResult(contract=contract, verified=True,
                                attempts=1, glyph_text=tile_text,
                                oracle=OracleResult(passed=True))

    saved = aa.escalate
    aa.escalate = _stub
    try:
        atlas = build_default_atlas()
        res = ingest(atlas, name, "ingested_c", contract,
                     {10: golden0 & 0xFFFFFFFF},
                     input_registers={10: arg0 & 0xFFFFFFFF})
    finally:
        aa.escalate = saved
    assert res.code == "OK", f"{name}: {res.code}: {res.detail}"
    assert res.ok
    assert res.glyph_text == tile_text, \
        f"{name}: ingest admitted text != transpiled artifact"
    atlas.register(name, tile_text, family="ingested_c", cols_instrs=64)
    assert atlas.tiles[name]["tile_text"] == tile_text


# ── the tile pack ─────────────────────────────────────────────────────
STRLEN_C = ("int strlen_c(const char *s) {\n"
            "    int n = 0;\n"
            "    while (s[n]) n++;\n"
            "    return n;\n"
            "}\n")

STRCMP_C = ("int strcmp_c(const char *a, const char *b) {\n"
            "    while (*a && *a == *b) { a++; b++; }\n"
            "    return (int)(unsigned char)*a - (int)(unsigned char)*b;\n"
            "}\n")

MEMCPY_C = ("void *memcpy_c(void *d, const void *s, int n) {\n"
            "    unsigned char *dd = (unsigned char *)d;\n"
            "    const unsigned char *ss = (const unsigned char *)s;\n"
            "    for (int i = 0; i < n; i++) dd[i] = ss[i];\n"
            "    return d;\n"
            "}\n")

MEMMOVE_C = ("void *memmove_c(void *d, const void *s, int n) {\n"
             "    unsigned char *dd = (unsigned char *)d;\n"
             "    const unsigned char *ss = (const unsigned char *)s;\n"
             "    if (dd < ss) {\n"
             "        for (int i = 0; i < n; i++) dd[i] = ss[i];\n"
             "    } else {\n"
             "        for (int i = n - 1; i >= 0; i--) dd[i] = ss[i];\n"
             "    }\n"
             "    return d;\n"
             "}\n")

DIVMOD_C = (
    "typedef struct { int q; int r; } dq_t;\n"
    "static unsigned udiv_core(unsigned a, unsigned b, unsigned *rem) {\n"
    "    unsigned q = 0, bit = 1;\n"
    "    while (bit && b < a) { b <<= 1; bit <<= 1; }\n"
    "    while (bit) {\n"
    "        if (a >= b) { a -= b; q |= bit; }\n"
    "        b >>= 1; bit >>= 1;\n"
    "    }\n"
    "    *rem = a;\n"
    "    return q;\n"
    "}\n"
    "dq_t divmod_c(int a, int d) {\n"
    "    dq_t res;\n"
    "    if (d == 0) { res.q = -1; res.r = 0; return res; }\n"
    "    unsigned ua = (a < 0) ? (unsigned)(-(long)a) : (unsigned)a;\n"
    "    unsigned ud = (d < 0) ? (unsigned)(-d) : (unsigned)d;\n"
    "    unsigned q, r;\n"
    "    q = udiv_core(ua, ud, &r);\n"
    "    if ((a < 0) != (d < 0)) q = (unsigned)-(long)q;\n"
    "    if (a < 0) r = (unsigned)-(long)r;\n"
    "    res.q = (int)q; res.r = (int)r;\n"
    "    return res;\n"
    "}\n"
)

# NOTE: itoa also avoids libgcc (see DIVMOD_C note): x % 10 / x / 10 on
# int/long lowers to __divsi3/__modsi3/__umodsi3, whose `jr t0` returns
# leak a glyph call frame via the pointer-table JMPR (r10 came back 0).
# udiv10_core is the same software divider restricted to the constant
# divisor 10, unrolled by GCC into shift-subtract — 0 computed jumps.
ITOA_C = ("static unsigned udiv10_core(unsigned v, unsigned *rem) {\n"
          "    unsigned q = 0, bit = 1, b = 10;\n"
          "    while (bit && b < v) { b <<= 1; bit <<= 1; }\n"
          "    while (bit) {\n"
          "        if (v >= b) { v -= b; q |= bit; }\n"
          "        b >>= 1; bit >>= 1;\n"
          "    }\n"
          "    *rem = v;\n"
          "    return q;\n"
          "}\n"
          "int itoa_c(int v, char *buf) {\n"
          "    char tmp[12];\n"
          "    int i = 0, neg = 0;\n"
          "    unsigned x;\n"
          "    if (v < 0) { neg = 1; x = (unsigned)(-(long)v); }\n"
          "    else x = (unsigned)v;\n"
          "    do { unsigned r; x = udiv10_core(x, &r);"
          " tmp[i++] = (char)('0' + r); }\n"
          "    while (x > 0);\n"
          "    int j = 0;\n"
          "    if (neg) buf[j++] = '-';\n"
          "    while (i > 0) buf[j++] = tmp[--i];\n"
          "    buf[j] = 0;\n"
          "    return j;\n"
          "}\n")

ATOI_C = ("int atoi_c(const char *s) {\n"
          "    int sign = 1, v = 0;\n"
          "    if (*s == '-') { sign = -1; s++; }\n"
          "    while (*s >= '0' && *s <= '9') { v = v * 10 + (*s - '0');"
          " s++; }\n"
          "    return sign * v;\n"
          "}\n")

POPCOUNT_C = ("int popcount_c(unsigned x) {\n"
              "    int n = 0;\n"
              "    while (x) { x &= x - 1; n++; }\n"
              "    return n;\n"
              "}\n")

ROTR32_C = ("unsigned rotr32_c(unsigned x, int n) {\n"
            "    n &= 31;\n"
            "    if (n == 0) return x;\n"
            "    return (x >> n) | (x << (32 - n));\n"
            "}\n")

ROTL32_C = ("unsigned rotl32_c(unsigned x, int n) {\n"
            "    n &= 31;\n"
            "    if (n == 0) return x;\n"
            "    return (x << n) | (x >> (32 - n));\n"
            "}\n")


@dataclass
class Tile:
    name: str
    func_symbol: str
    c_source: str
    contract: str
    family: str = "ingested_c"

    def build(self) -> str:
        return compile_and_transpile(self.c_source, self.func_symbol,
                                     self.name)


TILES: Dict[str, Tile] = {
    "strlen_c": Tile(
        "strlen_c", "strlen_c", STRLEN_C,
        "strlen_c(a0: ptr to NUL-terminated byte-lane string) -> a0 = "
        "length in bytes; does not include the NUL"),
    "strcmp_c": Tile(
        "strcmp_c", "strcmp_c", STRCMP_C,
        "strcmp_c(a0: ptr s1, a1: ptr s2) -> a0 = 0 if equal else "
        "(unsigned char)*s1 - (unsigned char)*s2 at first difference "
        "(word-wrapped, i.e. 0xFFFFFFFF for -1)"),
    "memcpy_c": Tile(
        "memcpy_c", "memcpy_c", MEMCPY_C,
        "memcpy_c(a0: dst ptr, a1: src ptr, a2: n bytes) -> a0 = dst; "
        "forward byte copy, caller guarantees no overlap"),
    "memmove_c": Tile(
        "memmove_c", "memmove_c", MEMMOVE_C,
        "memmove_c(a0: dst ptr, a1: src ptr, a2: n bytes) -> a0 = dst; "
        "overlap-safe (backward copy when dst > src)"),
    "divmod_c": Tile(
        "divmod_c", "divmod_c", DIVMOD_C,
        "divmod_c(a0: dividend, a1: divisor) -> a0 = quotient, "
        "a1 = remainder, C99 truncation toward zero; divisor 0 returns "
        "quotient 0xFFFFFFFF (status), remainder 0, no crash"),
    "itoa_c": Tile(
        "itoa_c", "itoa_c", ITOA_C,
        "itoa_c(a0: value, a1: buf ptr) -> a0 = string length; buf gets "
        "NUL-terminated decimal with '-' for negatives (INT32_MIN safe)"),
    "atoi_c": Tile(
        "atoi_c", "atoi_c", ATOI_C,
        "atoi_c(a0: ptr to decimal string with optional '-') -> a0 = "
        "value; INT32_MIN representable as the wrapped word"),
    "popcount_c": Tile(
        "popcount_c", "popcount_c", POPCOUNT_C,
        "popcount_c(a0: word) -> a0 = number of set bits"),
    "rotr32_c": Tile(
        "rotr32_c", "rotr32_c", ROTR32_C,
        "rotr32_c(a0: word, a1: shift) -> a0 = rotate right (n mod 32)"),
    "rotl32_c": Tile(
        "rotl32_c", "rotl32_c", ROTL32_C,
        "rotl32_c(a0: word, a1: shift) -> a0 = rotate left (n mod 32)"),
}


def build_tile(name: str) -> str:
    return TILES[name].build()


__all__ = ["TILES", "Tile", "Case", "build_tile", "pack_bytes",
           "words_of", "native_run", "oracle_leg", "ir_leg", "ingest_leg",
           "compile_and_transpile", "StaticVerificationError",
           "STR_A_BYTE", "STR_B_BYTE", "DST_BYTE", "ITOA_BUF_BYTE"]
