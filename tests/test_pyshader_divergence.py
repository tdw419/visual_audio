"""tests/test_pyshader_hart.py — PS010b structural harness (skeleton
round). Guards live HERE; the builder REPLACES each stub-raise guard
with the behavioral gate named in the brief's step table (replace,
never delete). Spec: tools/pyshader_divergence.py module docstring +
.builder_queue/brief_ps010b_divergence_sweep.md.
"""
import pytest

from tools.pyshader_divergence import (
    DIVERGENT_PROG,
    LOW_PROG,
    MIX_PROG_LONG,
    MIX_PROG_SHORT,
    SWEEP_NS,
    _words,
    gate_divergence,
    sweep,
)


class TestWordPins:
    """Assembler ground truth at the locking revision — the test FAILS
    if the assembler output changes (PS008/PS010 convention)."""

    def test_low_prog_words(self):
        assert _words(LOW_PROG) == [
            0x00200093, 0xFFF08093, 0xFE009EE3, 0x00100073]

    def test_mix_short_words(self):
        assert _words(MIX_PROG_SHORT) == [0x00000093, 0x00100073]

    def test_mix_long_words(self):
        assert _words(MIX_PROG_LONG) == [
            0x00800093, 0xFFF08093, 0xFE009EE3, 0x00100073]

    def test_divergent_words(self):
        assert _words(DIVERGENT_PROG) == [
            0x00029663, 0x00800093, 0xFFF08093, 0xFE104EE3, 0x00100073]

    def test_sweep_ns_locked(self):
        assert SWEEP_NS == (2, 8, 64, 4096, 65536)


class TestStep1SweepUniform:
    """PS010b step 1 behavioral gate (REPLACES the stub-raise guard —
    replace, never delete, per the skeleton-handoff contract)."""

    def test_ps010b_sweep_uniform_no_divergence(self):
        words = _words(LOW_PROG)
        prog = [words] * 8
        snapshot = [list(p) for p in prog]
        cell = sweep(prog)
        assert cell["rounds"] == 5
        assert cell["useful"] == 8 * 5 == 40
        assert cell["slots"] == 8 * 5 == 40
        assert cell["efficiency"] == 1.0
        assert cell["sampled_steps"] == [5, 5]
        assert prog == snapshot  # input program list NOT mutated

    def test_ps010b_sweep_budget_loud(self):
        # Budget discipline is a hard constraint: exhaustion raises,
        # never a silent partial result. JAL-to-self spins forever IN
        # bounds (a falling-off-imem program is a bounds fault, a
        # different loudness).
        spin = _words("loop: jal x0, 0")
        with pytest.raises(RuntimeError, match="budget 4"):
            sweep([spin] * 2, max_rounds=4)


class TestStep2StaticMix:
    """PS010b step 2 behavioral gate: static population-mix divergence.
    Uniform all-MIX_LONG is efficiency 1.0; a half-SHORT/half-LONG mix
    decays to exactly 72/136 == 0.5294 (4dp) — the ratio IS the
    deliverable (roadmap :250-252: numbers, not prose). SHORT harts halt
    after 1 counted transition but keep occupying slots for the
    remaining rounds (slots == n * rounds, per the brief's step-2
    arithmetic note machine-checked at step 1)."""

    def test_ps010b_static_mix_efficiency_decays(self):
        long_words = _words(MIX_PROG_LONG)
        short_words = _words(MIX_PROG_SHORT)

        # Leg A — uniform: all 8 harts run the LONG program → 1.0.
        uni = sweep([long_words] * 8)
        assert uni["rounds"] == 17
        assert uni["useful"] == 8 * 17
        assert uni["slots"] == 8 * 17
        assert uni["efficiency"] == 1.0

        # Leg B — static mix: harts 0-3 SHORT (1 transition), 4-7 LONG
        # (17 transitions).
        prog = [short_words] * 4 + [long_words] * 4
        snapshot = [list(p) for p in prog]
        cell = sweep(prog)
        assert cell["rounds"] == 17
        assert cell["useful"] == 4 * 1 + 4 * 17 == 72
        assert cell["slots"] == 8 * 17 == 136
        assert round(cell["efficiency"], 4) == 0.5294
        assert cell["efficiency"] < 1.0  # the decay, as an inequality
        assert cell["sampled_steps"] == [1, 17]
        assert prog == snapshot  # input program list NOT mutated


class TestStep3AdversarialSplit:
    """PS010b step 3 behavioral gate: MID-RUN REGISTER divergence (the
    adversarial leg). All 8 harts run the SAME DIVERGENT_PROG text; only
    the per-hart x5 preload splits the population (harts 0-3 x5=4 ->
    branch taken -> 2 transitions; harts 4-7 x5=0 -> not-taken -> 18
    transitions). This is the roadmap's \"half take one branch, half the
    other\" leg — divergence invisible in any static artifact.
    Efficiency == (4*2 + 4*18) / (8*18) == 80/144, rounded 4dp 0.5556 —
    the ratio IS the deliverable (numbers, not prose)."""

    def test_ps010b_adversarial_split_rounds_expose_divergence(self):
        words = _words(DIVERGENT_PROG)
        prog = [words] * 8
        snapshot = [list(p) for p in prog]
        x5 = [4] * 4 + [0] * 4

        cell = sweep(prog, x5_inits=x5)

        assert cell["rounds"] == 18  # the not-taken harts set the makespan
        assert cell["useful"] == 4 * 2 + 4 * 18 == 80
        assert cell["slots"] == 8 * 18 == 144
        assert round(cell["efficiency"], 4) == 0.5556
        assert cell["efficiency"] < 1.0  # the decay, as an inequality
        # Both sub-populations present: sampled harts 0 and 7 are the
        # taken (x5=4) and not-taken (x5=0) representatives.
        assert cell["sampled_steps"] == [2, 18]
        assert prog == snapshot  # input program list NOT mutated


class TestStep4GateDivergence:
    """PS010b step 4 behavioral gate (REPLACES the stub-raise guard —
    replace, never delete, per the skeleton-handoff contract): THE
    roadmap gate — the full sweep at every N in SWEEP_NS × all three
    legs, returned as a receipt dict (gate_divergence does NOT raise on
    pin mismatch; the receipt IS the gate artifact).

    Adjudication pins (brief row 4, verified INSIDE the receipt and
    re-asserted here so a silent receipt regression goes RED):
      (a) uniform efficiency == 1.0 at every N;
      (b) adversarial efficiency at N=8 == 80/144 == 0.5556 (4dp);
      (c) monotone decay: efficiency(adversarial) < efficiency(uniform)
          at every N;
      (d) the N=65536 adversarial cell RAN and completed — assert it
          RAN (rounds > 0); do NOT pin a value for its efficiency
          (host scheduler != warp hardware; the curve is the deliverable).
    Wall-clock is reported (wall_seconds on every cell) and NEVER gated
    on — machine-dependent; the efficiency ratios are not."""

    def test_ps010b_gate_divergence_curve(self):
        receipt = gate_divergence()

        # Receipt shape (locked docstring contract).
        assert set(receipt) >= {
            "ok", "cells", "pin_failures", "what_pass_does_not_prove"}
        cells = receipt["cells"]
        assert len(cells) == len(SWEEP_NS) * 3  # 15 labelled cells
        for n in SWEEP_NS:
            mixes = {c["mix"] for c in cells if c["n"] == n}
            assert mixes == {"uniform", "half-mixed", "adversarial"}
            for c in (x for x in cells if x["n"] == n):
                assert c["wall_seconds"] >= 0.0  # reported, not gated on

        # The receipt's own adjudication must be clean.
        assert receipt["pin_failures"] == []
        assert receipt["ok"] is True
        assert isinstance(receipt["what_pass_does_not_prove"], str)
        assert receipt["what_pass_does_not_prove"]  # honest boundary stated

        # Independent re-derivation of the pins from the raw cells
        # (never trust the receipt's self-assessment alone).
        by = {(c["n"], c["mix"]): c for c in cells}
        for n in SWEEP_NS:
            assert by[(n, "uniform")]["efficiency"] == 1.0          # (a)
            assert (by[(n, "adversarial")]["efficiency"]            # (c)
                    < by[(n, "uniform")]["efficiency"])
        assert round(by[(8, "adversarial")]["efficiency"], 4) == 0.5556  # (b)

        adv_max = by[(65536, "adversarial")]                         # (d)
        assert adv_max["rounds"] == 18  # it RAN to completion
        assert 0.0 < adv_max["efficiency"] < 1.0  # value reported, unpinned
