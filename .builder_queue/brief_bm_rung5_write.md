# BRIEF: BM-501..503 — Bare-Metal Rung 5 (the payload does real work: read a second image + write leg)

## Title
Bare-Metal Pixel Boot Ladder, Rung 5 — a pixel-booted program that reads
AND writes its own medium. Full roadmap:
`tools/bare_metal_poc/ROADMAP.md` (source of record for the ladder).

## Authority
Queued by host session 2026-09-18 under Jericho's in-channel ask
(2026-09-17): "lets make a roadmap for this" then "lets get the builder to
process this roadmap", plus "you lead" (2026-09-18, in-channel) for
unnamed follow-ups after the BM-401 verification report. The ladder
ROADMAP.md's own cadence rule — "rows beyond the active rung are
FILED-ONLY ... do not promote or activate without re-reading the previous
rung's receipt" — is satisfied: rung-4's receipt
(`tools/bare_metal_poc/rung4/RECEIPT_RUNG4.md`) was re-read at activation;
its honest boundaries (n=2 timings, absence probe is a layout property,
stage1 trusted-by-construction, nothing >256 KB run) gate this rung's
claims. This row activates the already-filed TASK_BM501..503; no new
design beyond what the filed rows specify.

## Spec pointers
- `tools/bare_metal_poc/ROADMAP.md` — Rung 5 section (tasks BM501-BM503,
  success criteria, explicit NOT-in-scope list). Tasks may be renumbered
  BM-501..BM-503 in receipts; the three deliverables are fixed.
- `tools/bare_metal_poc/rung4/` — the committed base: `stage1.asm`
  (bank-outer scatter, CRC32 gate v2), `stage2.asm`, `rung4_codec.py`,
  `rung4_pad.py`, `rung4_consts.py`, `run_gate4.sh`, `bm403_once.sh`.
  Rung 5 extends this pattern by COPY into `rung5/`; never edit rung4 in
  place.
- `tools/bare_metal_poc/rung4/RECEIPT_RUNG4.md` — baselines to beat and
  honest boundaries (read FIRST per the cadence rule).
- `tools/bare_metal_poc/rung3/ANCHORS.md` — machine anchors; ≤~500 KB
  conventional budget still binds whatever rung 5's stage2 grows to.
- `tools/bare_metal_poc/RECEIPT.md` — rung-1 COW-journal findings (the
  write leg is the guest-side sequel to that story).

## WHERE YOU ARE
Main checkout `/home/jericho/projects/zion/projects/visual_audio`, branch
`glyph-transpiler-autoloop`. Rung 4 is COMMITTED (a5596c88) and
independently re-verified by Jericho (2026-09-18: GATE PASS, values match
the commit exactly, corrected RED-A ordering confirmed). The rest of
`tools/bare_metal_poc/` remains uncommitted — landing it is TASK_BM001,
explicitly HOLD for Jericho's verbatim ratification. This row's work
lands in `rung5/` and commits the rung-5 subtree only.

## MEASURED STATE (do not re-derive; verify only what you touch)
- Rung-4 gate: GATE PASS ×2 consecutive. green64k
  `GATE4=PASS CRC=E1AE9612 STAGE2 SIZE=64 KB STAGE2 CKSUM=77B5 EXEC`;
  green256k `CRC=758F5EC8 ... CKSUM=ECB8 EXEC`; RED-A pixel corruption →
  `GATE4=FAIL CRC=5A5F772A EXP=E1AE9612` (host arithmetic agrees);
  RED-B 0 serial bytes; absence probe 0/65,521 contiguous payload
  windows; RE-GREEN byte-identical.
- Timings (the baseline rung 5 records against): boot-to-receipt ≤117 ms
  (64 KB), ≤115 ms (256 KB), TCG, n=2 per scale, 50 ms poll bound.
  Decode is free; SeaBIOS+int13h streaming dominates.
- Addressing shipped: pure real mode, bank-outer scatter
  (ES = DST_SEG + b*0x1000 per 64 KB bank; DI strides 4 within a bank,
  never wraps; walks banked with ES stepping). Unreal mode NOT needed.
  PAYLOAD_BANKS is 16-bit-safe to 16 banks (1 MB) by construction;
  nothing above 256 KB has been run.
- QEMU 8.2.2 + nasm + python3 (PIL 10.2.0, numpy 1.26.4) on host.

## Operational traps (each paid for once — cost noted)
1. **16-bit loop counters cap at 65536** — any single `loop` walking
   ≥128 KB is wrong by construction (rung-4 BUG-C). Bank every walk.
2. **DI/SI wrap silently at 64 KB** — 16-bit index registers fold
   higher addresses into segment 0 (rung-4 BUG-C). Step ES per bank;
   DI stays within-bank.
3. **Gate trap: late-leg failure leaves stale scale artifacts** — a leg
   [7] failure skips the restore, leaving `stage2.bin`/consts at the
   wrong scale; later probes then measure garbage (rung-4 21:25 tick).
   Rebuild before diagnose; add an always-rebuild guard to run_gate5.sh.
4. **Refusal prints must label computed vs expected** — swapped halves
   made correct refusals look like gate misses (DEFECT-R4PRINT, fixed in
   rung4/stage1.asm `r4_crc_fail`). Copy the corrected print order.
5. **E820 SMAP magic is `0x534D4150`** — byte-reversed → SeaBIOS
   silently rejects every call (rung 3, one full debug cycle).
6. **nasm**: `%%` local labels only inside `%macro`; bottom-of-file data
   labels attach to the last NON-LOCAL label (rung-1 `msg1` convention).
7. **RED legs must SPECIFY the failure** — assert computed-vs-expected
   values, never "it failed somehow" (rung-1 RED-A nop-for-nop).
8. **`qemu-io -P` takes DECIMAL patterns** (`-P 90` writes 0x5A).
9. **SeaBIOS IDE requires a writable disk** — keep the writable-raw +
   frozen-PNG archive pattern (`bake` re-derives raw from PNG).
10. **The write leg must not overwrite stage1/stage2's own sectors** —
    pick the write region disjoint from the boot stages and ASSERT the
    disjointness in the gate; a self-bricking write is the classic
    second-boot failure.
11. Context economy: run gates as `bash rung5/run_gate5.sh 2>&1 | tail -30`.
    The medium is 64 MB+ raw — never cat/hexdump it wholesale.
12. **Gate scripts EXCEED the 420s tool timeout** (rung-4 gates ran
    17–20 min; the 2026-09-18 03:30 run wedged for 3+ hours retrying a
    foreground gate call that could never finish). Run
    `bash rung5/run_gate5.sh` with the terminal tool in BACKGROUND mode
    (background=true, notify_on_complete=true), then poll the output
    file; NEVER run the gate as a foreground tool call. Same for
    `bm403_once.sh`-style boot+poll loops.

## Scope
POSITIVE (exclusive write set):
- `tools/bare_metal_poc/rung5/` (new directory — everything in it,
  including its own `.gitignore` for `*.raw`, `*.bin`, `*.log`,
  `*.meta.json`, `dbg_*`, `serial_*`, copied from rung4's)
- `tools/bare_metal_poc/ROADMAP.md` (status-cell updates only)
- `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (BM-501 row state cell only)
- `.builder_queue/brief_bm_rung5_write.md` (this brief; corrections only)
NEGATIVE (must-not-touch):
- `voicebook/`, `.rts/`, `rs_fixtures.json` (AGENTS.md protected assets)
- `tools/bare_metal_poc/rung1/`, `rung2/`, `rung3/`, `rung4/` (reference
  only — extend by copy into rung5/, never edit in place)
- The rest of the untracked bare_metal_poc tree (TASK_BM001 is HOLD)
- Any other roadmap row, ledger addendum, or maildrop state

## Tasks
1. **BM-501** Multi-image medium: `rung5/stage2.asm` reads a SECOND
   pixel-encoded image (data) beyond its own planes via int 13h and
   reports its checksum on serial; the checksum matches the build-time
   host value. RED leg: corrupt one pixel of the second image →
   specified refusal naming the CRC delta, host arithmetic agreeing.
2. **BM-502** Write leg: `rung5/stage2.asm` writes a marker block via
   int 13h AH=43h to a region gate-asserted disjoint from the boot
   stages. Persistence-across-reboot leg: boot 1 writes → reboot WITHOUT
   re-encode (same raw) → boot 2 reads back byte-identical. RED-style
   leg: corrupt the written marker post-write → boot 2 reports the
   specified mismatch (not silence).
3. **BM-503** (stretch, only if 501+502 are green cheaply) exec-from-data:
   stage2 decodes a second EXECUTABLE image and transfers control; the
   receipt must record the isolation situation (none) honestly. Skipping
   this task is an acceptable outcome if 501+502 consume the budget —
   record the skip and why in the receipt.

## Gates (RED-first)
- Every RED leg starts RED by construction: verify the refusal fires
  before the fix exists, naming computed vs expected.
- Non-vacuity: neutering the second-image checksum check must flip the
  gate RED (spot-verify once, restore).
- GREEN ×2 consecutive from clean (including the persistence leg both
  times) before any commit; serial excerpts in the commit body.
- Run from `tools/bare_metal_poc/`: `bash rung5/run_gate5.sh` → GATE PASS.

## DONE WHEN
- `rung5/run_gate5.sh` → GATE PASS ×2 consecutive, persistence leg
  included (pasted in commit body).
- `rung5/RECEIPT_RUNG5.md` carries: second-image checksum evidence with
  host cross-check, write-leg persistence evidence (the two-boot trace),
  disjointness assertion, timings vs the rung-4 baseline table, honest
  boundaries (what was NOT verified — e.g. nothing above 256 KB, TCG
  only), BM-503 disposition (done or skipped-with-reason).
- BM-501 row state cell updated with commit hash; ladder ROADMAP.md
  Rung 5 marked with measured numbers; commit lands on
  `glyph-transpiler-autoloop`.

## STOP-and-file-defect hatch
If BIOS write behavior under QEMU/SeaBIOS forks beyond "extend rung 4's
pattern" (CHS-vs-LBA geometry traps, write caching surprises, or any
design fork beyond the filed rows), STOP: write the RED evidence to
`.builder_queue/REPAIR_PENDING_bm501_writeleg.md`, leave the row ⏳ with
a defect note, and report. Do not invent a workaround inside this row.
