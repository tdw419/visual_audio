# RECEIPT — Rung 5: the payload does real work (read a second image + write leg)

**Row:** BM-501/502/503, bare-metal ladder Rung 5
(`tools/bare_metal_poc/ROADMAP.md`); roadmap row
`systems/GLYPH_SELF_HOSTING_ROADMAP.md` line 329.
**Brief:** `.builder_queue/brief_bm_rung5_write.md`
**Date:** 2026-09-18, builder cron af3e62239ce2
**Base:** rung 4 committed (a5596c88), receipt re-read at activation per
the cadence rule. Branch `glyph-transpiler-autoloop`.

## What shipped

`rung5/` (extend-by-copy from rung4, per scope; rung4 untouched):

- `stage2.asm` — rung-4 stage2 extended with three legs:
  1. **BM-501 read leg**: after the stage2 gate passes, stage2 reads a
     SECOND pixel-encoded image (`img2`, 2048 B at LBA 129,
     IMG2_SEG=0x4000) via int 13h, de-interleaves it the same way, and
     checks a build-time CRC32 (`EXPECTED_IMG2_CRC` in the `-D` set from
     `rung5_consts.py`, the code-side twin pattern). Serial:
     `IMG2 SUM=<sum16>` then `IMG2 CRC=<computed>` / `IMG2 FAIL CRC=<computed>
     EXP=<expected>`; execution continues only on match.
  2. **BM-502 write leg**: writes a 2048 B marker (stage2's own payload
     bytes with two runtime vars patched) via int 13h **AH=43h** (EDD
     write) to WR_LBA=133, 4 sectors — a region gate-asserted disjoint
     from stage1 (LBA 0), stage2 ([1,128)) and img2 ([129,133)) both in
     the layout constants and in `rung5_meta.json` at build time
     (`DISJOINT=OK` leg). Serial: `WRITE=OK`.
  3. **Persistence read-back**: stage2 then re-reads WR_LBA and compares
     byte-exact — and the gate re-boots WITHOUT re-encoding the medium
     and boot 2 confirms `persistence: marker still byte-identical after
     boot 2`.
- `rung5_codec.py` — rung4 codec extended for the 3-region medium
  (stage1 / stage2 / img2) + host decode/roundtrip legs.
- `rung5_layout.py` / `rung5_layout.inc`, `rung5_consts.py`,
  `make_img2.py`, `rung4_pad.py`/`rung4_consts.py` (copied), and
  `run_gate5.sh` — the gate.

## Gate: `bash rung5/run_gate5.sh` → GATE PASS ×2 consecutive

Runs `gate5_run14.log` + `gate5_run15.log` (this tick, from clean each
time), byte-identical leg outputs:

```
greenA/greenB/greenC: PXC1-RUNG5 GATE4=PASS CRC=329CD470
                      IMG2 SUM=E956 IMG2 CRC=7880D4BA WRITE=OK
                      STAGE2 SIZE=64 KB STAGE2 CKSUM=43E6 EXEC
redA    : IMG2 SUM=E9C7 IMG2 FAIL CRC=B3AEA74F EXP=7880D4BA
nonvac  : neutered check PASSES corrupted img2 (check is load-bearing)
regreen : boot serial identical to boot 1
```

- **RED-A (specified refusal)**: one XOR-0xFF payload pixel of img2 at
  medium offset 66052 → `IMG2 FAIL CRC=B3AEA74F EXP=7880D4BA`; host
  arithmetic cross-check agrees exactly (the refusal prints computed vs
  expected in the corrected DEFECT-R4PRINT order), and the guest halts
  before the write leg (`WRITE=` absent — asserted in the gate).
- **Non-vacuity**: stage2 rebuilt with `EXPECTED_IMG2_CRC` = the
  CORRUPTED image's CRC, corrupted medium re-encoded → boot PASSES img2
  (`IMG2 CRC=B3AEA74F`) and reaches `WRITE=OK` — the check is
  load-bearing, not decoration.
- **Disjointness**: layout asserts `stage2_lbas=[1,128)
  img2_lbas=[129,133) write_lbas=[133,137) DISJOINT=OK` at build; host
  verifies the written marker (`host verify: 2048 marker bytes at medium
  offset 68096`); the medium is NOT re-encoded between the persistence
  boots, so a self-bricking write would have failed boot 2's own
  stage2 CRC gate.
- **RE-GREEN**: medium rebaked from the untouched PNG → boot serial
  byte-identical to boot 1.

## Timings vs rung-4 baseline

| | rung 4 (baseline) | rung 5 (this receipt) |
|---|---|---|
| boot-to-receipt, 64 KB-class flow | ≤117 ms | **≤101 ms** (n=2, both 101 ms, 50 ms poll bound, TCG) |
| payload scale | 64 KB / 256 KB | 64 KB stage2 + 2 KB img2 |
| decode | free vs int13h | unchanged (same mechanism + 2 KB img2) |

n=2 per the rung-4 discipline; upper bounds (50 ms poll granularity).
Probe: `dbg_timing5.py` (gitignored `dbg_*`, numbers recorded here).

## Fix history (RED before GREEN, this tick)

The gate had two real defects, both found by running it (run12/run13
logs kept as the RED tails; `*.log` is gitignored, values quoted here):

1. **encode arg swap in the non-vacuity leg** (run12 RED:
   `GATE5 FAIL: qemu-io nv`): the nv leg's `rung5_codec.py encode` call
   passed `rung5_nv.png.json` in the RAW slot and `rung5_nv.raw` in the
   META slot — the "medium" was 541 bytes of JSON. Fixed the arg order
   (+ cleanup of the stray `.png.json`).
2. **stage1 consts not rebuilt for the nv stage2** (run13 RED:
   `GATE4=FAIL CRC=2DA13125 EXP=329CD470`): stage2_nv embeds the
   neutered CRC constant, so its bytes differ from pristine stage2 —
   stage1's own CRC gate (consts still generated from pristine
   `stage2.bin`) killed the nv boot before the img2 check could speak.
   Fixed by regenerating `stage1_const.inc` from `stage2_nv_padded.bin`
   (and restoring pristine consts right after).

Both are gate-script fixes; `stage2.asm`'s semantics were not touched
during fixing (the guest-side code was already correct — run12's legs
[1]-[4] were green).

## BM-503 disposition: SKIPPED (with reason)

exec-from-data is not attempted. BM-501+BM-502 consumed the tick's
budget (two gate-defect fix cycles + ×2 clean gate runs + timing n=2),
and the task's own framing (isolation: NONE — a decoded executable runs
with full real-mode privilege, no gate can contain it) wants a design
pass about what a *meaningful* exec receipt even is before code lands.
Recorded per the brief's skippable-with-reason clause. The ladder
ROADMAP.md carries the same note.

## Honest boundaries — what this does NOT prove

- **TCG only.** No KVM/hardware run; same boundary as rung 4.
- **Nothing above 64 KB stage2 was run this rung** (the 256 KB scale
  remains rung-4-only evidence; img2 is 2 KB — the read leg is
  exercised at one small scale only).
- **Boot-to-receipt 101 ms is an upper bound** (50 ms poll; includes
  SeaBIOS+int13h; the write leg serial `WRITE=OK` lands between the
  img2 CRC and the final CKSUM line, so the receipt timestamp covers
  the full flow).
- **Write path is AH=43h EDD write to a raw QEMU IDE disk only** — no
  CHS fallback, no real hardware, no write-caching assertion beyond
  the two-boot persistence evidence QEMU gives.
- **The marker is stage2's own bytes, not arbitrary data** — a
  payload-independent write was not tested.
- **The persistence read-back compares stage2's read vs the host copy**
  — it is not a cryptographic integrity claim about the written region
  (no ECC; that is rung 6).
- **RED-B class (55AA → zero exec) not re-run** — rung-4's stage1 gate
  (CRC over stage2 before any decode of img2/write) already covers the
  "no exec on bad medium" claim and is unchanged; run5 gate re-verifies
  the CRC value itself each run.
- **Absence probe not re-run for img2** (rung-4's probe covers the
  stage2 scatter layout; img2 sits past it, contiguity not probed).
- Gate artifacts (`*.raw/*.bin/*.log/*.json/*.inc`, `dbg_*`) are
  regenerable and gitignored; only source + receipts are committed.
