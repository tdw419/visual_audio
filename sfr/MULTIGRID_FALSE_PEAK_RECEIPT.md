# SFR multigrid false-peak livelock — root-cause receipt

**Date:** 2026-09-01
**Component:** `sfr/sfr_reference.py::SFR._diffuse`, `sfr/sfr_diffuse.wgsl`
**Status:** fixed, verified on CPU reference + GPU lockstep

---

## Symptom

`sfr_multidest.py` mode A (per-destination field, one well per sim) left
**18/200 packets undelivered**, all hitting the `AGE_TIMEOUT` cap of 512
frames. Mode B (single shared field) left 25/200 undelivered. The
single-destination gates (`test_delivery_guarantee`, well at exact corner
`(63,63)`) passed 100%, so the failure was specific to **wells not on an
exact grid corner** (e.g. `(4,4)`, `(59,4)`).

## Investigation

Trajectory + field dump of the stuck packets (`sfr` group k=0, well `(4,4)`):

```
stuck packets: (1,0) (2,0) (0,1) (0,2)      -- age 512, i.e. never moved productively
field around (1,0), x2^16:
        x=0     x=1     x=2     x=3
 y=0  57697   57459   56837   55888          <- DECREASES toward the well
 y=1  57459   57265   56783   56026
 y=2  56837   56783   56648   56172
```

The stuck packets sit **next to the well, in the true grid corner `(0,0)`**,
and the field gradient there points *away* from the well. The diffused field's
local maximum is at `(0,0)`, not at the well `(4,4)`. Packets greedily climb
to `(0,0)`, reach a false local max (all neighbours lower), and the age guard's
"pure steepest descent" keeps them pinned — every legal move is downhill and
none is toward the well.

## Root cause

The old `_diffuse` was a **lossy coarse-to-fine cascade**: at each level it
discarded the fine field and replaced it with the upsampled coarse result
(`levels[li-1] = kron(coarse_smoothed)`).

At the coarsest level (8x8, `scale = 64/8 = 8`) the well at `(4,4)` is re-pinned
at coarse cell `(4//8, 4//8) = (0,0)` — the **true corner block**. Well `(4,4)`
and corner `(0,0)` are *indistinguishable* at scale 8. The cascade then
"solves" for a peak at the corner and only 2 fine Jacobi sweeps run afterward —
nowhere near enough to migrate the peak the 4–7 cells back to `(4,4)`.

Well `(63,63)` was immune only by coincidence: `63//8 = 7`, and coarse cell
`(7,7)` *is* the corner block, so the snap is a no-op.

**The bug was semantic, not numerical.** Coarse cells do not merely lose
detail — they silently *relocate* features. Overwrite-prolongation is only
valid when the coarse representation is faithful to the fine one; for a
sub-coarse-cell feature like an interior well, it is not.

## Fix

Replace the lossy cascade with a **proper 3-level multigrid V-cycle**
(64 → 32 → 16) that applies coarse grids as an **additive correction**:

```
f  = smooth(field, it)
r0 = restrict(f)
c1 = smooth(r0, it)
r1 = restrict(c1)
c2 = smooth(r1, 2*it)                 # coarsest gets extra sweeps
c1 = smooth(c1 + prolong(c2 - r1), it)
f  = smooth(f  + prolong(c1 - r0), it)
```

Plus: well re-pin after **every** Jacobi sweep (was once per level). The
fine-resolution well pin is never discarded, so the true-position well
remains the field peak.

### Why "just add more fine sweeps" does not work

First fix attempt bumped the post-cascade fine sweeps: 0 → 32 extra sweeps
moved delivery 182/200 → 196/200 and then **plateaued**. Smoothing cannot
relocate a displaced peak — it can only diffuse from wherever the peak
currently is. Only re-injecting the true well position (per-sweep re-pin
inside a faithful V-cycle) fixes it. 32 fine sweeps/frame is also far more
expensive than the 12-sweep-equivalent V-cycle.

## Verification

| check | before | after |
|-------|--------|-------|
| mode A undelivered | 18/200 (512-fr timeout) | **0/200**, drain 122 fr |
| mode B undelivered | 25/200 | **0/200**, drain 69 fr |
| `test_delivery_guarantee` | pass | pass |
| `test_contention_no_deadlock` | pass | pass |
| convergence settle | 36 fr | 29 fr |
| convergence after-move | 30 fr | 38 fr (target < 50) |
| diffusion lockstep (GPU vs CPU) | n/a | max_float_err 4e-7, max_Q16_err ±1 |
| routing lockstep (3 scenarios) | bit-exact | bit-exact |

## Generalizable lesson

Any hierarchically-diffused field in this repo (SFR spatial routing, saccade
/ attention fields, mip-pyramid anything) must use **additive multigrid
correction**, not overwrite-prolongation, whenever a feature can be smaller
than a coarse cell. If you see a diffused field whose peak is at a grid-
aligned position near — but not at — a known source, suspect scale-snapping
in a lossy cascade before suspecting precision.
