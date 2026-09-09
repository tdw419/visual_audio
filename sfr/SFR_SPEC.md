# SFR — Stigmergic Field Routing: Protocol Specification

**Status:** implemented, GPU-verified (bit-exact lockstep vs CPU reference)
**Branch:** `sfr-stigmergic-routing` (commits 328dcf8 → 50aa14f → b464505)
**Reference implementation:** `sfr/sfr_reference.py` (authoritative — the WGSL
mirrors it bit-for-bit; `sfr_lockstep.py` / `sfr_diffuse_check.py` enforce that)

## 1. Idea

The framebuffer is the entire protocol state. No routing tables, no control
packets, no host round-trip. One compute dispatch = one hop for every packet
in flight. Two things live per cell:

- **packet layer** — sparse; present only where packets currently sit
- **field layer** — a per-channel scalar potential, diffused and decayed
  every frame. Destinations are potential wells. Routing state IS a fading
  pixel field; routes are emergent, not computed.

## 2. State layout

### Packet layer (uint32 ×4 per cell)

```
[destX, destY, age, hp]
  destX/destY : target cell coords (plain grid coords, NOT Hilbert index)
  age         : frames in flight; drives strictness and displacement
  hp          : handle<<5 | chan<<3 | prio
                handle  : unique packet id (0 = empty cell)
                chan    : field channel 0..3 (destination identity)
                prio    : 0..7 priority bits
```

### Field layer (f32 ×NCH=4 per cell)

Independent per-destination scalar potentials. Wells are stamped `WELL=1.0`
on their channel each frame; everything else decays by `DECAY=0.94` and is
diffused by a 3-level multigrid V-cycle.

Memory: one RGBA32F texture holds 4 independent destination fields; routing
reads a Q16 integer snapshot of the field (`FQ = 1<<16`) — the only field
data the routing step sees, which is what makes GPU/CPU bit-exactness
achievable.

## 3. Per-frame pipeline

```
decay & stamp wells  ->  diffuse (V-cycle)  ->  route (K rounds + displacement)
```

### 3.1 Diffusion — 3-level multigrid V-cycle (64 → 32 → 16)

```
f  = smooth(field, it)                    # edge-corrected 5-point Jacobi
r0 = restrict(f)
c1 = smooth(r0, it)
r1 = restrict(c1)
c2 = smooth(r1, 2*it)                     # coarsest: extra sweeps
c1 = smooth(c1 + prolong(c2 - r1), it)    # additive correction
f  = smooth(f  + prolong(c1 - r0), it)
```

**Rules learned the hard way** (see `MULTIGRID_FALSE_PEAK_RECEIPT.md`):

1. Coarse grids supply **additive correction**, never overwrite-prolongation.
   A lossy cascade silently relocates sub-coarse-cell features: well `(4,4)`
   snaps to coarse cell `(0,0)` at scale 8, packets climb the false peak and
   pin there under the age guard (9% permanent livelock).
2. Well re-pin after **every** Jacobi sweep, not once per level.
3. Smoothing cannot relocate a displaced peak — more fine sweeps plateau
   (196/200). Only faithful re-injection fixes it.

### 3.2 Routing — K=3 deflection rounds, then one forced displacement

Per packet, score each cardinal neighbour on the packet's channel:

```
score(n) = W_FIELD_Q * field_q16[n]                       (always)
         - W_HILB_Q * |hidx[n] - hidx[dest]| / (n*n)      (age < AGE_STRICT)
         - W_CONG_Q * occupied[n]                         (age < AGE_STRICT)
```

- `W_FIELD_Q=1`, `W_HILB_Q=1966` (0.03 field units), `W_CONG_Q=16384` (0.25)
- `AGE_STRICT=24`: strict packets drop the Hilbert + congestion terms —
  pure field ascent. `AGE_TIMEOUT=512` = protocol failure.
- Contention: strict total order `(age, source-cell)` — unique, deterministic,
  **non-forcing**, therefore acyclic. Losers deflect to next-ranked direction.

**Strict-ascent invariant:** a packet with `age >= AGE_STRICT` never claims a
neighbour whose channel field is lower-or-equal to its current cell. It waits
instead of sustaining a field-neutral deflection cycle. (Without this the
first displacement attempt stalled: the oldest packet "progressed" via a
2-cycle of ±54 field and was never unplaced when displacement ran.)

**Forced displacement (one per frame):** the globally-oldest AGE_STRICT
unplaced packet P (ties: lowest handle) is granted its rank-0 move — into the
cell if free, else by swap with the occupant (occupant takes P's vacated
cell). Chosen via atomicMax on a packed key in the GPU kernel; the
"settled cells never move" invariant is broken *only* inside this path.

**Livelock-freedom** (full argument in `SATURATION_LIVELOCK_NOTE.md`): P's
channel-field value strictly increases every frame on a V-cycle field (every
non-well cell has a strictly-higher neighbour), so P delivers in ≤ (distinct
field levels) frames; the next-oldest becomes P. Ping-pong is impossible by
construction. **Depends on the false-peak fix** — the proof needs
"strictly-higher neighbour" to hold everywhere.

### 3.3 Delivery

Cell == dest → consume, stamp an ack well on the packet's channel so return
paths light up for free. Sticky wells: any cell targeted by a live packet is
re-stamped each frame; wells expire `~512` frames after their last reference.

## 4. Operating modes

| mode | field usage | semantics | intended-hit | throughput |
|------|-------------|-----------|--------------|------------|
| **B** | all wells on channel 0 | any-well load balance (nearest-well drain) | ~25% (= chance, by design) | high — scales with well count |
| **A** | one well per channel | destination-aware routing | **99%** (198/200) | see §6 |

A single scalar field **structurally cannot** do destination routing — the
Hilbert tie-break (0.03 field units) is nowhere near strong enough to pull a
packet out of a wrong-but-closer basin. Mode B is for any-will-do workloads;
mode A is the destination router.

## 5. Verification model

- **Bit-exact lockstep**: `sfr_step.wgsl` (6 entry points: deliver →
  K×[clear_claims, claim_round, resolve, apply_vacate] → age_tick, plus
  displace/pick_oldest/find_p) mirrors `sfr_reference.py` integer-for-integer.
  All integer arithmetic (Q16 fixed-point scores, packed hp) — no float in the
  routing path.
- **Diffusion lockstep**: GPU f32 vs CPU within 4e-7 float / ±1 Q16.
- **Scenarios**: A general, B line-contention, C age-guard, D multichannel
  (descend own channel past a closer off-channel well), E saturation-jam
  (the exact livelock topology), F pingpong pair. All bit-exact + drain.
- **Gates**: delivery 200/200, contention 128/128 max_age < 512, convergence
  settle 29 fr / after-move 38 fr.

## 6. Throughput (re-baselined on committed state b464505)

Measured with `sfr_throughput_rebaseline.py` (sustained edge injection,
50-frame warm-up, steady-state window):

| scenario | rate | steady throughput |
|----------|------|-------------------|
| single-dest | 1 | 0.28 pkt/fr |
| single-dest | 2 | 0.81 pkt/fr |
| single-dest | 4 | 2.05 pkt/fr (**saturation ceiling** — rate 8 gives same) |
| mode B | 4 | 0.52 pkt/fr |
| mode B | 8 | **3.86 pkt/fr** (best measured) |
| mode A | 4 | 1.21 pkt/fr |
| mode A | 8 | 2.64 pkt/fr |
| mode A burst (200 pkt) | — | 151 fr drain ≈ 1.32 pkt/fr |

Notes:
- Single-dest saturates at **2.05 pkt/fr** — that is the one-well throat
  ceiling; rate 4 and rate 8 both pin there (backlog grows at rate 8).
- Mode B at rate 8 reaches 3.86 pkt/fr but its drain extends (553 fr vs
  ~340 fr at low rate) — approaching, not yet at, the 4-well ceiling.
- Mode A pays ~30% vs mode B at rate 8 (2.64 vs 3.86) — the price of
  destination-correct routing; single channel per well halves the effective
  well density when 4 wells each get their own channel.

Superseded figures: 0.86 pkt/fr (pre-V-cycle/pre-displacement single-dest
steady at rate 6), 3.86 pkt/fr (pre-fix mode B burst). Do not quote those.

## 7. Known limits / next

- **≤4 destinations per texture** (vec4 channels). >4 needs multiple field
  textures → O(⌈D/4⌉) dispatches.
- **Destination identity is channel-packed**, not arbitrary — a packet's
  `chan` selects one of 4 pre-agreed fields. General destination sets need a
  dest→channel assignment layer above the protocol.
- **Displacement is strictly oldest-first** — fairness tail is ~2× median
  (p50/p90/p99 = 66/106/132 on mode A), acceptable, but worth re-checking if
  AGE_STRICT or load changes.
- Throughput on a single well is throat-limited (~1 pkt/fr at the well
  neighbourhood); parallel delivery requires multiple wells/sinks.

## 8. File map

| file | role |
|------|------|
| `sfr_reference.py` | authoritative CPU model + reference gates |
| `sfr_step.wgsl` | GPU routing step (bit-exact mirror) |
| `sfr_diffuse.wgsl` | GPU diffusion (per-channel, V-cycle) |
| `sfr_lockstep.py` | routing GPU-vs-CPU lockstep, scenarios A–F |
| `sfr_diffuse_check.py` | diffusion lockstep |
| `sfr_multidest.py` | mode A vs B destination-correctness |
| `sfr_throughput_rebaseline.py` | sustained-load throughput (§6) |
| `sfr_sweep.py` | gradient tunables sweep |
| `MULTIGRID_FALSE_PEAK_RECEIPT.md` | diffusion root-cause receipt |
| `SATURATION_LIVELOCK_NOTE.md` | displacement design + termination proof |
