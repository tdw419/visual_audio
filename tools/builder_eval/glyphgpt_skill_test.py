#!/usr/bin/env python3
"""glyphgpt_skill_test.py — can GlyphGPT use the glyph-teleoperation skill to build?

Three tests, in increasing fairness to the model:

  A. CAN IT READ THE SKILL AT ALL?
     Feed the skill markdown to GlyphGPT's own tokenizer; report what happens
     and how many tokens it would need vs the model's max_seq_len.

  B. BEST-CASE PACKING ARITHMETIC
     Even if every skill byte encoded perfectly, how many positions would it
     take? Compare against max_seq_len (128).

  C. THE FAIR SHOT (its own modality)
     The skill's deliverable is a decoder. GlyphGPT cannot write Python, so the
     fair analogue is: can it emit an ORACLE-ACCEPTED glyph tile for a real
     routine it has never memorised? Best-of-N with the FSM, oracle-scored via
     the repo's own path (best_of_n / draft_tile machinery).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

SKILL_CANDIDATES = [
    pathlib.Path.home() / ".hermes" / "skills",
    ROOT / "skills",
]


def find_skill() -> pathlib.Path | None:
    for base in SKILL_CANDIDATES:
        for p in base.rglob("SKILL.md"):
            if "teleoperation" in str(p).lower():
                return p
    return None


def test_a_and_b() -> dict:
    from glyph_gpt.tokenizer import GlyphTokenizer  # type: ignore
    from glyph_gpt.model import GlyphGPTConfig  # type: ignore

    tok_path = ROOT / "tools" / "glyph_gpt" / "tokenizer.json"
    ckpt = ROOT / "tools" / "glyph_gpt" / "checkpoint.pt"
    skill = find_skill()
    out: dict = {"skill_path": str(skill) if skill else None}
    if skill is None:
        out["error"] = "skill markdown not found"
        return out
    text = skill.read_text(encoding="utf-8", errors="replace")
    out["skill_bytes"] = len(text.encode("utf-8"))
    out["skill_lines"] = text.count("\n") + 1

    cfg = GlyphGPTConfig()
    out["max_seq_len"] = getattr(cfg, "max_seq_len", None)

    tok = GlyphTokenizer.load(str(tok_path))
    out["vocab_size"] = getattr(tok, "vocab_size", None)
    try:
        enc = tok.encode(text)
        ids = enc[0] if isinstance(enc, tuple) else enc
        out["tokenized"] = True
        out["n_tokens"] = len(ids)
        out["first_tokens"] = [int(i) for i in list(ids)[:24]]
    except Exception as e:  # noqa: BLE001
        out["tokenized"] = False
        out["encode_error"] = f"{type(e).__name__}: {e}"

    # B: best-case packing (1 char per token)
    out["best_case_positions_needed"] = out["skill_bytes"] + 16
    if out["max_seq_len"]:
        out["oversubscription_x"] = round(out["best_case_positions_needed"] / out["max_seq_len"], 1)
    return out


def test_c(n: int, seed_family: str) -> dict:
    """Best-of-N oracle-scored tile drafting — GlyphGPT's own modality."""
    from glyph_gpt.best_of_n import best_of_n  # type: ignore
    from glyph_gpt.tokenizer import GlyphTokenizer  # type: ignore
    from glyph_gpt.model import load_checkpoint  # type: ignore

    tok = GlyphTokenizer.load(str(ROOT / "tools" / "glyph_gpt" / "tokenizer.json"))
    model = load_checkpoint(str(ROOT / "tools" / "glyph_gpt" / "checkpoint.pt"))

    # Seed: a real corpus tile, truncated to the prompt convention (first 60%).
    corpus = ROOT / "tools" / "glyph_gpt" / "corpus.jsonl"
    rows = [json.loads(l) for l in corpus.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("text")]
    if not rows:
        return {"error": "no corpus tiles with text"}
    row = rows[0]
    text = row["text"]
    cut = text.splitlines()
    head = "\n".join(cut[: max(1, int(len(cut) * 0.6))]) + "\n"

    enc = tok.encode(head)
    p_ids, p_vals = enc if isinstance(enc, tuple) else (enc, None)
    t0 = time.time()
    try:
        res = best_of_n(
            p_ids,
            p_vals,
            model,
            tok,
            n=n,
            temperature=0.7,
            max_new_tokens=200,
            cols_instrs=8,
        )
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "seed_tile": row.get("tile", "?")}
    wall = time.time() - t0
    best = res.get("best") or {}
    allr = res.get("all") or []
    score = best.get("score")
    scores = [r.get("score") for r in allr if isinstance(r.get("score"), int)]
    accepted = isinstance(score, int) and score > 0
    return {
        "seed_tile": row.get("tile", "?"),
        "n": n,
        "best_score": score,
        "score_histogram": {str(k): scores.count(k) for k in sorted(set(scores))},
        "halted": bool(best.get("halted")),
        "accepted": accepted,
        "detail": best.get("detail"),
        "wall_s": round(wall, 2),
        "ms_per_attempt": round(1000 * wall / max(1, n), 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--json-out", default=str(ROOT / "tools" / "builder_eval" / "glyphgpt_skill_results.json"))
    args = ap.parse_args()

    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    print("=== TEST A/B: can GlyphGPT even ingest the skill? ===")
    try:
        ab = test_a_and_b()
    except Exception as e:  # noqa: BLE001
        ab = {"error": f"{type(e).__name__}: {e}"}
    report["A_B"] = ab
    for k, v in ab.items():
        print(f"  {k}: {v}")
    print()
    print(f"=== TEST C: fair shot — best-of-{args.n} oracle-scored tile drafting ===")
    c = test_c(args.n, "alu_chain")
    report["C"] = c
    for k, v in c.items():
        print(f"  {k}: {v}")

    pathlib.Path(args.json_out).write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n[recorded] {args.json_out}")


if __name__ == "__main__":
    main()
