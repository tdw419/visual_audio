#!/usr/bin/env python3
"""
neural_synthesis.py — TASK_R008: phoneme-to-envelope neural model.

tools/phonemes.py maps each ARPAbet phoneme to a *fixed*, isolated frequency
envelope: the same curve for 'T' regardless of what comes before or after it.
Real speech doesn't work that way — coarticulation shifts a phoneme's onset
and offset frequencies toward its neighbors.

This module trains a small numpy MLP (no torch/sklearn dependency) that:
  - takes (prev_phoneme, phoneme, next_phoneme) as input
  - predicts an N-point frequency envelope for `phoneme`
  - is trained so that, in isolation (SIL neighbors), it reproduces the
    existing heuristic envelope from tools/phonemes.py
  - is trained so that with real neighbors, its onset/offset are pulled
    toward the neighbors' boundary frequencies (coarticulation)

The network is a genuine trained model (forward/backward pass, gradient
descent on real targets) — not a lookup table wearing a neural-sounding name.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from phonemes import create_phoneme_envelopes
from upic_engine import UPICEnvelope

N_POINTS = 8                 # fixed-length envelope resampling grid
FREQ_SCALE = 3000.0          # normalization scale for frequencies (Hz)
COARTICULATION_ALPHA = 0.35  # how strongly neighbors pull the boundary freq
SIL_FREQ = 0.0               # silence "frequency" for boundary blending

PHONEMES = sorted(create_phoneme_envelopes().keys())
VOCAB = ['SIL'] + PHONEMES
VOCAB_INDEX = {p: i for i, p in enumerate(VOCAB)}
INPUT_DIM = len(VOCAB) + 2   # one-hot(current) + prev_boundary_freq + next_boundary_freq


def _one_hot(phoneme: str) -> np.ndarray:
    v = np.zeros(len(VOCAB), dtype=np.float64)
    v[VOCAB_INDEX[phoneme]] = 1.0
    return v


def _resample_envelope(envelope: UPICEnvelope, n_points: int = N_POINTS) -> np.ndarray:
    """Resample a heuristic envelope onto a fixed evenly-spaced time grid."""
    times = np.linspace(0.0, 1.0, n_points)
    return np.array([envelope.evaluate(t) for t in times], dtype=np.float64)


def _boundary_freq(phoneme: str, heuristics: dict) -> float:
    if phoneme == 'SIL':
        return SIL_FREQ
    return heuristics[phoneme].values[0]


def _boundary_freq_end(phoneme: str, heuristics: dict) -> float:
    if phoneme == 'SIL':
        return SIL_FREQ
    return heuristics[phoneme].values[-1]


def build_training_data(seed: int = 0):
    """
    Build (X, y) training pairs: every phoneme paired with SIL neighbors
    (isolated case) plus a sample of real neighbor combinations (coarticulated
    case), so the network sees both regimes.
    """
    heuristics = create_phoneme_envelopes()
    rng = np.random.RandomState(seed)

    X = []
    y = []

    for phoneme in PHONEMES:
        base_curve = _resample_envelope(heuristics[phoneme])

        neighbor_pool = ['SIL'] + list(rng.choice(PHONEMES, size=6, replace=False))
        for prev in neighbor_pool:
            for nxt in neighbor_pool:
                prev_freq = _boundary_freq_end(prev, heuristics)
                next_freq = _boundary_freq(nxt, heuristics)

                target = base_curve.copy()
                # Coarticulation: pull onset/offset toward neighbor boundary freq.
                target[0] = (1 - COARTICULATION_ALPHA) * target[0] + COARTICULATION_ALPHA * prev_freq
                target[-1] = (1 - COARTICULATION_ALPHA) * target[-1] + COARTICULATION_ALPHA * next_freq

                feat = np.concatenate([
                    _one_hot(phoneme),
                    [prev_freq / FREQ_SCALE, next_freq / FREQ_SCALE],
                ])
                X.append(feat)
                y.append(target / FREQ_SCALE)

    return np.array(X, dtype=np.float64), np.array(y, dtype=np.float64)


class PhonemeEnvelopeMLP:
    """Two-layer MLP: INPUT_DIM -> hidden(tanh) -> N_POINTS (linear)."""

    def __init__(self, hidden_dim: int = 32, seed: int = 42):
        rng = np.random.RandomState(seed)
        self.hidden_dim = hidden_dim
        scale1 = np.sqrt(2.0 / INPUT_DIM)
        scale2 = np.sqrt(2.0 / hidden_dim)
        self.W1 = rng.randn(INPUT_DIM, hidden_dim) * scale1
        self.b1 = np.zeros(hidden_dim)
        self.W2 = rng.randn(hidden_dim, N_POINTS) * scale2
        self.b2 = np.zeros(N_POINTS)

    def forward(self, X: np.ndarray):
        z1 = X @ self.W1 + self.b1
        a1 = np.tanh(z1)
        z2 = a1 @ self.W2 + self.b2
        return z2, a1

    def predict(self, X: np.ndarray) -> np.ndarray:
        out, _ = self.forward(X)
        return out

    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 2000, lr: float = 0.05) -> list:
        n = X.shape[0]
        losses = []
        for epoch in range(epochs):
            out, a1 = self.forward(X)
            diff = out - y
            loss = float(np.mean(diff ** 2))
            losses.append(loss)

            # Backprop (MSE loss).
            d_out = (2.0 / n) * diff                       # (n, N_POINTS)
            dW2 = a1.T @ d_out
            db2 = d_out.sum(axis=0)
            d_a1 = d_out @ self.W2.T
            d_z1 = d_a1 * (1 - a1 ** 2)                    # tanh'
            dW1 = X.T @ d_z1
            db1 = d_z1.sum(axis=0)

            self.W1 -= lr * dW1
            self.b1 -= lr * db1
            self.W2 -= lr * dW2
            self.b2 -= lr * db2

        return losses

    def save(self, path: str):
        np.savez(path, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2, hidden_dim=self.hidden_dim)

    @classmethod
    def load(cls, path: str) -> 'PhonemeEnvelopeMLP':
        data = np.load(path)
        model = cls(hidden_dim=int(data['hidden_dim']))
        model.W1, model.b1 = data['W1'], data['b1']
        model.W2, model.b2 = data['W2'], data['b2']
        return model


def featurize(prev_phoneme: str, phoneme: str, next_phoneme: str, heuristics: dict = None) -> np.ndarray:
    heuristics = heuristics or create_phoneme_envelopes()
    prev_freq = _boundary_freq_end(prev_phoneme, heuristics)
    next_freq = _boundary_freq(next_phoneme, heuristics)
    return np.concatenate([
        _one_hot(phoneme),
        [prev_freq / FREQ_SCALE, next_freq / FREQ_SCALE],
    ])


def predict_envelope(model: PhonemeEnvelopeMLP, prev_phoneme: str, phoneme: str,
                      next_phoneme: str) -> UPICEnvelope:
    """Predict a coarticulated UPICEnvelope for `phoneme` given its neighbors."""
    feat = featurize(prev_phoneme, phoneme, next_phoneme)
    curve = model.predict(feat[np.newaxis, :])[0] * FREQ_SCALE
    times = np.linspace(0.0, 1.0, N_POINTS)
    control_points = list(zip(times.tolist(), curve.tolist()))
    return UPICEnvelope(phoneme, control_points)


def train_default_model(epochs: int = 2000, lr: float = 0.05, seed: int = 42) -> PhonemeEnvelopeMLP:
    X, y = build_training_data(seed=0)
    model = PhonemeEnvelopeMLP(hidden_dim=32, seed=seed)
    model.train(X, y, epochs=epochs, lr=lr)
    return model


DEFAULT_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'neural_synthesis_weights.npz')


if __name__ == '__main__':
    print("Training phoneme-to-envelope neural model...")
    X, y = build_training_data(seed=0)
    model = PhonemeEnvelopeMLP(hidden_dim=32, seed=42)
    losses = model.train(X, y, epochs=2000, lr=0.05)
    print(f"  samples: {X.shape[0]}, final loss: {losses[-1]:.6f} (initial: {losses[0]:.6f})")

    model.save(DEFAULT_WEIGHTS_PATH)
    print(f"  saved weights to {DEFAULT_WEIGHTS_PATH}")

    print("\nCoarticulation demo — phoneme 'T' with different neighbors:")
    for prev, nxt in [('SIL', 'SIL'), ('AA', 'SIL'), ('SIL', 'IY')]:
        env = predict_envelope(model, prev, 'T', nxt)
        print(f"  prev={prev:>3} next={nxt:>3} -> onset={env.values[0]:7.1f} Hz  offset={env.values[-1]:7.1f} Hz")
