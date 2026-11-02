"""PS010d — divergence-cost measurement rung (SKELETON ROUND).

Authority: .builder_queue/brief_ps010d_divergence_measurement.md
(READ IT FIRST — it is the contract, this file is the locked skeleton).

PS010 closed its correctness obligations in PS010c (bit-for-bit parity
at all 15 (leg, N) cells). What roadmap :246-268 still requires before
PS010's divergence requirement can be read: divergence cost as a
MEASURED OUTPUT — same-process paired wall-clock for the uniform
(low-divergence) and adversarial (max-divergence) legs at the roadmap's
named scale points N in {2, 64, 4096, 65536}, the ratio curve visible,
reported as numbers in the receipt. PS010b's correction proved the
host-scheduler proxy cannot supply this (algebraically scale-invariant);
PS010c's run_multihart_gpu CAN (its numbers move: 0.037s at N=2 vs 2.6s
at N=65536 for the adversarial leg).

Measurement discipline (the PS009B 6.15x rate-regime lesson, LOCKED):
  1. Same-process pairing — uniform and adversarial alternate
     rep-by-rep at each N.
  2. Warmup floor — one throwaway run_multihart_gpu call before any
     timed cell (shader compile / buffer alloc amortized).
  3. REPS medians — per-rep walls recorded raw; the reported number is
     statistics.median and MUST be recomputable from the raw list
     (a forged median is a gate pin failure).
  4. Determinism clause — wall-clock never gates on a threshold. The
     gate pins STRUCTURE (parity via the PS010c pins, recomputability,
     positivity, presence); the ratio curve is DATA for the
     three-named-outcomes verdict (roadmap :270-279), not pass/fail.

Reuse, do NOT reimplement: run_multihart_gpu (the parity-proven N-hart
kernel, PS010c), the leg programs LOW_PROG / DIVERGENT_PROG and the
pin machinery _analytic_steps / _cell_pins from
tools.pyshader_multihart / tools.pyshader_divergence. This module never
creates a wgpu device (run_multihart_gpu owns _cached_device()).

What the stubs do: raise NotImplementedError. Silence would be
dangerous; the behavioral tests replace the stub-raise guards one step
at a time, RED first, per the skeleton contract.
"""
from __future__ import annotations

import statistics
import time
from typing import Dict, List, Optional

from tools.pyshader_divergence import DIVERGENT_PROG, LOW_PROG
from tools.pyshader_multihart import (
    _analytic_steps, _cell_pins, run_multihart_gpu)

__all__ = [
    "MEASURE_NS", "REPS", "measure_cell", "wall_ratio", "_pair_medians",
    "gate_divergence_cost",
]

# ── locked discipline constants ──────────────────────────────────────────
# Roadmap :271-274 — the ratio curve at multiple N, "e.g. 2, 64, 4096,
# 65536", so the curve is visible, not one point.
MEASURE_NS = (2, 64, 4096, 65536)
# Paired reps per (leg, N); the reported wall is the median of REPS.
REPS = 3


def _programs_for(leg: str, n: int) -> tuple:
    """(programs, x5_inits) for a measurement leg — the PS010c gate's
    exact calling pattern, factored so the measurement cannot drift
    from the pinned legs."""
    if leg == "uniform":
        return [LOW_PROG] * n, None
    if leg == "adversarial":
        half = n // 2
        return ([DIVERGENT_PROG] * n,
                [4] * half + [0] * (n - half))
    raise ValueError(f"measure: unknown leg {leg!r}")


def measure_cell(leg: str, n: int, reps: int = REPS) -> Dict:
    """Populate PS010d step 1.

    Run ONE (leg, N) cell through run_multihart_gpu `reps` times
    (timed per rep with time.perf_counter around the WHOLE call —
    shader compile is amortized by the gate-level warmup, and the
    readback cost is part of BOTH legs symmetrically). Adjudicate each
    rep against the PS010c pins (_cell_pins + rounds pin) BEFORE
    timing is accepted — a parity failure is a measurement failure,
    never a number.

    Returns a receipt dict (does NOT raise on pin mismatch):
      leg, n            — as passed
      walls             — raw per-rep wall_seconds list (len == reps)
      wall_median       — statistics.median(walls) (recomputable)
      useful, slots     — from the LAST rep's receipt
      rounds            — from the LAST rep's receipt
      steps_ok          — pins clean on every rep
      pin_failures      — accumulated failed pin names (empty = clean)
      stops             — from the LAST rep's receipt
    """
    ROUNDS_PIN = {"uniform": 5, "adversarial": 18}
    if reps <= 0:
        raise ValueError(f"measure_cell: reps must be >= 1, got {reps}")
    programs, x5 = _programs_for(leg, n)
    walls: List[float] = []
    pin_failures: List[str] = []
    last: Dict = {}
    for _ in range(reps):
        t0 = time.perf_counter()
        r = run_multihart_gpu(programs, x5_inits=x5)
        walls.append(time.perf_counter() - t0)
        last = r
        for f in _cell_pins(leg, n, r):
            pin_failures.append(f)
        rounds_pin = ROUNDS_PIN[leg]
        if r["rounds"] != rounds_pin:
            pin_failures.append(
                f"rounds {r['rounds']} != {rounds_pin}")
    return {
        "leg": leg,
        "n": n,
        "walls": walls,
        "wall_median": statistics.median(walls),
        "useful": sum(last["steps"]),
        "slots": n * last["rounds"],
        "rounds": last["rounds"],
        "steps_ok": not pin_failures,
        "pin_failures": pin_failures,
        "stops": last["stops"],
    }


def _pair_medians(uni: List[Dict], adv: List[Dict]) -> Dict:
    """Populate PS010d step 2 (host-pure, no GPU).

    Given the measure_cell receipts of the uniform leg and the
    adversarial leg AT THE SAME N (lists of per-N dicts, paired by
    index), return:
      per_n — list of {'n', 'uni_median', 'adv_median', 'ratio'} where
              ratio = adv_median / uni_median
    Raises ValueError on empty input, length mismatch, n mismatch
    between the lists at any index, or any non-positive wall median
    (a zero wall is not a measurement).
    """
    if not uni or not adv:
        raise ValueError("_pair_medians: empty input is not a measurement")
    if len(uni) != len(adv):
        raise ValueError(
            f"_pair_medians: length mismatch uni={len(uni)} "
            f"adv={len(adv)}")
    per_n: List[Dict] = []
    for u, a in zip(uni, adv):
        if u["n"] != a["n"]:
            raise ValueError(
                f"_pair_medians: n mismatch at index {len(per_n)}: "
                f"uni n={u['n']} adv n={a['n']}")
        uni_med = statistics.median(u["walls"])
        adv_med = statistics.median(a["walls"])
        if uni_med <= 0 or adv_med <= 0:
            raise ValueError(
                f"_pair_medians: non-positive wall median at n={u['n']} "
                f"(uni={uni_med!r} adv={adv_med!r}) — a zero wall is "
                "not a measurement")
        per_n.append({
            "n": u["n"],
            "uni_median": uni_med,
            "adv_median": adv_med,
            "ratio": adv_med / uni_med,
        })
    return {"per_n": per_n}


def wall_ratio(uni: List[Dict], adv: List[Dict]) -> Dict:
    """Populate PS010d step 2 (public name).

    Thin wrapper: validate + delegate to _pair_medians, returning its
    {'per_n': [...]} receipt. (The ratio curve itself; never a single
    scalar — roadmap :271-274.)
    """
    return _pair_medians(uni, adv)


# ── RULING_ps012 clause 1 (2026-09-20): whole-curve verdict rule. ──────
# The catastrophic bound (roadmap :270-279 vocabulary keeps 2.0 as the
# named threshold; clause-1 point 2 keeps the three outcomes as the
# vocabulary but makes the reading curve-shaped).
PEAK_RATIO_LIMIT = 2.0


def curve_verdict(per_n: List[Dict]) -> Dict:
    """Read the divergence-cost ratio curve as a WHOLE (RULING_ps012
    clause 1). Host-pure; replaces the endpoint rule that read
    ratios[-1] against 2.0 and could not see a mid-range spike.

    Required reading basis (clause 1, points 1-2): max-over-N AND where
    it occurs, the peak-to-tail relation, and the spread — with
    "tolerable" a description of CURVE SHAPE (peaks then decays, never
    catastrophic at any measured N), not a boolean off the tail.

    Outcomes (roadmap :270-279 vocabulary):
      needs_scheduling_discipline — peak ratio > PEAK_RATIO_LIMIT at the
        LARGEST measured N (the cost has not decayed by the scale the
        roadmap cares about);
      bad_at_low_n_tolerable_at_scale — peak > limit at any smaller N
        but the largest-N point is at/below limit (a warp-fill hazard
        at agent-relevant mid scales that decays);
      tolerable — never catastrophic at ANY measured N.
    Returns {'verdict', 'basis'} where basis carries peak_n /
    peak_ratio / tail_n / tail_ratio / decayed_to_tail / spread — all
    recomputable from the per_n list. Empty curve -> verdict None (no
    measurement is not a verdict).
    """
    if not per_n:
        return {"verdict": None, "basis": None}
    peak = max(per_n, key=lambda p: p["ratio"])
    tail = per_n[-1]
    basis = {
        "peak_n": peak["n"],
        "peak_ratio": peak["ratio"],
        "tail_n": tail["n"],
        "tail_ratio": tail["ratio"],
        "decayed_to_tail": tail["ratio"] <= PEAK_RATIO_LIMIT,
        "spread": (max(p["ratio"] for p in per_n)
                   - min(p["ratio"] for p in per_n)),
    }
    if peak["ratio"] > PEAK_RATIO_LIMIT:
        if tail["n"] == peak["n"]:
            verdict = "needs_scheduling_discipline"
        else:
            verdict = "bad_at_low_n_tolerable_at_scale"
    else:
        verdict = "tolerable"
    return {"verdict": verdict, "basis": basis}


# RULING_ps012 clause 1 supersedes the endpoint rule (ratios[-1] vs
# 2.0) that lived in gate_divergence_cost's body. Guard REPLACED, not
# deleted: the three named outcomes stay, now derived by curve_verdict
# from the whole curve, and the forged mid-range spike case is pinned
# by tests/test_pyshader_measure.py::test_ps012_clause1_curve_verdict_reads_whole_curve.


def gate_divergence_cost(measure_ns: tuple = MEASURE_NS,
                         reps: int = REPS,
                         _measure_cell=measure_cell) -> Dict:
    """Populate PS010d step 4 — THE rung gate.

    Warmup (one throwaway run_multihart_gpu call, UNTIMED, recorded),
    then for each n in measure_ns: measure_cell('uniform', n, reps) and
    measure_cell('adversarial', n, reps) PAIRED rep-by-rep in one
    process (uniform cell, adversarial cell per rep would recompile —
    instead the pairing discipline is: both cells at n run back-to-back
    in the same process, alternating across ns). Returns a receipt dict
    (does NOT raise on pin mismatch):
      ok               — False if any pin fails
      warmup_wall      — the warmup call's wall (recorded, untimed lane)
      cells            — per (leg, n) measure_cell receipts
      ratios           — wall_ratio output (the curve, numbers)
      pin_failures     — failed pin names (empty when ok)
      verdict          — the three-named-outcomes field: WHICH outcome
                         the curve indicates (roadmap :270-279),
                         stated as data-reading, never pass/fail
      verdict_basis    — the whole-curve reading basis (RULING_ps012
                         clause 1): peak_n / peak_ratio / tail_n /
                         tail_ratio / decayed_to_tail / spread,
                         recomputable from ratios.per_n
      what_pass_does_not_prove — host-driven round-scheduler numbers;
                         readback in both legs; deterministic x5 split;
                         no profiling counters.

    Non-vacuity leg is owned by the TEST (mutant via the _measure_cell
    seam); this function runs the pin path identically for both.
    """
    out: Dict = {
        "ok": True,
        "warmup_wall": None,
        "cells": [],
        "ratios": {"per_n": []},
        "pin_failures": [],
        "verdict": None,
        "what_pass_does_not_prove": {
            "host_driven_round_scheduler",
            "readback_both_legs",
            "deterministic_x5_split",
            "no_profiling_counters",
        },
    }

    # Warmup floor — one throwaway UNTIMED GPU call, recorded; executed
    # before the first timed cell (discipline #2, LOCKED).
    try:
        _t0 = time.perf_counter()
        run_multihart_gpu([LOW_PROG] * 2, x5_inits=None)
        out["warmup_wall"] = time.perf_counter() - _t0
    except RuntimeError as e:
        if str(e).startswith("wgpu device acquisition failed"):
            out["skipped"] = True
            out["skip_reason"] = str(e)
            out["ok"] = False
            return out
        raise

    uni_cells: List[Dict] = []
    adv_cells: List[Dict] = []
    for n in measure_ns:
        # pairing discipline: both cells at n back-to-back, same process
        for leg, bucket in (("uniform", uni_cells),
                            ("adversarial", adv_cells)):
            try:
                cell = _measure_cell(leg, n, reps)
            except RuntimeError as e:
                if str(e).startswith("wgpu device acquisition failed"):
                    out["skipped"] = True
                    out["skip_reason"] = str(e)
                    out["ok"] = False
                    return out
                raise
            bucket.append(cell)
            out["cells"].append(cell)
            if not cell["steps_ok"]:
                out["ok"] = False
                out["pin_failures"].extend(
                    f"parity[{leg}/n={n}]: {f}"
                    for f in cell["pin_failures"])
            # recomputability pin — wall_median from its OWN walls list,
            # naming the cell (non-vacuity target)
            if statistics.median(cell["walls"]) != cell["wall_median"]:
                out["ok"] = False
                out["pin_failures"].append(
                    f"wall_median recompute failed at {leg}/n={n}: "
                    f"median({cell['walls']}) != "
                    f"{cell['wall_median']!r}")
            if not all(w > 0 for w in cell["walls"]):
                out["ok"] = False
                out["pin_failures"].append(
                    f"non-positive wall at {leg}/n={n}")
        try:
            out["ratios"]["per_n"].extend(
                _pair_medians([uni_cells[-1]], [adv_cells[-1]])["per_n"])
        except ValueError as e:
            out["ok"] = False
            out["pin_failures"].append(f"ratio pin at n={n}: {e}")

    # Verdict (RULING_ps012 clause 1): read from the WHOLE curve via
    # curve_verdict — max-over-N, where it occurs, decayed-to-tail —
    # never the endpoint rule (ratios[-1] vs 2.0) this supersedes. A
    # data-reading, never a pass/fail conversion; basis carried in the
    # receipt so the reading is recomputable from the reported ratios.
    _reading = curve_verdict(out["ratios"]["per_n"])
    out["verdict"] = _reading["verdict"]
    out["verdict_basis"] = _reading["basis"]
    return out


def full_scale_recorded(reps: int = REPS,
                        _measure_cell=measure_cell) -> Dict:
    """Populate PS010d step 3 — the full-scale recorded leg.

    Runs the gate-scale cells (uniform + adversarial at N=4096 and
    N=65536, REPS paired reps each, same process) and RECORDS the
    result: per-cell measure_cell receipts plus the wall_ratio curve
    per_n recomputed from the raw walls. NO threshold is asserted on
    any ratio (determinism clause) — the numbers are data for the
    step-4 verdict.

    Device discipline (PS011 step-2 smoke lane): if the device cannot
    be acquired, the failure surfaces as the canonical
    RuntimeError("wgpu device acquisition failed: ...") so the TEST
    can pytest.skip on exactly that message prefix — any other
    RuntimeError propagates as a real failure.

    Returns:
      cells    — [uni(4096), adv(4096), uni(65536), adv(65536)] receipts
      per_n    — wall_ratio per-N entries (ratio recomputable from walls)
      ok       — every cell steps_ok and wall_median > 0
      skipped  — True only when the device-acquisition skip fired
      skip_reason — the canonical message (skipped path only)
    """
    out: Dict = {"cells": [], "per_n": [], "ok": False, "skipped": False}
    for n in (4096, 65536):
        try:
            uni = _measure_cell("uniform", n, reps)
            adv = _measure_cell("adversarial", n, reps)
        except RuntimeError as e:
            if str(e).startswith("wgpu device acquisition failed"):
                out["skipped"] = True
                out["skip_reason"] = str(e)
                return out
            raise
        out["cells"].append(uni)
        out["cells"].append(adv)
        out["per_n"].extend(_pair_medians([uni], [adv])["per_n"])
    out["ok"] = (all(c["steps_ok"] and c["wall_median"] > 0
                     for c in out["cells"]))
    return out
