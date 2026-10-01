# RECEIPT — Rung 4: Scale (loader-side pixel decode at ≥64 KB)

**Date:** 2026-09-18 (builder cron af3e62239ce2)
**Location:** `tools/bare_metal_poc/rung4/`
**Inherits:** `../rung2/RECEIPT_RUNG2.md` (144 B proof), `../rung3/ANCHORS.md` (machine anchors, Path A).
**Tasks closed:** BM-401 (streaming reader + scatter), BM-402 (CRC32 gate v2), BM-403 (performance baseline), BM-404 (full leg-set gate).

## What ships (BM-401)

Path A, **pure real mode, no unreal mode** — windowing was sufficient; unreal
mode was never needed and none of its instructions shipped.

- `stage1.asm` (512 B MBR): EDD `AH=42h` streaming loop (8-sector/4 KB chunks
  through a fixed `SRC_SEG` window), **bank-outer scatter** de-interleave:
  bank b's destination segment is `DST_SEG + b*0x1000`; per (bank, plane,
  chunk) the LBA is `1 + p*PLANE/512 + 32*b + 8*c` and the scatter strides
  DI by 4 (`stosb; add di,3`), never leaving the bank segment at any scale
  the bank walk supports (DEFECT-R4SCATTER fix, measured: the plane-outer
  predecessor wrapped 16-bit DI at 64 KB and never wrote banks 1..3).
- `stage2.asm`: scale-parameterized receipt program (`RUNG4_SCALE`);
  computes its own sum16 over the payload and prints
  `STAGE2 SIZE=<KB> KB / STAGE2 CKSUM=<sum16> EXEC`.
- `rung4_codec.py` / `rung4_pad.py` / `rung4_consts.py`: PNG-archived
  RGBA medium (rung-2 twin pattern), padding to exact scale, build-time
  const generation (`stage1_const.inc`: `PLANE_LEN PAYLOAD_LEN PAYLOAD_BANKS
  CHUNK_SECTORS EXPECTED_CRC EXPECTED_SUM`).

## Integrity gate v2 (BM-402)

CRC32 (reflected `0xEDB88320`, init/final `0xFFFFFFFF`, zlib/PNG standard)
over the FULL decoded image, computed by the loader **before any control
transfer**; sum16 retained as a cheap pre-filter only.

Banked-walk fixes en route (each measured, not assumed):
- **DEFECT-R4CRC**: a 32-bit-count single `loop` silently CRC'd only the
  first 4096 B at 256 KB (guest `334D1A75` = crc of `folded[:4096]`).
- **DEFECT-R4CRC2/R4CRC3**: the bank advance clobbered AX, the CRC
  accumulator's low half (`E1AEDFFF` vs host `E1AE9612`); EAX now
  push/pop'd around every ES advance.

**DEFECT-R4PRINT (found and fixed THIS run, 2026-09-18):** the refusal path
printed the halves swapped — `CRC=<EXPECTED> EXP=<computed>` — so the
loader REFUSED CORRECTLY (no STAGE2 exec; computed CRC exact) but the
gate's greps could not recognize the refusal
(`GATE FAIL: RED-A: no specified failure (got: PXC1-RUNG4 / GATE4=FAIL CRC=E1AE9612 EXP=5A5F772A)`).
Host arithmetic cross-check confirmed the guest's computed `5A5F772A` was
exact before the print order was touched: `dbg_reda_crosscheck.py` →
`host cross-check CRC = 5A5F772A`. Fix: print computed then expected
(`stage1.asm` `r4_crc_fail`), matching the rung-2 receipt pattern.

## Gate results (BM-404) — GATE PASS ×2 consecutive

`bash rung4/run_gate4.sh` run twice back-to-back on 2026-09-18, both
`=== GATE PASS ===`, exit 0. Serial excerpts (run 1; run 2 identical):

```
green64k : PXC1-RUNG4 GATE4=PASS CRC=E1AE9612 STAGE2 SIZE=64 KB STAGE2 CKSUM=77B5 EXEC
redA     : PXC1-RUNG4 GATE4=FAIL CRC=5A5F772A EXP=E1AE9612
redB     : 0 serial bytes
green256k: PXC1-RUNG4 GATE4=PASS CRC=758F5EC8 STAGE2 SIZE=256 KB STAGE2 CKSUM=ECB8 EXEC
regreen  : byte-identical to green64k
```

Leg-by-leg:

| Leg | Expected | Measured | Verdict |
|---|---|---|---|
| Build + encode (64 KB) | stage2 65536 B, plane 16384 B, 128 sectors, CRC `E1AE9612` | as stated | PASS |
| Host roundtrips | bake(raw)==raw; decode(raw)==decode(png)==stage2.bin | byte-identical | PASS |
| GREEN 64 KB | `GATE4=PASS CRC=E1AE9612` + SIZE/CKSUM/EXEC | exact | PASS |
| RED-A: corrupt payload pixel (byte16 → medium offset 516, XOR 0xFF) | specified refusal naming computed AND expected, no exec | `GATE4=FAIL CRC=5A5F772A EXP=E1AE9612`, no STAGE2 line; host recomputation `5A5F772A` agrees | PASS |
| RED-B: 55AA destroyed | zero execution | 0 serial bytes | PASS |
| Absence probe at scale | no 16-B payload window contiguous in payload region | **0 of 65,521** windows contiguous; 55 hits are stage1's own shared helper code inside `[0,512)`; planted-probe control found at the planted offset | PASS |
| RE-GREEN (rebake from untouched PNG) | byte-identical GREEN serial | byte-identical | PASS |
| GREEN 256 KB | `GATE4=PASS CRC=758F5EC8` | exact (same stage1, consts-only change) | PASS |

## Performance baseline (BM-403) — this rung SETS the baseline

Method: wall time from QEMU start to the first `GATE4=` byte in the serial
log (50 ms polling granularity → values are upper bounds), TCG defaults,
x4 runs (2 per scale). Measured via `bm403_once.sh` (build → encode → boot
→ poll). A fixed-timeout variant (`bm403_timing.py`) was written first and
**rejected as a method error**: stage1 halts forever after the receipt, so
"timeout-bound wall time" measured the timeout (60.009 s), not the boot.

| Payload | Boot-to-receipt (upper bound) | Effective decode rate |
|---|---|---|
| 64 KB | ≤ 117 ms | ≥ ~560 KB/s |
| 256 KB | ≤ 115 ms | ≥ ~2.2 MB/s |

Decode cost is lost in the noise: the 4× payload adds no measurable time —
the walk is dominated by SeaBIOS + int 13h streaming; the ALU CRC over
256 KB is still under the polling granularity. Rung-2 comparison: 0.082 s
at 144 B (same order). No target was set; these numbers are the baseline
rung 5 optimizes against.

## Honest boundaries (what this receipt does NOT claim)

- Timings are n=2 per scale, TCG, polling-bounded (up to 50 ms coarse).
  Single-machine numbers, not characterization.
- The absence probe proves no 16-byte payload window is contiguous in the
  payload region of the CURRENT medium geometry — it is a property of the
  interleaved layout at 4 KB chunks, not a cryptographic claim.
- RED-B proves the MBR signature path refuses to execute; it does not
  probe corruption INSIDE stage1 (only the payload is CRC-gated — stage1
  itself is trusted-by-construction in this rung).
- 256 KB is the largest scale exercised. PAYLOAD_BANKS is 16-bit-safe to
  16 banks (1 MB) by construction; nothing above 256 KB has run.
- The entire `tools/bare_metal_poc/` tree beyond `rung4/` remains
  UNCOMMITTED (TASK_BM001, HOLD for Jericho's verbatim ratification).

## File inventory (rung4/)

Committed: `stage1.asm`, `stage2.asm`, `rung4_codec.py`, `rung4_pad.py`,
`rung4_consts.py`, `run_gate4.sh`, `bm403_once.sh`, `bm403_timing.py`,
`RECEIPT_RUNG4.md` (this file), `.gitignore`
(gate artifacts: `*.raw`, `*.bin`, `*.log`, `*.meta.json`, `dbg_*`,
`serial_*` — PNG mediums and sources are kept out of the archive rule).
Not committed: the `dbg_*.py`/`dbg_*.asm` debugging series INCLUDING
`dbg_reda_crosscheck.py` (the host-arithmetic cross-check that pinned
DEFECT-R4PRINT — its one-line payload is documented in this receipt's
integrity-gate section), plus the `mini_*`/`probe*` debugging mediums and
`DEBUG_NOTE.txt` (kept on disk untracked; the three defect stories above
are the documented residue).
