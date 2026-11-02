#!/usr/bin/env python3
"""
train.py — GlyphGPT training loop.

Round 4c implementation. Simple, honest, CPU-friendly:
  - AdamW, cosine LR schedule, next-token targets from ids shift
  - loss ignores PAD targets (masking handled in model.forward)
  - checkpoint carries config + tokenizer path + final metrics
  - deterministic: torch.manual_seed pinned in main()

Metrics returned/printed per the skeleton contract: final_loss, epochs,
params, seconds — plus token accuracy on the training set (the honest
overfit-check for a 1250-sequence corpus: we WANT near-100% train acc;
generalization receipts come from the Phase 4 oracle, not from held-out
splits at this corpus size).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Dict

import numpy as np
import torch

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_HERE.parent))

from glyph_gpt.dataset import load_dataset
from glyph_gpt.model import GlyphGPT, GlyphGPTConfig, save_checkpoint


def _batch_iterator(ids: np.ndarray, values: np.ndarray, batch_size: int,
                    generator: torch.Generator):
    n = ids.shape[0]
    order = torch.randperm(n, generator=generator)
    for start in range(0, n, batch_size):
        idx = order[start:start + batch_size]
        yield (torch.from_numpy(ids[idx]).long(),
               torch.from_numpy(values[idx]).long())


@torch.no_grad()
def _train_accuracy(model, ids: np.ndarray, values: np.ndarray,
                    batch_size: int = 128) -> float:
    """Next-token accuracy over non-PAD target positions."""
    model.eval()
    correct = total = 0
    for start in range(0, ids.shape[0], batch_size):
        ids_b = torch.from_numpy(ids[start:start + batch_size]).long()
        val_b = torch.from_numpy(values[start:start + batch_size]).long()
        logits, _ = model(ids_b, val_b)
        preds = logits[:, :-1].argmax(dim=-1)
        targets = ids_b[:, 1:]
        mask = targets != 0
        correct += int((preds[mask] == targets[mask]).sum())
        total += int(mask.sum())
    return correct / max(total, 1)


def train(dataset_path: Path, out_path: Path, epochs: int = 100,
          batch_size: int = 64, lr: float = 3e-4,
          device: str = "cpu") -> Dict:
    ids, values, meta = load_dataset(dataset_path)
    seq_len = int(meta["seq_len"]) if meta and "seq_len" in meta else ids.shape[1]

    cfg = GlyphGPTConfig(
        vocab_size=int(meta["vocab_size"]) if meta else 72,
        d_model=128, n_heads=4, n_layers=4,
        max_seq_len=seq_len, dropout=0.0, value_channels=8)

    torch.manual_seed(42)
    model = GlyphGPT(cfg).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    n_steps = epochs * (ids.shape[0] + batch_size - 1) // batch_size
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: 0.5 * (1 + __import__("math").cos(
            __import__("math").pi * min(s / max(n_steps, 1), 1.0))))

    t0 = time.time()
    gen = torch.Generator().manual_seed(42)
    final_loss = float("nan")
    for epoch in range(epochs):
        model.train()
        for ids_b, val_b in _batch_iterator(ids, values, batch_size, gen):
            targets = ids_b[:, 1:]
            logits, loss = model(ids_b[:, :-1], val_b[:, :-1], targets)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            final_loss = float(loss.item())
        if (epoch + 1) % 20 == 0 or epoch == 0 or epoch == epochs - 1:
            acc = _train_accuracy(model, ids, values)
            print(f"epoch {epoch + 1:4d}/{epochs}  loss {final_loss:.4f}  "
                  f"train_next_token_acc {acc:.4f}")

    seconds = time.time() - t0
    acc = _train_accuracy(model, ids, values)
    metrics = {
        "final_loss": final_loss,
        "epochs": epochs,
        "params": model.num_params(),
        "seconds": round(seconds, 1),
        "train_next_token_acc": round(acc, 4),
        "sequences": int(ids.shape[0]),
        "vocab_size": cfg.vocab_size,
    }
    save_checkpoint(model, str(out_path), metadata={"metrics": metrics})
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description="Train GlyphGPT")
    ap.add_argument("--dataset", default=str(_HERE / "dataset.npz"))
    ap.add_argument("--out", default=str(_HERE / "checkpoint.pt"))
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-4)
    args = ap.parse_args()
    metrics = train(Path(args.dataset), Path(args.out),
                    epochs=args.epochs, batch_size=args.batch_size, lr=args.lr)
    print("final:", metrics)


if __name__ == "__main__":
    main()
