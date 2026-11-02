#!/usr/bin/env python3
"""draft_tile.py — the builder's callable GlyphGPT drafter (tier-0 candidate).

WHY: GlyphGPT (828K params, FSM-masked, oracle-gated) is the cheapest drafter in the
repo — milliseconds per attempt, no API, no auth. It is currently reachable only from
library code (GH-26.3 admission, the S3 measurement) and from escalate.py's *Ollama*
path, so a builder that wants a tile drafted has no single command to call. This is
that command.

WHAT IT DOES: takes a SEED tile (a partial .glyph program) and a family contract, samples
N FSM-masked completions from GlyphGPT, executes each on the GlyphCPUv2 oracle, and
reports/persists the best one. Exit 0 iff at least one completion is oracle-accepted
under the family's semantic contract; exit 1 otherwise (so a caller can fall back).

HONEST EXPECTATION (measured, see tools/glyph_gpt/S3_RECEIPT.md): 9% first-try semantic
acceptance overall, clustered — 3 of 20 tiles at ~3/5 completions, the other 17 at 0/5.
So tier-0 is a cheap lottery with a known, low win rate; the oracle is what makes it safe
to try first. Do NOT treat an exit 0 as a capability claim beyond the tile it returns.

USAGE
  python3 tools/glyph_gpt/draft_tile.py --seed <tile.glyph> --family accumulate --n 8
  python3 tools/glyph_gpt/draft_tile.py --seed <tile.glyph> --family leaf_call --n 16 --out /tmp/draft.glyph
  python3 tools/glyph_gpt/draft_tile.py --text ':entry\n  LDI r10 1\n' --family alu_chain --n 4
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent
_REPO = _TOOLS.parent
for p in (str(_REPO), str(_TOOLS), str(_HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import torch  # noqa: E402

from glyph_gpt.best_of_n import best_of_n  # noqa: E402
from glyph_gpt.model import load_checkpoint  # noqa: E402
from glyph_gpt.tokenizer import BOS, EOS, GlyphTokenizer  # noqa: E402

PROMPT_FRACTION = 0.6  # the convention used by measure_acceptance.py


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", help="seed .glyph file whose first 60%% becomes the prompt")
    ap.add_argument("--text", help="seed text (alternative to --seed)")
    ap.add_argument("--family", default="leaf_call",
                    help="semantic contract family for grading (e.g. leaf_call, accumulate, alu_chain)")
    ap.add_argument("--n", type=int, default=8, help="sampled completions")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--out", help="write the accepted tile here (only if one is accepted)")
    args = ap.parse_args()

    if not args.seed and not args.text:
        ap.error("provide --seed or --text")

    text = Path(args.seed).read_text() if args.seed else args.text

    model = load_checkpoint(str(_HERE / "checkpoint.pt"))
    tok = GlyphTokenizer.load(str(_HERE / "tokenizer.json"))

    ids, vals = tok.encode(text)
    cut = max(1, int(len(ids) * PROMPT_FRACTION))
    keep = [(i, v) for i, v in zip(ids[:cut], vals[:cut]) if i not in (BOS, EOS)]
    p_ids = [i for i, _ in keep]
    p_vals = [v for _, v in keep]

    if not p_ids:
        print("ERROR: the seed produced an empty prompt (50%% cut removed every "
              "token, or the seed file is empty/missing).", file=sys.stderr)
        return 2

    t0 = time.time()
    res = best_of_n(p_ids, p_vals, model, tok,
                           n=args.n, family=args.family,
                           temperature=args.temperature)
    wall_ms = (time.time() - t0) * 1000

    best = res["best"]
    accepted = bool(best.get("text")) and int(best.get("score", -99)) > 0
    scores = [int(r.get("score", -99)) for r in res["all"]]

    print(json.dumps({
        "seed": args.seed or "<text>",
        "family": args.family,
        "n": args.n,
        "wall_ms": round(wall_ms, 1),
        "ms_per_attempt": round(wall_ms / max(1, args.n), 1),
        "any_halt": bool(res.get("any_halt")),
        "scores": scores,
        "score_histogram": {str(s): scores.count(s) for s in sorted(set(scores))},
        "median_score": statistics.median(scores) if scores else None,
        "accepted": accepted,
        "detail": best.get("detail"),
        "receipt": {k: v for k, v in (best.get("receipt") or {}).items()
                    if k in ("halted", "faulted", "steps", "error")},
    }, indent=2))

    if accepted:
        print("--- accepted tile ---")
        print(best["text"])
        if args.out:
            Path(args.out).write_text(best["text"])
            print(f"--- written to {args.out} ---")
        return 0

    print("NOT ACCEPTED: no completion satisfied the oracle under this contract.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
