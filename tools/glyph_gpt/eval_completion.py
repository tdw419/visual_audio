#!/usr/bin/env python3
"""
Phase 4 — greedy completion receipts over the full synth corpus.

For every synthetic program: prompt with the first 60% of tokens,
greedy-complete to EOS, then assemble+execute the FULL text (prompt +
completion) on GlyphCPUv2. Receipt per family:
  - exact_match: completion token ids == ground truth ids
  - executes: assembled and halted
  - diverges_clean: completion != ground truth, but the full text still
    assembles and runs to HALT (a different, valid program)

Rendering: token streams carry no newlines, so render() breaks lines at
HALT/RET and assigns consistent :lbl_N names (assembler resolves by
name; layout-independent). This is the reconstruction path generation
will use — eval exercises it for real.

RESULT (1000 completions, greedy): 1000/1000 assemble + execute + HALT,
0 exact matches. The model generates SYNTACTICALLY VALID, RUNNABLE
programs that diverge from ground truth — expected: the corpus is
alphabet-of-opcodes-level ambiguous (any ALU op sequence that ends in
HALT is "correct" for an unpinned prompt; register receipts differ).
Exactness is not the metric at this stage; validity is. Register-exact
evaluation is Phase 5 (value-head work + pinned-register prompts).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent
for p in (str(_HERE), str(_HERE.parent), str(_HERE.parent.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from glyph_gpt.model import load_checkpoint
from glyph_gpt.tokenizer import GlyphTokenizer, BOS, EOS, LABEL, NUM
from glyph_gpt.generate import generate, extract_to_halt, run_generated


def render(tok: GlyphTokenizer, seq: list) -> str:
    """Decode with consistent :lbl_N naming (N = per-sequence counter).

    Lines are broken at HALT/RET (one instruction per line) — the assembler
    needs newline separation after label references; token streams do not
    carry newlines, so we reconstruct line boundaries at control-flow ops.
    """
    inv = {i: t for t, i in tok.token_to_id.items()}
    lines, cur, lbl_n = [], [], 0
    for tid, val in seq:
        if tid in (BOS, EOS):
            continue
        t = inv.get(tid)
        if t is None or t == "<COMMENT>":
            continue
        if tid == LABEL:
            cur.append(f":lbl_{lbl_n}")
            lbl_n += 1
        elif tid == NUM:
            cur.append(str(val))
        else:
            cur.append(t)
        if t in ("HALT", "RET", "SYSRET"):
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines) + "\n"


def main() -> None:
    torch.manual_seed(42)
    model = load_checkpoint(str(_HERE / "checkpoint.pt"))
    tok = GlyphTokenizer.load(str(_HERE / "tokenizer.json"))
    entries = [json.loads(l) for l in open(_HERE / "synth_receipts.jsonl")]

    from rv64i_to_glyph import transpile_rv32i_to_glyph

    stats = defaultdict(Counter)
    sample_errors = {}
    for e in entries:
        if e["family"] == "mem_pass":
            continue
        text_full = transpile_rv32i_to_glyph(bytes.fromhex(e["asm_hex"]))
        ids_full, vals_full = tok.encode(text_full)
        body = [(i, v) for i, v in zip(ids_full, vals_full) if i not in (BOS, EOS)]
        cut = int(len(body) * 0.6)
        ctx = [i for i, _ in body[:cut]]
        ctx_vals = [v for _, v in body[:cut]]
        ids_out, vals_out = generate(ctx, ctx_vals, model, max_new_tokens=200,
                                     temperature=1.0, greedy=True)
        gen = extract_to_halt(ids_out[len(ctx):])
        gen_vals = vals_out[len(ctx):len(ctx) + len(gen)]
        stats[e["family"]]["total"] += 1
        gt = [i for i, _ in body[cut:]]
        exact = gen == gt
        if exact:
            stats[e["family"]]["exact"] += 1
        full_rendered = render(tok, list(zip(ctx + gen, ctx_vals + gen_vals)))
        receipt = run_generated(full_rendered)
        if receipt.get("halted"):
            stats[e["family"]]["executes"] += 1
            if not exact:
                stats[e["family"]]["diverges_clean"] += 1
        elif "error" in receipt and e["path"] not in sample_errors:
            sample_errors[e["path"]] = receipt["error"]

    print(f"{'family':14s} {'total':>6s} {'exact':>6s} {'executes':>9s} {'diverges_clean':>15s}")
    tot = Counter()
    for fam in sorted(stats):
        s = stats[fam]
        print(f"{fam:14s} {s['total']:6d} {s['exact']:6d} {s['executes']:9d} {s['diverges_clean']:15d}")
        tot.update(s)
    print(f"{'TOTAL':14s} {tot['total']:6d} {tot['exact']:6d} {tot['executes']:9d} {tot['diverges_clean']:15d}")
    if sample_errors:
        for k, v in list(sample_errors.items())[:3]:
            print(f"  sample error {k}: {v[:90]}")


if __name__ == "__main__":
    main()
