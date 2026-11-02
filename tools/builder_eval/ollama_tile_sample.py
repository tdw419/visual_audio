#!/usr/bin/env python3
"""ollama_tile_sample.py — MECHANICALLY sampled holdout for the local tile draftsman.

Why this exists: every routine set used today was chosen by hand, first the hardest ones
(double, negate: 33%), then easy ones (decrement, clear, and_mask: 75%). Both are
selection artifacts. This script removes the human from routine selection entirely:

  * tasks are drawn at random (seeded) from the ISA's register-register ALU space:
    op in {ADD, SUB, AND, OR, XOR, SHL, SHR}, constant K, seed value V
  * the EXPECTED value is not written by a human either — it is the value the machine
    oracle itself produces when the reference tile runs (LDI r0 K; OP r10 r0; RET)
  * acceptance = the model's tile leaves exactly that value in r10

Usage: python3 tools/builder_eval/ollama_tile_sample.py --model qwen3-coder:30b --tasks 12 --draws 2
"""
import argparse, json, random, re, subprocess, sys, time, urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in ("tools", "tools/glyph_gpt"):
    sys.path.insert(0, str(_REPO / p))
from atlas import run_generated  # noqa: E402  (GlyphCPUv2 oracle)

OLLAMA = "http://127.0.0.1:11434/api/generate"

ISA = """Glyph tile text format:
  :label
  LDI rN <imm> = load immediate into register rN
  OP rD rS     = register-register operation: OP is one of ADD SUB AND OR XOR SHL SHR
  RET          = end the tile
Registers r0..r31. All binary ops take TWO REGISTERS (never an immediate).
There is no MUL, no MOV and no NEG opcode. Emit ONLY the tile text, no fences, no prose."""


SHIFT_RULE = """
SHL rD rCount and SHR rD rCount shift rD by the amount in register rCount, in ONE
operation. Do NOT repeat it; never pass the shifted value as the count."""

# Targeted at SHR's specific measured bug (value-as-count: `SHR r10 r10`, i.e. shifting
# a register by its OWN current value instead of a separately loaded count), mirroring
# the shape of the SHL denial that worked: name the exact wrong pattern and forbid it.
SHR_DENIAL_RULE = """
SHR rD rCount shifts rD right by the amount held in rCount, in ONE operation. rCount
MUST be a register you loaded with LDI to hold the shift amount K — it must be a
DIFFERENT register from rD. NEVER write `SHR rD rD` (shifting a register by its own
current value is always wrong). NEVER repeat SHR to simulate a multi-bit shift."""


def oracle(tile_text: str, seed_reg: int = 10, seed_val: int = 0):
    src = f"LDI r{seed_reg} {seed_val}\n" + tile_text
    r = run_generated(src)
    rf = r.get("registers_full") or []
    ran = bool(r.get("halted")) and not r.get("faulted")
    if len(rf) > 10:
        return ran, rf[10], r.get("error")
    if ran:
        raise ValueError("executed but no r10 in receipt")
    return False, None, r.get("error")


def coincidence_check(tile_text: str, op: str, k: int, v_used: int, rnd: random.Random):
    """A tile that passes on ONE (k, v) can still be wrong — e.g. `SHR r10 r10` (value
    used as the shift count) happened to output 0 for a (k, v) pair where the correct
    answer was also 0. Re-run the SAME tile against a second, independently-drawn V and
    require it to match a freshly oracle-derived expected value too.

    BLIND SPOT FOUND LIVE (do not remove this note without re-deriving it): for some
    (op, k) pairs — e.g. SHR with k=6 over V in [8,40] — the CORRECT answer is 0 for
    nearly every V in the sampled range (V>>6==0 whenever V<64), and a buggy
    value-as-count tile ALSO collapses to 0 for nearly every V. A second check drawn
    from the same narrow range inherits the same blind spot and can rubber-stamp the
    same bug it exists to catch. So: search a widened pool for a v2 whose CORRECT
    answer is non-zero, and prefer that one — a bug that only reproduces the right
    answer at zero is exactly the failure mode this check exists to name.

    Returns (verified: bool | None, v2: int, expected2: int | None) — verified is None
    when no usable non-degenerate v2 could be found (can't judge, not a candidate fault).
    """
    candidates = [rnd.randint(8, 40) for _ in range(4)] + [rnd.randint(41, 500) for _ in range(4)]
    best = None  # (v2, expected2) preferring a non-zero expected value
    for v2 in candidates:
        if v2 == v_used:
            continue
        ok_ref, expected2, _ = oracle(f"LDI r0 {k}\n{op} r10 r0\nRET\n", 10, v2)
        if not ok_ref or expected2 is None:
            continue
        if expected2 != 0:
            best = (v2, expected2)
            break
        if best is None:
            best = (v2, expected2)  # fallback if every candidate happens to be degenerate
    if best is None:
        return None, None, None
    v2, expected2 = best
    ok, got2, _ = oracle(tile_text, 10, v2)
    return bool(ok and got2 == expected2), v2, expected2


def ask(model: str, prompt: str, temperature: float, max_tokens: int = 512):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": temperature, "num_predict": max_tokens}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        d = json.loads(resp.read().decode())
    return d.get("response", ""), d.get("eval_count", 0), time.time() - t0


def extract(text: str) -> str:
    m = re.search(r"```[a-z]*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-coder:30b")
    ap.add_argument("--tasks", type=int, default=12)
    ap.add_argument("--draws", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--isa", default="minimal",
                     choices=["minimal", "minimal_shift", "minimal_shr_denial"])
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--out", default="tools/builder_eval/ollama_tile_sample_results.json")
    a = ap.parse_args()

    rnd = random.Random(a.seed)
    ops = ["ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR"]
    OPLABEL = {"ADD": "add K to the input", "SUB": "subtract K from the input",
               "AND": "bitwise-AND the input with K", "OR": "bitwise-OR the input with K",
               "XOR": "bitwise-XOR the input with K", "SHL": "shift the input left by K bits",
               "SHR": "shift the input right by K bits"}

    tasks = []
    for _ in range(a.tasks):
        op, k = rnd.choice(ops), rnd.randint(1, 7)
        v = rnd.randint(8, 40)
        ok, expected, err = oracle(f":ref\n  LDI r0 {k}\n  {op} r10 r0\n  RET\n", 10, v)
        if not ok or expected is None:
            print(f"skip (reference tile unusable for {op} K={k} V={v}: ok={ok} expected={expected} err={err})")
            continue
        tasks.append({"op": op, "k": k, "v": v, "expected": expected,
                      "spec": f"The input value is in r10. Leave r10 equal to the result of: {OPLABEL[op]} (K = {k})."})

    check_rnd = random.Random(a.seed ^ 0x5EC0)  # independent stream from task sampling
    rows = []
    for i, t in enumerate(tasks, 1):
        accepts = 0
        print(f"[{i}/{len(tasks)}] {t['op']} K={t['k']} V={t['v']} → expect {t['expected']}")
        for c in range(1, a.draws + 1):
            rule = (SHIFT_RULE if a.isa == "minimal_shift" else
                    SHR_DENIAL_RULE if a.isa == "minimal_shr_denial" else "")
            prompt = f"{ISA}{rule}\n\nTASK: {t['spec']}\n\nTile:"
            text, tok, wall = ask(a.model, prompt, a.temperature)
            tile = extract(text)
            ok, got, err = oracle(tile, 10, t["v"])
            first_pass = bool(ok and got == t["expected"])

            # A pass on ONE (k, v) can be a coincidence (e.g. a value-as-count bug that
            # happens to output 0 when the correct answer is also 0). Only count a tile
            # as accepted once it also holds on a second, independently-drawn input.
            verified, check_v, check_expected = (None, None, None)
            if first_pass:
                verified, check_v, check_expected = coincidence_check(
                    tile, t["op"], t["k"], t["v"], check_rnd)
            good = bool(first_pass and verified)  # verified is None (unusable ref) -> not accepted
            accepts += good

            tag = "ACCEPT" if good else ("COINCIDENCE" if first_pass and verified is False else
                                          "unverifiable" if first_pass and verified is None else "reject")
            print(f"    draw {c}: {tag} got={got} {wall:.2f}s {tok}tok"
                  + (f"  [2nd check V={check_v} expect={check_expected}]" if first_pass else ""))
            rows.append({**{k: t[k] for k in ("op", "k", "v", "expected")},
                         "draw": c, "accept": good, "first_pass": first_pass,
                         "coincidence_check": ("VERIFIED" if verified else
                                                "COINCIDENCE" if verified is False else
                                                "UNCHECKED" if not first_pass else "SKIPPED"),
                         "check_v": check_v, "check_expected": check_expected,
                         "got": got, "tok": tok, "wall": round(wall, 2), "tile": tile})

    Path(a.out).write_text(json.dumps({"model": a.model, "seed": a.seed, "draws": a.draws,
                                       "rows": rows}, indent=1) + "\n")
    n, acc = len(rows), sum(1 for r in rows if r["accept"])
    print(f"\nMECHANICAL SAMPLE: {acc}/{n} = {100.0 * acc / max(n, 1):.1f}% acceptance")
    by_op = {}
    for r in rows:
        by_op.setdefault(r["op"], []).append(r["accept"])
    for op in sorted(by_op):
        v = by_op[op]
        print(f"  {op:4s} {sum(v)}/{len(v)}")
    print(f"results → {a.out}")


if __name__ == "__main__":
    main()
