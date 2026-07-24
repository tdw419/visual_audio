#!/usr/bin/env python3
"""
tests/test_neural_synthesis.py — TASK_R008 verification.

Verifies the phoneme-to-envelope neural model (tools/neural_synthesis.py):
- the model actually trains (loss decreases substantially on real targets)
- isolated (SIL-flanked) predictions track the static heuristic envelope
  from tools/phonemes.py
- neighbor phonemes measurably shift onset/offset frequencies
  (coarticulation), which the static per-phoneme lookup cannot do
- weights round-trip through save/load
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

from neural_synthesis import (
    PhonemeEnvelopeMLP,
    build_training_data,
    predict_envelope,
    train_default_model,
    FREQ_SCALE,
    N_POINTS,
    PHONEMES,
)
from phonemes import create_phoneme_envelopes


@pytest.fixture(scope="module")
def trained_model():
    return train_default_model(epochs=2000, lr=0.05, seed=42)


def test_training_data_shapes():
    X, y = build_training_data(seed=0)
    assert X.shape[0] == y.shape[0]
    assert X.shape[0] > 0
    assert y.shape[1] == N_POINTS


def test_model_actually_trains(trained_model):
    X, y = build_training_data(seed=0)
    fresh = PhonemeEnvelopeMLP(hidden_dim=32, seed=42)
    losses = fresh.train(X, y, epochs=2000, lr=0.05)

    assert losses[0] > losses[-1], "loss should decrease over training"
    assert losses[-1] < losses[0] * 0.05, "loss should drop by at least 20x"


def test_isolated_prediction_tracks_heuristic(trained_model):
    """With SIL on both sides, the model should closely reproduce the
    static heuristic envelope it was trained to imitate."""
    heuristics = create_phoneme_envelopes()

    for phoneme in ['AA', 'T', 'S', 'M', 'W']:
        env = predict_envelope(trained_model, 'SIL', phoneme, 'SIL')
        target = heuristics[phoneme]

        times = np.linspace(0.0, 1.0, N_POINTS)
        target_curve = np.array([target.evaluate(t) for t in times])

        # Interior points (not boundary-blended) should track closely.
        interior_error = np.abs(env.values[1:-1] - target_curve[1:-1])
        assert np.all(interior_error < 400), (
            f"{phoneme}: interior envelope diverged from heuristic: {interior_error}"
        )


def test_coarticulation_shifts_boundary_frequency(trained_model):
    """The same phoneme flanked by different neighbors must produce a
    different onset/offset — this is the actual capability the static
    per-phoneme lookup in tools/phonemes.py does not have."""
    isolated = predict_envelope(trained_model, 'SIL', 'T', 'SIL')
    after_aa = predict_envelope(trained_model, 'AA', 'T', 'SIL')
    before_iy = predict_envelope(trained_model, 'SIL', 'T', 'IY')

    onset_shift = abs(after_aa.values[0] - isolated.values[0])
    offset_shift = abs(before_iy.values[-1] - isolated.values[-1])

    assert onset_shift > 50, f"expected coarticulated onset shift, got {onset_shift:.1f} Hz"
    assert offset_shift > 50, f"expected coarticulated offset shift, got {offset_shift:.1f} Hz"


def test_all_phonemes_predictable(trained_model):
    """Every ARPAbet phoneme in the vocabulary should produce a valid,
    finite envelope regardless of neighbor context."""
    for phoneme in PHONEMES:
        env = predict_envelope(trained_model, 'SIL', phoneme, 'SIL')
        assert len(env.values) == N_POINTS
        assert np.all(np.isfinite(env.values))


def test_weights_roundtrip(trained_model, tmp_path):
    path = str(tmp_path / "weights.npz")
    trained_model.save(path)

    loaded = PhonemeEnvelopeMLP.load(path)

    env_before = predict_envelope(trained_model, 'AA', 'T', 'IY')
    env_after = predict_envelope(loaded, 'AA', 'T', 'IY')

    np.testing.assert_allclose(env_before.values, env_after.values, rtol=1e-10)


def test_output_scale_is_reasonable(trained_model):
    """Predicted frequencies should stay in a plausible acoustic range,
    not blow up due to unbounded extrapolation."""
    for phoneme in PHONEMES:
        env = predict_envelope(trained_model, 'SIL', phoneme, 'SIL')
        assert np.all(np.abs(env.values) < FREQ_SCALE * 2)
