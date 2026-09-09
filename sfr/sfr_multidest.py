#!/usr/bin/env python3
"""
Multi-destination routing: does per-channel field selection deliver packets to
their INTENDED well?

  mode B : 4 wells, all on channel 0 (one shared scalar field).  A packet
           descends whatever basin it starts in -> nearest-well heuristic.
  mode A : 4 wells, one per channel (vec4 field).  A packet descends only its
           own channel -> destination-aware routing.

Metrics: intended-hit rate, wrong-well rate, undelivered, drain frames, max age.
"""
from __future__ import annotations
import numpy as np
from sfr_reference import SFR, GRID, AGE_TIMEOUT

WELLS = [(4, 4), (GRID - 5, 4), (4, GRID - 5), (GRID - 5, GRID - 5)]
WSET = {w: k for k, w in enumerate(WELLS)}


class MultiSFR(SFR):
    """Delivery at ANY well cell; logs intended vs actual well."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.hpi: dict[int, int] = {}     # handle -> intended well index
        self.hits = 0
        self.wrong = 0

    def place(self, x, y, well_k, handle, chan, prio=0):
        self.hpi[handle] = well_k
        self.inject(x, y, WELLS[well_k], handle=handle, prio=prio, chan=chan)

    def _route(self):
        occ = self.packet[..., 3] != 0
        ys, xs = np.nonzero(occ)
        for x, y in zip(xs, ys):
            x, y = int(x), int(y)
            if (x, y) in WSET:
                h = int(self.packet[y, x, 3]) >> 5
                if self.hpi.get(h, -1) == WSET[(x, y)]:
                    self.hits += 1
                else:
                    self.wrong += 1
                self.packet[y, x, 0] = x    # relabel dest=self -> reference delivers
                self.packet[y, x, 1] = y
        super()._route()


def _drive(s, npkt):
    ma = 0
    for _ in range(AGE_TIMEOUT):
        s.step()
        occ = s.packet[..., 2][s.packet[..., 3] != 0]
        if occ.size:
            ma = max(ma, int(occ.max()))
        if s.in_flight() == 0:
            break
    tot = s.hits + s.wrong
    # fairness: per-packet wait (age at delivery).  A livelock->starvation
    # trade would blow up the tail here.
    waits = np.array([d["age"] for d in s.delivered], float)
    pcts = (np.percentile(waits, [50, 90, 99]).astype(int).tolist()
            if waits.size else [0, 0, 0])
    return dict(hits=s.hits, wrong=s.wrong, undel=npkt - tot,
               drain=s.frame, max_age=ma, p50=pcts[0], p90=pcts[1],
               p99=pcts[2], wmax=int(waits.max()) if waits.size else 0)


def _assign(npkt, seed):
    rng = np.random.default_rng(seed)
    free = [(x, y) for y in range(GRID) for x in range(GRID) if (x, y) not in WSET]
    rng.shuffle(free)
    return [(free[i], int(rng.integers(4))) for i in range(npkt)], rng


def mode_B(npkt=200, seed=7):
    s = MultiSFR(GRID, seed)
    for w in WELLS:                       # all wells on channel 0
        s.wells[w] = 9 ** 9
        s.wchan[w] = 0
    assign, rng = _assign(npkt, seed)
    for h, ((x, y), k) in enumerate(assign, 1):
        s.place(x, y, k, handle=h, chan=0, prio=int(rng.integers(0, 8)))
    m = _drive(s, npkt)
    print(f"[B shared ch0 ] intended={m['hits']}/{npkt} "
          f"({100*m['hits']/npkt:.0f}%)  wrong-well={m['wrong']}  "
          f"undelivered={m['undel']}  drain={m['drain']}fr  "
          f"wait p50/p90/p99/max={m['p50']}/{m['p90']}/{m['p99']}/{m['wmax']}")


def mode_A(npkt=200, seed=7):
    s = MultiSFR(GRID, seed)
    for k, w in enumerate(WELLS):         # one well per channel
        s.wells[w] = 9 ** 9
        s.wchan[w] = k
    assign, rng = _assign(npkt, seed)
    for h, ((x, y), k) in enumerate(assign, 1):
        s.place(x, y, k, handle=h, chan=k, prio=int(rng.integers(0, 8)))
    m = _drive(s, npkt)
    print(f"[A per-channel] intended={m['hits']}/{npkt} "
          f"({100*m['hits']/npkt:.0f}%)  wrong-well={m['wrong']}  "
          f"undelivered={m['undel']}  drain={m['drain']}fr  "
          f"wait p50/p90/p99/max={m['p50']}/{m['p90']}/{m['p99']}/{m['wmax']}")


if __name__ == "__main__":
    mode_B()
    mode_A()
