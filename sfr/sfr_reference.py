#!/usr/bin/env python3
"""
SFR -- Stigmergic Field Routing : CPU reference model (the spec).

The framebuffer IS the protocol state. Two layers, both per-cell:

  packet layer  (uint32 x4 per cell) : [destX, destY, age, handle<<3 | prio]
                                       handle == 0  => empty cell
  field  layer  (float32   per cell) : scalar potential. Destinations are
                                       potential wells (=1.0), diffused
                                       outward and decayed every frame.

One frame = { decay -> stamp wells -> diffuse (mip Jacobi) -> route }.
Routing is bufferless deflection: K claim/resolve rounds, losers stall,
an age guard forces steepest-descent once a packet gets old.

This module is authoritative. sfr_step.wgsl mirrors it bit-for-bit and
sfr_lockstep.py compares them frame by frame.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field as dc_field

# ---- tunables (mirrored as override constants in the WGSL) -------------------
GRID       = 64
DECAY      = np.float32(0.94)   # tuned: t_move 43->30 vs 0.98, delivery still 100%
WELL       = np.float32(1.0)
JACOBI_IT  = 2          # relaxation sweeps per mip level
FQ         = 1 << 16          # routing scores are Q16 fixed point (GPU/CPU exact)
W_FIELD_Q  = 1               # applied to the Q16 field value directly
W_HILB_Q   = 1966            # round(0.03 * FQ)
W_CONG_Q   = 16384           # round(0.25 * FQ)
K_ROUNDS   = 3          # deflection rounds per frame
AGE_STRICT = 24         # >= this: drop hilbert+congestion terms, pure descent
AGE_TIMEOUT = 512       # >= this without delivery: routing has failed
NCH        = 4          # field channels = independent per-destination fields
                        # packet hp = handle<<5 | chan<<3 | prio   (chan in 0..3)

_N4 = ((0, -1), (0, 1), (1, 0), (-1, 0))   # N, S, E, W  (matches WGSL order)


def _hilbert_d2xy_table(n: int) -> np.ndarray:
    """index -> (x,y) and inverse, for an n x n Hilbert curve (n power of two)."""
    xy = np.zeros((n * n, 2), np.int32)
    for d in range(n * n):
        rx = ry = 0
        x = y = 0
        t = d
        s = 1
        while s < n:
            rx = 1 & (t // 2)
            ry = 1 & (t ^ rx)
            if ry == 0:
                if rx == 1:
                    x = s - 1 - x
                    y = s - 1 - y
                x, y = y, x
            x += s * rx
            y += s * ry
            t //= 4
            s *= 2
        xy[d] = (x, y)
    return xy


class SFR:
    def __init__(self, grid: int = GRID, seed: int = 0, *,
                 w_hilb_q: int = W_HILB_Q, w_cong_q: int = W_CONG_Q,
                 decay: float = float(DECAY), jacobi_it: int = JACOBI_IT):
        self.n = grid
        self.w_hilb_q = int(w_hilb_q)
        self.w_cong_q = int(w_cong_q)
        self.decay = np.float32(decay)
        self.jacobi_it = int(jacobi_it)
        self.rng = np.random.default_rng(seed)
        self.packet = np.zeros((grid, grid, 4), np.uint32)
        self.fieldv = np.zeros((grid, grid, NCH), np.float32)
        self.wells: dict[tuple[int, int], int] = {}    # cell -> frames-to-live
        self.wchan: dict[tuple[int, int], int] = {}    # cell -> field channel
        self.frame = 0
        self.delivered: list[dict] = []
        self._hxy = _hilbert_d2xy_table(grid)
        self._hidx = np.zeros((grid, grid), np.int32)
        for i, (x, y) in enumerate(self._hxy):
            self._hidx[y, x] = i

    # -- injection ----------------------------------------------------------
    def inject(self, x, y, dest, handle, prio=0, chan=0):
        assert self.packet[y, x, 3] == 0, "cell occupied"
        dx, dy = dest
        self.packet[y, x] = (dx, dy, 0,
                             (handle << 5) | ((chan & 3) << 3) | (prio & 7))
        self.wells[(dx, dy)] = 999_999   # sticky well while a packet targets it
        self.wchan[(dx, dy)] = chan & 3

    # -- one frame --------------------------------------------------------
    def step(self):
        self._decay_and_stamp()
        self._diffuse()
        self._route()
        self.frame += 1

    def _decay_and_stamp(self):
        self.fieldv *= self.decay
        # sticky wells for live destinations
        live = set()
        occ = self.packet[..., 3] != 0
        ys, xs = np.nonzero(occ)
        for x, y in zip(xs, ys):
            dx, dy = int(self.packet[y, x, 0]), int(self.packet[y, x, 1])
            live.add((dx, dy))
        for cell in list(self.wells):
            if cell in live:
                self.wells[cell] = 999_999
            else:
                self.wells[cell] -= 1
                if self.wells[cell] <= 0:
                    del self.wells[cell]
                    self.wchan.pop(cell, None)
        for (wx, wy) in self.wells:
            self.fieldv[wy, wx, self.wchan.get((wx, wy), 0)] = WELL

    def _smooth(self, g, it):
        """`it` edge-corrected 5-point Jacobi sweeps, well re-pinned each sweep.
        `g` is (s, s, NCH); the stencil is per-channel, `nb` is shared."""
        scale = self.n // g.shape[0]
        nb = np.full(g.shape[:2] + (1,), 5.0, np.float32)
        nb[0, :] -= 1; nb[-1, :] -= 1; nb[:, 0] -= 1; nb[:, -1] -= 1
        for _ in range(it):
            acc = g.copy()
            acc[1:, :] += g[:-1, :]
            acc[:-1, :] += g[1:, :]
            acc[:, 1:] += g[:, :-1]
            acc[:, :-1] += g[:, 1:]
            g = (acc / nb).astype(np.float32)
            for (wx, wy) in self.wells:
                g[wy // scale, wx // scale, self.wchan.get((wx, wy), 0)] = WELL
        return g

    @staticmethod
    def _restrict(f):
        h = f.shape[0] // 2
        return f.reshape(h, 2, h, 2, f.shape[2]).mean(axis=(1, 3)).astype(np.float32)

    @staticmethod
    def _prolong(c):
        return np.repeat(np.repeat(c, 2, axis=0), 2, axis=1)

    def _diffuse(self):
        # 3-level multigrid V-cycle (64 -> 32 -> 16).  Coarse grids supply an
        # *additive* correction to the fine field -- the true-position well
        # stays the field peak, unlike the old lossy cascade which snapped
        # non-corner wells to the nearest coarse-grid corner (9% livelock).
        f = self._smooth(self.fieldv.copy(), self.jacobi_it)
        r0 = self._restrict(f)
        c1 = self._smooth(r0.copy(), self.jacobi_it)
        r1 = self._restrict(c1)
        c2 = self._smooth(r1.copy(), self.jacobi_it * 2)     # coarsest: extra sweeps
        c1 = self._smooth(c1 + self._prolong(c2 - r1), self.jacobi_it)
        f = self._smooth(f + self._prolong(c1 - r0), self.jacobi_it)
        self.fieldv = f

    # -- routing : K deflection rounds ----------------------------------
    def _route(self):
        n = self.n
        # Q16 integer snapshot of the field -- the only field data routing sees.
        fq = np.rint(self.fieldv * FQ).astype(np.int64)
        occ = self.packet[..., 3] != 0
        ys, xs = np.nonzero(occ)
        pk = [dict(x=int(x), y=int(y),
                   dx=int(self.packet[y, x, 0]), dy=int(self.packet[y, x, 1]),
                   age=int(self.packet[y, x, 2]), hp=int(self.packet[y, x, 3]),
                   chan=(int(self.packet[y, x, 3]) >> 3) & 3,
                   placed=False)
              for x, y in zip(xs, ys)]

        # deliveries first
        for p in pk:
            if (p["x"], p["y"]) == (p["dx"], p["dy"]):
                p["placed"] = True
                p["deliver"] = True
                self.delivered.append(dict(handle=p["hp"] >> 5, age=p["age"],
                                           frame=self.frame))
                # ack well so the return path lights up for free
                self.fieldv[p["y"], p["x"], p["chan"]] = WELL

        settled = np.zeros((n, n), bool)
        for p in pk:
            if p.get("deliver"):
                continue
            settled[p["y"], p["x"]] = True   # provisional; may vacate

        def ranked_dirs(p):
            cand = []
            strict = p["age"] >= AGE_STRICT
            wh = 0 if strict else self.w_hilb_q
            wc = 0 if strict else self.w_cong_q
            dtar = int(self._hidx[p["dy"], p["dx"]])
            for k, (ox, oy) in enumerate(_N4):
                nx, ny = p["x"] + ox, p["y"] + oy
                if not (0 <= nx < n and 0 <= ny < n):
                    continue
                s = (W_FIELD_Q * int(fq[ny, nx, p["chan"]])
                     - wh * abs(int(self._hidx[ny, nx]) - dtar) // (n * n)
                     - wc * (1 if settled[ny, nx] else 0))
                cand.append((-s, k, nx, ny))   # higher score, then N,S,E,W order
            cand.sort()
            return [(nx, ny) for _, _, nx, ny in cand]

        # deflection rounds: strict total order by (age, source-cell) -- unique,
        # deterministic, and non-forcing so it cannot create a cycle.  The
        # forced-displacement phase below is the only forcing path and uses
        # (age, handle); see SATURATION_LIVELOCK_NOTE.md.
        def order_key(p):                       # displacement pick only
            return (min(p["age"], 2047), -((p["hp"] >> 5) & 0xFFFFF))

        for r in range(K_ROUNDS):
            claims: dict[tuple[int, int], list] = {}
            for p in pk:
                if p["placed"]:
                    continue
                dirs = ranked_dirs(p)
                if r >= len(dirs):
                    continue
                tgt = dirs[r]
                if settled[tgt[1], tgt[0]]:
                    continue
                if p["age"] >= AGE_STRICT and (
                        int(fq[tgt[1], tgt[0], p["chan"]])
                        <= int(fq[p["y"], p["x"], p["chan"]])):
                    # a strict packet never steps to lower-or-equal field;
                    # it waits here for the forced-displacement phase instead
                    # of sustaining a sideways/backward deflection cycle.
                    continue
                key = (p["age"], -(p["y"] * n + p["x"]))   # older, then lower cell
                claims.setdefault(tgt, []).append((key, p))
            for tgt, lst in claims.items():
                lst.sort(key=lambda t: t[0], reverse=True)
                _, win = lst[0]
                settled[win["y"], win["x"]] = False
                settled[tgt[1], tgt[0]] = True
                win["x"], win["y"] = tgt
                win["placed"] = True

        # -- forced displacement: guarantee the globally-oldest AGE_STRICT
        #    unplaced packet its steepest-descent move (see
        #    SATURATION_LIVELOCK_NOTE.md termination argument).  Exactly one
        #    per frame -> race-free, provably livelock-free on a V-cycle field.
        strict_wait = [p for p in pk
                       if not p["placed"] and p["age"] >= AGE_STRICT]
        if strict_wait:
            P = max(strict_wait, key=order_key)
            tx, ty = ranked_dirs(P)[0]                 # rank-0, penalties dropped
            if not settled[ty, tx]:
                settled[P["y"], P["x"]] = False
                settled[ty, tx] = True
                P["x"], P["y"] = tx, ty
                P["placed"] = True
            else:
                O = next(q for q in pk if not q.get("deliver")
                         and (q["x"], q["y"]) == (tx, ty))
                O["x"], O["y"] = P["x"], P["y"]        # occupant -> P's old cell
                P["x"], P["y"] = tx, ty                # both cells stay settled
                P["placed"] = True
                O["placed"] = True

        # write back
        self.packet[:] = 0
        for p in pk:
            if p.get("deliver"):
                continue
            self.packet[p["y"], p["x"]] = (p["dx"], p["dy"], p["age"] + 1, p["hp"])

    # -- metrics ------------------------------------------------------------
    def in_flight(self):
        return int((self.packet[..., 3] != 0).sum())

    def snapshot(self):
        return self.packet.copy(), self.fieldv.copy()


# ---- verification scenarios -------------------------------------------------
def test_delivery_guarantee(n=64, npkt=200, seed=1, verbose=True):
    s = SFR(n, seed)
    dest = (n - 1, n - 1)
    free = [(x, y) for y in range(n) for x in range(n) if (x, y) != dest]
    s.rng.shuffle(free)
    for i in range(npkt):
        x, y = free[i]
        s.inject(x, y, dest, handle=i + 1, prio=s.rng.integers(0, 8))
    launched = npkt
    for f in range(AGE_TIMEOUT):
        s.step()
        if s.in_flight() == 0:
            break
    ok = len(s.delivered) == launched and s.in_flight() == 0
    ages = [d["age"] for d in s.delivered]
    if verbose:
        print(f"[delivery] {len(s.delivered)}/{launched} delivered in {s.frame} "
              f"frames  max_age={max(ages) if ages else '-'}  "
              f"{'PASS' if ok else 'FAIL'}")
    return ok


def test_convergence(n=64, seed=2, eps=1e-3, verbose=True):
    s = SFR(n, seed)
    s.wells[(8, 8)] = 999_999
    prev = s.fieldv.copy()
    for f in range(400):
        s.step()
        d = float(np.abs(s.fieldv - prev).max())
        prev = s.fieldv.copy()
        if d < eps:
            break
    t_settle = s.frame
    del s.wells[(8, 8)]
    s.wells[(n - 8, n - 8)] = 999_999
    prev = s.fieldv.copy()
    for f in range(400):
        s.step()
        d = float(np.abs(s.fieldv - prev).max())
        prev = s.fieldv.copy()
        if d < eps:
            break
    t_move = s.frame - t_settle
    if verbose:
        print(f"[converge] settle={t_settle} frames  after-move={t_move} frames")
    return t_settle, t_move


def test_throughput(n=64, rate=6, frames=300, seed=3, verbose=True):
    s = SFR(n, seed)
    dest = (n // 2, n // 2)
    h = 1
    for f in range(frames):
        for _ in range(rate):
            spots = [(x, y) for x in range(n) for y in (0, n - 1)
                     if s.packet[y, x, 3] == 0]
            if spots:
                x, y = spots[int(s.rng.integers(len(spots)))]
                s.inject(x, y, dest, handle=h); h += 1
        s.step()
    thru = len(s.delivered) / frames
    if verbose:
        print(f"[throughput] {len(s.delivered)} delivered / {frames} frames "
              f"= {thru:.2f} pkt/frame  (inject rate {rate})  "
              f"backlog={s.in_flight()}")
    return thru


def test_contention_no_deadlock(n=64, seed=4, verbose=True):
    """Every cell of the top two rows races to one throat cell. If the age
    guard works, all packets still drain and none hits AGE_TIMEOUT."""
    s = SFR(n, seed)
    dest = (n // 2, n - 1)
    h = 1
    for y in (0, 1):
        for x in range(n):
            if (x, y) == dest:
                continue
            s.inject(x, y, dest, handle=h); h += 1
    launched = h - 1
    max_age = 0
    for f in range(AGE_TIMEOUT):
        s.step()
        occ = s.packet[..., 2][s.packet[..., 3] != 0]
        if occ.size:
            max_age = max(max_age, int(occ.max()))
        if s.in_flight() == 0:
            break
    ok = len(s.delivered) == launched and max_age < AGE_TIMEOUT
    if verbose:
        print(f"[deadlock] {len(s.delivered)}/{launched} drained in {s.frame} "
              f"frames  max_age={max_age} (timeout {AGE_TIMEOUT})  "
              f"{'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    test_delivery_guarantee()
    test_contention_no_deadlock()
    test_convergence()
    test_throughput()
