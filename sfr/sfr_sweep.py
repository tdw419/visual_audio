#!/usr/bin/env python3
"""
SFR gradient tuning sweep (CPU reference only -- lockstep is param-independent).

Metrics per config:
  max_age  : oldest in-flight packet age, 200 pkt -> single corner  (target <150)
  t_move   : frames for field to re-settle after the destination jumps (target <50)
  deliv    : fraction delivered before AGE_TIMEOUT                    (must be 1.0)
  frames   : frames to fully drain the 200-packet load
"""
from __future__ import annotations
import numpy as np
from sfr_reference import SFR, GRID, AGE_TIMEOUT, FQ


def load_metrics(seed=1, npkt=200, **kw):
    s = SFR(GRID, seed, **kw)
    dest = (GRID - 1, GRID - 1)
    free = [(x, y) for y in range(GRID) for x in range(GRID) if (x, y) != dest]
    s.rng.shuffle(free)
    for i in range(npkt):
        x, y = free[i]
        s.inject(x, y, dest, handle=i + 1, prio=int(s.rng.integers(0, 8)))
    max_age = 0
    for _ in range(AGE_TIMEOUT):
        s.step()
        occ = s.packet[..., 2][s.packet[..., 3] != 0]
        if occ.size:
            max_age = max(max_age, int(occ.max()))
        if s.in_flight() == 0:
            break
    return dict(max_age=max_age, frames=s.frame,
                deliv=len(s.delivered) / npkt)


def move_settle(seed=2, eps=1e-3, **kw):
    s = SFR(GRID, seed, **kw)
    s.wells[(8, 8)] = 999_999
    prev = s.fieldv.copy()
    for _ in range(400):
        s.step()
        if np.abs(s.fieldv - prev).max() < eps:
            break
        prev = s.fieldv.copy()
    t0 = s.frame
    del s.wells[(8, 8)]
    s.wells[(GRID - 8, GRID - 8)] = 999_999
    prev = s.fieldv.copy()
    for _ in range(400):
        s.step()
        if np.abs(s.fieldv - prev).max() < eps:
            break
        prev = s.fieldv.copy()
    return s.frame - t0


def row(tag, **kw):
    m = load_metrics(**kw)
    tm = move_settle(**kw)
    flag = "ok " if (m["deliv"] == 1.0 and m["max_age"] < 150 and tm < 50) else "   "
    print(f"{flag}{tag:28s} max_age={m['max_age']:4d}  drain={m['frames']:4d}  "
          f"t_move={tm:3d}  deliv={m['deliv']:.2f}")


if __name__ == "__main__":
    print("baseline")
    row("W_HILB=1966 DECAY=0.98")
    print("\nexperiment A -- stronger hilbert bias")
    for w in (3277, 6554, 9830):          # ~5%, 10%, 15% of a Q16 field unit
        row(f"W_HILB={w} DECAY=0.98", w_hilb_q=w)
    print("\nexperiment B -- faster decay (+ compensating hilbert)")
    for d in (0.96, 0.94):
        for w in (6554, 9830):
            row(f"W_HILB={w} DECAY={d}", w_hilb_q=w, decay=d)
    print("\nexperiment C -- more jacobi sweeps (stiffer gradient)")
    for it in (3, 4):
        row(f"JACOBI={it} W_HILB=6554", jacobi_it=it, w_hilb_q=6554)
