#!/usr/bin/env python3
"""
Round 4b tests for model.py — causality, value-channel sensitivity,
loss masking, checkpoint round-trip.
"""
import sys
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent
for p in (str(_HERE), str(_HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from glyph_gpt.model import GlyphGPT, GlyphGPTConfig, save_checkpoint, load_checkpoint

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
    torch.manual_seed(42)
    cfg = GlyphGPTConfig(vocab_size=72, d_model=64, n_heads=4, n_layers=2,
                         max_seq_len=64, value_channels=8)
    model = GlyphGPT(cfg)
    print(f"params: {model.num_params():,}")

    B, T = 4, 32
    ids = torch.randint(1, 72, (B, T))
    values = torch.zeros(B, T, dtype=torch.long)
    values[:, ::4] = torch.randint(-200, 4351, (B, 8))

    # 1. causality: perturbing future tokens must not change past logits
    with torch.no_grad():
        logits1, _ = model(ids, values)
        ids_pert = ids.clone()
        ids_pert[:, 20] = (ids_pert[:, 20] + 7) % 71 + 1
        logits2, _ = model(ids_pert, values)
    past_same = torch.allclose(logits1[:, :20], logits2[:, :20], atol=1e-5)
    future_diff = not torch.allclose(logits1[:, 20], logits2[:, 20], atol=1e-5)
    check("causal: past logits unchanged by future edit", bool(past_same))
    check("causal: present logits change with present edit", bool(future_diff))

    # 2. value channel sensitivity: changing values changes logits
    values2 = values.clone()
    values2[:, 0] = 1234
    with torch.no_grad():
        logits3, _ = model(ids, values2)
    check("value channel affects logits",
          bool(not torch.allclose(logits1[:, 0], logits3[:, 0], atol=1e-6)))

    # 3. loss masking: PAD targets contribute zero
    targets = ids.clone()
    targets[:, 16:] = 0  # PAD ignore_index
    _, loss_full = model(ids, values, targets)
    check("loss finite with PAD-masked targets", bool(torch.isfinite(loss_full)))

    # 4. loss decreases over a few steps on a fixed batch (SGD sanity)
    model.train()
    opt = torch.optim.SGD(model.parameters(), lr=1e-3)
    first = None
    for step in range(30):
        _, loss = model(ids, values, targets)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if first is None:
            first = loss.item()
    check("loss decreases under SGD", loss.item() < first,
          f"{first:.4f} -> {loss.item():.4f}")

    # 5. checkpoint round-trip
    ckpt = _HERE / "_test_ckpt.pt"
    save_checkpoint(model, str(ckpt), metadata={"steps": 30})
    model2 = load_checkpoint(str(ckpt))
    with torch.no_grad():
        l1, _ = model.eval()(ids, values)
        l2, _ = model2(ids, values)
    check("checkpoint round-trip logits identical",
          bool(torch.allclose(l1, l2, atol=1e-6)))
    ckpt.unlink()

    print(f"\nModel tests: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
