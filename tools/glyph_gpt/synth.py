#!/usr/bin/env python3
"""
GlyphGPT Phase 3b — synthetic RV32I program generator + oracle gate.

Design: every template emits (instruction_bytes, interpreter) where
`interpreter` is a Python generator function that yields (label, action)
steps mirroring the assembly control flow. Simpler and safer: each template
returns (asm_bytes, expected_regs_fn) where expected_regs_fn() re-executes
the SAME control flow in Python and returns the final register values to
check. Control flow is template-structured (loops as Python loops), so the
reference and the RV code share structure by construction, and divergence
can only come from the transpiler/CPU — which is exactly what we're testing.

Receipt contract (per program):
  {"family", "seed_id", "asm_sha256", "expected_regs", "observed_regs",
   "steps", "match": bool, "error": optional}

Programs where observed != expected are kept as candidates for the DPO
negative set but excluded from SFT.
"""

from __future__ import annotations

import contextlib
import io
import struct
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"

SEED = 1337
MASK32 = 0xFFFFFFFF


# ─── RV32I encoders ───────────────────────────────────────────────────────

def ri(rd: int, rs1: int, imm: int, f3: int = 0, op: int = 0x13) -> bytes:
    return struct.pack('<I', (imm & 0xFFF) << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op)

def rtype(f7: int, rs2: int, rs1: int, f3: int, rd: int) -> bytes:
    return struct.pack('<I', f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | 0x33)

def rb(rs2: int, rs1: int, off: int, f3: int) -> bytes:
    o = off & 0x1FFF
    return struct.pack('<I',
        ((o >> 12) & 1) << 31 | ((o >> 5) & 0x3F) << 25 | rs2 << 20 |
        rs1 << 15 | f3 << 12 | ((o >> 1) & 0xF) << 8 | ((o >> 11) & 1) << 7 | 0x63)

def rj(rd: int, off: int) -> bytes:
    o = off & 0x1FFFFF
    return struct.pack('<I',
        ((o >> 20) & 1) << 31 | ((o >> 1) & 0x3FF) << 21 |
        ((o >> 11) & 1) << 20 | ((o >> 12) & 0xFF) << 12 | rd << 7 | 0x6F)

ECALL = struct.pack('<I', 0x00000073)
ADDI = lambda rd, rs1, imm: ri(rd, rs1, imm, 0)
SLTI = lambda rd, rs1, imm: ri(rd, rs1, imm, 2)
XORI = lambda rd, rs1, imm: ri(rd, rs1, imm, 4)
ORI  = lambda rd, rs1, imm: ri(rd, rs1, imm, 6)
ANDI = lambda rd, rs1, imm: ri(rd, rs1, imm, 7)
SLLI = lambda rd, rs1, sh: ri(rd, rs1, sh, 1)
SRLI = lambda rd, rs1, sh: ri(rd, rs1, sh, 5)
ADD  = lambda rd, rs1, rs2: rtype(0, rs2, rs1, 0, rd)
SUB  = lambda rd, rs1, rs2: rtype(0x20, rs2, rs1, 0, rd)
XOR  = lambda rd, rs1, rs2: rtype(0, rs2, rs1, 4, rd)
OR   = lambda rd, rs1, rs2: rtype(0, rs2, rs1, 6, rd)
AND  = lambda rd, rs1, rs2: rtype(0, rs2, rs1, 7, rd)
LW   = lambda rd, rs1, imm: ri(rd, rs1, imm, 2, 0x03)
def SW(rs2: int, rs1: int, imm: int) -> bytes:
    """S-type: imm is signed 12-bit split [11:5]|rs2|rs1|funct3|[4:0]."""
    i = imm & 0xFFF
    return struct.pack('<I', ((i >> 5) & 0x7F) << 25 | rs2 << 20 |
                       rs1 << 15 | 2 << 12 | (i & 0x1F) << 7 | 0x23)
BEQ  = lambda rs1, rs2, off: rb(rs2, rs1, off, 0)
BNE  = lambda rs1, rs2, off: rb(rs2, rs1, off, 1)
BLT  = lambda rs1, rs2, off: rb(rs2, rs1, off, 4)
JAL  = lambda rd, off: rj(rd, off)
RET  = struct.pack('<I', (0 << 20) | 1 << 15 | 0 << 7 | 0x67)
NOP  = ADDI(0, 0, 0)


def s32(x: int) -> int:
    x &= MASK32
    return x - 0x100000000 if x >= 0x80000000 else x


# ─── Constant registry (Phase 5.1b) ──────────────────────────────────────
# Fresh random constants are information-theoretically unpredictable at
# generation time (nothing in the context determines them; measured: the
# value head cannot even memorize them — 500-step overfit of 64 seqs
# stalls at MAE ~50). Drawing constants from a small per-(family, role)
# registry makes every immediate a learnable function of context.

_REGISTRIES = {
    "alu_chain": [7, 12, 24, 36],
    "counted_loop_n": [4, 6, 8, 10],
    "counted_loop_k": [2, 3, 5],
    "conditional_v": [-15, 9, -42, 27],
    "mem_pass_v": [18, 55, 128, 240],
    "mem_pass_addr": [64, 128, 256, 512],
    "leaf_call_v": [5, 9, 17, 33],
}


def registry_value(key: str, rng) -> int:
    return rng.choice(_REGISTRIES[key])


def ldi_reg_value_sets(receipts_path) -> Dict[str, set]:
    """Phase 5.4 valcond: derive (LDI, reg) -> admissible value sets from
    the oracle-verified corpus. Decodes each receipt's asm back through the
    transpiler + tokenizer and collects NUM values per LDI target register.
    Used at generation time to mask value-head candidates."""
    import json
    sys.path.insert(0, str(_TOOLS_DIR))
    from glyph_gpt.tokenizer import GlyphTokenizer
    from rv64i_to_glyph import transpile_rv32i_to_glyph
    here = Path(__file__).parent
    tok = GlyphTokenizer.load(str(here / "tokenizer.json"))
    inv = {i: t for t, i in tok.token_to_id.items()}
    out: Dict[str, set] = {}
    with open(receipts_path) as f:
        for line in f:
            e = json.loads(line)
            text = transpile_rv32i_to_glyph(bytes.fromhex(e["asm_hex"]))
            ids, vals = tok.encode(text)
            for k in range(len(ids) - 2):
                if (inv.get(ids[k], "") == "LDI"
                        and inv.get(ids[k + 1], "").startswith("r")
                        and inv.get(ids[k + 2], "") == "<NUM>"
                        and vals[k + 2] not in (0, -1)):
                    out.setdefault(inv[ids[k + 1]], set()).add(vals[k + 2])
    return out


# ─── Templates ────────────────────────────────────────────────────────────
# Each returns (asm_bytes, run_reference -> Dict[int,int], meta: Dict)
# check_regs: which register indices to compare at ECALL.

def t_alu_chain(rng, idx: int):
    """Straight-line ALU dependence chain on 2-3 registers."""
    regs = [rng.randint(5, 15) for _ in range(2)]
    r1, r2 = regs[0], regs[1]
    if r1 == r2:
        r2 = r1 + 1 if r1 < 31 else r1 - 1
    v1 = registry_value("alu_chain", rng)
    v2 = registry_value("counted_loop_k", rng)  # small constant
    asm = ADDI(r1, 0, v1) + ADDI(r2, 0, v2)
    ref = {r1: v1, r2: v2}
    n = rng.randint(3, 7)
    for _ in range(n):
        choice = rng.choice(["add", "xor", "or", "and", "slti"])
        if choice == "add":
            k = rng.choice([1, 2, 4, 8])
            asm += ADDI(r1, r1, k); ref[r1] = s32(ref[r1] + k)
        elif choice == "xor":
            asm += XOR(r1, r1, r2); ref[r1] = s32(ref[r1] ^ (ref[r2] & MASK32))
        elif choice == "or":
            asm += OR(r1, r1, r2); ref[r1] = s32(ref[r1] | (ref[r2] & MASK32))
        elif choice == "and":
            asm += AND(r1, r1, r2); ref[r1] = s32(ref[r1] & (ref[r2] & MASK32))
        else:
            asm += ADD(r2, r2, r1); ref[r2] = s32(ref[r2] + ref[r1])
    asm += ECALL
    return asm, lambda: ref, [r1, r2], {"family": "alu_chain", "ops": n}


def t_counted_loop(rng, idx: int):
    """Countdown loop accumulating a sum — backward branch + counter."""
    rc, rs_ = rng.randint(5, 10), rng.randint(11, 15)   # counter, sum
    n = registry_value("counted_loop_n", rng)
    k = registry_value("counted_loop_k", rng)
    # sum = 0; c = n; loop: sum += k; c--; bne c,x0
    body_len = 3 * 4  # addi sum; add sub... layout below
    # layout: addi rs,0,0 (4) | addi rc,0,n (4) | loop: addi rs,rs,k (4)
    #         | addi rc,rc,-1 (4) | bne rc,x0,loop | ecall
    loop_off = -(4 * 2)  # from bne back to loop
    asm = (ADDI(rs_, 0, 0) + ADDI(rc, 0, n) +
           ADDI(rs_, rs_, k) + ADDI(rc, rc, -1) +
           BNE(rc, 0, loop_off) + ECALL)
    total = k * n
    ref = {rs_: s32(total), rc: 0}
    return asm, lambda: ref, [rs_, rc], {"family": "counted_loop", "n": n, "k": k}


def t_conditional(rng, idx: int):
    """abs()/min via forward branch: if x < 0 then x = -x."""
    rx = rng.randint(5, 15)
    v = registry_value("conditional_v", rng)
    # layout: addi rx,0,v (4) | blt rx,x0,+8 (4) | jal x0,+8 (4)->ecall
    #         | sub rx,x0,rx (4) [negate] | ecall (shared target)
    # branch to ecall if >= 0 (skip negate)
    asm = ADDI(rx, 0, v)
    asm += BLT(rx, 0, 8)      # if x < 0 -> negate
    asm += JAL(0, 8)          # jump to ecall
    asm += SUB(rx, 0, rx)     # negate
    asm += ECALL
    expected = s32(abs(v))
    return asm, lambda: {rx: expected}, [rx], {"family": "conditional", "v": v}


def t_mem_pass(rng, idx: int):
    """Store then load a value through memory (sw/lw roundtrip)."""
    rd_, ra = rng.randint(5, 10), rng.randint(11, 15)
    v = registry_value("mem_pass_v", rng)
    # S-type imm is signed 12-bit; keep it positive AND below PTR_TABLE_BASE
    # so stores land in the plain data arena, never the jump pointer table.
    addr = registry_value("mem_pass_addr", rng)
    asm = ADDI(rd_, 0, v)
    asm += SW(rd_, 0, addr)         # sw rd, addr(x0)
    asm += LW(ra, 0, addr)          # lw ra, addr(x0)
    asm += ECALL
    return asm, lambda: {ra: s32(v)}, [ra], {"family": "mem_pass", "v": v, "addr": addr}


def t_leaf_call_atlas(rng, idx: int):
    """Leaf subroutine via the Patch-and-Copy atlas (Phase 5.6).

    The caller text ends at CALL :atlas_double + HALT — the callee body
    is NOT in the training text. At eval/link time the linker splices
    the verified atlas tile, so the model's job is coordination only:
    the layout-planning limit becomes inexpressible. Oracle semantics
    are unchanged (a0 doubled after link)."""
    ra0 = 10  # a0
    v = registry_value("leaf_call_v", rng)
    # 0: addi a0,0,v | 4: jal ra,+12 (->16) | 8: ecall | 12: nop
    # 16: add a0,a0,a0 | 20: ret   (RV-level truth; the glyph text the
    # linker assembles is caller-only, tile appended at link time)
    asm = ADDI(ra0, 0, v) + JAL(1, 12) + ECALL + NOP
    asm += ADD(ra0, ra0, ra0) + RET
    # The RV-level oracle gate compares against the RV reference (a0
    # doubled). Glyph-level linked-form verification lives in
    # test_atlas.py, which runs the caller text through atlas.link().
    return asm, lambda: {ra0: s32(v * 2)}, [ra0], {
        "family": "leaf_call", "v": v, "atlas": True}


def t_leaf_call(rng, idx: int):
    """Leaf subroutine: call double(), result in a0."""
    ra0 = 10  # a0
    v = registry_value("leaf_call_v", rng)
    # 0: addi a0,0,v | 4: jal ra,+12 (->16) | 8: ecall | 12: nop
    # 16: add a0,a0,a0 | 20: ret
    asm = ADDI(ra0, 0, v) + JAL(1, 12) + ECALL + NOP
    asm += ADD(ra0, ra0, ra0) + RET
    return asm, lambda: {ra0: s32(v * 2)}, [ra0], {"family": "leaf_call", "v": v}


TEMPLATES = [t_alu_chain, t_counted_loop, t_conditional, t_mem_pass,
             t_leaf_call_atlas]


# ─── Oracle gate ──────────────────────────────────────────────────────────

def run_oracle_rv(asm_bytes: bytes, ref_fn: Callable, check_regs: List[int],
                  max_instructions: int = 5000) -> Dict:
    """Transpile -> assemble -> execute on GlyphCPUv2; compare registers."""
    sys.path.insert(0, str(_TOOLS_DIR))
    from rv64i_to_glyph import transpile_rv32i_to_glyph, assemble_glyph_to_pixels
    from glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2

    receipt: Dict = {"error": None}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            text = transpile_rv32i_to_glyph(asm_bytes)
            img, _labels = assemble_glyph_to_pixels(text, cols_instrs=8)
            cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
            steps = cpu.run(img, max_instructions=max_instructions)
    except Exception as e:
        receipt["error"] = f"{type(e).__name__}: {e}"
        receipt["match"] = False
        return receipt

    nregs = len(cpu.registers)
    expected = ref_fn()
    observed = {r: int(cpu.registers[r]) & MASK32 for r in check_regs if r < nregs}
    exp_masked = {r: e & MASK32 for r, e in expected.items()}
    receipt["steps"] = int(steps)
    receipt["expected_regs"] = exp_masked
    receipt["observed_regs"] = observed
    receipt["match"] = (observed == exp_masked and int(steps) < max_instructions)
    if not receipt["match"]:
        receipt["error"] = "register mismatch" if observed == exp_masked else None
    return receipt


def synthesize_from_rv64i(binaries: List[Path], out_path: Path,
                          cols_instrs: int = 64,
                          n_per_family: int = 200, seed: int = SEED) -> List[Dict]:
    """Generate n_per_family programs per template family, oracle-gate each.

    NOTE: `binaries` is unused in Phase 3b (programs are generated, not read
    from disk) — kept for interface compatibility with the skeleton. Real
    binary synthesis can be added later by feeding ELF text sections through
    the same oracle gate.
    """
    import random
    rng = random.Random(seed)
    entries: List[Dict] = []
    sid = 0
    for template in TEMPLATES:
        for _ in range(n_per_family):
            asm_bytes, ref_fn, check_regs, meta = template(rng, sid)
            sid += 1
            receipt = run_oracle_rv(asm_bytes, ref_fn, check_regs)
            import hashlib
            entry = {
                "path": f"synth/{meta['family']}_{sid:05d}.S",
                "sha256": hashlib.sha256(asm_bytes).hexdigest(),
                "dialect": "isa_v2",
                "source": "synth",
                "family": meta["family"],
                "oracle": receipt,
                "asm_hex": asm_bytes.hex(),
                "text": "",
            }
            # optional template flags (e.g. atlas=True) ride on the entry
            for flag_key in ("atlas",):
                if meta.get(flag_key):
                    entry[flag_key] = True
            entries.append(entry)
    return entries


def summarize(entries: List[Dict]) -> str:
    from collections import Counter
    by_family = Counter(e["family"] for e in entries)
    ok = Counter(e["family"] for e in entries if e["oracle"].get("match"))
    lines = [f"total synth: {len(entries)}"]
    for fam in sorted(by_family):
        lines.append(f"  {fam:15s} {ok[fam]:4d}/{by_family[fam]:4d} match")
    total_ok = sum(ok.values())
    lines.append(f"  TOTAL MATCH: {total_ok}/{len(entries)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="programs per family")
    ap.add_argument("--out", default=str(Path(__file__).parent / "synth_receipts.jsonl"))
    args = ap.parse_args()
    entries = synthesize_from_rv64i([], Path(args.out), n_per_family=args.n)
    Path(args.out).write_text("".join(
        __import__("json").dumps(e) + "\n" for e in entries))
    print(summarize(entries))
