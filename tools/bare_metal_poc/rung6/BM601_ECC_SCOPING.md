# BM601 — ECC scoping pass (Rung 6): size budget and go/no-go

**Row asked:** can an RS decoder — or a cheaper erasure scheme over the 4-plane
interleave — fit the Rung-4 stage2 budget in 16-bit asm, and what does the
parity do to medium layout?
**Answer (measured, this pass):** yes, by a wide margin — the corrector is
**244 bytes** of assembled 16-bit code against **4,848 bytes** already unused in
the current 8,192 B stage2 image, and code size is therefore *not* the binding
constraint. What binds is **medium capacity** (+75% for the recommended code)
and **fault granularity**. Recommendation: **GO on option A**, with the risk
list below. Implementation is its own gated row and does **not** start from
this note.

Measurements come from two probes, both run against the real BM903 medium and
payload, neither of which boots anything or touches a live gate:

```bash
cd tools/bare_metal_poc/rung6
python3 probe_bee_scheme.py            # 10 legs, exit 0, tail below
nasm -f bin probe_bee_inner_loop.asm -o /tmp/bee.bin   # size only
```

Run twice back to back; every leg reproduced with identical numbers (only the
labelled host-throughput figure moved, 337 → 339 MiB/s). Full transcript:
`bm601_scoping_probe.txt`. The probe is seeded (`rng 20260919`), so the fault
positions — and the two RED CRCs quoted below — are reproducible, not sampled.

## 1. The fault model falls out of the existing interleave

PXC1 places payload byte `i` at medium byte
`PX_BASE_LBA*512 + (i%4)*PLANE_BYTES + i//4` (`rung9/bm903_pxcodec.py`). So the
four payload bytes of a Hamming(7,4) codeword — `4x, 4x+1, 4x+2, 4x+3` — are
**exactly the four planes at the same in-plane offset `x`**. The medium the tree
already writes spreads every codeword across four independent read streams for
free.

Consequence, measured rather than asserted (legs B–F): a media fault confined
to **one plane** — a bad 512 B sector, a bad 8-sector chunk (the guest's own
read unit), a 128 KiB flash erase block — corrupts **at most one symbol per
codeword**. That is precisely the class a single-error-correcting code fixes,
and it is the class Rung 8 cares about (USB bit-rot, bad flash sectors).

The code is Hamming(7,4) with **byte symbols**, linear over GF(2):

```
p1 = d0^d1^d3    p2 = d0^d2^d3    p4 = d1^d2^d3
s1,s2,s4 nonzero-pattern -> which symbol; fix value = any covering syndrome
```

No GF(256) multiply, no log/antilog table, no syndrome solver. Three parity
planes, and the parity of a codeword is just three more planes.

## 2. Budget (every number measured by the probe)

| quantity | today (PXC1) | with 3 parity planes (PXC2-E) |
|---|---|---|
| payload | 13,631,488 B | unchanged |
| planes / medium | 4 / 26,641 sectors = 13,640,192 B | 7 / **46,609** sectors = **23,863,808 B (22.76 MiB, +75%)** |
| reads per 16 KiB group | 4 × 8-sector | **7** × 8-sector → 5,824 chunk reads per boot |
| parity bytes on medium | — | 10,223,616 B = +75.0% of payload |
| stage2 code | 3,344 B used of an 8,192 B container | +**244 B** corrector (measured `nasm` output; container size is a declared knob, `stage2_sectors`) |
| tables | CRC32 1,024 B (already there) | **zero new tables** |
| low memory | planes 0x30000–0x34000, sink 0x34000–0x38000 | 3 × 4,096 B buffers at **0x38000–0x3B000** (unused in the BM903 map; nothing to move) |
| walk wall clock | ≤ 1.0 s (`RECEIPT_BM903_STEP2.md`, 0.1 s serial stamps) | ~1.75 s **projected** from +75% bytes — the probe does not boot; the implementation row measures this first |
| host decode bound | — | 337 MiB/s / 0.04 s for the whole payload (numpy, host: labelled host, not guest) |

Structural note that decides the go/no-go: the corrector is a **pass 1** that
patches the plane buffers in place; the existing `.pw_byte` de-interleave + CRC
loop is then left byte-for-byte alone. So BM903's L1/L4 identity legs keep
meaning "same loader text, different medium", and the CRC32 gate keeps running
over decoded, **corrected**, decoded-order bytes.

## 3. What it does not cover — the two REDs, both measured

* **Leg G** — two symbols wrong in one codeword (e.g. the same x-range damaged
  in *two* planes: 8,192 corrupted bytes). The decoder "corrects" 4,096 of them
  and lands **wrong**: post-decode `CRC=CE9C0E29 != 393950AA`. The refusal is
  the one BM903 already proves (L6), and it still fires.
* **Leg H** — the linear code's blind spot, built on purpose: `d0^=01, d1^=02,
  d2^=02, d3^=03` makes **all three syndromes zero**, so the corrector is blind
  by algebra and fixes nothing. The payload is still wrong (256 bytes) and the
  gate still refuses: `CRC=E1CA03F5 != 393950AA`.

**Therefore:** ECC goes *between* the read and the CRC gate, never in front of
it or in place of it. The gate stays the only path to the handoff, and a
mis-correction is a refused boot, not a silent one. Probability a wrong payload
passes a 32-bit CRC over 13.6 MB is ~2⁻³² for random faults — and leg H is the
warning that media faults are not always random, which is why the CRC is not
allowed to become optional.

## 4. Options considered

| | capacity | reads/boot | code | tolerance | status |
|---|---|---|---|---|---|
| **A. Hamming(7,4) over bytes (3 parity planes)** | +75% | 4→7 per group | **244 B measured** | ≤1 symbol per codeword, no locator needed: covers whole-plane/sector/chunk/erase-block faults and scattered single-channel rot | **RECOMMENDED** |
| **B. 1 parity plane + per-plane-chunk CRC32 table** | +25.4% (parity plane + 13,312 B of chunk CRCs = 4 B × 3,328 chunks, 0.1% of payload) | 4→5 per group | not separately measured; its two parts — a chunk CRC via the existing `CRC8` macro, and a 4-way XOR recovery loop — are each structurally smaller than A's 244 B | one bad 4 KiB chunk is *located* then fully recovered; a single scattered pixel rot also fails its chunk CRC, so it is recovered as 4,096 erasures. Fails when two located chunks collide in x across planes | cheapest capacity; revisit if 22.76 MiB is ever a problem. A is preferred because it needs no locator bookkeeping |
| **C. RS(255,223) + interleaving** | +14.3% | ~4.6 per group | **estimate only:** GF(256) tables (≥512 B) plus a 16-bit solver; this is the option whose code cost is genuinely unknown and must be measured before it is chosen | covers *column* faults — 4 consecutive payload bytes per offset, i.e. damage that hits all four planes at the same `x`, which A and B both fail | keep on the table **only** if the column-fault class turns out to matter for real media; it is the one threat A does not cover |

## 5. Gate shape the implementation row should inherit (not built here)

Row's letter: "flip N specified corrupted pixels and still boot byte-identical;
N+1 → specified refusal." Under this code N is not a bare count — it is a
fault-model predicate, and the gate should say so:

1. **GREEN:** one whole bad plane chunk (4,096 B, the guest read unit) boots
   byte-identical to the clean boot — transcripts *and* handoff dumps, BM903's
   L4 discipline unchanged.
2. **GREEN:** one bad 128 KiB erase-block-shaped span, same plane.
3. **RED:** two located collisions (same x-range, two planes) → refusal line
   names `CRC=<computed> EXP=<expected>`, no handoff, no stop at 0x100000 —
   BM903's L6 shape.
4. **NEW anchor, required for non-vacuity:** the guest prints
   `ECC=<fixed> PAR=<parity-only>` **before** the CRC verdict (DEFECT-R4PRINT
   order), so a leg that "passes" by correcting nothing cannot be mistaken for
   one that recovered a chunk. A run with `ECC=0` on a corrupted medium is a
   FAIL.
5. **Regression:** BM903's own gate stays green in the same invocation — ECC
   must not be able to buy a boot the old gate would have refused.

## 6. Honest boundaries of this pass

* Nothing booted. Every timing here is either a host-side bound (labelled) or a
  projection from BM903's measured walk; the guest number is the implementation
  row's first measurement.
* `probe_bee_inner_loop.asm` is a **code-size** probe. It is wired into no
  loader and has never executed. Its dispatch is *behaviourally* cross-checked
  by leg I against a literal scalar transcription of the same cmp/jne chain over
  200,000 codewords — that tests the algebra's equivalence, not the executed
  bytes.
* A new container version is mandatory (the guest must not read a PXC1 medium
  with PXC2 assumptions): tag it in the header band and assert the tag in
  stage2, the way `bm903_px_meta.json` pins the current one.
* **Do not touch the locked shim-side interfaces.** `locate_in_container` and
  the live pixel-substrate addressing are LOCKED; this rung's work is the
  rung-9 raw medium only. If an ECC geometry ever has to reach the shim, that
  is a separate ruling and a separate row, not a consequence of this one.
* Go/no-go is a **recommendation**. Queue order and the call to spend a row on
  it are Jericho's gate.
