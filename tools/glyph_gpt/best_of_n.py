#!/usr/bin/env python3
"""
best_of_n.py — Phase 5.5C: oracle rejection sampling.

Sample N completions (FSM+valcond masked, temperature>0), execute each on
GlyphCPUv2, and keep the best receipt by a graded score:

    executed+halted            (hard gate)
    family semantic contract   (e.g. leaf_call: a0 == 2*v_self, where v_self
                                is read from the completion's own LDI r10)
    steps to halt              (tiebreak: fewer is better)

The oracle is ground truth — a program that executes and halts with the
right register state IS correct, regardless of token-level divergence.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import torch

from glyph_gpt.generate import generate, extract_to_halt, run_generated
from glyph_gpt.tokenizer import GlyphTokenizer, BOS


def _read_ldi_reg(text: str, reg: str):
    """Read the last LDI <reg> <imm> immediate from glyph text, or None."""
    v = None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "LDI" and parts[1] == reg:
            try:
                v = int(parts[2], 0)
            except ValueError:
                pass
    return v


def semantic_score(text: str, receipt: dict, family: str) -> tuple:
    """Return (score, detail). Higher = better. Hard gates as negative
    scores so any executing receipt beats any non-executing one."""
    if not receipt.get("assembled"):
        return -3, receipt.get("error", "not assembled")
    if not (receipt.get("executed") and receipt.get("halted")):
        return -2, "did not halt"
    regs = receipt.get("registers_full")
    score, detail = 0, "ok"
    if family == "leaf_call" and regs:
        v = _read_ldi_reg(text, "r10")
        if v is not None:
            want = (2 * v) & 0xFFFFFFFF
            if regs[10] == want:
                score += 2
                detail = f"a0==2*v (v={v})"
            else:
                score -= 1
                detail = f"a0={regs[10]} != 2*{v}"
        else:
            score -= 1
            detail = "no LDI r10 found"
    if score > 0:
        score = score * 1000 - receipt.get("steps", 0)  # tiebreak on steps
    return score, detail


def best_of_n(prompt_ids: list, prompt_values: list, model, tok,
             family: Optional[str] = None, n: int = 8,
             temperature: float = 0.7, max_new_tokens: int = 200,
             ldi_reg_vals: Optional[dict] = None,
             cols_instrs: int = 8) -> dict:
    """Sample n completions, return the best receipt + text + stats."""
    results = []
    for i in range(n):
        torch.manual_seed(1000 + i)
        ids_out, vals_out = generate(
            prompt_ids, prompt_values, model,
            max_new_tokens=max_new_tokens, temperature=temperature,
            greedy=False, tok=tok, use_fsm=True, ldi_reg_vals=ldi_reg_vals)
        gen = extract_to_halt(ids_out[len(prompt_ids):])
        gen_vals = vals_out[len(prompt_ids):len(prompt_ids) + len(gen)]
        if not gen:
            results.append({"score": -4, "detail": "empty generation",
                            "text": None, "receipt": {}})
            continue
        text = tok.decode([BOS] + gen, [0] + gen_vals, resolve_labels=True)
        receipt = run_generated(text, cols_instrs=cols_instrs)
        score, detail = semantic_score(text, receipt, family or "")
        results.append({"score": score, "detail": detail, "text": text,
                        "receipt": receipt})
    results.sort(key=lambda r: -r["score"])
    return {"best": results[0], "all": results,
            "n": n, "any_halt": any(r["receipt"].get("halted") for r in results)}
