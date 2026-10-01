# SFR saturation livelock — root-cause receipt

**Date:** 2026-09-02
**Status:** FIXED, verified on CPU reference + GPU lockstep (scenarios D, E, F).
Surfaced by the vec4 per-channel migration; was a pre-existing protocol gap,
not a regression.

## What

`sfr_multidest.py` mode A (4 wells, one per field channel, 200 packets with
random intended destinations) permanently livelocks **33/200 packets**. The
count freezes at ~frame 200 and never changes out to 3000 frames.

Single-destination gates (`test_delivery_guarantee`, 200 pkt → one well) still
pass 100%. Mode B (all packets on channel 0, drain-to-nearest) drains fully.
The earlier V-cycle validation used 4 *separate* 50-packet sims — half the
density and no head-on cross-channel traffic — so it never hit this.

## Where

Stuck packets form a solid triangular jam pinned against a grid **edge**,
right where two wells sit close together. Example: channels 0 and 1 have wells
at `(4,4)` and `(59,4)` — both on row y=4. Channel-0 packets want to go
left+down, channel-1 packets right+down, and they all pile up along y=0..3
fighting for the same cells. Every packet in the jam is the same (maximum)
age.

## Why

Bufferless deflection routing has **no delivery guarantee under regional
saturation**. The age guard breaks *ordering ties* (older packet wins a
contested free cell) but it cannot let an old packet **displace a settled
one**. When a whole region is full and every packet is equally old:

* each packet's steepest-descent cell is occupied
* deflection sends it sideways along the edge
* it can never enter the next row because that row is equally jammed
* → stable standoff, forever

This is independent of the field being correct — channel 0's field here is
bit-identical to a clean single-well field (verified), peak exactly on the
well. The field is fine; the *contention resolution* has no forward-progress
guarantee.

## Fix

Two parts:

### 1. Strict-ascent rule (the part that actually mattered)

A packet with `age >= AGE_STRICT` **never claims a neighbour whose channel
field is lower-or-equal to its current cell.** If its steepest-descent
(rank-0) cell is occupied and no strictly-higher-field neighbour is free, it
*waits in place* rather than taking a sideways/backward deflection.

Without this, the first fix attempt failed: an old packet kept "progressing"
via a 2-cycle (N to +54 field, then S to -54 field, forever) that the K
deflection rounds sustained, so it was never unplaced when displacement ran.

### 2. Forced displacement — one packet per frame

After the K rounds, the **globally-oldest** `AGE_STRICT` unplaced packet P
(ties: lowest handle) is granted its rank-0 move: into the cell if free, else
by swapping with the occupant (occupant goes to P's vacated cell; both cells
stay settled). Exactly one forced move per frame:

* race-free — a single designated packet, chosen by `pick_oldest` (atomicMax
  on a packed `(min(age,2047)<<20 | 0xFFFFF-handle)` key) then `find_p`
  (atomicMin of the matching cell index). `displace` acts only in P's cell.
* the deflection rounds keep their existing `(age, source-cell)` order —
  strict, unique, and non-forcing, so they cannot form a cycle. Displacement
  is the only forcing path.

### Termination argument (livelock-freedom)

> Let P be the globally-oldest `AGE_STRICT` unplaced packet (ties: lowest
> handle). Every frame P is granted its steepest-descent move — into a free
> cell, or by displacing the occupant into P's vacated cell. On a V-cycle
> field every non-well cell has a strictly-higher-potential neighbour, so P's
> channel-field value strictly increases each frame and P reaches its well in
> at most (number of distinct field levels) frames. On P's delivery the
> next-oldest packet becomes P. Hence the `AGE_STRICT` set drains, and
> `Σ(field potential over strict packets)` is strictly increasing while any
> strict packet exists — no livelock.

This **depends on the false-peak fix** (`MULTIGRID_FALSE_PEAK_RECEIPT.md`): if
the field had a local maximum away from the well, "strictly-higher neighbour"
would not hold and P could get pinned.

Ping-pong (two adjacent strict packets each wanting the other's cell) is
impossible by construction — only one packet forces per frame, it wins, done.
Scenario F exercises the pair anyway.

## Verification

| check | before | after |
|-------|--------|-------|
| mode A (200 pkt, 4 channels) undelivered | 33/200 (permanent) | **0/200**, drain 151 fr |
| routing lockstep D multichannel | 30 stuck @ 600 fr | bit-exact, drains 168 fr |
| routing lockstep E saturation-jam | (new) | bit-exact, drains 227 fr |
| routing lockstep F pingpong | (new) | bit-exact, drains 71 fr |
| routing lockstep A / B / C | bit-exact | bit-exact (unchanged path) |
| diffusion lockstep | 4e-7 / ±1 Q16 | unchanged |
| reference gates | pass | pass (delivery 200/200 @ 237 fr) |
| fairness (mode A wait p50/p90/p99/max) | — | 66 / 106 / 132 / 150 |

The fairness tail is ~2x the median, not a starvation blow-up — favouring the
oldest did not trade livelock for starvation.

## Blast radius (checked before touching `resolve`)

`settled` is read only by the congestion term (advisory) and the
`claim_round` gate. Delivery detection uses `pk[i].x` directly; ack stamping
touches `fieldv`. The "settled cells never move" invariant break is confined
to the new `displace` kernel.
