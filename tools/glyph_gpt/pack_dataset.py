#!/usr/bin/env python3
"""
pack_dataset.py — build the Phase 3c training dataset from corpus + synth.

Usage:
    python3 tools/glyph_gpt/pack_dataset.py [--seq-len 128]

Outputs:
    tools/glyph_gpt/dataset.npz      (ids, values, meta_json)
    tools/glyph_gpt/tokenizer.json   frozen vocab
    tools/glyph_gpt/DATASET_RECEIPT.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from glyph_gpt.tokenizer import GlyphTokenizer
from glyph_gpt import dataset

SEQ_LEN_DEFAULT = 128


def load_opcodes_from_transpiler() -> list:
    """Opcode set = what OpcodeMapV2 accepts (superset of what the
    transpiler emits) — the model may need every legal opcode."""
    # glyph_isa_v2 imports "tools.wordbase", so the REPO ROOT must be on
    # sys.path (not just tools/) for the package import to resolve.
    repo_root = str(_TOOLS.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from glyph_isa_v2 import OpcodeMapV2
    return sorted(OpcodeMapV2()._opcode_to_rgb.keys())


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq-len", type=int, default=SEQ_LEN_DEFAULT)
    ap.add_argument("--include-nohalt", action="store_true",
                    help="include repo no_halt programs (execution-unverified)")
    ap.add_argument("--upsample", action="append", default=[],
                    metavar="FAMILY:COUNT",
                    help="repeat a synth family's entries COUNT times "
                         "(e.g. --upsample leaf_call:4 fixes class imbalance "
                         "for rare control-flow patterns)")
    args = ap.parse_args()

    # parse upsample spec
    upsample: dict = {}
    for spec in args.upsample:
        fam, _, cnt = spec.partition(":")
        upsample[fam] = int(cnt)

    # ── load entries ──────────────────────────────────────────────────
    corpus_path = _HERE / "corpus.jsonl"
    synth_path = _HERE / "synth_receipts.jsonl"
    entries = []
    if corpus_path.exists():
        for line in corpus_path.read_text().splitlines():
            e = json.loads(line)
            if e.get("oracle", {}).get("status") != "pass":
                # keep no_halt only if explicitly allowed; drop errors/unknown
                if not (args.include_nohalt and e["oracle"].get("status") == "no_halt"):
                    continue
            entries.append(e)
    if synth_path.exists():
        for line in synth_path.read_text().splitlines():
            entries.append(json.loads(line))

    # Phase 5.5: family upsampling (rare control-flow patterns like
    # leaf_call's CALL plumbing are 1-per-program against hundreds of
    # ALU ops — repeat to rebalance the gradient)
    if upsample:
        repeated = []
        for e in entries:
            fam = e.get("family")
            count = upsample.get(fam, 1)
            repeated.extend([e] * count)
        entries = repeated

    # ── tokenizer ─────────────────────────────────────────────────────
    opcodes = load_opcodes_from_transpiler()
    tok = GlyphTokenizer(opcodes=opcodes)
    tok.save(str(_HERE / "tokenizer.json"))

    # ── pack ──────────────────────────────────────────────────────────
    ids, values, receipt = dataset.build_sequences(
        entries, tok, seq_len=args.seq_len)
    receipt["opcodes_in_vocab"] = len(opcodes)
    receipt["entries_loaded"] = len(entries)

    # vocab coverage: which token ids actually appear
    used = sorted(set(ids.flatten().tolist()) - {0})
    receipt["tokens_used"] = len(used)
    num_positions = (ids != 0) & (ids == 5)  # NUM token id
    vals = values[num_positions]
    if vals.size:
        receipt["value_min"] = int(vals.min())
        receipt["value_max"] = int(vals.max())

    dataset.save_dataset(ids, values, _HERE / "dataset.npz", meta=receipt)
    (_HERE / "tokenizer.json").write_text(json.dumps(
        {"opcodes": opcodes}, indent=2))

    # ── receipt ───────────────────────────────────────────────────────
    import numpy as np
    size_kb = (_HERE / "dataset.npz").stat().st_size / 1024
    lines = [
        "# Dataset Receipt — Phase 3c",
        "",
        f"**Date**: see git log",
        f"**Command**: `python3 tools/glyph_gpt/pack_dataset.py --seq-len {args.seq_len}`",
        "",
        "| metric | value |",
        "|---|---|",
        f"| entries loaded | {receipt['entries_loaded']} |",
        f"| sequences packed | {receipt['sequences']} |",
        f"| skipped | {receipt['skipped']} |",
        f"| seq_len | {args.seq_len} |",
        f"| max program tokens | {receipt['max_len_seen']} |",
        f"| vocab size | {receipt['vocab_size']} |",
        f"| opcodes in vocab | {len(opcodes)} |",
        f"| distinct tokens used | {len(used)} |",
        f"| immediate value range | {receipt.get('value_min')} … {receipt.get('value_max')} |",
        f"| array shape | {ids.shape} |",
        f"| dataset.npz size | {size_kb:.1f} KB |",
        "",
        "## per-family",
        "",
        "| family | sequences |",
        "|---|---|",
    ]
    for fam, cnt in sorted(receipt["per_family"].items()):
        lines.append(f"| {fam} | {cnt} |")
    (_HERE / "DATASET_RECEIPT.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
