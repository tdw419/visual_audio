#!/usr/bin/env python3
"""
SHA-256 compression core, implemented in the Glyph ISA v2.

Scope of this kernel
--------------------
This generator emits a Glyph ISA program that computes the SHA-256 hash of a
SINGLE, ALREADY-PADDED 512-bit message block. The host harness
(tools/sha256_lockstep_test.py) is responsible only for the mechanical,
non-cryptographic parts:

  * padding the message to a 64-byte block (0x80 marker, zero fill, 64-bit
    big-endian length), and
  * placing the SHA-256 round-constant ROM K[0..63] in memory.

Everything cryptographic runs in Glyph ISA:

  * the H[0..7] initial-hash constants (LDI'd by the program),
  * the message-schedule expansion  W[16..63]  (sigma0 / sigma1),
  * the 64 compression rounds        (Sigma0 / Sigma1 / Ch / Maj),
  * the working-var -> H feed-forward add, and
  * big-endian serialisation of H[0..7] into 32 output bytes.

Multi-block messages and in-Glyph padding are a straightforward extension
(loop the compression over blocks, feed H forward) and are noted as TODO.

Memory map (GlyphCPUv2.memory, one 32-bit int per cell)
------------------------------------------------------
  100 .. 163   K[0..63]     round constants        (written by harness)
  200 .. 263   W[0..63]     schedule work area     (written by this program)
  270          block index  outer-loop cursor      (init by this program)
  271          block count  N padded 512-bit blocks (written by harness)
  280 ..       blocks       N*16 big-endian words   (written by harness)
  400 .. 431   digest       32 output bytes         (written by this program)

Register map
------------
  r0            CMP flag (written by CMP, tested by JZ)
  r1   RMASK    0xFFFFFFFF  (mod-2^32 mask)
  r2..r9        working vars a,b,c,d,e,f,g,h
  r10..r17      H[0..7]
  r18  RSH      shift-amount scratch
  r19  P        address scratch
  r20  T        loop counter (round / schedule index)
  r21  KP       pointer into K[]
  r22  WP       pointer into W[]
  r23  ONE      constant 1
  r24  TLIM     constant 64 (loop limit)
  r25  S        sigma/Sigma accumulator
  r26  T1       round temp t1
  r27  T2       round temp t2
  r28  TA       rotate internal temp
  r29  TB       general temp
  r30  TC       general temp
"""

from pathlib import Path
from typing import List

H_INIT = [
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
]

# register constants
RMASK, RSH, P, T, KP, WP, ONE, TLIM = 1, 18, 19, 20, 21, 22, 23, 24
S, T1, T2, TA, TB, TC = 25, 26, 27, 28, 29, 30
A, B, C, D, E, F, G, HH = 2, 3, 4, 5, 6, 7, 8, 9
HREG = list(range(10, 18))
ABC = [A, B, C, D, E, F, G, HH]

K_BASE = 100
W_BASE = 200
BIDX_ADDR = 270
BCNT_ADDR = 271
BLK_BASE = 280
OUT_BASE = 400


def _build(width_instrs: int,
           K_BASE: int = K_BASE,
           W_BASE: int = W_BASE,
           BIDX_ADDR: int = BIDX_ADDR,
           BCNT_ADDR: int = BCNT_ADDR,
           BLK_BASE: int = BLK_BASE,
           OUT_BASE: int = OUT_BASE) -> List[str]:
    ins: list = []          # each entry: final str, or ('J', op, label)
    labels: dict = {}

    def EM(s: str):
        ins.append(s)

    def LBL(name: str):
        labels[name] = len(ins)

    def JMP(name: str):
        ins.append(('J', 'JMP', name))

    def JZ(name: str):
        ins.append(('J', 'JZ', name))

    # --- primitive sequences -------------------------------------------------
    def MOV(dst, src):
        EM(f"LDI r{dst} 0")
        EM(f"ADD r{dst} r{src}")

    def MOVI(dst, imm):
        EM(f"LDI r{dst} {imm}")

    def ADDM(dst, src):
        EM(f"ADD r{dst} r{src}")
        EM(f"AND r{dst} r{RMASK}")

    def XORR(dst, src):
        EM(f"XOR r{dst} r{src}")

    def ROTR(dst, x, n, tmp=None):
        # dst = rotr32(x, n) via the native ROTR opcode. `tmp` is unused now
        # (kept so existing call sites don't change); x must be masked to 32 bits
        # and must not be the RSH scratch register.
        MOV(dst, x)
        MOVI(RSH, n)
        EM(f"ROTR r{dst} r{RSH}")

    def SHRX(dst, x, n):
        MOV(dst, x)
        MOVI(RSH, n)
        EM(f"SHR r{dst} r{RSH}")

    def NOTR(dst, x):
        MOV(dst, x)
        EM(f"XOR r{dst} r{RMASK}")

    def sig0(dst, x):            # lowercase sigma0: rotr7 ^ rotr18 ^ shr3
        ROTR(dst, x, 7, TA)
        ROTR(TB, x, 18, TA)
        XORR(dst, TB)
        SHRX(TB, x, 3)
        XORR(dst, TB)

    def sig1(dst, x):            # lowercase sigma1: rotr17 ^ rotr19 ^ shr10
        ROTR(dst, x, 17, TA)
        ROTR(TB, x, 19, TA)
        XORR(dst, TB)
        SHRX(TB, x, 10)
        XORR(dst, TB)

    def Sig0(dst, x):           # uppercase Sigma0: rotr2 ^ rotr13 ^ rotr22
        ROTR(dst, x, 2, TA)
        ROTR(TB, x, 13, TA)
        XORR(dst, TB)
        ROTR(TB, x, 22, TA)
        XORR(dst, TB)

    def Sig1(dst, x):           # uppercase Sigma1: rotr6 ^ rotr11 ^ rotr25
        ROTR(dst, x, 6, TA)
        ROTR(TB, x, 11, TA)
        XORR(dst, TB)
        ROTR(TB, x, 25, TA)
        XORR(dst, TB)

    # --- setup -------------------------------------------------------------
    MOVI(RMASK, 0xFFFFFFFF)
    for i, hv in enumerate(H_INIT):
        MOVI(HREG[i], hv)
    MOVI(ONE, 1)
    #   block index := 0
    MOVI(P, BIDX_ADDR)
    MOVI(TB, 0)
    EM(f"ST r{P} r{TB}")

    # --- outer loop over padded 512-bit blocks --------------------------
    LBL('outer')
    MOVI(P, BIDX_ADDR); EM(f"LD r{T2} r{P}")     # T2 = block index
    MOVI(P, BCNT_ADDR); EM(f"LD r{TC} r{P}")     # TC = block count
    EM(f"CMP r{T2} r{TC}")
    JZ('outer_end')
    #   BP := BLK_BASE + index*16  (index is 0/1, SHL 4 == *16)
    MOVI(TB, 4); EM(f"SHL r{T2} r{TB}")
    MOVI(TB, BLK_BASE); EM(f"ADD r{T2} r{TB}")   # T2 = BP
    #   copy 16 big-endian words of this block into W[0..15]
    for k in range(16):
        EM(f"LD r{TB} r{T2}")
        MOVI(P, W_BASE + k)
        EM(f"ST r{P} r{TB}")
        EM(f"ADD r{T2} r{ONE}")

    # --- message schedule: W[16..63] -------------------------------------
    MOVI(T, 16)
    MOVI(WP, W_BASE + 16)
    MOVI(TLIM, 64)
    LBL('sched')
    EM(f"CMP r{T} r{TLIM}")
    JZ('sched_end')
    #   S = sigma1(W[t-2])
    MOV(P, WP); MOVI(TC, 2); EM(f"SUB r{P} r{TC}"); EM(f"LD r{TC} r{P}")
    sig1(S, TC)
    #   S += W[t-7]
    MOV(P, WP); MOVI(TC, 7); EM(f"SUB r{P} r{TC}"); EM(f"LD r{TC} r{P}")
    ADDM(S, TC)
    #   S += sigma0(W[t-15])
    MOV(P, WP); MOVI(TC, 15); EM(f"SUB r{P} r{TC}"); EM(f"LD r{TC} r{P}")
    sig0(T1, TC)
    ADDM(S, T1)
    #   S += W[t-16]
    MOV(P, WP); MOVI(TC, 16); EM(f"SUB r{P} r{TC}"); EM(f"LD r{TC} r{P}")
    ADDM(S, TC)
    #   W[t] = S
    EM(f"ST r{WP} r{S}")
    EM(f"ADD r{T} r{ONE}")
    EM(f"ADD r{WP} r{ONE}")
    JMP('sched')
    LBL('sched_end')

    # --- compression: 64 rounds ----------------------------------------
    for i in range(8):
        MOV(ABC[i], HREG[i])
    MOVI(T, 0)
    MOVI(KP, K_BASE)
    MOVI(WP, W_BASE)
    MOVI(TLIM, 64)
    LBL('comp')
    EM(f"CMP r{T} r{TLIM}")
    JZ('comp_end')
    #   S = Sigma1(e)
    Sig1(S, E)
    #   TC = Ch(e,f,g) = (e & f) ^ (~e & g)
    MOV(TC, E); EM(f"AND r{TC} r{F}")
    NOTR(TB, E); EM(f"AND r{TB} r{G}")
    EM(f"XOR r{TC} r{TB}")
    #   t1 = h + Sigma1(e) + Ch + K[t] + W[t]
    MOV(T1, HH)
    ADDM(T1, S)
    ADDM(T1, TC)
    EM(f"LD r{TB} r{KP}"); ADDM(T1, TB)
    EM(f"LD r{TB} r{WP}"); ADDM(T1, TB)
    #   S = Sigma0(a)
    Sig0(S, A)
    #   TC = Maj(a,b,c) = (a&b) ^ (a&c) ^ (b&c)
    MOV(TC, A); EM(f"AND r{TC} r{B}")
    MOV(TB, A); EM(f"AND r{TB} r{C}"); EM(f"XOR r{TC} r{TB}")
    MOV(TB, B); EM(f"AND r{TB} r{C}"); EM(f"XOR r{TC} r{TB}")
    #   t2 = Sigma0(a) + Maj
    MOV(T2, S)
    ADDM(T2, TC)
    #   shuffle:  h=g g=f f=e e=d+t1 d=c c=b b=a a=t1+t2
    MOV(HH, G)
    MOV(G, F)
    MOV(F, E)
    MOV(E, D); ADDM(E, T1)
    MOV(D, C)
    MOV(C, B)
    MOV(B, A)
    MOV(A, T1); ADDM(A, T2)
    #   advance counters
    EM(f"ADD r{T} r{ONE}")
    EM(f"ADD r{KP} r{ONE}")
    EM(f"ADD r{WP} r{ONE}")
    JMP('comp')
    LBL('comp_end')

    # --- feed-forward: H[i] += working var ----------------------------
    for i in range(8):
        ADDM(HREG[i], ABC[i])

    #   block index += 1 ; loop
    MOVI(P, BIDX_ADDR); EM(f"LD r{T2} r{P}")
    EM(f"ADD r{T2} r{ONE}")
    EM(f"ST r{P} r{T2}")
    JMP('outer')
    LBL('outer_end')

    # --- serialise H[0..7] big-endian -> 32 bytes at OUT_BASE --------
    MOVI(TC, 0xFF)
    out = OUT_BASE
    for i in range(8):
        for j in range(4):
            sh = 24 - 8 * j
            MOV(TA, HREG[i])
            MOVI(RSH, sh)
            EM(f"SHR r{TA} r{RSH}")
            EM(f"AND r{TA} r{TC}")
            MOVI(P, out)
            EM(f"ST r{P} r{TA}")
            out += 1

    EM("HALT")

    # --- resolve symbolic jump targets -------------------------------
    resolved: List[str] = []
    for it in ins:
        if isinstance(it, tuple):
            _, op, name = it
            idx = labels[name]
            col = idx % width_instrs
            row = idx // width_instrs
            resolved.append(f"{op} {col},{row}")
        else:
            resolved.append(it)
    return resolved


def build_sha256_glyph_program(width_instrs: int = 64,
                               K_BASE: int | None = None,
                               W_BASE: int | None = None,
                               BIDX_ADDR: int | None = None,
                               BCNT_ADDR: int | None = None,
                               BLK_BASE: int | None = None,
                               OUT_BASE: int | None = None) -> List[str]:
    """Return the SHA-256 kernel (multi-block) as Glyph ISA assembly lines.

    BK-8: the working-set bases are parameters (defaults = the legacy
    host-RAM map) so the kernel can be rebuilt with its entire working set
    inside the GH-8b pixel-resident FS window [1024, 1280). The bases are
    BAKED into LDI immediates by the program body — relocation REQUIRES a
    rebuild, not just a different seed address.
    """
    kw = {}
    if K_BASE is not None: kw["K_BASE"] = K_BASE
    if W_BASE is not None: kw["W_BASE"] = W_BASE
    if BIDX_ADDR is not None: kw["BIDX_ADDR"] = BIDX_ADDR
    if BCNT_ADDR is not None: kw["BCNT_ADDR"] = BCNT_ADDR
    if BLK_BASE is not None: kw["BLK_BASE"] = BLK_BASE
    if OUT_BASE is not None: kw["OUT_BASE"] = OUT_BASE
    return _build(width_instrs, **kw)


# --- reference host helpers (padding + K ROM), shared by the lockstep test
#     and the dispatcher so there is exactly one glyph SHA-256 entry point ---

# SHA-256 round constants: first 32 bits of the fractional parts of the cube
# roots of the first 64 primes.
_K = [
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1,
    0x923F82A4, 0xAB1C5ED5, 0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174, 0xE49B69C1, 0xEFBE4786,
    0x0FC19DC6, 0x240CA1CC, 0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7, 0xC6E00BF3, 0xD5A79147,
    0x06CA6351, 0x14292967, 0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85, 0xA2BFE8A1, 0xA81A664B,
    0xC24B8B70, 0xC76C51A3, 0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5, 0x391C0CB3, 0x4ED8AA4A,
    0x5B9CCA4F, 0x682E6FF3, 0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
]


def _pad(message: bytes) -> bytes:
    """Merkle-Damgard padding to a whole number of 512-bit blocks."""
    ml = len(message) * 8
    padded = message + b"\x80"
    while len(padded) % 64 != 56:
        padded += b"\x00"
    padded += ml.to_bytes(8, "big")
    assert len(padded) % 64 == 0
    return padded


def sha256_glyph(message: bytes, *, width_instrs: int = 64,
                 max_instructions: int = 400_000,
                 wordbase_path=None) -> bytes:
    """Compute SHA-256(message) by executing the Glyph ISA kernel on GlyphCPUv2.

    This is the single canonical entry point: the lockstep test and the
    dispatch harness both call it, so a regression cannot pass one and fail
    the other unnoticed.
    """
    from .glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2

    op = OpcodeMapV2() if wordbase_path is None else OpcodeMapV2(wordbase_path=wordbase_path)
    try:
        asm = GlyphAssemblerV2(op)
        image = asm.assemble(build_sha256_glyph_program(width_instrs=width_instrs),
                             width_instrs=width_instrs)
        cpu = GlyphCPUv2(op, width_instrs)

        for i, kv in enumerate(_K):
            cpu.memory[K_BASE + i] = kv
        padded = _pad(message)
        nblocks = len(padded) // 64
        cpu.memory[BCNT_ADDR] = nblocks
        for w in range(nblocks * 16):
            cpu.memory[BLK_BASE + w] = int.from_bytes(padded[4 * w:4 * w + 4], "big")

        executed = cpu.run(image, max_instructions=max_instructions)
        if executed >= max_instructions:
            raise RuntimeError(
                f"glyph SHA-256 did not HALT within {max_instructions} steps")
        return bytes(cpu.memory[OUT_BASE:OUT_BASE + 32])
    finally:
        try:
            op.close()
        except Exception:
            pass


if __name__ == '__main__':
    W = 64
    prog = build_sha256_glyph_program(W)
    print(f"SHA-256 glyph kernel: {len(prog)} instructions "
          f"({(len(prog) + W - 1) // W} rows @ width {W})")
    as_path = Path(__file__).with_name('sha256_glyph.as')
    header = [
        "# SHA-256 single-block compression core - Glyph ISA v2",
        "# AUTO-GENERATED by sha256_kernel.py -- do not edit by hand.",
        f"# {len(prog)} instructions, assemble with width_instrs={W}.",
        "",
    ]
    as_path.write_text("\n".join(header + prog) + "\n")
    print(f"wrote {as_path}")
