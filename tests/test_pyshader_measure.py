"""PS010d structural harness — tests/test_pyshader_measure.py.

Skeleton-round guards (brief_ps010d_divergence_measurement.md). Every
test here is a LIVE GUARD: stub-raise legs get REPLACED (never silently
deleted) by behavioral gates as steps 1..4 populate. RED first — a
failing tail is pasted in the landing commit — then GREEN.

Signature lock: interfaces in tools/pyshader_measure.py are LOCKED;
test_ps010d_signatures_locked pins them (PS011's precedent).
"""
import inspect
import math
import statistics

import pytest

from tools.pyshader_measure import (
    MEASURE_NS, REPS, PEAK_RATIO_LIMIT, _pair_medians,
    curve_verdict, full_scale_recorded, gate_divergence_cost, measure_cell,
    wall_ratio)
from tools.pyshader_multihart import _analytic_steps


def test_ps010d_signatures_locked():
    """Interfaces are LOCKED (brief: do not change signatures)."""
    sig = inspect.signature(measure_cell)
    assert list(sig.parameters) == ["leg", "n", "reps"]
    assert sig.parameters["reps"].default == REPS
    assert list(inspect.signature(wall_ratio).parameters) == ["uni", "adv"]
    assert list(inspect.signature(_pair_medians).parameters) == [
        "uni", "adv"]
    gsig = inspect.signature(gate_divergence_cost)
    assert list(gsig.parameters) == [
        "measure_ns", "reps", "_measure_cell"]
    assert gsig.parameters["measure_ns"].default == MEASURE_NS
    assert gsig.parameters["reps"].default == REPS
    assert MEASURE_NS == (2, 64, 4096, 65536)
    assert REPS == 3


# ── step 1 behavioral gate (REPLACES the stub-raise guard per the
#    keep-guards-live constraint; removal noted here — audit trail) ──────
def test_ps010d_measure_cell_small_n():
    """PS010d step 1: measure_cell at N=2, both legs.

    Gate clause: dict shape (leg/n/walls len==reps/wall_median>0/
    useful/slots/steps_ok/pin_failures==[]/stops==[]); useful and slots
    match the analytic pins via _analytic_steps; recomputable median.
    """
    for leg in ("uniform", "adversarial"):
        r = measure_cell(leg, 2, reps=REPS)
        assert r["leg"] == leg and r["n"] == 2
        assert len(r["walls"]) == REPS
        assert all(w > 0 for w in r["walls"])
        assert r["wall_median"] == statistics.median(r["walls"])
        assert r["wall_median"] > 0
        assert r["steps_ok"] is True
        assert r["pin_failures"] == []
        assert r["stops"] == []
        assert r["rounds"] == 5 if leg == "uniform" else r["rounds"] == 18
        assert r["useful"] == sum(_analytic_steps(leg, 2))
        assert r["slots"] == 2 * r["rounds"]
    # unknown leg refuses loudly
    with pytest.raises(ValueError):
        measure_cell("nope", 2, reps=1)


# ── step 2 behavioral gate (REPLACES the stub-raise guard per the
#    keep-guards-live constraint; removal noted here — audit trail) ──────
def test_ps010d_pairing_medians_recomputable():
    """PS010d step 2: medians exactly recomputable; ratio finite.

    Gate clause: host-pure forged cell lists -> _pair_medians returns
    per-leg medians EXACTLY recomputable (statistics.median over the
    raw walls lists), wall_ratio == adv_median/uni_median; empty,
    length-mismatched, n-mismatched, or zero-wall input raises
    ValueError. One real paired N=2 run: ratio finite and > 0.
    """
    uni = [{"n": 2, "walls": [1.0, 2.0, 3.0]},
           {"n": 64, "walls": [10.0, 20.0, 30.0]}]
    adv = [{"n": 2, "walls": [2.0, 4.0, 9.0]},
           {"n": 64, "walls": [5.0, 5.0, 5.0]}]
    r = wall_ratio(uni, adv)
    per_n = r["per_n"]
    assert [p["n"] for p in per_n] == [2, 64]
    # medians recomputable from the RAW walls, not read from a field
    assert per_n[0]["uni_median"] == statistics.median([1.0, 2.0, 3.0])
    assert per_n[0]["adv_median"] == statistics.median([2.0, 4.0, 9.0])
    assert per_n[0]["ratio"] == 4.0 / 2.0
    assert per_n[1]["uni_median"] == 20.0 and per_n[1]["adv_median"] == 5.0
    assert per_n[1]["ratio"] == 5.0 / 20.0
    # refusals: empty, length mismatch, n mismatch, zero wall
    with pytest.raises(ValueError):
        _pair_medians([], [])
    with pytest.raises(ValueError):
        _pair_medians(uni[:1], adv)
    with pytest.raises(ValueError):
        _pair_medians(uni, [dict(n=99, walls=[1.0, 1.0, 1.0])] + adv[1:])
    zero = [dict(uni[0], walls=[0.0, 0.0, 0.0])]
    with pytest.raises(ValueError):
        _pair_medians(zero, adv[:1])
    # one real paired N=2 run: ratio finite and > 0
    real_uni = measure_cell("uniform", 2, reps=2)
    real_adv = measure_cell("adversarial", 2, reps=2)
    rr = wall_ratio([real_uni], [real_adv])
    p = rr["per_n"][0]
    assert p["n"] == 2
    assert math.isfinite(p["ratio"]) and p["ratio"] > 0


# ── PS010d step 3 behavioral gate (replaces the stub-raise guard,
#    which was RED first: NotImplementedError tail pasted in the
#    step-3 commit). Full-scale cells RECORDED — pins are structure
#    only, never a ratio threshold (determinism clause). ──────────────
def test_ps010d_full_scale_recorded():
    """PS010d step 3: full-scale leg recorded, skip on no-device."""
    try:
        rec = full_scale_recorded(reps=2)
    except RuntimeError as e:
        if str(e).startswith("wgpu device acquisition failed"):
            pytest.skip("wgpu device acquisition failed")
        raise
    if rec.get("skipped"):
        pytest.skip("wgpu device acquisition failed")
    assert rec["ok"], "cells recorded but pins/positivity failed"
    # cells present: uniform + adversarial at 4096 and 65536
    got = [(c["leg"], c["n"]) for c in rec["cells"]]
    assert got == [("uniform", 4096), ("adversarial", 4096),
                   ("uniform", 65536), ("adversarial", 65536)]
    for c in rec["cells"]:
        assert c["steps_ok"], f"pin failure at {c['leg']}/{c['n']}: " \
                              f"{c['pin_failures']}"
        assert c["wall_median"] > 0
        # recomputability: median recomputable from raw walls
        assert statistics.median(c["walls"]) == c["wall_median"]
    # ratio curve per_n present at both scale points, recomputable
    # from the raw walls, NO threshold asserted on any ratio value
    assert [p["n"] for p in rec["per_n"]] == [4096, 65536]
    for p, c_u, c_a in zip(rec["per_n"], rec["cells"][::2],
                           rec["cells"][1::2]):
        assert p["ratio"] == (statistics.median(c_a["walls"])
                              / statistics.median(c_u["walls"]))
        assert math.isfinite(p["ratio"]) and p["ratio"] > 0


# ── PS010d step 4 behavioral gate (replaces the stub-raise guard,
#    which was RED first: NotImplementedError tail pasted in the
#    step-4 commit). THE rung gate: full receipt structure + pins,
#    non-vacuity via a forged-median mutant through the SAME gate
#    path (_measure_cell seam). Real-GPU cells run at tiny N only;
#    device-acquisition failure skips (PS011 step-2 discipline). ──────
def _forge_median_cell(leg, n, reps=1, **_kw):
    """Mutant measure_cell: walls are real, wall_median is forged
    (inconsistent with its own walls list) — the non-vacuity probe."""
    cell = measure_cell(leg, n, reps)
    cell["wall_median"] = cell["wall_median"] * 1.5 + 7.0
    return cell


def test_ps010d_gate_divergence_cost():
    """PS010d step 4: THE rung gate (tiny N live; full N pinned by
    MEASURE_NS lock + step-3 recorded receipt)."""
    # non-vacuity FIRST, through the SAME gate path: a mutant cell with
    # a forged wall_median must be caught by the recomputability pin,
    # ok=False, and the pin must NAME the cell.
    mutant = gate_divergence_cost(
        measure_ns=(2,), reps=1, _measure_cell=_forge_median_cell)
    assert mutant["ok"] is False
    recomp = [f for f in mutant["pin_failures"]
              if "recompute" in f.lower()]
    assert recomp, f"recomputability pin did not fire on the mutant: " \
                   f"{mutant['pin_failures']}"
    assert "uniform" in recomp[0] and "2" in recomp[0], \
        f"pin does not name the forged cell: {recomp[0]}"

    # live tiny-N run through the same gate path
    try:
        rec = gate_divergence_cost(measure_ns=(2,), reps=1)
    except RuntimeError as e:
        if str(e).startswith("wgpu device acquisition failed"):
            pytest.skip("wgpu device acquisition failed")
        raise
    if rec.get("skipped"):
        pytest.skip("wgpu device acquisition failed")
    assert rec["ok"] is True
    # warmup executed before the first timed cell and recorded
    assert rec["warmup_wall"] > 0
    # cells: both legs at n=2, steps_ok (parity pins) at every cell
    got = [(c["leg"], c["n"]) for c in rec["cells"]]
    assert got == [("uniform", 2), ("adversarial", 2)]
    for c in rec["cells"]:
        assert c["steps_ok"], f"pin failure at {c['leg']}/{c['n']}: " \
                              f"{c['pin_failures']}"
        assert c["walls"] and all(w > 0 for w in c["walls"])
        assert statistics.median(c["walls"]) == c["wall_median"]
    # ratios reported per N — numbers, not prose
    assert [p["n"] for p in rec["ratios"]["per_n"]] == [2]
    p = rec["ratios"]["per_n"][0]
    assert p["ratio"] == (statistics.median(rec["cells"][1]["walls"])
                          / statistics.median(rec["cells"][0]["walls"]))
    assert math.isfinite(p["ratio"]) and p["ratio"] > 0
    # verdict is one of the three named outcomes (data-reading field)
    assert rec["verdict"] in ("tolerable", "needs_scheduling_discipline",
                              "bad_at_low_n_tolerable_at_scale")
    assert set(rec["what_pass_does_not_prove"]) == {
        "host_driven_round_scheduler", "readback_both_legs",
        "deterministic_x5_split", "no_profiling_counters"}
    # RULING_ps012 clause 1: the receipt carries the WHOLE-curve reading
    # basis, recomputable from the reported ratios (peak location named)
    assert rec["verdict_basis"]["peak_n"] == 2
    assert rec["verdict_basis"]["peak_ratio"] == p["ratio"]


# ── RULING_ps012 clause 1 (2026-09-20): the PS010d verdict must be
#    derived from the WHOLE curve — max-over-N and WHERE it occurs,
#    peak-to-tail relation, spread — not the tail alone. The endpoint
#    rule this supersedes lived in gate_divergence_cost's body; the
#    guard is REPLACED (never deleted): the three roadmap :270-279
#    outcomes stay the vocabulary, "tolerable" becomes a curve-shape
#    description, and a forged mid-range spike must NOT read the same
#    as a flat curve (non-vacuity, peak cell NAMED per pin discipline).
#    Host-pure: no GPU leg needed to prove the reading rule. ───────────
def _curve(*pairs):
    return [{"n": n, "ratio": r} for n, r in pairs]


def test_ps012_clause1_curve_verdict_reads_whole_curve():
    # flat curve (never above the catastrophic limit) -> tolerable
    flat = curve_verdict(
        _curve((2, 1.4), (64, 1.5), (4096, 1.3), (65536, 1.2)))
    assert flat["verdict"] == "tolerable"
    # forged LARGE MID-RANGE SPIKE must NOT return the flat curve's
    # verdict — the endpoint rule read both of these as "tolerable"
    spike = curve_verdict(
        _curve((2, 1.2), (64, 9.5), (4096, 1.3), (65536, 1.2)))
    assert spike["verdict"] != flat["verdict"]
    assert spike["verdict"] == "bad_at_low_n_tolerable_at_scale"
    # the reading NAMES where the peak is (pin discipline)
    assert spike["basis"]["peak_n"] == 64
    assert spike["basis"]["peak_ratio"] == 9.5
    # catastrophic AT THE TAIL -> needs_scheduling_discipline
    tail_bad = curve_verdict(
        _curve((2, 1.5), (64, 2.1), (4096, 3.3), (65536, 4.4)))
    assert tail_bad["verdict"] == "needs_scheduling_discipline"
    # the real measured PS010d curve (receipt: 1.780 / 2.498 / 1.760 /
    # 1.715): peak at N=64, decayed tail -> named outcome with basis
    real = curve_verdict(
        _curve((2, 1.780), (64, 2.498), (4096, 1.760), (65536, 1.715)))
    assert real["verdict"] == "bad_at_low_n_tolerable_at_scale"
    assert real["basis"]["peak_n"] == 64
    assert real["basis"]["decayed_to_tail"] is True
    # single-point curve keeps old-shape behavior; empty -> None
    assert curve_verdict(_curve((2, 3.0),))["verdict"] == \
        "needs_scheduling_discipline"
    assert curve_verdict([])["verdict"] is None
    # the limit constant is the roadmap's 2.0 catastrophic bound
    assert PEAK_RATIO_LIMIT == 2.0
