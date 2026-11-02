#!/usr/bin/env python3
"""
model.py — GlyphGPT transformer.

Phase 5 implementation. Pre-norm decoder-only transformer, weight-tied
embeddings, same proven shape as pixel-hypervisor train_opcode_llm.py
(530K params → 100% syntactic validity) with:

  - dual-input embedding: token id + sinusoid value encoding (NUM/LABEL
    immediates projected to d_model and added to the token embedding)
  - a VALUE HEAD: parallel linear projection hidden → 1 that regresses
    the immediate scalar at NUM positions. Trained with masked MSE loss
    (only positions where the target value != 0 carry regression signal;
    other positions predict 0 and are ignored). At inference, generate()
    reads value_pred at whichever position the model emitted NUM.

Loss = token cross-entropy (PAD-masked) + value_weight * value MSE.

Config is saved inside checkpoints (glyphgpt-training contract:
"generate.py reads config from checkpoint").
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class GlyphGPTConfig:
    vocab_size: int = 72           # specials(10) + 32 regs + 30 opcodes
    d_model: int = 128
    n_heads: int = 4
    n_layers: int = 4
    max_seq_len: int = 128
    dropout: float = 0.0           # tiny corpus: no dropout
    value_channels: int = 8        # value embedding dimensionality (small)
    value_weight: float = 1.0      # value-loss weight in combined loss
    value_scale: float = 4351.0    # normalization bound (dataset max)
    n_value_bins: int = 96         # value classifier vocabulary size (+1)
    value_head_mode: str = "cls"   # "cls" (softmax bins) | "mse" (legacy)


# Value bin vocabulary: bin b (1..N) = direct small int; large values map
# by 64-step offsets. Built from the synth registries + common constants.
# Phase 5.4: 31 added — it occurs 250x as 'LDI r29 31' (SRLI shift const
# lowering) and was silently collapsing into the bin-0 catch-all, which
# decodes to 0 (measured as the entire r29 31->0 confusion class).
VALUE_BIN_TABLE = sorted(set(
    [-15, -9, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 17, 18,
     24, 27, 31, 33, 36, 42, 55, 64, 128, 240, 256, 512,
     0xaf, 0x10ff, 4351] + [64 * i for i in range(1, 64)]
))


def value_to_bin(v: int, table=VALUE_BIN_TABLE) -> int:
    """Map an int immediate to its bin id (0 = none/ignore)."""
    try:
        return table.index(int(v)) + 1
    except ValueError:
        return 0


def bin_to_value(b: int, table=VALUE_BIN_TABLE) -> int:
    return table[b - 1] if 1 <= b <= len(table) else 0


class CausalSelfAttention(nn.Module):
    def __init__(self, config: GlyphGPTConfig):
        super().__init__()
        assert config.d_model % config.n_heads == 0
        self.n_heads = config.n_heads
        self.d_head = config.d_model // config.n_heads
        self.qkv = nn.Linear(config.d_model, 3 * config.d_model, bias=False)
        self.proj = nn.Linear(config.d_model, config.d_model, bias=False)
        self.attn_dropout = config.dropout
        self.resid_dropout = nn.Dropout(config.dropout)

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q = q.view(B, T, self.n_heads, self.d_head).transpose(1, 2)
        k = k.view(B, T, self.n_heads, self.d_head).transpose(1, 2)
        v = v.view(B, T, self.n_heads, self.d_head).transpose(1, 2)
        # scaled dot product with causal mask (Flash attention when avail)
        y = F.scaled_dot_product_attention(
            q, k, v, is_causal=True,
            dropout_p=self.attn_dropout if self.training else 0.0)
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.resid_dropout(self.proj(y))


class Block(nn.Module):
    def __init__(self, config: GlyphGPTConfig):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.d_model)
        self.attn = CausalSelfAttention(config)
        self.ln2 = nn.LayerNorm(config.d_model)
        self.mlp = nn.Sequential(
            nn.Linear(config.d_model, 4 * config.d_model, bias=False),
            nn.GELU(),
            nn.Linear(4 * config.d_model, config.d_model, bias=False),
            nn.Dropout(config.dropout),
        )

    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.mlp(self.ln2(x))
        return x


class GlyphGPT(nn.Module):
    """Decoder-only LM over opcode tokens with parallel value embeddings
    and a value-regression head for exact immediates."""

    def __init__(self, config: GlyphGPTConfig):
        super().__init__()
        self.config = config
        self.tok_emb = nn.Embedding(config.vocab_size, config.d_model)
        self.val_proj = nn.Linear(config.value_channels, config.d_model, bias=False)
        self.pos_emb = nn.Embedding(config.max_seq_len, config.d_model)
        self.drop = nn.Dropout(config.dropout)
        self.blocks = nn.ModuleList([Block(config) for _ in range(config.n_layers)])
        self.ln_f = nn.LayerNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)
        self.lm_head.weight = self.tok_emb.weight  # weight tying
        # Phase 5.1: value head. "cls" mode = classifier over VALUE_BIN_TABLE
        # (exact argmax — MSE regression provably converges to the
        # conditional mean, measured MAE ≈ registry mean ≈ 20). "mse" mode
        # retained for comparison.
        if config.value_head_mode == "cls":
            self.value_head = nn.Linear(config.d_model, config.n_value_bins, bias=False)
        else:
            self.value_head = nn.Linear(config.d_model, 1, bias=False)
        self.apply(self._init_weights)

    @staticmethod
    def _init_weights(module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    @staticmethod
    def value_to_vector(values: torch.Tensor, channels: int) -> torch.Tensor:
        """Scalar int values → (B, T, channels) fixed sinusoid encoding.

        Sign handled by a dedicated channel; magnitude encoded over the
        remaining channels with increasing periods.
        """
        B, T = values.shape
        x = values.float().unsqueeze(-1)  # (B, T, 1)
        chans = []
        chans.append(torch.sign(x))       # channel 0: sign
        for c in range(1, channels):
            period = 2.0 ** (2 * (c - 1) + 2)
            chans.append(torch.sin(2 * math.pi * x / period))
        return torch.cat(chans, dim=-1)[:, :, :channels]

    def forward(self, ids: torch.Tensor, values: Optional[torch.Tensor] = None,
                targets: Optional[torch.Tensor] = None):
        """Returns (logits, loss). loss is None when targets is None.

        Token loss ignores positions where target == 0 (PAD = ignore_index).
        Value loss is masked MSE at positions where values != 0 — i.e. the
        NUM/LABEL immediates. Returns loss as a scalar; value loss is
        attached to the last module-level _last_value_loss for logging.
        """
        B, T = ids.shape
        pos = torch.arange(T, device=ids.device).unsqueeze(0)
        x = self.tok_emb(ids) + self.pos_emb(pos)
        if values is not None:
            vvec = self.value_to_vector(values, self.config.value_channels)
            x = x + self.val_proj(vvec)
        x = self.drop(x)
        for block in self.blocks:
            x = block(x)
        x = self.ln_f(x)
        logits = self.lm_head(x)
        value_pred = self.value_head(x).squeeze(-1)  # (B, T), normalized space
        self._last_value_pred = value_pred

        loss = None
        if targets is not None:
            ce = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)), targets.reshape(-1),
                ignore_index=PAD_ID)
            if values is not None:
                # Value head — SHIFTED, matching the CE contract:
                # targets[t] = ids[t+1], so value_pred[t] predicts the
                # bin of values[t+1]. Mask excludes 0 (PAD/no-value) and
                # -1 (unresolvable <LABEL> refs).
                v_tgt_vals = values[:, 1:]
                v_mask = (v_tgt_vals != 0) & (v_tgt_vals != -1)
                if v_mask.any():
                    if self.config.value_head_mode == "cls":
                        v_tgt = torch.zeros_like(v_tgt_vals)
                        for i in range(v_tgt_vals.shape[0]):
                            for j in range(v_tgt_vals.shape[1]):
                                v_tgt[i, j] = value_to_bin(int(v_tgt_vals[i, j]))
                        v_loss = F.cross_entropy(
                            value_pred[:, :-1][v_mask], v_tgt[v_mask])
                    else:
                        v_tgt = v_tgt_vals.float() / self.config.value_scale
                        v_loss = F.mse_loss(value_pred[:, :-1][v_mask], v_tgt[v_mask])
                else:
                    v_loss = torch.zeros((), device=ids.device)
            else:
                v_loss = torch.zeros((), device=ids.device)
            self._last_value_loss = float(v_loss.item())
            loss = ce + self.config.value_weight * v_loss
        return logits, loss

    def num_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


PAD_ID = 0  # tokenizer.PAD; kept local to avoid import cycle at module load


def save_checkpoint(model: GlyphGPT, path: str,
                    metadata: Optional[dict] = None) -> None:
    """Checkpoint carries config + training metadata (glyphgpt-training
    contract: generator reads config from checkpoint)."""
    payload = {
        "config": asdict(model.config),
        "state_dict": model.state_dict(),
        "metadata": metadata or {},
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    torch.save(payload, path)


def load_checkpoint(path: str, map_location: str = "cpu") -> GlyphGPT:
    payload = torch.load(path, map_location=map_location, weights_only=True)
    cfg_data = payload["config"]
    # tolerate checkpoints saved before newer config fields existed
    known = {f.name for f in fields(GlyphGPTConfig)}
    config = GlyphGPTConfig(**{k: v for k, v in cfg_data.items() if k in known})
    model = GlyphGPT(config)
    try:
        model.load_state_dict(payload["state_dict"])
    except RuntimeError as e:
        msg = str(e)
        if "value_head.weight" in msg and "size mismatch" in msg:
            # legacy checkpoint (mse scalar head) — reinit the cls head,
            # load everything else
            sd = {k: v for k, v in payload["state_dict"].items()
                  if k != "value_head.weight"}
            model.load_state_dict(sd, strict=False)
            nn.init.normal_(model.value_head.weight, mean=0.0, std=0.02)
        else:
            # pre-value-head checkpoint: initialize missing heads, load rest
            model.load_state_dict(payload["state_dict"], strict=False)
            nn.init.normal_(model.value_head.weight, mean=0.0, std=0.02)
    model.eval()
    return model
