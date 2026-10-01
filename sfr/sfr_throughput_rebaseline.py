#!/usr/bin/env python3
"""
Sustained-load throughput re-baseline for the committed SFR protocol.

Every earlier throughput figure (0.86 pkt/fr single-dest, 3.86 pkt/fr mode B)
predates the multigrid V-cycle field and the forced-displacement fix.  This
script measures steady-state throughput on the committed state:

  1. single-dest   : one center well, sustained injection, rate sweep
  2. mode B        : 4 wells on channel 0 (any-well load balance), rate sweep
  3. mode A        : 4 wells, one per channel (destination-aware), rate sweep
  4. burst         : mode A, all 200 packets at once (batch-drain rate)

Throughput = delivered / frames measured over the *steady-state* window
(after a 50-frame warm-up), with backlog reported at cutoff so saturation
is visible rather than hidden.
"""
from __future__ import annotations
import numpy as np
from sfr_reference import SFR, GRID, AGE_TIMEOUT
from sfr_multidest import WELLS, WSET, MultiSFR, _assign

WARMUP = 50


def _drive_steady(s, npkt_total, rate, frames, mode):
    """Inject at `rate`/frame up to npkt_total; report steady-state stats."""
    h = 1
    assign, ai = None, 0
    if mode != "single":
        assign, s.rng = _assign(min(npkt_total, GRID * GRID - len(WELLS)), 7)
    delivered_mark = 0
    for f in range(frames):
        for _ in range(rate):
            if h > npkt_total:
                break
            if mode == "single":
                spots = [(x, y) for x in range(s.n) for y in (0, s.n - 1)
                         if s.packet[y, x, 3] == 0]
                if spots:
                    x, y = spots[int(s.rng.integers(len(spots)))]
                    s.inject(x, y, (s.n // 2, s.n // 2), handle=h); h += 1
            else:
                if ai >= len(assign):
                    break
                (x, y), k = assign[ai]; ai += 1
                if s.packet[y, x, 3] != 0:
                    continue            # spot still occupied; skip this slot
                chan = 0 if mode == "B" else k
                s.place(x, y, k, handle=h, chan=chan,
                        prio=int(s.rng.integers(0, 8))); h += 1
        s.step()
        if f >= WARMUP:
            delivered_mark = len(s.delivered)
    # drain phase: stop injecting, run until empty or timeout
    for _ in range(AGE_TIMEOUT):
        s.step()
        if s.in_flight() == 0:
            break
    steady = (len(s.delivered) - delivered_mark) / (frames - WARMUP)
    return dict(delivered=len(s.delivered), steady=steady,
                backlog_end_inject=s.in_flight() if False else None,
                drain=s.frame)


def _burst(npkt=200):
    s = MultiSFR(GRID, 7)
    for k, w in enumerate(WELLS):
        s.wells[w] = 9 ** 9
        s.wchan[w] = k
    assign, rng = _assign(npkt, 7)
    for h, ((x, y), k) in enumerate(assign, 1):
        s.place(x, y, k, handle=h, chan=k, prio=int(rng.integers(0, 8)))
    for _ in range(AGE_TIMEOUT):
        s.step()
        if s.in_flight() == 0:
            break
    return s.frame, len(s.delivered)


if __name__ == "__main__":
    print("=== throughput re-baseline (committed state b464505) ===")
    for rate in (1, 2, 4, 8):
        s = SFR(GRID, 3)
        m = _drive_steady(s, 10_000, rate, 300, "single")
        print(f"[single-dest] rate={rate}  steady={m['steady']:.2f} pkt/fr"
              f"  delivered={m['delivered']}  drain={m['drain']}fr")
    for rate in (1, 2, 4, 8):
        s = MultiSFR(GRID, 7)
        for w in WELLS:
            s.wells[w] = 9 ** 9
            s.wchan[w] = 0
        m = _drive_steady(s, 10_000, rate, 300, "B")
        print(f"[mode B     ] rate={rate}  steady={m['steady']:.2f} pkt/fr"
              f"  delivered={m['delivered']}  drain={m['drain']}fr")
    for rate in (1, 2, 4, 8):
        s = MultiSFR(GRID, 7)
        for k, w in enumerate(WELLS):
            s.wells[w] = 9 ** 9
            s.wchan[w] = k
        m = _drive_steady(s, 10_000, rate, 300, "A")
        print(f"[mode A     ] rate={rate}  steady={m['steady']:.2f} pkt/fr"
              f"  delivered={m['delivered']}  drain={m['drain']}fr")
    fr, d = _burst()
    print(f"[mode A burst] 200 pkt drained in {fr} frames = {200/fr:.2f} pkt/fr")
