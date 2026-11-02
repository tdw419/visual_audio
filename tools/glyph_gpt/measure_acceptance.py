#!/usr/bin/env python3
"""S3 acceptance measurement — productive emitter vs safe filter?

Roadmap open question (GH-24 S3): whether the 838K-param GlyphGPT on the
frozen post-GH-23 corpus is a *productive* emitter (oracle-accepted on
first try) or merely *safe* (rejections free, but never accepted).

Method (measured, no inference):
  For each of the 20 admitted backfill tiles (the post-GH-19 ABI corpus):
    - prompt = first 60% of the tile's token stream (eval_completion.py
      convention), tile text tokenized with the frozen tokenizer
    - N sampled completions (temperature 0.8, FSM-masked, valcond on)
      + 1 greedy completion per tile
    - completion -> full program text -> autoatlas raise -> assemble ->
      GlyphCPUv2 execute to HALT = SYNTACTIC acceptance
    - register-contract check vs the tile's oracle receipt =
      SEMANTIC acceptance (word-exact, the GH gate standard)
  Rates reported per completion class.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # tools/glyph_gpt
_TOOLS = _HERE.parent
_REPO = _TOOLS.parent
for p in (str(_REPO), str(_TOOLS), str(_HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import torch

from glyph_gpt.model import load_checkpoint
from glyph_gpt.tokenizer import GlyphTokenizer, BOS, EOS
from generate import generate, extract_to_halt, ids_to_text
from oracle import run_oracle

CORPUS = _HERE / "corpus.jsonl"
N_SAMPLES = 4          # sampled completions per tile
TEMP = 0.8
SEED = 42


def load_admitted_tiles():
    """The 20 measured backfill tiles: last 20 tile records (oracle.pass,
    oracle_exec_result present). Fall back to all pass records if fewer."""
    recs = [json.loads(l) for l in CORPUS.read_text().splitlines() if l.strip()]
    tiles = [r for r in recs
             if r.get("record_type") != "environment_header"
             and r.get("oracle", {}).get("status") == "pass"
             and "oracle_exec_result" in r]
    if len(tiles) < 20:
        tiles = [r for r in recs
                 if r.get("record_type") != "environment_header"
                 and r.get("oracle", {}).get("status") == "pass"]
    return tiles


def normalize_regs(regs):
    return [int(r) & 0xFFFFFFFF for r in regs]


def main():
    torch.manual_seed(SEED)
    model = load_checkpoint(str(_HERE / "checkpoint.pt"))
    tok = GlyphTokenizer.load(str(_HERE / "tokenizer.json"))
    tiles = load_admitted_tiles()
    print(f"measuring {len(tiles)} admitted tiles x "
          f"{N_SAMPLES} sampled + 1 greedy completion")

    stats = {
        "completions": 0,
        "syntactic_pass": 0,     # assembled + executed to HALT
        "semantic_pass": 0,      # + register contract word-exact
        "greedy_completions": 0,
        "greedy_semantic_pass": 0,
        "per_tile_first_try": [],   # tile-level: any of its completions passed?
    }

    for t_idx, tile in enumerate(tiles):
        text = tile["text"]
        oer = tile["oracle_exec_result"]
        expect = {}
        for k, v in (oer.get("checked_registers") or {}).items():
            expect[int(k)] = int(str(v), 16) if str(v).startswith("0x") \
                else int(v)
            expect[int(k)] &= 0xFFFFFFFF
        # seed argv/data from the receipt's seed_memory if recorded
        seed_mem = {int(k): int(v) for k, v in
                    (oer.get("seed_memory") or {}).items()} or None

        prompt_ids, prompt_vals = tok.encode(text)
        # 60% prompt convention; drop BOS/EOS so generation continues
        cut = int(len(prompt_ids) * 0.6)
        ctx_ids = [i for i in prompt_ids[:cut] if i not in (BOS, EOS)]
        ctx_vals = [v for i, v in zip(prompt_ids, prompt_vals)
                    if i not in (BOS, EOS)][:len(ctx_ids)]

        tile_any = False
        for s in range(N_SAMPLES + 1):
            greedy = (s == N_SAMPLES)
            with torch.no_grad():
                ids, vals = generate(ctx_ids, ctx_vals, model,
                                     max_new_tokens=160,
                                     temperature=TEMP if not greedy else 1.0,
                                     greedy=greedy, tok=tok, use_fsm=True)
            gen_ids = extract_to_halt(ids[len(ctx_ids):])
            if not gen_ids:
                stats["completions"] += 1
                continue
            gen_vals = vals[len(ctx_ids):len(ctx_ids) + len(gen_ids)]
            full_text = ids_to_text(tok, [BOS] + ctx_ids + gen_ids,
                                    [0] + ctx_vals + gen_vals)
            res = run_oracle(full_text, expect_registers=expect or None,
                             seed_memory=seed_mem, max_instructions=50_000)
            stats["completions"] += 1
            if greedy:
                stats["greedy_completions"] += 1
            if res.passed:
                stats["semantic_pass"] += 1
                tile_any = True
                if greedy:
                    stats["greedy_semantic_pass"] += 1
                if res.memory_hash:      # executed to HALT => syntactic too
                    stats["syntactic_pass"] += 1
            elif "no-halt" not in (res.error or "") and \
                 "assemble" not in (res.error or "").lower() and \
                 res.steps and res.steps > 0:
                # ran but contract mismatch / different-but-runnable
                stats["syntactic_pass"] += 1
        stats["per_tile_first_try"].append(tile_any)
        if (t_idx + 1) % 5 == 0:
            print(f"  ... {t_idx + 1}/{len(tiles)} tiles done: "
                  f"semantic {stats['semantic_pass']}/{stats['completions']}")

    n = max(stats["completions"], 1)
    nt = max(len(stats["per_tile_first_try"]), 1)
    print("\n=== S3 ACCEPTANCE MEASUREMENT ===")
    print(f"tiles measured:            {len(stats['per_tile_first_try'])}")
    print(f"completions measured:      {stats['completions']}")
    print(f"syntactic acceptance:      {stats['syntactic_pass']}/{n} "
          f"= {stats['syntactic_pass']/n:.1%}")
    print(f"SEMANTIC (word-exact):     {stats['semantic_pass']}/{n} "
          f"= {stats['semantic_pass']/n:.1%}")
    g = max(stats['greedy_completions'], 1)
    print(f"greedy semantic:           {stats['greedy_semantic_pass']}/{g} "
          f"= {stats['greedy_semantic_pass']/g:.1%}")
    print(f"tile-level hit rate:       "
          f"{sum(stats['per_tile_first_try'])}/{nt} "
          f"= {sum(stats['per_tile_first_try'])/nt:.1%}")
    verdict = ("PRODUCTIVE" if stats['semantic_pass']/n >= 0.25 else
               "SAFE-ONLY (fallback: template/grammar-guided generation)")
    print(f"verdict:                   {verdict}")

    (_HERE / "S3_ACCEPTANCE_MEASUREMENT.json").write_text(json.dumps({
        "method": "60% prompt, FSM-masked decode, oracle word-exact contract",
        "checkpoint": "checkpoint.pt (retrained post-GH-23, 100 epochs)",
        **stats}, indent=1))
    print("receipt: tools/glyph_gpt/S3_ACCEPTANCE_MEASUREMENT.json")


if __name__ == "__main__":
    main()
