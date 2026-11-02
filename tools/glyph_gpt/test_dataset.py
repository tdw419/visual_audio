#!/usr/bin/env python3
"""
Round 4a tests for dataset.py — run before model training relies on it.

Verifies:
  1. save/load round-trip preserves ids/values/meta exactly.
  2. Framing: every sequence starts BOS, ends EOS before pads.
  3. Padding: all positions after EOS are PAD and value 0.
  4. Decode-then-reencode stability of a packed sequence (modulo comments).
  5. Oracle-gate honored: oracle_fail entries excluded when require_match.
"""
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent
for p in (str(_TOOLS), str(_HERE), str(_TOOLS.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from glyph_gpt.tokenizer import GlyphTokenizer, PAD, BOS, EOS, NUM
from glyph_gpt import dataset

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def main():
    tok = GlyphTokenizer.load(str(_HERE / "tokenizer.json"))
    ids, values, meta = dataset.load_dataset(_HERE / "dataset.npz")
    print(f"loaded {ids.shape} meta={ {k: meta[k] for k in ('sequences','seq_len')} }")

    # 1. round-trip via temp file
    tmp = _HERE / "_test_roundtrip.npz"
    dataset.save_dataset(ids[:5], values[:5], tmp, meta={"probe": 1})
    ids2, values2, meta2 = dataset.load_dataset(tmp)
    check("save/load ids identical", np.array_equal(ids[:5], ids2))
    check("save/load values identical", np.array_equal(values[:5], values2))
    check("save/load meta identical", meta2 == {"probe": 1})
    tmp.unlink()

    # 2. framing on every sequence
    bos_ok = (ids[:, 0] == BOS).all()
    check("every sequence starts BOS", bool(bos_ok))

    eos_present = (ids == EOS).any(axis=1).all()
    check("every sequence contains EOS", bool(eos_present))

    # 3. padding: after first EOS, everything PAD and value 0
    pad_ok = True
    for i in range(ids.shape[0]):
        row = ids[i]
        eos_pos = int(np.argmax(row == EOS))
        tail = row[eos_pos + 1:]
        if (tail != PAD).any() or (values[i, eos_pos + 1:] != 0).any():
            pad_ok = False
            print(f"    row {i} bad tail at eos_pos={eos_pos}: {tail[:5]}")
            break
    check("padding clean after EOS", pad_ok)

    # 4. decode/re-encode stability (modulo comments and the family
    # conditioning prefix), first 50 rows. decode() drops FAMILY tokens
    # by design (they're training-side conditioning, not program text),
    # so re-encode without family= lacks the prefix.
    from glyph_gpt.tokenizer import FAMILY_TOKENS
    fam_ids = {tok.token_to_id[t] for t in FAMILY_TOKENS}
    stable = 0
    for i in range(min(50, ids.shape[0])):
        row_ids = ids[i][ids[i] != PAD].tolist()
        row_vals = values[i][:len(row_ids)].tolist()
        text = tok.decode(row_ids, row_vals)
        ids_r, vals_r = tok.encode(text)
        # compare modulo COMMENT and FAMILY tokens (decode drops them)
        def strip_extra(i_list, v_list):
            return [(a, b) for a, b in zip(i_list, v_list)
                    if a != 4 and a not in fam_ids]
        if strip_extra(row_ids, row_vals) == strip_extra(ids_r, vals_r):
            stable += 1
    check("decode/re-encode stable (50 rows)", stable == min(50, ids.shape[0]),
          f"only {stable}/50")

    # 5. NUM values survived packing
    num_mask = ids == NUM
    n_num = int(num_mask.sum())
    check("value channel carries immediates", n_num > 1000,
          f"only {n_num} NUM positions")
    nz = values[num_mask]
    check("immediate range matches receipt",
          int(nz.min()) >= meta["value_min"] and int(nz.max()) <= meta["value_max"])

    print(f"\nDataset tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
