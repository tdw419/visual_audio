# ROADMAP: Bare-Metal Pixel Boot Ladder

**Location:** `tools/bare_metal_poc/`
**Thesis:** pixels are the disk — a machine with no OS, no disk file, and no
host-side storage shim can boot and do real work from a medium whose bytes
are a pixel stream.
**Cadence:** one rung at a time; each rung's measured outcome shapes the
next. Rows beyond the active rung are FILED-ONLY and provisional — do not
promote or activate without re-reading the previous rung's receipt (same
discipline as the SE ladder).

---

## Current Status (2026-09-20, post-rung-6 / rung-6.5 / rung-9 / BM802 refresh)

- **Progress:** Rungs 1–5 COMPLETE (4 and 5 landed via a5596c88 / ea3cc949
  with GATE PASS ×2 receipts). **Rung 6.5 CLOSED IN EMULATION (BM651,
  2026-09-20):** after its design pass (edafa7fd) and scoping pass (BM650: GO
  on the rung-5 base, four corrections to the design), `rung6_5/run_bm651_e2e.sh`
  GATE651 PASS ×2 — 2,048 B that arrived as pixels prints its own banner from
  inside its own code, leaves the contract words in memory, and only then gets
  `EXEC=OK`; three broken variants each fail exactly one of the two loader checks;
  one flipped pixel means the image is never entered. Leg 230 B, receipt
  `rung6_5/RECEIPT_BM651.md`. **Its follow-on design pass CLOSED THE SAME DAY
  (BM652):** option C — running BM651's image off the *self-repairing* medium —
  costs **zero medium bytes** (the payload already wastes three whole padding
  groups; anything up to 96 KiB is free) and **one mode** (96 B of a 392 B leg to
  drop out of flat-32 and back), rehearsed host-side to five named replays
  including the corrector-off control that refuses at the gate. GO verdict, six
  corrections, `TASK_BM653` filed. Note `rung6_5/BM652_SCOPING.md`. **That
  implementation row CLOSED THE SAME DAY (BM653):** the image now rides the
  self-repairing medium, 256 of its plane-1 bytes destroyed and restored by the
  executed decoder before the jump, into a handoff byte-identical to the clean
  medium's — while its corrector-off twin refuses at the gate. `run_bm653_e2e.sh`
  2 of 2 passes clean, 46 identity checks ×2, receipt
  `rung6_5/RECEIPT_BM653.md`.
  Rung 7 CLOSED GREEN 16:56 (TC-1 evidence probe: TinyCore boots from a
  pixel medium ×2 byte-identical — `rung7/RECEIPT_TC_PROBE.md`). **Rung 9
  CLOSED IN EMULATION (M4):** `rung9/run_bm903_e2e.sh` 42 pass / 0 red ×2 —
  a pixel medium carries bzImage+initrd to `tc@box` on serial with our own
  executed 16-bit stage2 building Linux's protocol handoff; BM904 (write-side
  pixel diff) and BM905 (input mailbox over the medium) closed on top of it.
  **BM802 MEASURED (Rung 8 hardening):** fault-sensitivity map over the raw
  medium, 363 boots, rc=0 — see its cell for the 42.6% floor and what the
  map cannot see. Its sharpest outcome is not a fatal byte: 17 initrd legs
  booted to completion on a `core.gz` whose own gzip CRC fails, i.e. decay
  here means "a box that boots something else", not "a box that will not
  boot". **Rung 6 BUILT AND MEASURED (BM602):** the same payload on a
  self-repairing medium — PXC2-E, 7 planes, +75% capacity, Hamming(7,4) over
  byte symbols executed in 16-bit, loader forked from rung9 by 23 named,
  round-tripped deltas. `rung6/run_bm602_e2e.sh` GREEN 15 / RED 0 ×2: a
  destroyed 4 KiB chunk and a lost 128 KiB erase block both reach `tc@box`
  with the counters the host replay had named before the boot, and the
  repaired boot is byte-identical to the clean one — transcript apart from
  its one counter field, and handoff dumps strictly. Receipt
  `rung6/RECEIPT_BM602.md`.
- **What is left on this ladder is Jericho's, not the lane's:** BM801 needs a
  physical x86 box designated; BM001 (landing the tree) needs his ratification
  and a per-blob decision on the 37 MB of third-party media. Rung 7B stays
  unprioritized — its own trigger ("pursue only if raw-RGB medium size becomes
  the binding constraint") never arrived. **What remains executable is
  BM653** — the option C *implementation* row that BM652 designed
  (`rung6_5/BM652_SCOPING.md`): 7 boots ×2 over the PXC2-E medium, ~68 s per
  pass, all five files named and every cost measured. BM652 itself was a design
  pass and is now **CLOSED 2026-09-20**. Booking BM653 is the lane's to do;
  running it is a boot row, so it inherits the substrate etiquette. Every other
  closed rung is closed: nothing left here can be finished by scoping — the
  remaining rows need either hardware or his word.
- **Critical path (revised 2026-09-18):** Rung 7 (shim-allowed scale probe)
  → **Rung 9 (kernel handoff, NEW)** → Rung 8 (silicon). Rung 6 (ECC) and
  Rung 6.5 (exec-from-data) were the two parallel rows; **both closed
  2026-09-20**.
- **Key metrics:** decode is free at every scale measured — 144 B: 0.082 s
  boot-to-receipt; 64/256 KB: ≤117/≤115 ms; 18 MiB ISO served through
  nbdkit+PNG plugin with SeaBIOS reporting exact geometry
  (PCHS=36/16/63, s=36864 = 18,874,368 B). Capacity math: 4096² RGBA
  medium carries ~64 MiB payload at 1 B/medium-byte — a bzImage+initramfs
  (10–30 MiB) FITS. Scale is a format question, not a geometry question.
- **Format-split decision (2026-09-18, Jericho-endorsed):** boot media are
  raw channel-planed byte streams (firmware reads sectors, not PNGs);
  PNG structure is the ARCHIVE/recovery format (PXC1, provenance, diffing,
  and the source a corrupted boot medium is rebuilt from — proven when the
  rung-2 nested audit restored a corrupted byte from PNG pixels). Not a
  compromise; the two artifacts were never the same requirement.
- **Commit state (measured 2026-09-18):** rungs 4–5 cores LANDED. Still
  unlanded under TASK_BM001: rung-1 core (boot.asm, codec, nbd plugin,
  gate, receipt), rung-2 core (stage1/stage2 asm, codec, receipt, consts),
  rung-3 entirely. Hygiene flag: `rung4/rung4_medium.png` is TRACKED and
  currently dirty — mediums should be gitignored per the original BM001
  plan (gates re-derive them); fold into BM001 execution.
  **Re-measured 2026-09-20, and the flag understated the problem.** The dirty
  bytes are not lost work: HEAD's PNG reproduces *exactly* (`a840b7ee…`) from
  HEAD's own tracked `stage1.asm`/`stage2.asm`/codec/pad/consts at the 256 KB
  scale, built in the gate's order — and so does the working tree's, at 64 KB
  (`3c8ec00c…`). The file is dirty because `run_gate4.sh` ends with
  `run_scale $SCALE_DEFAULT 64k` under the comment "restore the 64 KB build as
  the standing artifact set", while HEAD tracks the 256 KB build. **Every
  green run of rung 4's gate therefore makes the tree dirty**, deterministically,
  by design. The same class turned up the same night in a record:
  `rung9/bm902_diff_receipt.txt` stamps its own `date:` line, so re-running
  BM902's diff gate moves a tracked file without moving a claim — the copy found
  dirty in the working tree tonight carried a 00:34 UTC stamp and differed from
  HEAD in that stamp alone, and re-running the gate here at 21:58 (host-only,
  0.4 s, source of the 00:34 run not established) reproduced the same result:
  every oracle pin, constructed pin and PASS/FAIL verdict byte-identical, one
  line moved. So "is the tree
  clean?"
  cannot be the test that landing is finished, which is why
  `bm001_landing_plan.sh` now lists this third state (tracked, present, differing
  from HEAD) beside the other two instead of leaving it to be inferred. One
  caveat while reading that listing: ordinary edits in flight appear in it too —
  the class is the point, not any single line.
- **Nested-guest corroboration:** the full rung-2 gate was re-executed
  INSIDE the pixel-booted VM (nested KVM) — GATE=PASS CKSUM=4541, RED-A
  FAIL SUM=4640, RED-B 0 serial bytes, absence 0/129, re-green
  byte-identical (`rung2/RECEIPT_RUNG2_NESTED_GUEST_AUDIT.md`,
  commit 0156493c). Environment-independence of the boot chain: evidenced.

## Phase 0: Completed Rungs ✅

### Rung 1 — Pixels boot a CPU (host-side decode) ✅ COMPLETE
512-byte MBR exists only as RGBA pixels in a PNG; a standalone decoder
(nbdkit plugin) serves bytes over NBD; SeaBIOS loads and a real CPU
executes them. Guest checksum 0x5F3B independently reproduced host-side.
- Receipt: `RECEIPT.md`. Gate: `./run_gate.sh` → GATE PASS (8 legs:
  roundtrip, GREEN, guest-vs-host cksum, RED-A corrupt-byte specified
  cksum change, checksum arithmetic, RED-B 55AA → zero exec, PNG
  immutability under journal writes, RE-GREEN after restart).
- Standing findings: SeaBIOS IDE requires a writable disk (COW journal
  pattern, base PNG frozen); "corrupt → fail" needs the failure
  *specified* (RED-A still EXECs — nop-for-nop).

### Rung 2 — Loader-side pixel decode (no NBD shim) ✅ COMPLETE
The MBR itself reads the raw-RGBA medium via int 13h, de-interleaves four
channel planes byte-by-byte, enforces a build-time sum16 gate, and jumps
into the decoded stage2 only on GATE=PASS. No host process under the
machine; the IDE disk's bytes ARE the pixel stream.
- Receipt: `rung2/RECEIPT_RUNG2.md`. Gate: `./rung2/run_gate2.sh` →
  GATE PASS ×2 consecutive (CKSUM=4541; RED-A pixel corruption →
  specified `GATE=FAIL SUM=4640`, host arithmetic agrees; RED-B zero
  exec; absence probe: 0/129 payload windows contiguous on the medium;
  RE-GREEN byte-identical).
- Standing findings: build-time consts (`stage1_const.inc`) = code-side
  twin of the codec's tEXt dual-sha256 gates; decode latency immaterial.

### Rung 3 — Machine anchors (memprobe) ✅ COMPLETE
`rung3/memprobe.asm` measured what a real-mode pre-boot stub can see
(QEMU 8.2.2 SeaBIOS defaults): 128 MiB RAM via int 15h E801; E820 works
from real mode (7 entries); real mode can *see* that memory but address
only 1 MB.
- Receipt: `rung3/ANCHORS.md`. Decision encoded: **Path A next** —
  raw-RGB, pure real mode, decoded payload ≤ ~500 KB, streaming
  per-byte scatter decode, zero new primitives. Path B (PNG-native
  inflate) deferred to iPXE/OVMF (Rung 7).
- Gotcha bank (do not re-pay): E820 SMAP magic is `0x534D4150`
  (byte-reversed → SeaBIOS silently rejects every call); nasm non-local
  data labels at bottom of file (rung-1 `msg1` convention).

---

## Rung 4 — Scale: ≥64 KB payload, loader-side decode (Path A) ✅ COMPLETE (2026-09-18)

**Goal:** prove the rung-2 mechanism at a payload size that can carry a
real program, not a receipt. ANCHORS.md budget: ≤ ~500 KB conventional.

- [x] **TASK_BM401**: Streaming multi-sector reader + scatter de-interleave
  - Priority: CRITICAL
  - Dependencies: none (rung 2 stage1 is the base)
  - Receipt: stage2 of ≥64 KB is read from the raw medium in chunks
    through a segment window (EDD AH=42h loop; unreal mode only if
    windowing proves insufficient — record which shipped), de-interleaved
    streaming, and executes to a serial receipt naming the payload size.
  - Test: `./rung4/run_gate4.sh` GREEN leg (this row authorizes creating it)
  - Status: ✅ DONE 2026-09-18 — bank-outer scatter (ES = DST_SEG +
    b*0x1000 per 64 KB destination bank; DI strides 4 within a bank,
    never wraps). Pure real mode; unreal mode NOT needed (windowing
    sufficed at both 64 KB and 256 KB).
- [x] **TASK_BM402**: Integrity gate v2 — CRC32 over the payload
  - Priority: HIGH
  - Dependencies: TASK_BM401
  - Receipt: build-time CRC32 (in `*_const.inc`, code-side twin pattern)
    checked by the loader before control transfer; sum16 retires. RED leg:
    one specified pixel corruption → refusal printing computed vs
    expected CRC (host arithmetic cross-check, rung-2 RED-A pattern).
  - Test: `./rung4/run_gate4.sh` RED-A leg
  - Status: ✅ DONE 2026-09-18 — zlib CRC32 in stage1_const.inc checked
    before control transfer; RED-A pixel corruption → `GATE4=FAIL
    CRC=5A5F772A EXP=E1AE9612`, host arithmetic agreeing exactly
    (DEFECT-R4PRINT print-order fix measured and fixed this run).
- [x] **TASK_BM403**: Decode performance at scale
  - Priority: MEDIUM
  - Dependencies: TASK_BM401
  - Receipt: boot-to-receipt wall time measured for 64 KB and 256 KB
    payloads; effective decode rate (KB/s) recorded in
    `rung4/RECEIPT_RUNG4.md`. No target yet — this rung *sets* the
    baseline the next rungs optimize against (measure, don't assume).
  - Test: receipt table in `rung4/RECEIPT_RUNG4.md`
  - Status: ✅ DONE 2026-09-18 — boot-to-receipt ≤117 ms (64 KB) / ≤115 ms
    (256 KB), TCG, n=2 per scale, 50 ms poll granularity (upper bounds);
    decode cost lost in the noise vs SeaBIOS+int13h streaming. Baseline
    table in rung4/RECEIPT_RUNG4.md.
- [x] **TASK_BM404**: `run_gate4.sh` — full leg set at scale
  - Priority: CRITICAL
  - Dependencies: TASK_BM401, TASK_BM402
  - Receipt: build+encode, host roundtrips (bake/decode byte-identical),
    GREEN, RED-A (specified CRC refusal), RED-B (55AA → zero exec),
    scaled absence probe (payload windows not contiguous on medium),
    RE-GREEN byte-identical — all PASS, run twice consecutively.
  - Test: `cd rung4 && ./run_gate4.sh` → GATE PASS ×2
  - Status: ✅ DONE 2026-09-18 — GATE PASS ×2 consecutive; RED-B 0 serial
    bytes; absence probe 0/65,521 contiguous payload windows (55 hits =
    stage1's own shared helper code); RE-GREEN byte-identical; 256 KB
    scale sweep GREEN.

**Success criteria:** 64 KB payload boots and executes from pure pixels
with loader-side decode; corruption refusal specified and host-verified;
×2 consecutive GATE PASS; numbers in the receipt.

---

## Rung 5 — The payload does real work ✅ COMPLETE (2026-09-18; BM-503 skipped-with-reason)

**Goal:** ANCHORS.md's "big enough to matter" target — a pixel-booted
program that reads and writes its own medium.

- [x] **TASK_BM501**: Multi-image medium — stage2 reads a second
  pixel-encoded image (data or code) beyond its own planes and reports
  its checksum. Proves the pixel disk holds more than the bootloader.
  - Status: ✅ DONE 2026-09-18 — img2 (2 KB, LBA 129) read via int 13h,
    de-interleaved, build-time CRC32 gate (`IMG2 CRC=7880D4BA` serial
    receipt, computed-vs-expected print order per DEFECT-R4PRINT);
    RED-A one-pixel corruption → `IMG2 FAIL CRC=B3AEA74F EXP=7880D4BA`
    with host arithmetic agreeing; non-vacuity: neutering the check
    (rebuild with the corrupted CRC baked in) → corrupted medium PASSES
    img2 and reaches WRITE=OK, proving the check load-bearing.
- [x] **TASK_BM502**: Write leg — stage2 writes sectors (int 13h AH=43h);
  persistence-across-reboot leg: boot 1 writes, reboot WITHOUT re-encode,
  boot 2 reads back byte-identical. Pixel-domain persistent storage,
  in-machine (the rung-1 COW-journal story, now from the guest side).
  - Status: ✅ DONE 2026-09-18 — 2 KB marker written to WR_LBA=133
    (4 sectors), region DISJOINT=OK-asserted from stage1/stage2/img2 at
    build (layout + meta legs); host verifies the marker bytes at
    offset 68096; persistence leg: `persistence: marker still
    byte-identical after boot 2` on a NOT-re-encoded medium (a
    self-bricking write would have failed boot 2's own stage2 gate).
- [x] **TASK_BM503** (stretch): exec-from-data — stage2 decodes a second
  *executable* image and transfers control. BIOS-level analog of SE021
  glyph-on-glyph exec; receipt must record isolation (none) honestly.
  - Status: ⏸️ SKIPPED-WITH-REASON 2026-09-18 — budget consumed by
    BM-501/502 + two gate-defect fix cycles; the task wants a design
    pass on what a meaningful exec receipt is (isolation: NONE) before
    code lands. Carried in RECEIPT_RUNG5.md.
  - → ✅ **CLOSED BY RUNG 6.5 (BM651) 2026-09-20**, not here: design pass
    edafa7fd, scoping BM650, gated row `rung6_5/run_bm651_e2e.sh` PASS ×2. The
    "meaningful receipt" question it deferred got its answer — the executed image
    identifies itself by a value derived from its own CRC and the loader checks
    the check (three broken variants, one refusal each), and **isolation: none**
    is recorded in `rung6_5/RECEIPT_BM651.md` §Honest boundaries exactly as this
    row asked.

**Gate:** `cd rung5 && bash run_gate5.sh` → GATE PASS ×2 consecutive
(gate5_run14/run15, byte-identical): greenA/B/C
`GATE4=PASS CRC=329CD470 IMG2 CRC=7880D4BA WRITE=OK EXEC`, redA
specified refusal, nonvac flip, regreen byte-identical. Boot-to-receipt
≤101 ms (n=2, 50 ms poll, TCG) vs rung-4's ≤117 ms baseline.
Receipt: `rung5/RECEIPT_RUNG5.md` (honest boundaries: TCG only, one
scale, marker = stage2's own bytes, no ECC, RED-B/absence not re-run).

**Explicitly NOT in scope for this rung** (file nothing until Rung 5's
outcome is measured): filesystem layer on the pixel medium; multi-boot
chainloading; Path B compression.

---

## Rung 6.5 — Exec-from-data ✅ CLOSED IN EMULATION (BM651 + BM653, 2026-09-20)

**Design landed 2026-09-18 (edafa7fd, BM-503D):** WORTH ITS OWN RUNG.
Three-part receipt design: banner NID derived from the payload CRC,
mailbox word 0x4B4F, stage2-printed EXEC=OK anchor — the isolation story
is "decoded code must identify itself by a value the decoder never
stored" instead of a claim. Implementation is its own gated row; scoping
pass (sizes, budget) required before code, same as Rung 6.

- [x] **BM650 (scoping pass)** → ✅ **DONE 2026-09-20, verdict GO** —
  `rung6_5/BM650_SCOPING.md`, probe `rung6_5/bm650_scope.py` (assembles the
  leg rather than estimating it; writes nothing outside `scope/`, boots
  nothing). Sizes: the whole leg is **279 B** (199 B code + 80 B text) against
  **64,740 B free** in rung5's 65,536 B stage2 image — 0.43%, so the design's
  byte-budget question does not exist at this base. Method cross-checks: this
  run reproduces BM601's landed **4,848 B free** in the PXC1 image exactly, and
  costs BM602's ECC fork at 432 B of it. Green path adds 35 B of transcript =
  3.0 ms at the 115200 baud rung5 programs, against a ≤101 ms
  boot-to-receipt history. Four corrections to the design, all from reading the
  landed file rather than the table: **R-SCOPE-1** the leg goes *after* the
  self receipt (a halt must not take rung-5's anchors down with it, or the
  TIMEOUT leg is indistinguishable from a rung-5 regression); **R-SCOPE-2** the
  bytes below 2048 are the write bounce buffer, so "after `.wr_ok`" is a
  constraint with a reason, not a coincidence; **R-SCOPE-3** the entry table
  claims IF=0 while `stage2.asm:42` leaves `sti` in force — one byte buys the
  table's claim; **R-SCOPE-4** `EXEC` is already rung-5's terminal token
  (`msg3`), so every new grep must be anchored or it matches the old line.
  **Base = option A (rung5's chain, delta-forked), because it is the only base
  with a decoded real-mode image to jump into.** Option B (the same leg on the
  PXC1/PXC2-E media) is rejected as a smaller copy of Rung 9; **option C is
  FILED** — put a real-mode image on the *ECC* medium so the claim becomes
  "the pixels were wrong, the loader repaired them, and the repaired pixels
  ran", which needs a design pass first because it forks the locked
  `bm903_pxcodec.build_payload`.
- [x] **TASK_BM651** (implementation row, filed by BM650): fork rung5 by named,
  round-tripped deltas into `rung6_5/`; land the 279 B leg with the four
  corrections; four img2 variants (green / no-banner / no-mailbox / halt) each
  assembled and padded to exactly 2,048 B; consts emit `EXPECTED_EXEC_NID`
  beside `EXPECTED_IMG2_CRC`; 7 boots (green ×2 + 5 RED/control legs), no
  anchor budget because no guest waits.
  → ✅ **CLOSED GREEN ×2 2026-09-20** — `rung6_5/run_bm651_e2e.sh` GATE651 PASS
  ×2 (143 s, 7 boots, 18 predictions fixed before the first boot), receipt
  `rung6_5/RECEIPT_BM651.md`. Fork: 5 stage2 + 4 consts deltas, each asserted
  once, undone newest-first to `byte-for-byte`. **The leg is 230 B** (796 → 1,026
  B against a matched baseline = rung5's own `stage2.asm` at the identical define
  set minus this rung's one define) — BM650's 279 B was a 49 B over-estimate
  because the shipped handover is a 5 B far `call`, not push/push/jmp. Executed
  image: 2,048 B, `crc32=101BFE00`, `nid=EE1B`; wire shows
  `IMG2EXEC BANNER NID=EE1B` → `EXEC=OK`, and the banner string exists **only** in
  the image (`evidence/banner_provenance.txt`: 1× in img2, 0× in the 65,536 B
  padded payload and the 512 B stage1), so the line cannot have come from the
  loader. Non-vacuity by construction: three broken variants each fail **exactly
  one** of the two checks and pass the other (`EXEC=NO-BANNER 0000 EXP=FC2B` /
  `EXEC=BAD-MAILBOX 0000 EXP=4B4F`); the hang variant's banner is the last line
  the loader ever emits. The safety half: one flipped pixel in the image's window
  gives `IMG2 FAIL CRC=0229EB69 EXP=101BFE00` with **no banner, no write, no
  verdict** — an unverified image is never in reach of the instruction pointer —
  and re-greening from the untouched PNG boots identical. Rebooting the same
  medium without re-encoding leaves the image's bytes and the written marker
  byte-identical (hashes in `evidence/`). Two findings worth the ladder's books:
  **R-SCOPE-5** the design review's "copy-down overlaps fully, go backward" is
  wrong (dst `[0,2048)` and src `[2048,4096)` are disjoint — forward `rep movsw`
  ships); **R-SCOPE-6** stage1's `push seg/push off/retf` is a far **jump** with
  no return, so borrowing it for the handover made the image's `retf` land inside
  the image's own bytes (measured: two banners plus serial garbage). Not proven,
  and the receipt says so plainly: this is a **liveness** contract, not
  authentication (whoever writes the pixels can write a self-consistent image),
  and a hung image is detectable only from the host.
- [x] **BM652 (option C design pass)** — execute an image off the **PXC2-E**
  medium so the claim becomes "the pixels were wrong, the loader repaired them,
  and the repaired pixels ran". Needs a scoping note before code: it forks the
  locked `rung9/bm903_pxcodec.py` payload builder to add an image region, and
  must say what that costs the ECC geometry (+75% capacity, 7 planes) before any
  row is booked. Filed by BM650; rung 6's loader and rung 6.5's leg both already
  exist, so this is composition, not invention.
  → ✅ **DESIGN PASS DONE 2026-09-20** — note `rung6_5/BM652_SCOPING.md`,
  measured by `rung6_5/bm652_scope.py` (104 lines, `scope652/`; two consecutive
  runs byte-identical once the replay timings are stripped). Nothing booted;
  `rung6/` and `rung9/` imported, not copied.
  **VERDICT: GO — and the medium cost is ZERO, but the row costs a *mode*.**
  PXC1's payload has carried 49,152 B of bank padding since BM903 landed (three
  whole groups read off the pixels, corrected, CRC'd, then dropped at `PX_SINK`
  for want of a destination), so option C *employs capacity the medium already
  wastes* rather than adding any: medium unchanged at 23,863,808 B / 46,609
  sectors / 5,824 reads, free up to **6 groups = 96 KiB**, the 7th at
  +114,688 B / 224 sectors / 28 reads (+0.48 %). The "locked payload builder"
  needs no unlocking — the fork is a 2,048 B post-build patch of one padding
  group plus a 4th sub-image row, expressible as a byte delta against the
  payload BM903 booted (measured: 2,048 of 13,631,488 bytes differ, all inside
  group 829). `EXPECTED_CRC 0x393950AA → 0x2C14707B`, `NID=EE1B` (BM651's own,
  from the landed transcripts). The new cost is that the walk runs flat-32 while
  the image is real-mode: **96 B of the leg's 392 B** is leaving protected mode
  and coming back, trivial in bytes and the entire risk of the row.
  Options: **C1b GO** (walk → correct → gate → real mode → BM651's img2
  unchanged → re-enter → handoff → boot) — the only composition where all three
  rungs' claims survive; **C1a NO** (halt after the image — forfeits the
  byte-identical handoff dumps that prove the image gave the machine back);
  **C2 NO** (a 32-bit image — saves 96 B, throws away BM651's four proven
  variants, which exist to show the refusal checks are not vacuous).
  Host rehearsal on the real geometry with the loader's own replay (`guest_walk`):
  clean `ECC=0` PASS; 256 B plane-1 scratch → `ECC=256`, gate PASS, **image at
  dst byte-identical** (every fourth byte of its first kilobyte was wrong on the
  medium and right in memory); corrector NOPed → `ECC=0 CRC=A315E8EB` REFUSE;
  two-symbol leg G inside the image → `ECC=2` mis-fixed, `CRC=55AFFF65` REFUSE;
  equal-triple blind spot → `ECC=0 PAR=0` — what a clean medium prints —
  `CRC=24A8BF80` REFUSE. Destination `0x50000`: 0 collisions across the 16
  mapped claims; the GDT's 16-bit code selector (limit `0xFFFF`) puts a real
  ceiling on the mode-exit's landing label, with 24,576 B of headroom. Leg costed
  from nasm's own list file (392 B = exit 43 / exec 155 / re-entry 53 / helpers 79
  / strings 62) against a re-measured **4,416 B free** — baseline code end 3,776 B,
  exactly BM650's number for this file, so the methods agree. Six corrections
  filed (**R-SCOPE-7…12**: contract block to the top of the group; the image may
  have destroyed the machine the re-entry needs — reload GDT, re-assert A20,
  re-aim SS/ESP, restore `eflags=0x46`; a hung image is now a failed Linux boot,
  so the halt leg needs structural anchors not a diff; keep BM602's payload
  assertion in bounded scanned form; the BEE-OFF control is a round-tripping
  named delta — measured size-neutral at 5 bytes, code end unchanged — or it is
  an edit to a gated loader; every `0x393950AA` anchor is a build product, so the
  fork gets its own `.inc` and consts).
- [x] **TASK_BM653 (option C implementation)** — filed by BM652, designed in
  `rung6_5/BM652_SCOPING.md` §"The row this designs": the five designed files
  (`bm653_pxcodec.py` patching img2 into group 829 and emitting the 4-row table
  + new CRC, its constants inline rather than in the bm653_consts.py the design
  named — that module never existed; `bm653_construct.py` named deltas onto
  rung6's `bm602_stage2_px.asm` plus the `BEE-OFF` control; `bm653_img2.py`
  reusing BM651's
  four variants unchanged; `run_bm653_e2e.sh`), which shipped as twelve — see the
  Files table in `rung6_5/RECEIPT_BM653.md`. **7 boots ×2** ≈ 68 s per pass
  from BM602's measured wall times: green, repaired (predicted `ECC=256`),
  BEE-OFF control, two-symbol refusal, blind-spot refusal, halt, and the
  scribbler — an image that prints `EXEC=OK` then trashes `HDR_SCRATCH`, where
  BM602's locked capture proves the handoff differs. Predictions to a fixtures
  file before qemu. Not proven by the design pass, and the note says so: the
  mode-return has never executed (§4 proves the bytes, not the modes), and the
  seconds are BM602's shapes, not this medium's.
  → ✅ **CLOSED GREEN ×2 2026-09-20** — `rung6_5/run_bm653_e2e.sh` **2 of 2
  passes clean, 334 s**, receipt `rung6_5/RECEIPT_BM653.md`, run from a directory
  with every generated artifact deleted. **Both of the design's two unproven
  items are now measured:** the mode-return executes (each boot reaches `tc@box`,
  and the captured handoff's 25 register fields equal BM903's PXC1 and BM602's
  PXC2-E landed dumps — `rip=0x100000 rsi=0x13ab0 rsp=0x1f784 cr0=0x11
  eflags=0x46`), and the seconds were BM602's shapes: 74 s of boots on a clean
  pass against the cell's ≈68 s estimate, 45 s of it the halt leg's own patience.
  Medium: PXC2-E + BM651's 2,048 B image in padding group **829 of 832** →
  `0x50000`, payload length unchanged, and the bounded delta holds — **2,048 of
  13,631,488 bytes differ from rung6's payload, all inside
  `[0xcf4000,0xcf4800)`**. Fork: 7 named deltas round-tripping to
  `rung6/bm602_stage2_px.asm` byte-for-byte, **352 B measured code cost**
  (3,776 → 4,128 B) against BM652's priced 392 B; the `BEE-OFF` control is 5
  bytes and +0 B. Headline leg: **256 consecutive plane-1 bytes of the image
  group stuck at 0xFF** → `ECC=00000100` (the design's predicted 256, written
  `00000100` on the wire), CRC back to the clean `2C14707B`, `EXEC=OK`,
  `tc@box`, and its zero page **byte-identical to the clean medium's** — repaired
  pixels that ran, into a machine state indistinguishable from an undamaged
  boot. The control proves the repair did it: identical medium, corrector NOP'd,
  `CRC=F0050680 EXP=2C14707B` refused at 1.3 s with no banner and no verdict.
  Two refusals moved *into* the executable region: the equal-triple blind spot
  prints the clean medium's own `ECC=0 PAR=0` with 3 image bytes wrong (and its
  pass-1-off and pass-1-on replays are **identical**, so the decoder provably
  did nothing), and the two-symbol leg is the row's sharpest number — 2 bytes
  damaged, **3 wrong after the "fix"**, at `400, 401, 402` where the decoder
  *wrote* 402, printed as `ECC=00000001`. `ECC=` counts what the decoder did;
  only the CRC says whether it was right. And BM602's locked capture sees the
  scribbler: an image that keeps every word of BM651's contract, prints
  `EXEC=OK`, and rewrites the kernel header band — **2 of its 4 poisoned bytes
  land in the handoff** (`0x1f1 1B→EF`, `0x1f4 2A→DE`), predicted byte-by-byte
  before the boot and confirmed against all three reference dumps, with 4,094
  other bytes and all registers identical. Identity: 46 checks green / 0 red per
  pass — every transcript equal to the clean boot's up to its cut with all diffs
  inside four whitelisted fields matching their pre-boot predictions, and every
  tail checked for a hidden verdict. Side-measurement the gate could not make:
  given a full window the poisoned handoff **still boots Tiny Core to `tc@box`** —
  8 alternating boots, 4 green and 4 scribbler, every loader mark at the same
  0.3 s/1.3 s, and the two guest logs line-for-line identical apart from the
  loader's own `CRC=`/`EXP=` and `NID=` fields — so this corruption costs nothing
  observable on this kernel, and the only boot that failed to print a shell was a
  *clean* one that lost Tiny Core's autologin tty1/ttyS0 coin. The scribbler
  therefore proves the **absence of a sandbox**, not the presence of damage.
  `rung6_5/bm653_longwatch.py`, kept as a side-probe and deliberately not part of
  the gate.

## Rung 6 — Corruption-tolerant decode (ECC) ✅ BUILT AND MEASURED IN EMULATION (BM602, 2026-09-20)

**Goal:** flip N specified corrupted pixels and still boot byte-identical;
N+1 → specified refusal. Direct heir to the codec's Reed-Solomon heritage.

- [x] **TASK_BM601**: ECC scoping pass FIRST — can an RS decoder (or
  cheaper erasure scheme over the 4-plane interleave) fit the Rung-4
  stage2 budget in 16-bit asm, and what does the parity do to medium
  layout? Deliverable: scoping note with a size budget and a
  go/no-go; implementation is its own gated row and must not start
  from this filing alone.
  → ✅ **scoping pass done 2026-09-19** (manual lane; note
  `rung6/BM601_ECC_SCOPING.md`, measured by
  `rung6/probe_bee_scheme.py` — 10 legs, exit 0 — and
  `rung6/probe_bee_inner_loop.asm`, assembled for size only).
  **ANSWER: code size is NOT the constraint — capacity is.** The
  interleave already does the hard part: payload bytes 4x..4x+3 are
  exactly the four PXC1 planes at in-plane offset x, so any fault
  confined to one plane (sector, 4 KiB read chunk, 128 KiB erase block)
  hits AT MOST ONE symbol per codeword — the exact class Hamming(7,4)
  over byte symbols corrects, with no GF(256) multiply and no new
  tables. Budget measured: corrector **244 B** vs **4,848 B** already
  unused in the 8,192 B stage2 image; 3 parity planes = 10,223,616 B =
  **+75%** capacity (26,641 → 46,609 sectors, 22.76 MiB), reads/group
  4 → 7, 3 × 4 KiB buffers at 0x38000 (free in the BM903 map). Legs
  B–F restored the payload **byte-identical** on the real BM903 medium
  for 1 / 512 / 4,096 / 32,768 / 512 scattered symbol faults. Two REDs
  measured, both refused by the CRC that stays in place: two symbols in
  one codeword mis-corrects to `CRC=CE9C0E29 != 393950AA`, and the
  linear blind spot (`01,02,02,03` across one codeword — all three
  syndromes zero, decoder fixes nothing) gives `CRC=E1CA03F5`. Hence
  ECC sits BETWEEN the read and the gate, never in front of it, and the
  guest must print `ECC=<n> PAR=<n>` before the verdict so a
  "pass" that corrected nothing cannot be mistaken for a recovery.
  **GO on option A** (Hamming-7,4 byte symbols); option B (1 parity
  plane + per-chunk CRC locator, +25.4%) is the cheaper-capacity
  variant, option C (RS(255,223)+interleaving, +14.3%) is the only one
  that survives a *column* fault — damage to all four planes at the
  same x — which A and B both fail, and its 16-bit code cost is the one
  number this pass could not measure. Implementation row must not start
  from this filing; queue priority and the spend are Jericho's gate.
  Nothing booted here, and the locked shim-side addressing
  (`locate_in_container`) is out of scope for this rung.
- [x] **TASK_BM602**: implementation row — build option A and gate it.
  → ✅ **BUILT AND MEASURED 2026-09-20** (manual lane; gate
  `rung6/run_bm602_e2e.sh`, receipt `rung6/RECEIPT_BM602.md`) —
  `GREEN 15 RED 0` on two consecutive full runs (110 s and 340 s; the
  difference is Tiny Core's autologin race, which costs two anchor legs a
  second boot on the slower pass), after two more `GREEN 14` runs on the
  version before the last leg. **The PXC2-E medium:** PXC1's payload,
  byte-identical (`cmp` against `rung9/bm903_px_payload.bin`, sha256
  `e6ebe1ab…`), on 7 planes = 46,609 sectors = 23,863,808 B, +75.0%
  capacity and 7 ATA reads per group instead of 4; container tag `'PXC2'`
  at MBR `0x180`, read back out of the BIOS copy of stage1. CRC32 gate
  unchanged at `393950AA` — parity is derived, never checksummed, and the
  corrector sits between the read and the gate, never in front of it.
  **Loader by delta, not by re-typing:** 11 stage2 + 2 stage1 + 10 capture
  named textual deltas onto rung9's gated files, each asserted to match
  exactly once and **round-tripped** — undoing them must return rung9's
  bytes, which is machine-checked rather than claimed. Executed corrector:
  **236 B** (228 B code + 8 B counters) against BM601's 244 B standalone
  estimate, 4.9% of the 4,848 B free in the 8 KiB stage2.
  **Predicted before booted:** `bm602_mkimg.py` replays the walk and pass 1
  twice — the codec's algebra and an instruction-by-instruction scalar
  transcription of the asm's dispatch, agreeing over all 3,407,872
  codewords — and writes `bm602_fixtures.json`; the boot gate compares the
  wire against a file written before qemu ran.
  **Results:** a whole 4 KiB data-plane chunk destroyed (`ECC=00000FF4`), a
  4 KiB chunk read back as zeros (`ECC=00000FF5`), a 128 KiB single-plane
  erase block (`ECC=0001FE1C` = 130,588 symbols) and a parity-only chunk
  (`ECC=0 PAR=00000FF2`) each reach `tc@box` with exactly the predicted
  counters; transcripts are byte-identical to the clean boot once the one
  25-byte `ECC=`/`PAR=` field is tokenised (differing bytes: 3, 3, 5, 3 —
  containment, at the same offset, at the same length); the executed handoff
  (4 KiB zeropage, 512 B cmdline, 25 register fields) is byte-identical
  across those media **and** identical to BM903's landed PXC1 evidence.
  Refusals: the two-symbol codeword is mis-fixed (`ECC=1`) and stopped at
  predicted `CRC=B72A10FD`; the equal-triple fault whose three syndromes are
  all zero prints the *clean* medium's counters (`ECC=0 PAR=0`) and is still
  stopped at predicted `CRC=8E53C9D5`; a PXC1 medium is refused by tag in
  0.3 s. BM903's own medium and own gate re-run in the same invocation:
  anchors at 12 s, refuses its corrupt medium at the CRC rung9's own
  predictor derived (`6AB8F2D3`). **Column faults (all four planes at one
  in-plane offset) remain out of this code's reach** — option C's class, not
  injected anywhere here — and nothing is written back: repair is per-boot,
  in RAM, not a healed medium. Two rig defects found here would have
  produced a false green on the headline claim (a serial transcript sharing
  a path with its own leg report; a `--resume` guard matching the word
  GREEN inside a line containing both verdicts); both are recorded in the
  receipt.

## Rung 7 — Path B scale probe (shim-allowed) ✅ CLOSED GREEN (TC-1, evidence probe)

**Scope note (2026-09-18):** this rung is deliberately SHIM-ALLOWED
(nbdkit + pixel-decode plugin serve the medium); it cannot wear the
no-shim thesis — that is Rungs 2/4/5 territory. Its job: prove the pixel
pipeline holds at ISO scale and surface the image-format problems a real
kernel payload will hit, while the decode stack is still a known good
quantity.

- [x] **TASK_R7-TC-1 — CLOSED GREEN 2026-09-18** (receipt:
  `rung7/RECEIPT_TC_PROBE.md`; verified independently by host session:
  both normalized serials sha256 `aa44c974…`, cmp rc=0, artifact pins
  match). TinyCore boots to the `tc@box` serial prompt from a pixel
  medium — ×2 consecutive boots, byte-identical after normalizing only
  busybox-login PID/tty-race lines. Final form: 28,135,424 B payload in
  one 4096² RGBA plane (41.9% util), attached `media=cdrom` (SeaBIOS El
  Torito → isolinux → kernel+initramfs, every disk byte through
  PNG → nbdkit → NBD); measured decode throughput 18,525 KB/s (full
  medium, qemu-io). Serial determinism came from isolinux.cfg
  `SERIAL 0 115200` + `console=ttyS0` + getty respawn — NOT from MBR
  injection: the earlier NBD-as-HDD RED dissolved via CD-ROM
  presentation (host sector-0 check had shown the ISO already
  isohybrid-complete). Dead-leg root cause (16:14–16:33 RED legs): an
  in-place core.gz repack over-consumed its gzip member and spilled
  128,775 B over vmlinuz64's extent head — isolinux loaded a corrupt
  kernel; pixel layer exonerated. RED provenance preserved: same
  pipeline, corrupt kernel → 0-byte serial.
- [ ] **TASK_R7-GATE**: rung7 gate script — ACTIVATION DEFERRED: TC-1's
  close satisfied the probe row without it; stand up from the rung-4
  skeleton only if a shim-allowed consumer appears (first candidate:
  TASK_BM802 fault-sensitivity sweeps).
  - **Candidate withdrawn 2026-09-19:** BM802 sweeps the rung-9 RAW medium
    through stage2's own ATA PIO walk — no nbdkit, no shim, so it would
    never have activated this gate. R7-GATE stays deferred with no live
    consumer; see BM802's scoping finding for what that sweep actually
    needs first.

**Standing lessons (from R7-TC-1):** failure legs must assert WHERE they
failed (debugcon, not serial presence alone) — "new silence" and "old
silence" are different failures that look identical on serial. And: every
in-place image rewrite must assert extent disjointness BEFORE booting —
repack_v3's vmlinuz-MZ-head check is the pattern; its v2 absence cost an
afternoon of false silence.

## Rung 7B — PNG-native inflate in firmware ⚪ EXPLORATORY (was Rung 7)

- [ ] **TASK_BM701**: Boot where the on-medium artifact is a real PNG
  (zlib), not raw RGB — via iPXE's native inflate or an OVMF payload,
  per ANCHORS.md. Rung-2's gate pattern (build-time consts + runtime
  checksum + specified RED legs) transfers unchanged. Does not block
  Rungs 4–6; pursue only if raw-RGB medium size becomes the binding
  constraint.

## Rung 9 — Kernel handoff (the real climb) ✅ CLOSED IN EMULATION (M4; hardware is Rung 8)

**Goal:** a pixel-delivered payload that reaches Linux's protected-mode
entry with a valid handoff: bzImage loaded per the boot protocol,
boot_params zero-filled then populated, cmdline resident and pointed to,
jump to the kernel's 32-bit entry. This is a different class of hard than
Rungs 1–5: the failure mode of a wrong boot_params is a silent hang or
triple-fault with no diagnostic. "Looks plausible" and "boots" diverge
invisibly.

- [x] **TASK_BM901**: Handoff ORACLE FIRST — conventional QEMU boot of a
  real Linux through the real chain (SeaBIOS→isolinux→kernel), GDB-stub
  snapshot of register state at the protected-mode entry plus full
  boot_params/cmdline tables dumped from guest memory. Deliverable: a
  field-by-field reference table. NO stage2 handoff code may start
  before this exists (staged 2026-09-18 in
  `.builder_queue/DIAGNOSIS_r7tc1_eltorito_as_hdd.md`).
  → ✅ **done 2026-09-18** (builder cron af3e62239ce2) — gate
  `bash rung9/run_oracle.sh` **GATE PASS** (exit 0, phases A–D, RED legs
  verified). Chain: TinyCore-current.iso (serial recipe baked, `tc@box`
  boot re-verified plain `-cdrom` this run) → SeaBIOS → isolinux →
  bzImage protocol 2.13. Capture: GDB hw-bp at code32_start=0x100000 —
  the chain hits it TWICE (hit 0 = isolinux trampoline, rsi=0x160005 no
  HdrS; hit 1 = kernel handoff, rsi=0x13ab0 = &boot_params); registers
  sampled pre-first-instruction; QEMU gdbstub re-fire handled by
  stepi-24-then-continue between stops (probe33 measured the same stop
  at 0x100053 post-step, confirming the sampled stop-1 is the handoff
  instant). ×2 legs byte-identical on zeropage (sha c3120d8e…), cmdline
  (sha 30cd829f…), and registers — **zero variability fields observed**
  (QEMU/TCG property, flagged do-not-carry-to-Rung-8). Key fields:
  type_of_loader=0x33 (isolinux chainload — BM902 must classify
  LOADER-SPECIFIC, not reproduce), loadflags=0x81, code32_start=0x100000
  =rip, e820_entries=7, ramdisk_image=0x1f6ea000/size 0x8d4f07,
  cmd_line_ptr=0x1f800 ("loglevel=3 cde console=ttyS0,115200
  initrd=/boot/core.gz BOOT_IMAGE=/boot/vmlinuz"), cs=0x10 ds/ss/es=0x18
  flat, cr0=0x11 (PE, no PG), eflags=0x46 (IF=0), rsp=0x1f784. RED
  legs: redA single flipped byte (zp[0x228] LSB) flagged; redB
  QEMU-direct (-kernel, different loader path) zeropage differs in 206
  bytes (schema is real, not a constant). Deliverables:
  `rung9/ORACLE_BOOT_PARAMS.md` (full field table + honest boundary),
  `rung9/run_oracle.sh`, `rung9/probe34_capture.py`,
  `rung9/probe27_qemu_direct.py`, dumps + pins in `rung9/oracle_*`.
  34 probes total; scratch probes archived to /tmp/rung9_scratch
  (volatile — only the landed artifacts are evidence). BM902 may now
  start against this reference.
- [x] **TASK_BM902**: stage2 constructs the handoff; differential test =
  byte-identical boot_params/cmdline against BM901's dump, not a boot
  attempt. Mismatches surface as diffs, never as hangs.
  → ✅ **done 2026-09-19** (builder cron af3e62239ce2) — gate
  `bash rung9/run_bm902_diff.sh` **GATE PASS, exit 0** (all six legs in
  one clean invocation; receipt `rung9/RECEIPT_BM902_STAGE2_HANDOFF.md`).
  Phase A ×2 deterministic constructions byte-identical (zp sha
  f6605707…); L1 differ: 138 zeropage diff bytes, ALL inside the
  field-plan whitelist union (517 offsets — 126 = the flagged
  STAGE2-CHOICE band 0x000-0x1e7 + 12 whitelisted loader fields:
  ram_size/root_dev/start_sys_seg/type_of_loader 0xff/setup_move_size/
  ramdisk×2/heap_end_ptr/cmd_line_ptr/root_flags); L2 cmdline byte-exact
  oracle string (`30cd829f…` pins match); L3 registers = pinned oracle
  state (rip 0x100000, rsi 0x13ab0, cs 0x10, ds/ss/es 0x18, cr0 0x11,
  eflags 0x46). RED legs pasted in receipt: L4 flipped zp[0x214]
  (code32_start, outside whitelist) → `L1 FAIL: … 0x214`; L5 mutant
  field plan (0x210 whitelist line removed) → `L1 FAIL: … 0x210` —
  whitelist enforced, not decorative. Construction licensed by
  measurement, not doc: `bm902_zp_probe3.py` shows oracle zp band
  [0x1f1,0x268) byte-identical to `vmlinuz64.extracted` except
  loader-owned offsets (0 unexcused), e820 = 7 entries ending 0x35c,
  above-0x35c all zero. Deliverables: `rung9/bm902_stage2_construct.py`,
  `rung9/bm902_differ.py` (parses whitelist from the committed field
  plan — plan and gate cannot drift apart), `rung9/run_bm902_diff.sh`,
  artifacts `bm902_{zp,cmdline,regs}*`, probes `bm902_zp_probe*.py`.
  HONEST BOUNDARY: host-side construction only — no QEMU boot, no 16-bit
  stage2 binary executed; the artifact is proven oracle-grade, the
  executed-loader proof is BM903+ territory (session-mode capture under
  the probe34 harness).
  *(Checkbox was left unchecked after the row closed; re-verified
  first-hand by the manual lane on 2026-09-19 — `bash
  rung9/run_bm902_diff.sh` rc=0, `GATE PASS: BM902 stage2 handoff (L1-L3
  green, L4/L5 RED demonstrated, x2 identical)`, pins above reproduced
  byte-for-byte.)*
- [x] **TASK_BM903**: end-to-end — pixel medium carries bzImage+cmdline
  (10–30 MiB: capacity measured sufficient), kernel reaches
  serial/console output through the standard handoff. Gate: ×2
  byte-identical boots.
  → ✅ **e2e pixel boot CLOSED 2026-09-19** (steps 1+2+3 of
  `.builder_queue/brief_bm903_e2e_pixel_boot.md`) — gate
  `bash tools/bare_metal_poc/rung9/run_bm903_e2e.sh` **`42 pass, 0 red`,
  twice consecutively**. Executed 16-bit `bm903_stage2_px.asm` (8192 B, no
  nasm warnings) walks the PXC1 four-plane medium (26,641 sectors; payload
  13,631,488 B = 832 groups = 208 banks; `CRC=393950AA`) over ATA PIO with
  per-sector DRQ handshake, de-interleaves into 0x20000 / 0x100000 /
  0x10000000 (all 13,556,135 B proven byte-identical to the host blobs by
  `bm903_px_memcmp.py`), and computes the CRC32 **inside the guest** on the
  only path to the handoff — rung-4 discipline DEFECT-R4PRINT kept:
  compute fully, print computed-then-expected, then decide. L1: the handoff
  the executed loader *builds* differs from the BM902 oracle by 4 bytes
  (0x21b-0x21e, the constructed initrd pair), all inside the 517-offset
  whitelist union; L1b: pixel and contiguous media hand the kernel
  byte-identical memory; L2: 26 registers re-pinned
  (rsp 0x1f784, cr0 0x11, eflags 0x46, rsi 0x13ab0, rip=rax=0x100000); L3:
  `tc@box` on serial at 11.0–12.0 s; L4: ×2 boots, 881 B of transcript
  byte-identical after T1–T4 plus strict dump equality; L5 RED: a
  zp[0x244] flip is caught and named while a whitelisted 0x210 flip stays
  green; L6 RED: one corrupted medium byte makes the guest print exactly
  the host-predicted `CRC=6AB8F2D3 EXP=393950AA`, refuse, build no handoff,
  and never stop at 0x100000 under gdb (2 × 20 s). R1: step-1's gate green
  in the same run. **Newly measured defect, not the loader's:** Tiny Core's
  inittab races tty1 and ttyS0 through one `/sbin/autologin` flag file, so
  which console draws the prompt is a coin flip on BOTH media (19 timed
  pixel boots → 11 anchors; 8 step-1 boots → 3; `-vga none` → 6/8; a longer
  single budget rescues nothing — a lost boot sits silent forever). L3/L4
  therefore allow 8 named 45 s boots, the same worst-case wall clock the
  original single 180 s boot had, rather than asserting a determinism the
  guest does not have; the anchor string itself is unchanged, nothing was
  OR'd or relabelled. Three gate-rig bugs found RED-first and pasted in the
  receipt: a probe path that resolved to `tools/output/`, a substring
  collision that read a *correct* refusal as a false RED, and a cut position
  that moved 129 B between two legitimate boots. Deliverables
  `rung9/run_bm903_{step1,e2e}.sh`, `bm903_stage2{,_px}.asm`,
  `bm903_mkimg{,_px}.py`, `bm903_pxcodec.py`, `bm903_capture.py`,
  `bm903_differ.py`, `bm903_lane.py`,
  `bm903_{anchor_boot,norm_transcript,px_corrupt,px_memcmp,tty_race}.py`,
  `BM903_FIELD_PLAN_ADDENDUM.md`, `RECEIPT_BM903_STEP2.md`,
  `RECEIPT_BM903_E2E.md`.
  → ✅ **guest-side provenance sub-task done 2026-09-19** (builder cron
  af3e62239ce2; brief `.builder_queue/brief_bm903_guest_hermes.md`) —
  gate `python3 rung9/guest_provenance_gate.py` **GATE PASS exit 0**
  (run5; RED defect tail run1): three-way agreement measured on a
  guest-Hermes-written 2400 B file (1 extent, first disk byte
  12,990,693,376, frame 194) — chain A guest Hermes `sha256sum`/`od`
  quote == chain B `locate_in_container.py verify` pixel reconstruction
  (`recon_sha256 == expected`, rc=0) == chain C backend `/peek` after
  forced LRU eviction (`0x42` at the first disk byte, guest-equivalent
  read path). RED leg discriminating: guest `rm+sync` → verify RED
  (`TRANSIENT-EXHAUSTED … filefrag`); measured honestly, `/peek` after
  rm still returns `0x42` — stale pixels persist until overwritten.
  Defect found+fixed RED-first (run1): prompt-embedded payloads are NOT
  byte-faithful through the LLM (2400→2750 B rewrite, sha mismatch);
  fix = 9p seed file + Hermes `cp` (run2 20 s, sha match). Receipt
  `rung9/RECEIPT_BM903_GUEST_PROVENANCE.md`. **The e2e boot itself
  (executed 16-bit stage2 + serial verdict) remains OPEN** per
  `brief_bm903_e2e_pixel_boot.md`.
- [x] **TASK_BM904**: guest write-side pixel diff — the inverse provenance
  gate. Guest writes 256 random bytes at a known offset of a preallocated
  64 MiB probe file; host predicts the EXACT changed-pixel set through the
  address chain and asserts the decoded-pixel diff equals it.
  → ✅ **done 2026-09-19** (builder cron af3e62239ce2; brief
  `.builder_queue/brief_bm904_guest_write_diff.md`) — gate
  `python3 rung9/bm904_write_diff_probe.py` **GATE PASS ×3 consecutive,
  exit 0** (final `output/bm904_gate_final.log`; live RED
  `output/bm904_gate_mutant_red.log`): deterministic self-check (comparator
  RED vs off-by-one chain) every invocation; fallocate-first extents (2
  extents, frames [223,225]); control noise floor **0 px** ⇒ EXACT-equality
  assertion; treatment legs 32 MiB mid-frame + 64 MiB frame-boundary
  straddle → **changed=64 == predicted=64, extra=0, missing=0, EXACT** both,
  ×3 runs with fresh random bytes; R1 measured not gated: post-write/
  pre-writeback `/peek` serves the NEW byte while PNGs decode the OLD
  (`peek_leads_png: true`, both runs — shim-forensics, recorded not
  deepened); R2 host paint of one channel caught exactly that pixel,
  restore byte-identical; cleanup verified GONE. **Live RED leg:
  `--mutant` (extent-0 physical block +1) → boundary-straddle leg predicts
  64 vs 96 actual, extra=32 → FAIL, exit 1** — the assertion is
  load-bearing on the real container. Defects found+fixed in-session (RED
  tails): R1 peek ran pre-write (measured nothing), R2 (frame,y,x) vs
  (frame,x,y) tuple-order bug, straddle-offset clamp for degenerate
  layouts. Scope: `rung9/bm904_write_diff_probe.py` (new) + this cell +
  `output/bm904_*`; guest writes limited to the probe files (rm'd, GONE);
  no `systems/virtio_pixel_rs/` edits, no backend restart. Receipt
  `rung9/RECEIPT_BM904_WRITE_DIFF.md` (honest boundaries: n=2 offsets/run,
  single probe file, same-boot ×3, R2 proves host-paint sensitivity not
  concurrent-guest-writer sensitivity; the medium contract that survives
  shim deletion = Chain + decoded-pixel diff primitive + noise-floor
  method). Follow-ons filed in the brief's backlog note, not built.
- [x] **TASK_BM905**: input mailbox over the pixel medium — host paints
  `[seq, type, code, value]` packets into a reserved, FS-dead-space LBA
  window; guest daemon polls its own /dev/vdX, injects via /dev/uinput;
  BM904's diff gate proves pixel landing, guest evdev testifies keycode.
  → ⏳ **queued 2026-09-19** (Jericho ruling: mailbox ranked ABOVE the
  mind-state/KV-cache probe; brief `.builder_queue/brief_bm905_input_mailbox.md`).
  Un-shelved deliberately from the BM904 backlog note (that note parked it as
  replacement-scaffold work; the ruling keeps it shim-era because its
  verification reuses BM904's fresh gate). Leg 0 STOP-condition: no in-guest
  uinput ⇒ REPAIR_PENDING with measurements, no weakened testify fallback.
  **→ Leg 0 measured GREEN + gate assembled, PARKED at iteration cap 12:15**
  (agent run started 11:43; artifacts untracked in `rung9/`): uinput works
  in-guest (raw-ABI create of `BM905-Mailbox-Keyboard`, EV_KEY 30 press+
  release read back from `/dev/input/event5` — guest lacks pip/gcc so evdev
  uninstallable, ABI done by hand); **window placement REJECTED the brief's
  disk-tail default by measurement** (tail carries initramfs+gguf payload
  sections, 179 nonzero bytes) → chosen vda LBA [256,512) alignment gap,
  verified all-zero via pixel path AND /peek; sudo via pty-answerer
  (`bm905_sudo_drive.py`), guest credential in gitignored `.env` (pending
  Jericho ratification). OPEN for next run: codec self-test was RED at cap
  (struct padding; rewrite `"<HIBBHH"` untested), guest raw-dd read leg
  unproven (pty ate the pipe, empty md5), Legs A–E unexecuted, nothing
  committed, guest residue in /var/tmp. Order: codec retest → guest dd
  file-then-md5 → gate `--skip-guest` (Leg A/D) → full gate → receipt +
  this cell ✅. Geometry note: 16-B slots are 512-aligned ⇒ the brief's
  "slot straddling a sector edge" is impossible — straddle leg = frame
  boundary only.
  **→ ✅ GATE PASS (exit 0) 2026-09-19 16:38, manual lane.** Host paints
  16-B `[magic|seq|type|code|value|crc16]` slots into a 128 KiB FS-dead window
  (vda LBAs [256,512), proven outside all GPT partitions by `fdisk -l`); the
  guest's own daemon polls `/dev/vda`, injects through raw-ABI `/dev/uinput`
  (`BM905-Mailbox-Keyboard`), and evdev testifies. Leg A exact-equality pixel
  diff ×2 (15/15 and 11/11, extra=missing=control-noise=0); Leg B keycodes
  30/31/32 + 33/34 at 0.374 s / 0.979 s AFTER guest-visible (budget 5 s);
  Leg C replay of consumed seqs added zero testimony (7→7 — `seq` is
  load-bearing); Leg D mutant RED (extra=15 missing=15, exit 1); Leg E
  CRC-corrupted slot skipped + counted, good neighbour still injected.
  Receipt `rung9/RECEIPT_BM905_INPUT_MAILBOX.md`; guest residue GONE, window
  back to the 128 KiB all-zero digest on a cold guest read. Measured medium
  facts (paint→guest-visible 13.5–62 s, `/peek` leads guest `dd`, journal
  overlay masks a sector after a guest write for >150 s) are recorded, not
  tuned. Boundaries: poll-loop not interrupt-path, single writer (the
  concurrent-writer gap stays BM904's open question), window proof is
  per-image. Follow-ons filed in the brief's ladder, not built.

## Rung 8 — Real silicon 🔴 BLOCKED (external: physical hardware)

**Goal:** the ladder's namesake. `dd` the raw medium to a bootable USB;
boot a physical x86 machine; serial receipt.

**Scope discipline (2026-09-18):** Rung 8 is a TRANSPORT test, not a
construction test. The byte stream it carries must already be known-
correct — Rung 9's oracle is QEMU-only and can be fully green before any
hardware exists, and the sequencing is deliberate: retire the riskiest
unknown (a silent wrong-but-plausible handoff) in software first, so the
one irreversible, hard-to-debug rung reduces to "does this exact byte
stream survive being written to and read from a real chip."

- [ ] **TASK_BM801**: Hardware boot attempt. Blocked on: a physical x86
  box Jericho designates (serial port or agreed receipt channel —
  fallback candidate: VGA text beacon verified by XOR-diff glyph
  matching, not OCR). Prereq by ladder logic: Rung 5's write leg
  (BIOS write variance across real chipsets is the known unknown).
  - **Write-verify discipline (pre-registered 2026-09-18):** after
    `dd` + sync, read the physical medium back and `cmp` against the
    gate-validated `.raw` BEFORE any boot attempt — the rung-4
    encode→bake→cmp identity gate applied to real media. Never boot an
    unverified medium.
  - **Write-verify discipline: BUILT AND GATED IN EMULATION 2026-09-21.**
    That paragraph had no implementation anywhere in the ladder; it does now.
    `rung8/bm801_write_verify.py` bakes with `dd conv=fsync` + `sync`, reads the
    medium back and `cmp`s it byte-exact against the source, and separates its
    answers by exit code: 0 verified, 1 MISMATCH — never boot — 2 refused
    before writing, 3 tool failure. `rung8/run_bm801_write_verify_gate.py`
    holds 7/7 legs at rc=0 by **breaking the medium on purpose**: a byte
    changed after `sync` returned, a truncated target, a bake that stopped at
    1 MiB of 4, a mutation through a descriptor opened before the sync. Each
    was caught at its exact offset. Leg 6 ran the whole discipline on a real
    gate-validated medium (`rung5/rung5_medium.raw`, 67,108,864 B, read-only as
    a source): bake, sync, read back, byte-identical. Refusals come first and
    are gated too — a block-device target needs `--device`, and a target
    inside the repository tree is refused outright, because this box's live
    pixel VM disk is a file under git and the failure mode there is not a wrong
    verdict but an unwrongable write. Building it found the trap the discipline
    exists for: `dd count=` counts *blocks*, so a `--short-bytes 1048576`
    partial-write fault at `bs=4M` silently wrote all 4 MiB — a test that
    cannot fail. Receipt `rung8/RECEIPT_BM801_WRITE_VERIFY.md`, which names
    what stays out of reach: firmware that flushes after reporting completion.
  - **Capture-decay boundary: MEASURED 2026-09-21.** `rung8/bm801_reader_decay.py`
    degrades one clean frame along five axes (noise, contrast, resolution,
    sub-pixel grid shift, off-grid crop) and asks the only question a receipt
    channel has to answer: when it is wrong, does it say so? Verdict —
    **the reader has no graceful-degradation zone**: accept a beacon only when
    every cell matches its atlas entry at XOR distance 0, which across 25
    degraded levels accepted 13, was wrong in 0 of them, misread 8, and
    declined 1 that had actually read right. Neither available statistic
    separates right from wrong (wrong reads span distance 8..39, correct reads
    0..10; runner-up gap 0..2 vs 0..1), so anything short of an exact match is
    a *decline*, not a doubtful read. The live risk is named by the sweep: a
    **one-pixel grid shift misreads and is invisible to `pitch_is_exact()`**,
    because a shifted 720x400 frame still divides evenly — so the hardware step
    is grid alignment against the on-screen calibration block, not a better
    camera. `rung8/RECEIPT_BM801_DECAY.md` keeps the prediction this leg
    falsified (contrast collapse, which per-cell thresholding makes harmless)
    and the leg that went RED before it was restructured, plus the two
    vacuous-pass bugs found on the way.
  - **Grid alignment: BUILT AND GATED 2026-09-21.** `rung8/bm801_align.py` closes
    the risk that bullet named. It searches all 144 sub-cell phases, scoring each
    by how many of the 1,744 cells *outside* the calibration block carve to a
    plane some block entry has, then registers the block's true origin from the
    beacon's own fill. Measured over one boot, 9 legs at rc=0: each of the eight
    displaced frames — rolls of (1,0) (2,0) (0,1) (0,3) (1,2) (2,7) (4,5) px and
    a whole-cell slide of 9 — goes from a naive read of 0, 5, 16, 30 or 32 exact
    cells to **33 of 33 and the exact string**, and a correct frame is
    left alone. Two findings reshaped it. The redundancy the step asked for —
    matching cells inside the calibration block, or using the message that the
    sector paints twice — is blind to a global shift: both copies slide together,
    so every phase scored the same. And a sub-pixel displacement carries a
    whole-cell slide with it, which a phase search cannot express at all, so the
    block has to be *relabelled* as well as re-phased. `rung8/RECEIPT_BM801_ALIGN.md`
    keeps the leg that went RED (the corrected view read the receipt perfectly
    while the file written from it did not — a pixel index used as a byte index)
    and the leg added afterwards because the first version of the guard test
    never once forced the aligner to face its own rule.
  - **Clamp mode: the frame edge became a measured behaviour, not an assumption
    (B5, 2026-09-22).** B4's receipt admitted in its own words that the offset frame "wraps and
    so invents edge pixels" — harmless for a screendump, false for a camera. `rung8/bm801_align.py`
    gains a `clamp` mode that samples only in-frame cells: it can shorten the usable set, never
    fill it. 9 legs at rc=0 over one boot. On a 32-px roll clamp scores 1584 where wrap reports
    1712, and on larger shifts the modes disagree about the *answer*, not merely its confidence —
    wrap's phase (0,14) reads 1692 of 1,744 leaning on 80 invented cells, clamp's phase (0,0)
    reads 1629 on none. Three of the gate's own predictions were refuted by measurement and
    rewritten before 9/9 landed, and the one that mattered forced a code change: the edge rule is
    now judged ahead of increase-only, because run 3 measured both firing on the same report and
    only the weaker one reaching the operator. `cells_edge_invented` and `msg_cells_edge_invented`
    join the report because on a lost-strip capture "aligned" and "aligned on pixels this capture
    does not contain" score the SAME 1504/1744 — the count is the only thing that separates them.
    `materialize()` still writes a wrapped view, named as a non-goal, and wrap stays the default.
    `rung8/RECEIPT_BM801_CLAMP.md`.
  - **The written file now obeys the mode that authorized it (B6, 2026-09-24).** B5's
    non-goal was a live hole, not a deferred nicety: `materialize()` hand-rolled its own
    `% view.h` / `% view.w` sampling instead of calling `plane()`, so it was wrap-only no matter
    which mode decided the view — a clamp report with `cells_edge_invented=0` could authorize a
    file full of opposite-edge pixels. It now samples through the same accessor every reader uses,
    writes a cell the mode refuses to see as the declared zero plane, and says so in the PPM header
    (`mode=clamp sentinelled=N of 2000 cells`). 9 legs at rc=0 over one boot; RED first, measured
    against the old code: 0 bytes separated a clamp file from a wrap file, and 9,771 bytes — 79 of
    80 invented cells, one already black in the capture — separated the old writer from a frame
    rebuilt cell-by-cell. B5's 1629-vs-1692 price reproduced in the report, and the file's own price
    measured at fixed geometry: 1,676 against 1,744 exact, 68 cells the honest file refuses to
    invent. Where the message row is off-edge the sentinel region decodes as 33 blanks and
    `distance0=0`, where wrap's file supplies 32 plausible calibration glyphs. Five of the gate's
    predictions were refuted by measurement and kept in `rung8/RECEIPT_BM801_MATERIALIZE.md`,
    including the one that mattered — a clamp view accepted at its own phase does not read its own
    receipt, so the leg has to take the geometry wrap was accepted at. B5's gate calls `materialize()`
    zero times and B4's twice, so the older gates do not hold this rule; these 9 legs and the
    default staying `wrap` do.
  - **The reader's other sampling path now honours the offset too (B7, 2026-09-25).** B6
    named this one and left it: `OriginFrame.grid()` was inherited from `vga.Frame`, so it
    carved `self.pixels` at `(r*ch+y)*w + c*cw+x` — no `dx`, no `dy`, no `ko`, no `jo`, no
    mode — and `vga.Frame.plane()` and `vga.Frame.ink_profile()` are both built on it. The
    claim survived being checked: on one capture (`85efe386fd8c6703`) at one displaced
    geometry (`roll(3,5)`, phase (6,11), block at (24,79)) the displaced view reported an
    ink profile summing to 2,235,183 over three columns where the pixels actually there sum
    to 1,273,956, and the inherited carve disagreed with the honouring one on 160 of 160
    sampled cells — while agreeing on 0 of 160 at zero offset, which is the whole reason no
    older gate ever saw it. `grid()` is now derived from `raw_cell()` on both classes, so it
    carries the mode as well as the offsets: on the clamp view the inherited carve invented
    opposite-edge bytes for 104 of the 104 cells the mode refuses to sample, and the fixed
    carve invents none. 10 legs at rc=0 over one boot; B4's, B5's, B6's and B1's gates all
    still rc=0 under leg 9. The census is what chose fix over refusal — `.grid(` has exactly
    two call sites tree-wide, both inside `bm801_vga.py`, and zero outside it, so refusing
    would have raised from inside `plane()` to protect a caller that does not exist — and
    that census is now an AST walk, because run 3's grep census counted the fix's own
    override and one word of its docstring as new consumers. Four predictions refuted and
    kept in `rung8/RECEIPT_BM801_GRID.md`, the worst being that a GREEN log means a landed
    file: the lane's `bm801_align.py` was restored to its committed content by a process
    outside this session twice mid-run (01:56:38Z, 02:17:31Z), leaving untracked files
    alone both times, so the fix had to be replayed from the transcript and verified
    byte-identical to the 18,074 bytes the gate measured. `OffsetFrame.lum`/`OriginFrame.lum`
    stay inherited-by-way-of-nothing: `Frame.grid` was `lum`'s only caller tree-wide and both
    classes now override `grid`, which is B8's table row with its number attached.
  - **The number of blind sampling paths is now measured, not searched for (B8, 2026-09-25).**
    B6 and B7 were each found by accident and each survived four gates that printed 9/9, so
    the lane owed the question a table: `rung8/AUDIT_BM801_SAMPLING_PATHS.md`, regenerated by
    `rung8/run_bm801_path_audit_gate.py`. Rows are `dir()` on the two offset frames -- so a
    method added tomorrow appears whether or not anyone remembers to list it -- with a column
    naming the MRO class that *defines* it, which is what separates `OffsetFrame.lum()`
    (overridden) from `OriginFrame.lum()` (inherited from `vga.Frame`, never overridden).
    `reaches pixels` is a transitive AST walk; every honour cell is compared against a value
    derived by hand from the PPM bytes, never by calling the aligner, so the table cannot be
    made true by a fix agreeing with itself. Measured on one 720x400 `-snapshot` beacon boot
    (`85efe386fd8c6703`) at an anchor carrying phase (3,5) and block origin (2,7) -- 104 of
    the 2000 cells out-of-frame, which is the only reason `mode` has anything to bite on.
    **3 of 22 rows carry a NO.** `OriginFrame.lum()` honours none of the five (`dx` blind on
    21 of 45 samples where the bytes differ, `dy` 17, `ko` 7, `jo` 6; 4 under `clamp`) and no
    gate file calls `.lum(` anywhere -- B7 closed the accessor's last caller and left it in
    place, which is the row B7's own receipt named. `OffsetFrame.lum()` and `OffsetFrame.rgb()`
    honour the phase but not the mode (6 of 45 each), and bite nowhere inside the file only
    because `raw_cell()` tests `drops()` before it reaches them: B6 fixed the writer, not the
    two accessors the writer was written in terms of. The other finding is coverage rather than
    correctness -- 9 of the 15 pixel-reaching rows have no direct call site in any gate file,
    so a defect there contradicts nothing. 19 of 22 rows read `yes` or `n/a` in every column,
    all six whole-cell accessors among them, and the module sweep found 3 `X.pixels[...]`
    indexers ladder-wide (2 in `rung8/bm801_align.py`, 1 in `rung8/bm801_vga.py`) and zero
    under `rung9/`. 13 legs at rc=0 -- two `-snapshot` boots, this gate's own and the one leg
    12 hands to B7's gate (9/9 at rc=0 under that gate's own skip flag) -- with leg 0 hashing
    all eight audited sources against their `HEAD` blobs, because this item was an audit and
    the claim needed proving, and leg 11 re-emits the table and diffs it against the landed
    block so the prose cannot drift from the measurement. Two false GREENs the audit found in
    itself first: `inspect.getsource` returns a method *with its leading indentation*, so
    every `ast.parse` raised, the blanket `except Exception: return None` swallowed it, and
    all 22 rows read "reaches nothing" -- leg 1 now asserts `bodies that failed to parse=none`;
    and the census matched `startswith('run_bm80')` against paths already relative to
    `rung8/`, so it returned empty for every row and leg 4's "no gate reaches it" passed for
    the wrong reason -- it matches on basename now, and carries a control that prints
    `NONE (the filter is broken)` if no accessor shows any gate caller at all. B9, B10 and B11
    queue the three NO rows and the coverage gap; the cap was explicit -- land the table,
    queue the worst three, do not start fixing during the audit.
  - **B9 -- `OriginFrame.lum()` honoured none of the five and nothing reached it: fixed, and
    the blindness kept in evidence.** The row B8's table measured (21/17/7/6 of 45 samples
    unchanged where the bytes differ on `dx dy ko jo`, 4 on `mode`, gate column `nothing`) is
    one `return` now: `sum(self.raw_cell(r, c)[y * self.cw + x])` at `bm801_align.py:168`, so
    the pixel comes from the same gate `plane()` and `grid()` use and `drops()` is honoured by
    the same act. Fix or cut was decided by the census, not by taste: the production call site
    count is one (`bm801_vga.py:64`, inside `Frame.grid`, which both classes override), so an
    override is free and a refusal would raise out of the unbound call B7's leg 1 leans on.
    **B8's queue text was half wrong about that, and the half is the finding:** an override
    does keep `Frame.grid` *usable* unbound and does not keep it *blind*, because
    `Frame.grid` is built on `self.lum`. So B7's blind side moved -- `blind_grid()` takes a
    plain `vga.Frame` over the same bytes now (same formula, still live code, no longer a fact
    about inheritance) -- and B9's leg 3 measures why: 0 of 5 sampled cells disagree between
    `vga.Frame.grid(view, ...)` and the view's own honouring carve. B7's legs 0-6 and 8 print
    values identical to its pre-fix run, digit for digit, across three boots of the same
    capture; only leg 7's lines differ (the census now separates a gate caller from a
    production one, and a line number moved). `rung8/run_bm801_lum_gate.py`, 11 legs: leg 1
    reproduces B8's five digits from the base formula as its permanent RED, leg 2 answers
    45/45 on all five columns against a hand-derived pixel, leg 4 counts 0 invented pixels on
    104 dropped cells against the base formula's 104, leg 7 asserts `OffsetFrame.lum` still
    wraps so this item cannot be mistaken for B10, leg 8 prints the census before and after,
    and leg 10 re-reads the receipt message at 33/33 on the corrected geometry. B8's audit
    moved with it: leg 1 separates the two `lum` rows the other way, leg 3 reads the
    `OriginFrame.lum` row out of *this file at `a5bf99e3`* and refuses to pass unless the
    landed table disagrees, leg 4 requires a gate to call `.lum(`, and leg 0 stopped raising
    `CalledProcessError` on a `SOURCES` file that is on disk but not yet in `HEAD` -- which is
    what the item adding one looks like mid-run (pre-landing it prints `11/12`, the single FAIL
    being its own three files). Landed state: `RESULT 11/11` here, `9/9` nested from B7,
    `13/13` nested from B8's audit; `RECEIPT_BM801_LUM.md`, and `RECEIPT_BM801_GRID.md`
    carries a dated correction of the section that named this row. B10 and B11 stay queued.
    **Corrected by B9 after landing, same day (`5ab0b0ef`):** the counts above are what the
    gates print, and one run mode was quoted wrong -- B8's audit is `13/13` *standalone*
    (measured at the landing commit, leg 0 `drifted=none`), and `12/12` when B9's leg 9 nests
    it, because nesting sets `BM8_SKIP_OLDER` and leg 12 -- the nested B7 gate -- then declines
    to run. A leg count without its skip flag is the same class of claim B8's table exists to
    catch, and this lane raised it against itself.
  - **B10 -- the two single-pixel rows honoured the phase but not the mode: routed, and the
    table now has no NO cell.** `OffsetFrame.rgb()` and `OffsetFrame.lum()` were each
    `NO (wraps)` in B8's audit -- 6 of 45 samples unchanged where the bytes differ -- because
    both did their own `% h` / `% w` arithmetic and a `self.pixels` slice without consulting
    `drops()`, so on a clamped view a one-pixel read returned the opposite edge of the
    capture: `raw_cell()` tested `drops()` before it ever reached them, which is exactly why
    B6 and B7 came out clean and why B8 called this "the B6 defect at single-pixel scale".
    `rgb()` grew the `drops()` branch and `lum()` became `sum(self.rgb(...))`
    (`bm801_align.py:94` and `:137`, +24/-5 with docstrings); `raw_cell()` is untouched, since
    it already sampled through `rgb()` behind its own gate. `SENTINEL` was chosen by an
    equality, not by taste: `sum(SENTINEL)` is the zero `raw_cell()`, `grid()` and `plane()`
    already return for a dropped cell, so a raise or a second sentinel would have made the
    pixel and the cell disagree and broken the equality B9's leg 6 rests on.
    `rung8/run_bm801_rgb_gate.py`, 11 legs, one boot: 5 of 5 sampled out-of-frame cells invent
    before and 0 after; across all 104 dropped cells `rgb`, `lum` and `raw_cell` invent on 0
    while the untouched base formula still invents on 104, and the item's own superseded
    arithmetic -- kept live in the gate file -- invents on 102 of them; `wrap` is byte-for-byte
    unchanged on 2000 cells x 5 pixels; the sentinel does not leak (1896 in-frame clamp cells
    still equal the pre-fix bytes, 29 reading all-zero); the audit's probe, run from inside
    this gate, reads `yes` on `dx`, `dy` and `mode` for both rows. Three legs had to move, not
    the one the queue text named: **B9's leg 7** existed to keep this row open and flipped
    sign; **B8's leg 2** could not keep asserting a `NO` against code that no longer produces
    one, so it now reads B8's verdict out of the landed table at `a5bf99e3` with `git show` and
    requires the fresh `yes`; and **B8's leg 9**, which forbade `self.pixels[...]` outside the
    two modules, now permits exactly one `old_*` helper per gate file and prints it -- a gate
    that keeps a superseded formula in evidence has to index the bytes itself. The item's
    price clause held: B7 `9/9`, B4's clamp gate and B6's materialize gate, and `wrap` all
    unmoved, and B8's leg 11 reports `generated block == the landed block` with the two rows
    reading `yes`. What the audit's last column also lost is worth more: `raw_cell` left the
    `nothing` set because this gate calls it directly, so the count of pixel-reaching rows
    with no gate caller has now gone 9 -> 7 -> 4, and B11 is `physical()` alone. One
    consequence nothing measured: this insert moves every `bm801_align.py` line citation at or
    after `:99` by +12 to +19 (`OriginFrame.lum` 168->187, `materialize` 297->316), and
    `doc_ref_audit.py` still printed `173 line citations (0 stale)` while doing so, because its
    line check is range-only -- four receipts now cite lines that point elsewhere, and they are
    left as written. See `rung8/RECEIPT_BM801_RGB.md`; B11 stays queued.
  - **B11 -- the one row that returns a coordinate had no gate call site: pinned, with no
    source change.** `OriginFrame.physical()` is the line every other accessor on that class
    hands off through, and B8's audit column said `nothing` for it -- the same exposure B6 had,
    a rule everything depends on and no leg names. The wrap is the behaviour that was already
    right, so what landed is `rung8/run_bm801_physical_gate.py`, 9 legs, one boot, and
    `bm801_align.py` untouched. The pin is behavioural because deleting the two `%` raises
    nothing: leg 4 shows no offset pair drops any of the 2,000 cells at zero sub-cell phase, and
    leg 5 shows that at the audit's anchor phase every one of eight pairs drops exactly the 104
    cells the hand-derived rule names -- while the control the gate keeps live for the purpose,
    the same relabelling with the modulo removed, drops 416 at `(ko, jo) = (2, 7)` and all 2,000
    at `(25, 80)`. Leg 3 is the leg that stops a fake pass: the map must be a bijection, so an
    edit cannot go green by clamping instead of wrapping (the control names 321 off-grid samples
    and leaves 321 real cells unreachable). `--emit-table` moved three cells and B8's leg 11
    agrees with itself: `physical` off the `nothing` set, and both `drops()` rows gained this
    gate as a caller -- a side effect of pinning a coordinate by asking the mode what it makes of
    it, and named in `rung8/RECEIPT_BM801_PHYSICAL.md` rather than smoothed over. The four
    `vga.Frame` base rows still read `nothing`, which is a different claim and was never this
    item's: nothing calls them unbound. Pre-commit the nested audit gate reads `11/12` on its
    own leg 0 (`run_bm801_physical_gate.py(not-in-HEAD)`), the shape B9 recorded for an item
    that adds a `SOURCES` file. Landed state, measured at `dd8b55ea`: this gate `9/9` with no
    skip flags, its nested audit gate `12/12` (leg 0 `drifted=none`) and B10's rgb gate `10/10`,
    and B8's audit standalone `13/13` with leg 11 reporting `generated block == the landed
    block`. That closes the last ruling-free, hardware-free builder item
    this lane has: B1-B11, H1, H2, V1, F1, F2, G1, G2, G3 and P2 are landed, P1 is
    trigger-gated on Jericho's scoping clause and W1 is a standing watch.
  - **Failure modes the emulated path cannot produce** (named now so a
    RED is diagnosable): partial writes on power loss; controllers/
    firmware that report write completion falsely; BIOS boot-order and
    USB-storage-stack quirks that are chipset-specific rather than
    spec-general. Rung 5's int13h marker-write leg exercises the real
    firmware's storage stack — write-path variance on real silicon is
    a MEASURED OUTCOME recorded per-box, never a pixel-layer gate
    failure.
  - **Receipt channel: BUILT AND GATED IN EMULATION 2026-09-21.** The
    fallback named above (VGA text beacon, glyph matching, not OCR) is
    host-side software, so it was constructible without a box:
    `rung8/bm801_beacon.asm` paints the whole 256-code page plus a
    33-glyph message in two colours, and `rung8/bm801_vga.py` reads a
    captured frame by XOR against an atlas measured from that SAME
    frame — the font is never assumed, which is what has to hold when
    the capture stops being a screendump. `rung8/run_bm801_beacon_gate.py`
    holds 7/7 legs at rc=0 (carve, identity, colour-blindness, atlas
    ambiguity, noise margin, negative control, cross-boot determinism).
    Three things that were guesses until it ran: the 80x25 text cell is
    9 px wide and **all nine columns carry ink**, so the first reader's
    8-px carve confirmed the message while throwing data away — exactly
    the silent-wrong-shape failure this ladder exists to catch; glyph
    `0xDB` is **blank** in this font, so a beacon can be written in an
    invisible character; and no cell changed identity within 12 flipped
    pixels, so the channel fails by **refusing**, not by substituting a
    plausible glyph. Receipt `rung8/RECEIPT_BM801_CHANNEL.md`, which
    names what it does NOT establish: no hardware booted, and a
    photograph is not a screendump (the reader needs an exact 80x25
    pitch, so deskew and level-fixing stay open on the hardware side).
- [x] **TASK_BM802 (post-oracle)**: Fault-sensitivity map —
  systematic single-pixel flip sweep over a known-good medium, boot each
  variant, classify each offset SENSITIVE vs INERT vs RECOVERED
  (red-gradient runs prove RECOVERED is real, not a classification
  error). Serves rung 8 hardening: characterizes real-media corruption
  tolerance (USB bit-rot, bad flash sectors) BEFORE first silicon boot,
  and provides the falsifiable ground truth if a medium is ever
  suspected corrupt. DISCIPLINE (2026-09-18): this is fuzzing ON TOP of
  a known-correct baseline (BM901/BM902 oracle) — never a substitute
  for it. Poke-to-discover only says "this byte matters"; the spec +
  oracle approach gives the known-correct target to hit. File origin:
  Jericho's pixel-mapping question + web-claude's sharpening, 2026-09-18.
  - **→ ✅ MEASURED 2026-09-19; corrected and method-checked 2026-09-20.
    Manual lane, agent-free overnight sweeps, rc=0, 363 boots.** Headline:
    weighting each named region uniformly between its samples, **42.6% of the
    medium (5.82 MB of 13,640,192 B) sits on a byte where a single-byte fault
    stops the boot**; stage2 CRC table 16/16 fatal, pm-kernel 73%, executable
    stage2-code 43%, initrd 29%; the pads and the filler-sink came back
    all-INERT. Controls 3/3@stage5, both gate-on legs refused on
    `gate-MISMATCH`, all 12 coverage regions sampled, 20 timeout-recheck legs
    stayed DEAD at 3× budget.
    **Correction, and it matters:** the first map read the setup area as 0%
    fatal — that was a 512 B stride walking 16 KB of real-mode code the
    handoff never executes. Split three ways, the zero-page handshake window
    (payload 0x1f1..0x268, the bytes stage2 copies into the zero page) is the
    sharpest small region on the medium, and a **stride-1 census of it
    measured 15 of 119 bytes fatal (12.6%) where the 4-byte stride had
    reported 10% — the stride recalled 3 of those 15**, because a fixed stride
    aliases one byte per structured field. All 15 sit in kernel fields the
    loader does *not* re-pin from its own constants (`header`/'HdrS' 4/4,
    `hardware_subarch` 4/4, `setup_data` 5/8, `init_size` 2/4); mechanism and
    field-layout pinning in `rung8/bm802_header_fields.py` (rc=0). Hence **the
    per-region fatal% in this map are samples, not rates — read them as a
    floor**, and 42.6% is a floor for the critical area, not an estimate of
    it. The census's worst case is on the INERT side: `setup_data` bytes 1-3
    flip the list pointer the kernel walks (NULL → 42,240 / 10,813,440 /
    2,768,240,640, the last past this VM's 512 MB) and the boot reaches a
    prompt anyway — CRC-approved, gate-approved silent rot.
    **The initrd row made that concrete, with no boots spent**
    (`rung8/bm802_archive_local.py`, rc=0): its 17 INERT legs were re-inflated
    host-side and **all 17 ran on a `core.gz` whose own gzip CRC fails** — the
    extracted root filesystem differs from the intended one in 1 to 4 bytes at
    a named cpio entry (16 in a `*.ko.gz` this boot never loads; 1 in
    `lib/libresolv-2.28.so`), with the unpacked length unchanged. The 7
    SENSITIVE legs differ in 344 K to 11.5 M bytes. So SENSITIVE vs INERT on
    this medium tracks how far the damage cascades through the DEFLATE stream,
    not whether the data survived: decay here is not "a box that will not
    boot", it is "a box that boots something else", and nothing between the
    CRC gate and the prompt checks the archive trailer.
    Boundaries: 303 of 13,640,192 medium bytes perturbed (0.0022%), so this is
    a SHAPE, not a census; past `HANDOFF BUILT` the ladder's only signal is
    silence, which conflates hang, oops and early panic (no fatal leg printed
    diagnosis text); and **RECOVERED is structurally empty until Rung 6 is
    funded + built** — no ruling on Rung 6 here. Receipt
    `rung8/RECEIPT_BM802.md`, addendum included.
  - **Scoping finding (2026-09-19, manual lane; no boots spent): as filed,
    this sweep cannot see what it is looking for.** BM903's CRC32 covers
    the WHOLE decoded payload — sink/padding bytes included, by `px_dst`'s
    own comment — so ONE flipped payload byte anywhere (the stage2 band at
    LBAs 1-16 is the exception: it is outside the CRC and breaks the loader
    instead) is refused before a handoff exists. That is BM903's L6 RED,
    already proven twice. So on a
    gate-ON medium every offset classifies SENSITIVE and the
    SENSITIVE/INERT/RECOVERED split is vacuous. Before any budget: (a)
    build a gate-OFF fixture, rung-5's non-vacuity pattern ("neuter the
    check, show the corrupted medium now passes"), as a separate artifact
    so the gate-ON build stays the only thing that boots; (b) state the
    cost — 13,631,488 offsets × ~11 s ≈ 1,700 days of one TCG core — so
    the sweep is over NAMED regions (setup header 0x0-0x1FF, cmdline,
    sampled pm kernel, sampled initrd), never the medium; (c) RECOVERED is
    empty until Rung 6 lands — ECC is scoped
    (`rung6/BM601_ECC_SCOPING.md`, GO recommended) but unimplemented, and
    implementation must not start from that filing alone.

---

## Housekeeping

- [ ] **TASK_BM001**: Land the tree in git — HOLD GATE (Jericho's verbatim
  ratification; flagged in rung3/ANCHORS.md).
  - Scope: sources + receipts in (`boot.asm`, `pxc1_boot_codec.py`,
    `pxc1_nbd_plugin.py`, `run_gate*.sh`, rung2/, rung3/ asm + receipts);
    64 MB raws, PNG artifacts, serial logs OUT via `.gitignore` — every
    gate re-derives them.
  - **Measured gap in that last clause (2026-09-19, BM903 close-out; the
    per-blob facts re-measured 2026-09-20 — flagged, not ruled):** "every gate
    re-derives them" is true of the `*.raw`/`*.bin` build products (both e2e
    media are rebuilt at leg S0) and FALSE for two third-party blobs the
    rung-7/rung-9 chain reads directly, and the two are not alike:
    * `rung7/core.gz` — 9,260,807 B, sha256 `7f1e370dd4e489fd…`. Untracked and
      **not** ignored, so `git status` does show it. It is a gate input:
      `run_bm903_e2e.sh`'s S0 leg pins it, `bm903_pxcodec.build_payload` derives
      the 13.6 MB payload from it, and `reproduce_prereqs.sh` refuses without it.
    * `rung7/TinyCore-current.iso` — 28,135,424 B, sha256 `c465424052643dc9…`.
      **Ignored**, by `.gitignore:68 *.iso`, so it does not appear in
      `git status` at all and the original "neither ignored" here was wrong. Its
      only reader in the tree is `rung9/probe34_capture.py` (BM901's oracle),
      which no closed gate invokes — so it is a provenance input, not a build
      one: it is the only place `core.gz` can be re-extracted from, which is why
      losing it costs reproducibility rather than compilation.
    So the ratification has to add either (a) a download-and-pin step with those
    two sha256s, or (b) the blobs themselves — and (b) needs a `!.gitignore`
    negation for the ISO, not just `git add -f`, because the ignore rule is what
    hides it (`rung6/.gitignore`'s `!/evidence/refs/*.bin` is the working
    precedent). Per-blob table with readers in `rung9/RECEIPT_BM903_E2E.md`
    ("Reproducing this gate on another machine"). Rung 9 is green and committed;
    it is not yet self-hosting from git alone.
  - **A counting tool for that decision, landed 2026-09-20, and extended the same
    day with the question it was missing:**
    `bm001_landing_plan.sh` is read-only — it never touches the index — and
    classifies what is untracked-and-not-ignored under `tools/bare_metal_poc/`
    into source / evidence / data / artifact / vendor / other with byte totals,
    then lists the two vendor blobs by existence with their sha256 prefixes and
    ignore status (which is how the ISO's ignore rule above got found). The
    first run answered "how big is the pile"; it did not answer what a ratifier
    asks first, which is **which parts of the ladder exist in the commit at all**.
    So the script now buckets by directory, HEAD's count against the box's, and
    the answer is blunt. And it sweeps the *ignored* population as a second
    section, because that directory table was built from `git status`, which
    cannot show an ignored file at all — see the two bullets below the table:

        dir        in-git  untracked  of-src
        rung2           2          7       5
        rung3           0          2       2   WHOLLY OUTSIDE GIT
        rung4          11         13       5
        rung5          14         35      25
        rung6          74          8       1
        rung6_5        93          0       0   landed, nothing waits
        rung7           0         20      13   WHOLLY OUTSIDE GIT
        rung8          12          1       0
        rung9          80          6       2
        (top)           6          6       5

    **292 files are in HEAD at the commit this table was re-taken from; 98 are
    not, 58 of those source** — and both figures move as landing proceeds, which
    is the point of the tool rather than the numbers. The afternoon snapshot of
    the same day read 287 in HEAD with `rung6` at 71 and `(top)` at 4, the first
    night reading after it 289 at 72 and 5, and the next 291 at 73 and 6. Every
    file between those readings is a record this row landed, and the newest of
    them -- the one that took rung6 to 74 and the total to 292 -- is the
    lower-rungs record written below, so this sentence is the fourth time the
    delta has been this lane's own commit. `(top)` has stopped moving at 6, and
    the untracked side has not moved all
    day -- 98 then, 98 now, because everything written here went in
    as a tracked file. `rung3/` and
    `rung7/` have zero tracked files, so `git archive HEAD` does not create those
    directories at all — the two `mkdir`s in this row's clean-tree recipe are not
    a nicety, they are the absence of a rung. And `rung6_5/` is fully landed
    because this lane committed its own way through it, which is the pattern the
    other eight directories have not followed yet. The script also names
    **15 gate entry points outside the commit** (`run_*` and `*probe*`):
    rung 1's `run_gate.sh`, rung 5's ten (`boot_probe.sh`, seven `probe_*.py`,
    `run_gate5_persist_probe.sh`, `run_probe_stub.py`), rung 7's
    `boot_probe.sh` and `throughput_probe.py`, and two
    `rung9/bm905_*_probe.py` that belong to another lane and are listed because
    the tool counts the tree, not the author. A reviewer who lands nothing
    cannot re-derive any of those rows. The listing also checks the
    mirror case (tracked in HEAD, absent from the box): currently none, printed
    either way, and now a third state as well — tracked, present, and differing
    from HEAD — because a green gate can produce that one too. That state has
    just read empty on the re-run: `rung4/rung4_medium.png`, the one file the
    afternoon listing carried, matches HEAD's blob again (66,625 B, sha `a840b7ee…`,
    rewritten on this box at 18:56:33 by a step this row did not measure, so the
    row records the state and not a cause). The reporter prints that listing only
    when it is non-empty, and the pristine run reproduces the same class in six
    files, below. Today's live
    totals: **98 files — 58 source (193 KB), 17
    artifact (86.2 MB), 18 data (6 KB), 4 matching no rule (rung7's
    extension-less `iso2`/`iso3`/`kernel` captures and
    `rung6/fixtures/*.crc`), 1 vendor visible in `git status`, 0 evidence** —
    and 0 evidence, since the day's clean-tree records all landed. Prose counts
    of that set rot (this file said 76, then 99, and the 99 was already one too
    many because the script counted itself while untracked); the script is re-run
    in seconds and its own dated snapshots are named so as to be excluded from
    its counts — writing down a number cannot change it.
    **That last clause was false for about an hour, and the second run of the
    new section below is what caught it.** The exclusion covered the file LIST,
    not the tracked corpus that section greps for names, so once the snapshot had
    recorded the largest-five listing, the next run read those five names back
    out of the snapshot and re-classified one of them as cited — 172/496 became
    173/495 because the previous run had been written down. The corpus now drops
    the same filenames the LIST drops, and the run after the fix returned to
    172/496. ROADMAP.md itself stays in the corpus; it is the document under
    ratification and its citations are real, so this paragraph was written
    without naming a single previously-unspelled basename, and the promise that
    followed -- that the figures below therefore still reproduce -- went false
    anyway two hours later, for a cause the paragraph could not have met: not the
    the tool writing itself down but this row landing a record. The re-verifier
    and its evidence file were untracked when that was written and are tracked
    now, so
    they are corpus, and the record names two ignored transcripts, which moved
    the split to **174 spelled / 493 unspelled**. Checked rather than assumed:
    the 2,745 B the spelled total gained is exactly those two files, 1,355 B and
    1,390 B. A corpus that grows when this row lands is the one property the
    exclusion cannot fix, so the pair is printed live by the script and the
    numbers here are the ones in force when written.
    `bm001_landing_plan_2026-09-20.txt` is that snapshot, the sixth copy taken
    today (its own header names each earlier one and why it was superseded), with
    the reading above spelled out and the day's own delta in it. It records the
    numbers as of `60ced60c`; the two above it, 292 and 174/493, are the same
    script at this row's own later commits. Its own closing addendum records that
    difference rather than editing around it, and starts by catching this file
    out at its own commit: the body it pastes is 127 lines, not the 125 the
    sentence above it promises, and the run re-taken at `12789220` is 129 with
    `rung6` at 74 and check 4 at 88 files / 256 citations.
    - **The first of the two: the ignored population, which the whole directory
      table above structurally cannot see.** It was added to the script the same
      evening and re-ran in well under a second, and the answer is that the pile
      `git status` reports is a fraction of the pile that is absent from a clean
      checkout: **668 ignored files and 1,790,064,977 B under the ladder, against
      the 98 files and 86.2 MB of untracked artifact the table has been counting
      all day** — seven times the files, twenty times the bytes. The headline
      artifact figure in this row has therefore been describing the smaller half.
      The script splits the 668 by whether any tracked file spells the basename
      out (172 files, 962 MB, do; 496 files, 828 MB, do not -- 174 and 493 on the
      latest re-run, for the corpus reason just given above) and prints that
      second line as a cleanup candidate list, not a verdict, because a producer
      that composes its filename from a variable hides its own outputs from the
      test either way. (It is a live count, and it has moved twice for one cause:
      the 668
      included one `__pycache__` entry that an ad-hoc `import doc_ref_audit` had
      created and nothing else needed, so deleting it made the next run report 667
      and 1,790,052,236 B -- and that entry came back at 19:42, from a later
      import of the same kind, and removing it again is what this row's numbers
      were taken on. The reporter itself writes no such file; running it twice
      gives byte-identical output. So the number to distrust is the pile, not the
      split: any reader who has imported a ladder module into another script
      should expect 667 plus however many caches that left behind.)
    - **The second: what the 668 are, and why they are a different decision from
      TASK_BM001.** They are not a missed backlog; they are what the ladder's own
      ignore rules delete on purpose — the counting is over the eight rules that
      fire most (`logs/` at 142 files, `*.log` at 100, rung4's `dbg_*` at 81,
      `*.bin` at 56 plus 29 more under rung5, `__pycache__/` at 44, rung5's
      `serial_*` at 37, rung6_5's `/captures/` at 30), i.e. the boot captures and
      serial dumps every closed gate re-derives and then discards. The consequence
      for the ratifier is a scope correction, not a new task list: **landing the
      98 leaves all 668 exactly as invisible to a clean checkout as they are
      today**, so a reviewer deciding the 98 is deciding the reproducibility of
      rows whose largest inputs are governed by a separate decision — which of
      them to un-ignore, and which to pin and fetch. The ISO in the vendor table
      above is that decision in miniature: one file, ignored by a repo-wide rule,
      and the only reason it was ever noticed is that the script asks about
      vendor blobs by existence rather than by `git status`.
    - **The two tools meet in the script, and the result re-cuts the question.**
      `bm001_landing_plan.sh` now feeds `doc_ref_audit.py --list-outside` through
      its own classifier, so the files that a record names and the commit lacks
      appear as classes rather than as a filename list, and then as the cut the
      classes cannot make: **of those 88, 30 are among the 98 TASK_BM001 is asked
      about, 50 belong to the ignored population, and 8 are outside
      `tools/bare_metal_poc/` altogether** -- `rung9/RECEIPT_BM905_INPUT_MAILBOX.md`
      pointing at another lane's `output/bm905_*` and
      `.builder_queue/BM905_MANUAL_LANE_STATE.md`, which no commit that lands the
      ladder can deliver whatever it decides. So the ratification's reach over the
      prose's promises is barely a third, which is the same scope correction the
      ignored section made, seen from the other end. Two checks came out of
      building it: the vendor bucket's bytes are exactly `core.gz` plus the
      ignored ISO, so the audit and the script are counting the same files, and the
      section cannot report a quiet zero -- pointed at an audit that will not run
      it prints ERROR and exits 1, and pointed at one that runs and finds nothing
      it prints one explicit line instead of a blank table. Neither count here is
      snapshot-proof, which is a claim this row made and has now refuted twice.
      When it was written the split was 87 files and 240 citations against 241
      with the day's snapshot file set aside -- one mention of `run_gate.sh`, a
      file already in the list -- so the file count looked like the stable number
      and only the citations moved. The first refutation was the lower-rungs
      record: measured by exclusion, it took the split from 87 files to 88 and
      the citations from 244 to 254, and the one new file is `rung2/stage1.asm`,
      named there because it is one of the four sources the commit lacks and the
      run has to copy in. The second is this paragraph. It cites the same
      `rung2/stage1.asm` to make its point, which tripled that file's citations
      and pushed the total to 256, and it means the exclusion no longer
      reproduces 87 -- with the record set aside the sweep now answers 88 files /
      246 citations, because ROADMAP itself keeps the claim alive. **A name
      enters this list the first time any prose speaks it and leaves only when
      the file lands or every mention goes, so the proof a record offers is that
      it re-derives, never that it is stable; the snapshot-proof number in this
      row is the one that counts files in HEAD, and even that moved from 291 to
      292 when a record landed.** The counts above are today's and this file is
      the only place they are written down; the script
      re-derives every one of them in a second, which is where a reader should
      check them rather than here.
  - **And the prose itself is now checked: `doc_ref_audit.py` (landed the same
    day).** A citation is a gate on paper. The tool sweeps every `*.md` and
    `*.txt` under the ladder -- ROADMAP, the receipts, the
    scoping notes and this day's clean-tree records -- pulls each backticked
    path out, and resolves it first against the citing file's own directory (so
    a `../x` means what a reviewer would click), then the ladder root, the repo
    root, every rung directory and, for a bare name, the whole project. It runs
    end to end in about two and a half seconds, and it prints the files it
    refuses to read --
    two guest-memory dumps that carry a `.txt` name and are not prose -- because
    a skip that is not stated is the conditional this ladder forbids.
    What it turned up first was not a phantom file but a **stale claim in this
    row's own checkbox line**: it still described BM653 as shipping the
    design's five files including bm653_consts.py, while `RECEIPT_BM653.md`
    records that module as deviation (a), folded into `bm653_pxcodec.py` "so both
    gate constants come out of one emitter and cannot disagree". The receipt was
    right and the summary drifted; the checkbox is corrected and the name
    de-backticked so the audit reads it as history, not a promise.
    **Then widening the sweep to the day's own evidence records found two real
    dead pointers in prose written hours earlier, both this lane's.**
    `pristine_rows_table.txt` pointed at two sibling records with a two-dot-up
    path that lands one directory *above* the ladder -- correct depth is three,
    and the record now spells both paths out from the ladder root instead, which
    is the form the audit can honour. And
    `bm802_pristine_preflight.txt` cited bm802_preflight_rows.txt as if the file
    had landed: `run_bm802_sweep.py` routes preflight rows into its own file
    *relative to whichever tree runs it*, so those 12 rows were written inside
    the scratch tree and deleted with it. The record now says so -- the 12 rows
    exist only as the table it carries -- and keeps, separately, the claim the
    routing was actually for: the repo's real `bm802_sweep_rows.txt` and
    `bm802_sensitivity_map.txt` are untouched by a preflight.
    The same evening it grew a second and a third check, and the second paid for
    itself on its first run. It reads both spellings of a numbered pointer --
    `rung5/stage2.asm:37` inline and "foo.sh ... line 212" at a distance -- and
    range-checks each against every file the token could mean, printing the cited
    line beside the claim so a reader can judge what the tool only suspects. On
    its first pass it flagged the 238 in
    `BM650_SCOPING.md`'s R-SCOPE-3 paragraph as out of range -- against
    `rung2/stage2.asm`, which has 108 lines, because the note cites stage2.asm
    bare and three files in this ladder carry that name. The claim was sound and
    the citation was under-qualified: rung5's `stage2.asm` does have its `cli` at
    37, its `sti` at 42, its bounce copy at 212-213, its int-13h at 231 and its
    .wr_ok label at 238, which is the whole ordering argument of R-SCOPE-3. The
    note now names the rung at all five of its numbered cites, and
    `RECEIPT_BM651.md`'s bare `stage2.asm:94` prints all three candidate lines
    rather than an arbitrated one. And the tool answered its own
    first false pointer by refusing to pick silently: candidates() returns every
    match, a number in range in any one of them is not called stale, and the
    third check prints the bare names that are ambiguous -- 23 of them -- as
    information, not as failures, because a citation that lands on one of
    several real files is not a broken citation and scoring it as one would
    train a reader to ignore the list.
    What the numbered pass confirmed is worth stating, because two of its
    targets are the defect this row keeps for the next: `bm903_pristine_pair.txt`
    cites `bm903_mkimg_px.py:133` and `bm903_pxcodec.py:124`, and those lines
    still read `if step1_s1.exists():` and the `... if ... .exists() else ...`
    fallback -- the two conditionals, pinned by line number in a landed record,
    so the finding survives the deletion of the scratch tree it was made in.
    Its remaining unresolved tokens are all judged, not hidden (and none of them
    is backticked in this bullet, because a backtick is exactly the promise the
    audit checks): three are the
    cpio entry lib/libresolv-2.28.so *inside* `core.gz` (right about the guest,
    absent from the host; a fourth mention of it, lower in this very bullet, is
    left unbackticked for exactly that reason), one is
    run_gate6.sh, a name `DESIGN_EXEC_FROM_DATA.md` proposed before
    implementation decided it, three are rung5_nv.raw, rung5_nv.png.json and
    stage2_nv_padded.bin -- intermediates `run_gate5.sh` builds for its
    non-vacuity leg and deletes on its own line 212, which is why
    `RECEIPT_RUNG5.md` can name them and no checkout can open them -- one is
    bm802_preflight_rows.txt, the preflight rows the paragraph above already
    accounted for (written relative to the scratch tree, deleted with it), one is
    the
    per-run payload file BM903's guest-provenance receipt says travelled through
    the host side of the shared 9p mount, a mailbox that exists only while a
    probe runs, and the last
    two are the bm653_consts.py mentions in the BM652 design table and in
    deviation (a) of this row's receipt, which is history doing its job.
    **A fourth check, added the same night, asks the question the other three
    cannot:** a citation can resolve on this box and still name a file the commit
    does not carry. Cross-referencing every resolving token against
    `git ls-files`, the tool now prints the files the ladder's own prose promises
    and a clean checkout cannot deliver, each with its citation count and the
    records that cite it — rung 7's `core.gz` far ahead of the rest, then the
    ancestor build products rung 6, 6.5, 8 and 9 read as landed, then rung 1's
    gate script and, further down the list, whole receipts of other rungs. A bare
    name counts once per file it
    answers to, which is why `stage1_const.inc` is several lines and not one.
    This is the prose counterpart of the landing plan's untracked listing: the
    plan says which files sit outside the commit, and this says which of them
    the records *promise*, so "drop it as scratch" and "five receipts cite it"
    stop being the same line in a decision. It is informational like check 3, and
    for the same reason — the citation is not wrong here, the gap is TASK_BM001's
    to close, and scoring it as a broken pointer would bury the eleven that
    really are. The counts are the tool's to print; what is worth fixing here is
    that `git status` never showed this population either, exactly as it never
    showed the ignored one.
    That is the tool's contract, printed in its own
    docstring: **UNRESOLVED is not WRONG** -- it is a list for a reader, and the
    alternative, a check that silently skips the lines it cannot parse, is the
    conditional this ladder already rejected. The counts are the tool's to print
    and not this bullet's to quote -- it is run in seconds, and a number written
    down here is a number that can rot on the next edit, as the landing plan's
    did. What does not move: the eleven unresolved tokens are the eleven above,
    and no line-number citation in the ladder's prose points outside its file.
  - **The promise those records make is now tested by one command, and it held.**
    `pristine_reverify.sh` re-runs the closed rows in a tree built by
    `git archive` of a sha named on its own first line -- 13 legs in its default
    `upper` mode, from the
    ancestor build products through BM903, BM902, the four BM802 checks, BM602,
    BM651 and BM653 -- and another lane can commit
    mid-run, so this is the difference between verifying a commit and verifying
    whatever the branch happened to be. The lower rungs are its other mode, below. It refuses to start on a scratch root that
    already holds something, refuses to start under 4 GB free on that device,
    checks `core.gz` against its pinned sha before copying, and confirms
    `reproduce_prereqs.sh` actually arrived before running a leg that depends on
    it; a leg whose log contains the disk-full phrase is reported ENV-FAIL, not
    FAIL. Each of those refusals was exercised rather than asserted: a scratch
    root holding one file, and a device under the floor, each abort with its own
    FATAL line and rc 1 before a tree is built, and the disk-full pattern matches
    the run-1 log it was written for. The first run at `1175b2ef` went RED twice
    and neither was the ladder:
    one leg's expected sign had been invented by the driver and inverted the
    verdict of a check that prints `[BITES]` and exits 0, and the second ran out
    of disk mid-gate at 2.5 GB free. Both mechanisms are gone. The second run, at
    `1de7ee86`, was GREEN across all 13 legs in 27 min 14 s, with each gate's own
    marker line quoted in
    `rung6/evidence/cleanroom/pristine_reverify_at_1de7ee86.txt`.
  - **And it measured the thing no gate reports: a pristine tree does not stay
    pristine.** After the legs the driver re-archives the same sha and diffs the
    two trees. **Six tracked files came back different**, and every changed line
    is a duration, a spinner or a timestamp -- `rung6/bm602_fixtures.json`'s two
    `*_seconds` fields, the per-leg seconds column in BM653's two landed
    `e2e_pass_*.txt`, two of its boot transcripts' spinner characters, and
    `rung9/bm902_diff_receipt.txt`'s own `date:` line. No verdict, sha pin, fault
    offset or gate value moved. So this row's standing advice to the ratifier
    sharpens: a reviewer who lands the ladder and then runs a gate will see dirt
    that is not a mistake, and BM653 overwrites evidence it landed under
    `rung6_5/evidence/` while doing it -- **`git status` cannot be the test that
    the landing worked**, which is the same defect `rung4/rung4_medium.png`
    showed from the other direction. (The record of this run is itself a prose
    file the audit sweeps, and for a few minutes it made the unresolved count
    twelve: one backticked path at a scratch log no checkout carries. It is
    de-backticked now, so the eleven above are still eleven, and the count is the
    tool's to print rather than this bullet's to quote.)
  - **A second class of missing input, measured 2026-09-20 while verifying
    BM653 from `git archive HEAD`:** a clean checkout lacks not only the two
    vendor blobs but every *ancestor build product* a descendant gate reads as
    landed — `rung9/bm903_stage1.bin`, `rung9/bm903_px_payload.bin`,
    `rung6/bm602_px_payload.bin`, `rung6/fixtures/`. All are regenerable, and
    the recipe is now measured: pinned `core.gz` + `rung9`'s
    `bm903_mkimg.py`, `bm903_mkimg_px.py`, `bm903_pxcodec.py` + `rung6`'s
    `bm602_pxcodec.py` and `bm602_mkimg.py` reproduce payloads
    **sha256-identical to the lane's** (`e6ebe1ab…`). The one thing that is
    *not* stable is a rung's working dump: BM653's identity stage compared
    against `rung9/bm903_px_*_leg0.bin`, which rung9's own gate rewrites and
    git does not carry, so that row now pins its references under
    `rung6_5/evidence/refs/` with a sha256 check at the point of use
    (`bm653_refs.py`). Two rules fall out for the ratification: **land the
    dump or pin it in the row that consumes it**, and **state the build
    order** — "every gate re-derives them" is only true of artifacts a gate
    re-derives itself.
  - **The class is not BM653-local, measured the same day.** BM602's identity
    stage reads the same three `rung9/bm903_px_*_leg0` dumps. It now pins their
    sha256 *and* reads a landed verbatim copy from `rung6/evidence/refs/`
    (manifest `refs.json`, tracked via a `!/evidence/refs/*.bin` negation). Both
    sides measured in a `git archive HEAD` tree given the ancestor recipe above —
    which supplies `bm903_px_payload.bin` and `bm903_stage1.bin` but, being a
    clean tree, none of the `bm903_px_*_leg0.bin` dumps: before the fix the row scores
    `IDENTITY: GREEN 23 RED 2`, both REDs "no landed reference to match", and
    ends `BM602_RUN_STATUS=RED (1 legs)` only after paying for all seven boots;
    after it, `GREEN 15 RED 0` with `IDENTITY: GREEN 32 RED 0` (was 29), and that
    run's 18 handoff dumps are byte-identical to the lane's, predictions too once
    the two host-replay timing fields are stripped. Same tree, one variable.
    One rung over, `rung8/bm802_fixture.py:108` guarded its stage1 comparison
    with `if (RUNG9/'bm903_stage1.bin').exists():` — the same quiet disappearance
    — and it is now a pin on the bytes *that rig assembles itself*
    (`STAGE1_SHA`), which needs no ancestor file and additionally fires on a
    nasm or flag change: 5/5 legs ok in 0.8 s, and `bm802_pin_bitest.py` proves
    the pin bites by rebuilding against a deliberately wrong value.
    Where a descendant reads an ancestor's working file, the ratification has
    exactly three acceptable answers: regenerate it first, land it, or pin its
    sha256. What it must not accept is a conditional. And the two cases differ:
    `bm903_stage1.bin` is a build *input* a named command regenerates, while the
    `_leg0` dumps are gate outputs whose only regeneration is a full rung-9 gate
    run — inputs need a recipe step, references need to be landed.
  - **The recipe is a script now, and a closed row was run on top of it (same
    day):** `tools/bare_metal_poc/reproduce_prereqs.sh` is the paragraph above as
    one command with its own verdict. It refuses (exit 1) unless `rung7/core.gz`
    is present and matches its pinned sha, runs the five ancestor steps, then
    re-pins the six byte landmarks the closed rows measure against and hashes the
    six generated-but-tracked files before and after so a regeneration cannot
    silently rewrite the checkout. Measured cold in a fresh
    `git archive HEAD tools/bare_metal_poc` tree given nothing else but
    `core.gz`: **`PREREQ_STATUS=GREEN`, 35 s, 12/12 legs, no boots, no tracked
    file moved** — and `run_bm653_e2e.sh` over exactly that tree then came back
    **2 of 2 passes clean, 372 s, `IDENTITY: GREEN 49 RED 0` both passes, 18
    dumps landed, `BM653_RUN_STATUS=GREEN`**
    (`rung6_5/evidence/bm653/prereq_pristine.txt`). That record also holds the
    four refusal tests — wrong `core.gz`, absent `core.gz`, a flipped landmark
    pin, a hand-edited `.inc` — each of which exits 1 and names the step that
    owns the file, because a check that only prints OK is the same defect class
    as the conditional above. **Rung 9 — the producer of those reference dumps —
    then ran over the same tree: `42 pass, 0 red` ×2, both RED legs firing on the
    same offset (`0x244`) and the same host/guest CRC cross-check, ~3 min a
    pass** (`rung6/evidence/cleanroom/bm903_pristine_pair.txt`). That run pays
    for the pinning work rather than merely repeating it: the three
    `bm903_px_*_leg0` dumps rung 9 rewrote there hash `bc2431d7be0ab1d2`,
    `30cd829f2a88c80c`, `935d5fe1c23f878e` — the exact values BM602's and BM653's
    `evidence/refs/` pin — so the landed references are proven to be what their
    producer emits from the commit, not a copy of one lucky run. **Rung 8 was
    then touched in the same tree** — four host legs rc=0 (its selftest's
    equivalence leg asserts the pristine `bm903_medium_px.raw` byte for byte over
    13,640,192 B), plus a 12-boot preflight whose rows agree with the landed 363
    on every verdict, fault offset and computed gate value, 11 of 12 on stage,
    the twelfth being the autologin race (`rung8/bm802_pristine_preflight.txt`;
    the 319-boot map was planned `--dry` and deliberately not re-run). **Then
    rungs 6 and 6.5's other row followed in the same tree:** BM602 twice
    (`GREEN 15 RED 0`, `IDENTITY: GREEN 32 RED 0`, `BM602_RUN_STATUS=GREEN`, 47
    `[PASS]` lines, 6.8 and 8.3 min), BM651 once (`GATE651 PASS`, 18
    predictions fixed before the first boot, 7 boots, 144 s), and BM653's pair
    again — same two clean passes, same `IDENTITY: GREEN 49 RED 0`, and its 18
    landed dumps byte-identical to this lane's by `cmp`, 613 s wall against the
    372 s above. The 241 s is timing, not
    verdict: 115 s of it is the boot legs (pass 1's `exec_green` drew 4 autologin
    attempts, 155.3 s, where the cold tree drew 2 and 59.1 s; pass 2's drew 2
    against 1, partly offset by `exec_image_repaired` costing 37.6 s less), 22 s
    is the two identity legs at 29 s against the cold record's 18 s, and the rest
    cannot be attributed because that record does not time the static legs
    individually. So **five closed
    rows** — BM903, BM602, BM653, BM651, BM802 — now run against the commit plus
    one vendor blob rather than against this box, all in one tree, one at a time;
    the table is `rung6/evidence/cleanroom/pristine_rows_table.txt`. Two gaps it
    exposes rather than fixes: `rung7/`
    carries no tracked file at all, so a clean checkout has no `rung7/`
    *directory* to put `core.gz` in, and the vendor-blob download/pin step is
    still TASK_BM001's to ratify.
    (That hand-run became a script, and the script has since been run again at a
    later commit with the dirt it leaves measured too — two bullets above.)
  - **The lower rungs, measured in the same way (2026-09-20, immediately after):
    `rung6/evidence/cleanroom/lower_rungs_pristine.txt`.** Rungs 1-5's gates went
    into a fresh `git archive HEAD` tree -- 6.5 MB, no `reproduce_prereqs.sh`, no
    vendor blob, since those rungs build everything they measure from their own
    `.asm` and `.py`. **Rung 4 `GATE PASS` (157 s) and rung 5 `GATE5 PASS`
    (153 s), each emitting the CRCs and checksums its own receipt records**
    (`E1AE9612`/`77B5`, `758F5EC8`/`ECB8`, `329CD470`/`IMG2 7880D4BA`/`43E6`), so
    two more rungs are reproducible to the serial line. **Rung 2's gate is in the
    commit and does not run from it** -- `run_gate2.sh` is tracked, `stage1.asm`,
    `stage2.asm`, `rung2_codec.py` and `RECEIPT_RUNG2.md` are not, and the first
    command dies with `nasm: fatal: unable to open input file 'stage2.asm'`. Copy
    those four in and the same tree gives `=== GATE PASS ===` in 43 s with the
    receipt's `CKSUM=4541`/`SUM=4640`; rung 1's gate (untracked itself, with five
    root files) passes in 35 s the same way, twice, identical summary blocks.
    That is the decision package's sharpest fact: **a commit can carry a gate
    that fails on its first command in the only tree it defines**, and landing
    4 files turns it green. Rung 3 has no gate script at all, tracked or
    untracked -- its closure was a hand-run probe -- so there is nothing there
    for the commit to be missing beyond `ANCHORS.md` and `memprobe.asm`.
  - **That hand-run is now the driver's other mode, and it re-paid itself at
    `88562ec0`.** `bash pristine_reverify.sh lower` runs five legs in 6 min 26 s,
    GREEN, in
    `rung6/evidence/cleanroom/lower_rungs_pristine_at_88562ec0.txt`: leg 0 is the
    rung-2 finding as a check that has to bite (its contract is to exit 0 when
    nasm reports the missing input and to go RED if the commit ever grows the
    sources, because that would make the claim above stale), then the nine named
    files the commit lacks are copied in and all four gates run. Every marker
    matches the hand-run line for line -- `5F3B`/`5E99`, `4541`/`4640` with
    `absence: 0 of 129`, `E1AE9612`/`77B5` and `758F5EC8`/`ECB8`,
    `329CD470`/`7880D4BA`/`43E6` -- and two walls are identical to the second.
    Rung 1's leg is the one row that takes a host socket, so the mode refuses it
    while another `nbdkit` is alive and records a named SKIP in the status line
    rather than dropping it; none was alive, and `skips 0` is a measurement.
    The dirt step ran here too and came back with **one** tracked file,
    `rung4/rung4_medium.png`, at the same 66,572 B against HEAD's 66,625 B that
    the landing plan flagged: the tree read clean when this started and one green
    gate later it did not, which is the same finding as above seen arriving from
    the other direction.
  - **Sweep for the rest of the class, same day: it survives only in rung 9,
    where this lane may not write.** Every `exists()`-guarded site under
    `tools/bare_metal_poc/` was read — 49 across 22 `.py` files
    (`grep -n -E 'if.*\.exists\(\)|if os\.path\.exists' --include='*.py'`).
    Three are the conditional this
    bullet forbids, all in the read-only tree:
    `rung9/bm903_mkimg_px.py:133` (`if step1_s1.exists(): assert s1 == …` — the
    "same stage1 in step 1 and step 2" check, vanishing in a clean tree) and
    `rung9/bm903_pxcodec.py:124-125` (missing stage bins fall back to
    `b'\0' * 512` / `b''` as the codec selftest's input). Both are
    self-healing in practice — `bm903_mkimg_px.py` writes `bm903_stage1.bin`
    unconditionally three lines above the first one, and
    `reproduce_prereqs.sh`'s step order guarantees the file for the second — so
    neither is a live false-green today; they are the same loaded gun, filed
    rather than touched, because rung 9's tree is a read-only input to this
    lane. The rest are legitimately conditional: scratch/log/transcript
    polls, resume markers, and one — `bm653_pxcodec.py:243` — that reads the
    on-disk copy *in order to assert* it equals what the builder just assembled,
    with `None` meaning "no stale copy to disagree with". One shape was chased
    down and dismissed rather than patched: `norm()` in both identity stages
    returns `None` when the `.norm` sidecar is absent, and its callers
    `continue` — but the normalizer writes that file whenever it exits 0, and it
    already reports its own failure, so the branch is unreachable rather than
    quiet, and hardening it would add a gate string with no test behind it.
    Nothing in rung 6, 6.5
    or 8 needs a change, so BM602 + BM653 + BM802 close the class for the
    writable tree.
  - **Inventory of the rest (same day; the numbers re-derived from the tree on
    2026-09-20, and stale by construction — run the script above, whose
    per-directory table now carries the source counts, so they are not repeated
    here).** Of what is not in git, **58 files are source or document** and the
    rest are artifacts, generated data and one vendor blob; the heaviest single
    entry is a 67 MB `rung4/probe2_medium.png`, so the artifacts weigh 86.2 MB
    against the sources' 193 KB. Reproduce with `bash bm001_landing_plan.sh`, or
    by hand with
    `git status --porcelain -uall tools/bare_metal_poc | grep '^??'`.
    The point of the list is not its arithmetic:
    among the two untracked `rung3/` files is **`rung3/ANCHORS.md`, the very
    document this row's own scope line cites as where the HOLD gate was
    flagged**, and the top-level five the scope line names by hand (`RECEIPT.md`,
    `boot.asm`, `pxc1_nbd_plugin.py`, `pxc1_boot_codec.py`, `run_gate.sh`) are
    still untracked at this commit. So the scope line names only part of the
    set, and its "64 MB raws, PNG artifacts, serial logs OUT" framing understates
    it — by the two whole rungs above, and by the fact that `git add -A` at the
    end of a landed tree would take the 86 MB of artifacts with it.
  - **The same defect was inside the decision package itself; the fix landed in
    the reporter, not in the decision (`609c46be`).** Every number in the two
    bullets above came out of `git ls-files` and `git status --porcelain` —
    questions about this box's **index**. A clean checkout answers to HEAD, and
    three lanes share this index, so one `git add` by another lane retired a
    promise recorded here with no commit existing to keep it. Measured rather
    argued: a single `git add -N tools/bare_metal_poc/rung2/stage1.asm` against
    a *copy* of this box's index (`GIT_INDEX_FILE=/tmp/idx_probe`; the real
    index was never written — the file reads `??` still) moved five numbers off
    the old reporter at once:

    | what it claimed | clean tree | index with that one `-N` entry |
    |---|---|---|
    | rung2 in git | `2 of 9 in git` | `3 of 9 in git` |
    | source bucket | 59 files / 214,882 B | 58 / 209,768 B |
    | untracked total | 99 | 98 |
    | decision split | 30 among the 99 · 8 outside the ladder | 29 among the 98 · **9 outside** |
    | tree dirt | clean | "differing from HEAD: `stage1.asm`, here 5114 B, HEAD ? B" |

    The last row is the one that would have cost a reviewer the most: an
    intent-to-add entry has no blob, so `git diff --cached --diff-filter=ACM`
    called a file HEAD does not carry a *modified tracked* file — a dirt claim
    about a clean tree, with `HEAD ? B` for the side that does not exist. The
    "9 outside" row is the second-worst: the old code compared repo-relative
    `ls-files` output against ladder-relative paths, so a ladder file could be
    reported as belonging to another lane's decision.
    The fixed reporter reads `git ls-tree -r --name-only HEAD` and `find`, and
    it keeps the index as what it is — a separate fact with its own section:
    "Staged in this box's index, carried by NO commit". Proof of the fix is a
    diff, not an assertion: the same probe index run against both versions
    leaves the new reporter byte-identical to its own clean run except for that
    section. And the clean-tree equivalence holds in both: 292 files in HEAD, 98
    untracked-and-not-ignored, 88 files / 256 citations outside the commit,
    split 30 / 50 / 8, and 765 files on disk that HEAD lacks (667 of them
    ignored). One consequence for the recipe one bullet up — `git status
    --porcelain -uall | grep '^??'` reproduces the 98 only while this index
    happens to agree with HEAD, which in a three-lane box is a coincidence with
    a shelf life.
  - **One commit later (`45eb5d15`): the package counted the backlog and never
    spelled it, so it could not be acted on.** Every bucket above is a number;
    the only place the 98 files were ever *listed* was the `git status` recipe,
    which the preceding bullet had just proved unreliable here. So `--names`
    prints a bucket — `untracked`, `cited-untracked`, `cited-ignored`,
    `cited-elsewhere` — one repository-relative path per line on stdout and its
    weight on stderr, which makes the ratification a command rather than a
    transcription. Measured at this commit (stale by construction, as every
    number here; re-run `bash bm001_landing_plan.sh --names cited-untracked`):
    the 30 promised files weigh 94,693,071 B, and **three of them are
    94,605,608 B of that** — `rung4/probe2_medium.png`, `rung7/tc_medium.png`
    and the vendor `rung7/core.gz`. The other 27, which is the actual text of
    rungs 1–5 and 7 plus their receipts, come to 87,463 B. That is the shape of
    the decision: landing the promise is 87 KB of source and prose, or 87 KB
    plus two regenerable media and one third-party blob.
    Cross-checks, both run rather than asserted: the `--names` byte sums equal
    the ones the report's own split lines print, bucket for bucket (30 →
    94,693,071 B, 50 → 82,802,511 B, 8 → 25,261 B), and all four lists are
    identical under the same copied-index probe as on a clean one — the naming
    path reads HEAD and `find`, so a staged file cannot vanish from the set a
    commit does not carry. The dirt line got exercised by this change arriving:
    while the script was modified the report named it (`here 24162 B, HEAD
    20870 B`), and one commit later it reads "this tree is clean" again.
    And the self-reference this row keeps recording kept: spelling those three
    heavy files here is exactly what moved check 4's citation total from 256 to
    259 under this edit, with the file count unchanged at 88. A record that
    names what it measures is measured by the naming.
  - **`ef52b414`, same evening: the four buckets above are the citation cut, and
    the ratification also has a class cut, which `--names` now spells too** —
    `source`, `evidence`, `data`, `artifact`, `vendor`, `other`, so the sentence
    three bullets up called "58 files are source or document" is a list rather
    than a price. `--names source` is then the plainest option on the table: 58
    files, 197,795 B, which is 0.2% of the 95,688,929 B the untracked set
    weighs. Verified as a partition, not a sample: the six class lists joined
    are byte-identical to the 98 paths `--names untracked` prints, and each
    list's count and byte sum equal the row it came from. A class table and a
    name list that disagreed would be the same silent-blank failure this ladder
    rejects everywhere else.
  - **What that one bucket buys, measured rather than claimed** (derive it with
    `comm -12 <(--names source|sort) <(--names cited-untracked|sort)`; the
    numbers below are that command at this commit). Landing the 58 source files
    takes `rung3` from 0 to 2 files in the commit and `rung7` from 0 to 13, so
    **no directory under the ladder is wholly outside git any more** — the two
    rows the table above flags as "`git archive` does not create it" are exactly
    the two it clears. All **15 of the 15 untracked gate entry points** are in
    it, which retires the reviewer's "cannot re-derive those rows at all"
    without shipping a byte of media. And it answers 22 of the 30 promises the
    prose makes about this scope; the 8 it leaves are the two regenerable media,
    the vendor `core.gz`, and five small records — i.e. the residue is the part
    of the decision that is not a `git add`, and it is 99.9% of the weight.
    197,795 B for that, against 94,693,071 B for all 30.
    Re-deriving the four bullets above at this commit, only one kind of number
    in them moved: check 4's citation total went 256 → 259 → 260 as they each
    spelled a name, while 88 files outside HEAD, the 98 untracked, the 30/50/8
    split, 292 in the commit and 765 on disk that it lacks all held. The
    citation count is the one measurement a record changes just by being written
    down; the others only change when the tree does. This sentence says so
    without spelling a filename, and 260 is what the audit prints with it in the
    corpus and with it out — the fixed point lasts exactly as long as nobody
    names a thing.
  - **`028f2281`, same night: the reporter let an empty measurement read as a
    verdict, in the one tree this row is about.** Every bullet above tells a
    ratifier to reproduce with this script, and a clean checkout is what
    `git archive HEAD` hands you — so the script was run inside exactly such an
    extraction. Measured there, at the commit before the fix: 47 lines out, exit
    1, and the failure notice on line 46. Above it, a finished-looking report in
    which every count was 0 and three of its own sentences vouched for the tree
    — "Every file HEAD tracks under the ladder is present on this box", "No
    tracked file under the ladder differs from HEAD: this tree is clean", "the
    index and HEAD agree". Each is true of an empty set; none is a fact about
    this ladder, and a reader who stopped at the table took them as one. That is
    the vacuous-pass shape, not the silent-zero one, and it is worse: the error
    was printed, just after everything reassuring.
    `doc_ref_audit.py` already refuses this situation (exit 1, one line, before
    any output). The script now matches it: `$ROOT` must be inside a repository
    and must be that repository's own `tools/bare_metal_poc`, or it exits 3
    before printing anything. Both branches run rather than reasoned about — the
    extraction gives exit 3 and no tables, a copy planted at the wrong depth in
    another repo gives exit 3 naming the path it expected — and in place the
    report is unchanged, apart from the fix's own temporary copy of the script
    being counted by the run it was measuring: 59 source files and 222,695 B
    while that scratch copy sat in the ladder, 58 and 197,795 B once it was
    deleted.
  - **Before `--names source` is called safe to land, it was cross-read against
    every record that says a file stays out — and it is not: 3 of the 58 carry a
    documented keep-out.** Method, run rather than argued: all 579 prose files
    on this box (tracked and untracked, `.builder_queue/` included) were
    searched for exclusion language ("not committed", "intentionally", "kept on
    disk", "left out", and near-synonyms) in a ±2-line window, and each window's
    literal filenames and same-directory backticked globs were matched against
    the bucket. Two hits are BM905's: `rung9/bm905_console_probe.py` and
    `rung9/bm905_uinput_probe.py`, named together at
    `.builder_queue/BM905_MANUAL_LANE_STATE.md:225` as "intentionally NOT
    committed — outside brief scope". Read on purpose, the stated reason is a
    scope boundary and not a content objection, and neither file carries a
    credential (the scan below). The third is this lane's own: `mini_read.asm`
    is caught by `rung4/RECEIPT_RUNG4.md:122`, whose keep-out list is written as
    globs ("the `mini_*`/`probe*` debugging mediums") rather than filenames — it
    is uncited by any record, so landing it retires no promise either.
    So the sentence "land the source bucket, one command" would overrule two
    lanes' recorded decisions without saying so; what is unopposed is 55 of the
    58. The same scan is where a pre-add credential check belongs, and it was
    run here as part of this: over all 58 files, zero lines matched
    password/secret/token-key/private-key/`.env` patterns, which is what made
    the keep-out question the only live objection.
    And this bullet moved the very numbers it is written beside: naming the two
    probes and the `mini_` file took check 4 from 88 files to 91 and the
    "land these and the promise holds" bucket from 30 to 33, with 0 stale line
    citations across the 41 it now checks. Three more files are now promises
    because a record said they should not be landed — which is the honest
    reading of the instrument, not a bug in it: the audit asks what a clean
    checkout owes the prose, and prose that names a file makes it owed.
  - **The driver had the same blank-measurement shape, and it beat the reporter
    to it (`028f2281` fixed the reporter; this is the second one).**
    `pristine_reverify.sh` derived `REPO` and `HEAD_SHA` as two bare
    `$(git ...)` substitutions, and the failure was measured in the tree it
    actually gets run against — a fresh `git archive HEAD tools/bare_metal_poc`
    extraction. With no git above it the script printed two raw `fatal: not a git
    repository` lines that bypass `say` and so never reach `driver.log`, carried
    on with both values empty, printed its first landmark as `HEAD ` with nothing
    after the blank, and then died at whichever later check happened to fire
    first. Three runs gave three different stated causes for one fault:
    "scratch filesystem has 3651944 KB free" (scratch on `/tmp`, which is not
    where the 4 GB floor can be met), then "rung7/core.gz is not on this box"
    with the scratch moved to the 44 GB device, then "git archive | tar failed"
    once `core.gz` was copied in to clear that guard. None of the three names the
    actual cause. The case that matters more is a tree
    with some *other* git ancestor: `REPO` resolves and the leg reports on that
    repository's HEAD as if it were the ladder's. It now refuses first, in the
    reporter's shape — location established before any check that can beat it, a
    message naming the real cause, `RUN_STATUS=RED` printed rather than omitted,
    exit 3. Verified in all three trees: no-git and wrong-repo both refuse before
    creating a scratch directory, and in the lane itself the guards pass silently
    (the next guard, the mode check, still fires as before).
    Writing the bullet moved what the bullets beside it count: check 4 went from
    263 citations to 264 and the token sweep from 753 to 755, with 91 cited files
    outside HEAD, 84 prose files, 41 line citations at 0 stale and
    POINTER_STATUS=REVIEW (11) all held.
  - **The same shape inside rung 5's gate: a check that can be satisfied by
    another run's bytes.** `rung5/run_gate5.sh` built its expected-marker hex at
    the fixed path `/tmp/expected_marker.hex` and leg [3] compared the medium
    against that name after a reboot. Demonstrated, not argued: build the marker
    from a stage2 with one byte flipped at offset 64 into the shared name while a
    correct medium sits on disk, and the untouched medium now FAILS the gate
    (`first diff 64` — the poison's own offset) because the verdict came from a
    run that never touched it; the reverse interleaving passes for the same
    reason. Two concurrent legs — which is exactly what `pristine_reverify.sh
    lower` can create against an interactive rung-5 run, since they are different
    trees sharing one `/tmp` — decide each other's outcome. It is now a
    per-run `mktemp` with a `trap ... EXIT`, in `run_gate.sh`'s existing style,
    and the debug helper that read the fixed name (`rung5/run_gate5_persist_probe.sh`,
    untracked, so it rides in nobody's commit) takes the path as an argument.
    Re-measured with the same interleaving: the correct medium PASSes.
    `bash rung5/run_gate5.sh` after the change: **GATE5 PASS, exit 0** — three
    GREEN boots with identical serials (`CRC=329CD470`, `SUM=E956`,
    `IMG2 CRC=7880D4BA`, `WRITE=OK`), the RED-A refusal leg (`IMG2 FAIL
    CRC=B3AEA74F EXP=7880D4BA`, `SUM=E9C7`), the non-vanishing check, and
    re-green byte-identical to boot 1; no temp file left behind.
    Writing this took the row's citation total from 264 to 266 and the token
    sweep from 755 to 758; the 91 owed files held, because the probe helper was
    already cited by an earlier record before this one named it.
  - **Both fixes re-paid in the tree they protect (`lower` mode, HEAD
    `1e8ebeb7`):** `bash pristine_reverify.sh lower` came back
    **`RUN_STATUS=GREEN`, 5 legs, 0 skips, 6 min 26 s**, with the rung-2 leg
    printing `[BITES] rung 2 from the commit alone dies at nasm, as recorded`
    before the nine sources were copied in, and rung 5 green on its new per-run
    marker. The dated section is in
    `rung6/evidence/cleanroom/lower_rungs_pristine.txt`, which also records the
    box fact the run needed: `/tmp` has 3.66 GB free against the driver's own
    4 GB floor, so `PRISTINE_DIR` has to point at the other device here. This
    bullet added one token to the sweep (759) and no file to the 91, and one
    dangling path token written on the way was caught by the audit and removed.
  - **F1 gate 1 of the P2 sweep: `rung6_5/run_bm651_e2e.sh` leg [2] hashed its
    medium to two shared names.** P2 measured the population (21 write-then-read
    H2-class `/tmp` names across 11 `.sh` files); this is the first of them.
    Leg [2] hashes the medium before and after a second boot of the SAME image,
    and `cmp` of those two files IS the verdict that executing the image did not
    perturb the medium — but both files lived at `/tmp/bm651_h1.txt` and
    `/tmp/bm651_h2.txt`, so either could arrive from another run or from an
    aborted one. Demonstrated on the host, with the gate's own hash body read
    verbatim out of the file (its two heredocs are byte-identical, so one
    extraction is both sites): a synthetic 8,192 B medium, `img2_base` 4096,
    `wr_lba` 2. Perturbing one marker byte makes the verdict fire — `cmp rc=1`,
    differing at line 2, `marker_sha=b434793e… → 7f071834…`, so the check is not
    vacuous. Replaying the pre-change shape on the same perturbation with the
    shared `h1` name holding the *other* run's bytes gives **GREEN: the false
    pass the fixed name allowed, on a medium this run perturbed**. Replaying it
    against the per-run names keeps the verdict **RED with the poison still in
    place** at `/tmp/bm651_h1.txt` — the fix is load-bearing, not cosmetic. The
    gate's own three new lines (`run_bm651_e2e.sh:35-37`) were sourced verbatim
    in a subshell: 2/2 temps exist inside, 0 survive `EXIT`, so the `trap` sweeps.
    **What this commit did NOT re-run:** the gate itself.
    `bash rung6_5/run_bm651_e2e.sh` is ~8 QEMU boots plus 4 builds against a
    rung-6.5 medium, and BM-651 is not among the `lower` legs this lane may
    drive, so legs [2]-through-[8] — both GREEN reboots, the three contract
    refusals, the hang, the corrupted-medium RED and the re-green — are unexercised
    here, and the `evidence/medium_hashes_after_boot2.txt` durable copy was not
    rewritten. What is verified is the hashing body, the compare, and the cleanup,
    on host arithmetic only. 20 of P2's 21 names remain, in 4 more files.
    Writing this bullet moved the token sweep 759 → 761 and the line-citation
    count 41 → 42 (the new one is this lane's own, and it resolves: 0 stale),
    with 66 owed files, 151 citations, 84 prose files at 76 fully resolving,
    2 skipped, REVIEW (11) and the single pre-existing unresolved ROADMAP token
    all held. The totals sentence above names no path, so it cannot move them.
  - **F1 gate 2: `rung9/run_bm902_diff.sh` built its differ inputs, and reads its
    RED evidence back, from four shared names.** P2's list for this file was 4
    names at 11 sites; re-derived here before touching it and it held exactly —
    `/tmp/bm902_zp_flipped.bin` (55, 57), `/tmp/BM902_FIELD_PLAN_mutant.md`
    (71, 74), `/tmp/bm902_l4.log` (58, 61, 63, 92), `/tmp/bm902_l5.log` (74, 77,
    79, 94): 12 mentions on 11 lines, because line 74 carries the mutant plan and
    the L5 redirect. All four are now per-run `mktemp` files under one
    `trap … EXIT` (`run_bm902_diff.sh:28-32`), and the two heredoc writers take
    the target as `sys.argv[1]` rather than a literal — which is the only reason
    those two could move at all, a quoted heredoc not being expandable.
    **The stale population was not hypothetical, it was on the box.** At run time
    all four fixed names existed, 4096 B / 12255 B / 180 B / 180 B, every one
    stamped `2026-09-20 18:27:50` local (23:27:50Z) by an earlier BM-902 run. Two
    of them are the evidence this gate says it produces: `grep -q "0x214"` against
    that stale `/tmp/bm902_l4.log` returns **rc=0 with the differ never run**, and
    `grep -q "0x210"` on `_l5.log` the same — neither RED leg needs this run's
    bytes to be believed. And Phase C, run verbatim out of HEAD (`82-95`) in a
    copy, wrote a receipt stamped `2026-09-21T05:21:19Z` whose L4 and L5 tails are
    byte-identical to those 23:27:50Z logs: the committable artifact is assembled
    from names it does not own. Within one uncontended run every writer precedes
    its reader, so what the shared namespace actually costs is the interrupted or
    concurrent case — and the receipt tail in both. The fix removes the option.
    **Re-measured by running the gate for real, host-only** (which gate 1 could
    not be): the seven-pattern substrate grep is 0 hits across this file and both
    helpers, and `grep -E '\.\./|/home/'` over the same three is 0 hits, so the
    path is self-contained — `bm902_stage2_construct.py` reads
    `vmlinuz64.extracted` and two tracked oracle files and spawns nothing. In a
    copy of `rung9/`, `bash run_bm902_diff.sh` returned **exit 0, `GATE PASS:
    BM902 stage2 handoff (L1-L3 green, L4/L5 RED demonstrated, x2 identical)`,
    wall under 1 s**, and its receipt matches the tracked `bm902_diff_receipt.txt`
    modulo its own date line — same four oracle pins, same constructed pins
    `f6605707…`, same `0x214` and `0x210` RED tails. **The fix changed no
    verdict.** The `trap` swept (0 per-run temps survived), and the four shared
    names still hold their 23:27:50Z bytes (`sha256sum -c` rc=0): this harness
    checked they existed before it ran, kept copies, and wrote to none of them.
    **What this commit did NOT re-run:** the run happened in a copy, so the
    tracked `bm902_diff_receipt.txt` was not rewritten and the rung-9 boot set,
    paints and writebacks stayed untouched (guardrail 3). 6 of P2's 21 H2-class
    names are now per-run; 15 remain, in `rung9/run_bm903_step1.sh` (2),
    `rung9/run_bm903_e2e.sh` and `rung9/run_oracle.sh`.
    Writing this bullet moved the token sweep 761 → 768 and the line-citation
    count 42 → 43 (the new citation is this lane's own and it resolves: 0 stale),
    with 66 owed files, 151 citations, 84 prose files at 76 fully resolving,
    2 skipped, REVIEW (11) and the single pre-existing unresolved ROADMAP token
    all held. That took a second pass: named bare, those four evidence files read
    as four unresolved pointers — REVIEW went to (15) until the audit said so —
    and only the `/tmp/`-prefixed form gate 1 already uses leaves it at (11).
  - **F1 gate 3: `rung9/run_bm903_step1.sh` — two shared names, and the two legs
    that read them demand OPPOSITE verdicts.** P2's list said 2 names in this file;
    re-derived here it held exactly — `/tmp/bm903_zp_mutant.bin` at HEAD lines 98
    (write) and 101 (read), `/tmp/bm903_zp_white.bin` at 115 (write) and 117
    (read). S5 builds a zeropage with one byte flipped OUTSIDE the whitelist and
    calls the differ with `--expect-fail`, so it passes only when the differ fails;
    S6 builds one flipped INSIDE it and passes only when the differ passes. Both
    legs then read back a name they do not own, so the bytes sitting there — not
    the code path above them — decide which of the two verdicts is being
    adjudicated. Both names are now per-run `mktemp` files under one
    `trap … EXIT` (`run_bm903_step1.sh:29-31`), the heredocs take the target as
    `sys.argv[1]`, and 4 use sites moved.
    **Both names were on the box, and they were this gate's own output.** 4096 B
    each, stamped `2026-09-20 18:27:49` local (23:27:49Z) — and `cmp` against what
    the legs build today says identical, both directions. So a re-run of the
    pre-fix shape is not adjudicating its own work: with the build step skipped
    entirely, the two differ calls return **rc=0 for both legs**, and the gate
    prints `ok "mutant caught…"` and `ok "whitelisted change still green"` over
    ten-hour-old bytes. The script also never checked the build step — the heredoc
    at HEAD lines 92-100 has no `||`, so a failed write or a tripped assert reaches
    no verdict.
    **The hazard is bidirectional, measured by swapping those bytes.** Feed the
    whitelisted file to the `--expect-fail` leg and the 0x244 mutant to the
    control leg, building nothing: the first returns rc=1 (gate `bad`), the second
    rc=1 with `L1 FAIL: 1 zeropage diff(s) … outside whitelist: 0x244` (gate
    `bad`). A concurrent or interrupted run therefore does not merely reuse bytes,
    it can turn the control RED and the RED leg green depending on which name wins.
    **Re-measured for real, host-only:** the fixed legs in a copy, fresh temps —
    S5 → `L1 FAIL … 0x244` with `--expect-fail` rc=0 (ok), S6 → `L1 PASS: 5
    zeropage byte(s) differ … all inside the whitelist union (517 offsets):
    0x210, 0x21b, 0x21c, 0x21d, 0x21e` rc=0 (ok). `bm903_differ.py` is the seven
    patterns at 0 hits (grep rc=1) and resolves its five pins from its own
    directory, so the copy is self-contained. The `trap` swept clean (0
    mktemp-shaped survivors before and after; 2 created during), and `sha256sum -c`
    confirms both shared names still hold their exact 23:27:49Z bytes — this
    harness copied them and wrote to neither.
    **What this commit did NOT re-run, and why:** the gate as a whole. Its S2 leg
    calls `bm903_capture.py`, and `bm903_capture.py:131` spawns
    `qemu-system-x86_64` — a boot, which the BM-651 precedent and guardrail 3 keep
    out of this lane. Only S5/S6, the legs whose names changed, were run, and only
    over tracked inputs (`bm903_zp_leg0.bin` `bc2431d7…`, `bm903_cmdline_leg0.bin`,
    `bm903_regs_leg0.json`). One honest gap: post-fix, a dead build leaves a 0-byte
    temp and the differ raises, so the gate does go RED instead of masking — but
    the line S5 prints blames the differ ("mutant NOT caught — the differ is
    decoration") rather than the build, the real reason sitting only in the log.
    8 of P2's 21 H2-class names are now per-run; 13 sites remain, in
    `rung9/run_bm903_e2e.sh` (12) and `rung9/run_oracle.sh` (1).
    Writing this bullet moved the token sweep 768 → 775 and the line-citation
    count 43 → 46 (the three new citations are this lane's own and all resolve: 0
    stale), with 66 owed files, 151 citations, 84 prose files at 76 fully
    resolving, 2 skipped, REVIEW (11) and the single pre-existing unresolved
    ROADMAP token all held. The audit was also run against the tree with the
    script edited and the bullet unwritten, and it read 768 / 43 / REVIEW (11)
    there — the comment's two `/tmp/`-prefixed names are net-neutral against the
    two literals the code lost.
  - **F1 gate 4: `rung9/run_bm903_e2e.sh` — 12 names, and one whole RED leg that
    prints GREEN with no boot at all.** Re-derived before editing: **12 distinct
    `/tmp/` names at 22 sites** (193, 196, 199, 206, 209, 217, 224, 226, 228, 245,
    248, 259, 261, 270, 271, 272, 274, 277, 283, 286, 289, 292) — P2's line list
    held exactly. Gate 3's "13 sites remain, in … e2e (12)" tally is *names*, not
    sites: 12 here plus 1 in `rung9/run_oracle.sh`. All 13 physical paths were on
    the box — 8 bases plus the `.att1`/`.norm` siblings, 18 files for this gate's
    namespace — stamped `2026-09-20 18:25–18:27` local (23:25–23:27Z) by the same
    earlier BM-903 run that left gate 2's and gate 3's leftovers. Around them,
    `/tmp` holds **86** `bm903_*` paths and only 11 of those are named by any lane
    `.sh`: the rest belong to the `.py` writers P2 never measured.
    **Three vacuities, each measured against those leftovers, none staged.**
    (1) L5, as gate 3: with the build steps skipped, both differ calls return
    **rc=0** over the stale bins — `L1 FAIL: 1 zeropage diff(s) … outside
    whitelist: 0x244` and `L1 PASS: 5 … all inside the whitelist union` — so
    "mutant caught" and "whitelisted stays green" both print from bytes this run
    never made. (2) L4: the normalizer at HEAD line 224 is piped to `sed` and its
    rc is never checked; made to fail (rc=1, input log absent), the `cmp` at HEAD line 226
    returned **0** over the two stale `.norm` files (881 B each, both sha256
    `4d64ac9d…`) and the gate prints "transcripts byte-identical after T1-T4" for a
    pair of boots that did not happen. (3) **L6 is the worst, and it is not one
    reader but a chain**: the corruptor at HEAD line 269 is piped and unchecked, so
    `pred`/`expct` come off `/tmp/bm903_medium_px_corrupt.crc` (`6AB8F2D3
    393950AA`) while the guest line comes off `/tmp/bm903_e2e_l6.log`
    (`BM903-S2 GATE2 CRC=6AB8F2D3 EXP=393950AA`) — **stale against stale, and they
    agree**. All four of that leg's verdicts then fire GREEN with no corruptor run
    and no boot: cross-check equal, `GATE2=FAIL` present, no `HANDOFF BUILT`, no
    `tc@box`. The leg that exists to prove the gate refuses a corrupted medium was
    adjudicated entirely by ten-hour-old files.
    **Fix shape, and why it deviates from gates 1–3.** Seven bases now live in one
    per-run directory (`run_bm903_e2e.sh:59-68`) — `mktemp -d` plus a single
    `trap 'rm -rf "$E2E"' EXIT` — because this gate's derived siblings are
    unbounded: `boot_attempts` writes `${logf}.att$N` for up to 8 attempts per leg,
    and `.norm`/`.crc` follow their bases (`bm903_norm_transcript.py:70`,
    `bm903_px_corrupt.py:68`). Two constraints the directory had to respect, both
    measured: the two L5 heredocs still take the target as `sys.argv[1]`, a quoted
    heredoc expanding nothing, and **the template must keep the substring `bm903`**
    — `bm903_lane.py:35` detects a live boot by looking for that substring in qemu's
    argv, so a path with no `bm903` in it would blind the serialization guard this
    file's own header calls MEASURED. Checked against the real module's predicate:
    it sees the new per-run path and the old fixed one, and not an un-prefixed
    hypothetical.
    **The rename carried a bug and running the leg is what caught it.**
    `bm903_px_corrupt.py:68` uses `DST.with_suffix('.crc')`, which REPLACES `.raw`
    instead of appending, so the first draft's per-run-quoted crc path pointed at a
    file that is never written. Static review passed — `bash -n` rc=0, zero literals
    left — and the leg would have gone false-RED on its first real run. There is now
    a separate `PX_CRC` at line 68, and the two helpers' disagreement (`.norm`
    appended through `p.suffix + '.norm'`, `.crc` replaced) is written into the
    comment above the block so the next reader does not re-derive it.
    **Verified host-only, which here means the analysis legs and nothing that
    boots.** The gate cannot run in this lane: `bm903_capture.py` at HEAD 98/120/292
    and `bm903_anchor_boot.py` at HEAD 180/273 (qemu spawned at
    `bm903_anchor_boot.py:47`) and all of `run_bm903_step1.sh` re-invoked at HEAD
    303. What ran for real, in a 15-file closure:
    L5's both legs, mutant built into the per-run dir, rc=0 with `L1 FAIL … 0x244`,
    control rc=0 with `L1 PASS: 5 …` — and the per-run mutant is **byte-identical to
    the leftover** (bytes differing: none), so the fix changed no verdict. L4's
    normalization on synthetic transcripts: identical pre-onset bodies with divergent
    tails → `T2 login pid=1, T4 cut=53 B` fired and `cmp` rc=0; divergence *before*
    the cut → `cmp rc=1`, so the leg still REDs when it should, and both `.norm`
    files landed inside the per-run dir as designed; made to fail post-fix, `cmp`
    returns **2** (No such file) — absence became loud where it used to be a pass.
    L6's host side ran for real (`bm903_px_corrupt.py` is qemu-free): rc=0, `0xe5 ->
    0xe4` at medium offset `0xf6440` of 13,640,192 B, `.crc` written in the per-run
    dir, `pred=6AB8F2D3 expct=393950AA`, pred != expct; with a dead corruptor the
    same comparison is now FALSE where pre-fix it was vacuously TRUE. (That it still
    reads the same two hex words as the leftover is the medium and offset being
    unchanged, not a coincidence to lean on.) After every harness: 0 per-run
    directories survived the trap, and all 12 shared paths still hash to their
    pre-run bytes with mtimes at `18:26:32`/`18:27:00` — the harness read them and
    wrote none of them.
    **Not re-run, and one exposure that was already narrow.** S0, S0b, S1, L1, L1b,
    L2, L3, L4's two boots, L6's two boots and R1 stay unexecuted here. The three
    boot-log bases were the least exposed of the seven: `bm903_anchor_boot.py:46`
    truncates the log before qemu opens it and `boot_attempts` requires rc=0 before
    it greps for the anchor, so a solo interrupted run could not read a stale verdict
    from them. What the shared names cost there is concurrency — two runs of this
    gate interleave into one file and the truncate protects neither — so they moved
    with the rest, at no cost.
    20 of P2's 21 H2-class names are now per-run; the last is
    `rung9/run_oracle.sh`'s `/tmp/oracle_zp_flipped.bin`, 2 sites (62, 64).
    Writing this bullet moved the token sweep 775 → 782 and the line-citation count
    46 → 53 (the seven new citations are this lane's own and all resolve: 0 stale),
    with 66 owed files, 151 citations, 84 prose files at 76 fully resolving, 2
    skipped, REVIEW (11) and the single pre-existing unresolved ROADMAP token all
    held — REVIEW in particular, where gate 2's first draft went to (15) by naming
    leftover evidence bare, so every `/tmp` path here carries its `/tmp/` prefix.
    The reading was taken twice more after five line-number corrections in the draft
    (`PX_CRC` is 68 not 64, the decl block is 59-68, and the HEAD-vs-post-edit site
    numbers are now labelled), and it held at 782 / 53 / REVIEW (11) throughout.
  - **F1 gate 5: `rung9/run_oracle.sh` — the last H2-class name, and a leftover that
    is the gate's own correct answer.** Re-derived before editing: **1 name at 2
    sites**, HEAD `rung9/run_oracle.sh:62` (a quoted heredoc's `open(...,'wb')`) and
    `:64` (`cmp -s oracle_zp_leg0.bin /tmp/oracle_zp_flipped.bin`) — P2's list held
    exactly, and the read side is a *tracked* artifact, so this leg's shape is the
    one the other four did not have. Substrate measured, not inherited: the gate file
    is 0-hit on the seven-pattern grep, but `rung9/probe34_capture.py:71` (Phase A)
    and `rung9/probe27_qemu_direct.py:75` (redB) each spawn `qemu-system-x86_64`, so
    the gate is not re-runnable here — redA is pure host file ops and is what ran.
    **What was on the box is the finding.** `/tmp/oracle_zp_flipped.bin` exists,
    4096 B, stamped `2026-09-18 19:55:14` — two days before the `4972ccee` snapshot
    and older than this lane — and a read-only byte compare against the tracked
    `oracle_zp_leg0.bin` shows **exactly one** differing byte: `0x228 0x00 -> 0x01`,
    the offset this leg flips. The leftover is not stale input, it is a
    byte-perfect copy of what the leg is supposed to produce, so `cmp -s` of that
    pair returns rc=1 right now with nothing written, and HEAD's line 64 takes the
    PASS branch. Unlike gates 2-4 the leg cannot trip over its own staleness: the
    stale answer is the right answer. Nothing else in the ladder names the path
    (ladder-wide `grep -rl oracle_zp_flipped` → this gate and ROADMAP prose only).
    **Three host-only measurements in a sandbox, on copies, with the shared name read
    and never written.** (a) HEAD's reader lines alone, writer skipped — the state a
    discarded rc leaves the gate in — print `PHASE C redA PASS`, rc=0. (b) HEAD's
    whole block with its write made to *actually* fail (target `chmod 400`,
    `PermissionError` on stderr) still prints PASS, rc=0: a false GREEN with zero
    bytes written by that run. (c) the same failing block over a plant that is a copy
    of `oracle_zp_leg0.bin` prints `GATE FAIL: redA flip produced identical file
    (impossible)` and exits 1 — a rig fault reported as the differ being decoration,
    so the hazard is bidirectional as it was at gate 3.
    **Fix shape, and the constraint that proved it.** `rung9/run_oracle.sh:38-39` is
    one per-run `mktemp` under a `trap ... EXIT`, the `run_bm902_diff.sh:28-32`
    shape. Relocating the path by editing the string, which is what test (b) needed,
    does not work — a quoted heredoc never expands `$PLANT`, so the first version of
    that harness wrote a file literally named `$PLANT` while the reader read the
    planted one and the test passed for the wrong reason. `sys.argv[1]` is the only
    way this leg moves at all, same as gates 1-4; the corrected (b) and (c) fail the
    write and print the verdicts above.
    **One line beyond the rename, flagged for a ruling rather than assumed free:**
    `rung9/run_oracle.sh:76` now carries the `|| { echo "GATE FAIL: redA mutant build
    errored"; exit 1; }` that the sanity and redB heredocs in this file already have
    and line 59 at HEAD did not. The rename alone makes the dead-writer path *quieter*
    (a 0-byte per-run temp differs from leg0, so PASS still prints — measured with the
    guard stripped, rc=0), and with the guard it is a RED naming the build (measured,
    rc=1). Revert that one line and the namespace fix stands on its own.
    **Verdict unchanged, and concurrency closed.** Post-fix redA runs for real: PASS,
    and the per-run mutant hashes `13ea0308c5c6545c…` — the same sha256 as the
    three-day-old leftover it replaced, so the gate earns byte-identical output and
    nothing about its verdict moved. Two post-fix runs started together each made its
    own temp (2 distinct paths, both rc=0); the trap swept 0 survivors in every run
    here, and the shared name passed `sha256sum -c` with `mtime_ns 1789779314`
    unchanged throughout — read, never written. `bash -n` rc=0; the only remaining
    `/tmp/` text in the file is the comment naming what HEAD did.
    **Not re-run:** Phase A (`probe34_capture.py`), Phase B's log diff over its
    output, redB (`probe27_qemu_direct.py`), and Phase D, which `tee`s the tracked
    `oracle_pins.txt` and so stays out of the real tree either way.
    **F1 is done: 21 of 21 H2-class names are per-run.** What P2 left outside its
    scope is unchanged and still open — 2 fixed sockets, 2 by-name logs, 1 pidfile,
    1 hardcoded historical directory, the timestamp-collision at
    `pristine_reverify.sh:64`, and the 17 `.py` files under the ladder that name
    `/tmp/` and were never measured.
    Writing this bullet moved the token sweep 782 → 788 and the line-citation count
    53 → 61 (the eight new citations are this lane's own and all resolve: 0 stale),
    with 66 owed files, 151 citations, 84 prose files at 76 fully resolving, 2
    skipped, REVIEW (11) and the single pre-existing unresolved ROADMAP token held —
    every `/tmp` path above carries its `/tmp/` prefix, so REVIEW never moved. The
    intermediate reading, with the script edited and this bullet unwritten, was
    782 / 53 / REVIEW (11): the code's two lost literals and its one gained comment
    net to zero.
    **F2 step 2, group A — the two rung-6 corrector-size probes go per-run
    (2026-09-21T13:33Z, BM000 lane).** The `.py` half of Jericho's 12:40Z shared-name
    ruling; step 1 (report-only, 12:57Z) measured 47 sites and narrowed this group to
    4 pure-host sites in these 2 files. **Pre-fix, both were vacuous, measured:** with
    `nasm` replaced by `/bin/true`, `rung6/bm602_measure_corrector.py` printed the
    plant's size as this run's result — "333 B assembled", rc=0, from HEAD's line 47
    reading `/tmp/bm602_corrector_only.bin` — and `rung6/probe_bee_scheme.py:271` leg J
    unpacked `routine=244` out of the `2026-09-19` leftover `/tmp/bm601_bee.bin` and
    PASSed with nothing built.
    **Fix shape: a per-run directory, not a bare `mktemp` file.** `mkdtemp` at
    `rung6/bm602_measure_corrector.py:46` with `finally: shutil.rmtree` at `:65`,
    `TemporaryDirectory` at `rung6/probe_bee_scheme.py:271`. A bare temp *file* makes an
    inert build raise on read-back; the directory keeps absence loud. One line goes
    beyond the rename: `built = res.returncode == 0 and out.exists()` at
    `rung6/probe_bee_scheme.py:276` routes the inert case through the leg's own verdict
    instead of a traceback — **drop that line and the privatization still stands on its
    own.**
    **Verdict unchanged, and now demonstrably independent of the shared name.** Full
    post-fix `probe_bee_scheme.py`: legs A–I as before, leg J "corrector 244 B assembled
    clean vs 4848 B unused … 23,863,808 B (22.76 MiB, +75%) … host decode 287 MiB/s",
    tally 0 red, rc=0 — the same 244 HEAD reported, while `/tmp/bm601_bee.bin` sits at
    254 B with its `2026-09-19 19:50:22` mtime and sha `ffd65676…` untouched and
    `/tmp/bm601_bee_*` empty, so the number no longer comes from that file.
    `rung6/bm602_measure_corrector.py` for real: "236 B assembled, 228 B of code + 8 B
    of counters … 4.9% of the free budget", rc=0, byte-identical to HEAD's real run.
    **Inversion and privatization:** leg J with `nasm`→`/bin/true` gives `built=False`,
    `size=0 B`, `routine=-1`, leg J FALSE; the measure script with an inert builder and
    the 333 B plant restored at the OLD name gives `FileNotFoundError` on its own per-run
    path, rc=1 — the plant is ignored, which is the point. `python3 -m py_compile` rc=0
    on both. `/tmp/bm602_corrector_only.bin` is absent again after the real run (HEAD's
    run had left it behind); 0 survivors under either per-run prefix.
    **Not touched:** groups B–E — the boot probes (`rung9/bm903_*`), the by-name logs,
    the fixed inputs at `repack_v2.py`/`repack_v3.py`, and the cleanroom historical dir.
    B is boot-path, so its verification caps at (a)+(c) under guardrail 3; D needs a
    refuse-if-absent shape rather than a temp name.
    Writing this bullet moved the token sweep 788 → 793 and the line-citation count
    61 → 66, all five citations this lane's own and 0 stale, with 66 owed files, 151
    citations, 84 prose files at 76 fully resolving, 2 skipped and REVIEW (11) held —
    every path above carries its `/tmp/` prefix. The pre-bullet reading, with the code
    edited and this bullet unwritten, was already 788 / 61 / REVIEW (11): the two lost
    literals and the two gained comments net to zero, since the sweep counts backticked
    tokens and those comments are plain text.
    **F2 step 3, group B1 — the last true write-then-read in the `.py` sweep goes
    per-run (2026-09-21T14:39Z, BM000 lane).** `rung9/bm903_dbg_silence_probe.py`, 4
    sites: `:26` wrote `/tmp/bm903_dbg_cmd.bin` for gdb's `restore` at `:37`, `:27`
    named the serial log it `unlink`ed at `:28`, `:48` named the gdb log read back at
    `:63-66`. Split from group B2 (the five boot-written logs read for a verdict in
    `bm903_time_to_prompt.py`, `bm903_tty_race.py`, `bm903_dbg_memcmp.py`,
    `bm903_px_memcmp.py`) because that half needs a different fix shape.
    **Pre-fix it was fully vacuous, and the rig never had to run for that to show.** An
    inert harness — `subprocess` stubbed so no qemu and no gdb ever start — reproduces
    the whole 2026-09-19 transcript from the shared names: "--- gdb tail ---" prints
    `Restoring binary file /tmp/bm903_dbg_cmd.bin into memory (0x1f800 to 0x1f900)` and
    the `x/s` read-back of the cmdline, plus `--- serial (177 B) ---` of BM903-S2
    markers, with zero work done this run. Neutering the probe's own `write_bytes`
    (dead-build mode) changes the output by nothing at all: the restore target is still
    `exists = True, 256 B, mtime 1789857458638488326` — a 2026-09-19 buffer being
    restored into guest memory and reported as this run's rewrite. The harness also
    caught that `:28` deletes another run's serial log before it reads it.
    **Fix, and what it does NOT do: no boot this run, per guardrail 3, so this file is
    verified by (a) + (c) only.** One `mkdtemp` directory at
    `rung9/bm903_dbg_silence_probe.py:33` holds the run's cmd.bin, serial.log and
    gdb.log, removed by `atexit` at `:34`; the now-impossible `serial.unlink` is gone with the
    shared name. Post-fix in the same inert harness the restore target is
    `/tmp/bm903_dbg_silence_b8z7adoe/cmd.bin`, `exists = True, 256 B`, mtime
    `1790001482797151172` — this run's bytes — and the gdb tail prints **empty** instead
    of a three-day-old transcript; dead-build mode gives `exists = False`, so gdb would
    fail on the missing restore input rather than quietly using a stranger's. The three
    2026-09-19 leftovers (`85724241…`, `7da57c11…`, `60b9136a…`, 256/177/640 B) are
    byte-identical after all four harness runs, so the reads never wrote; 0 survivors
    under `/tmp/bm903_dbg_silence_*`; (c) holds — the only holders of those names in
    `tools/bare_metal_poc .builder_queue` were this file and prose.
    `python3 -m py_compile` rc=0. **Two consequences worth stating plainly:** the
    per-run directory is deleted at exit, so a real run's full logs no longer persist
    for post-hoc reading (the script prints a 12-line gdb tail and 6 k+3 k chars of
    serial before that; keeping the evidence would be one line — drop the `atexit`
    register and print `RUN_DIR`); and `PORT = 12470` is still fixed, so two
    concurrent runs of this probe still collide on the gdb port. That is the same class
    as `pristine_reverify.sh:64`'s timestamp collision — reported, not swept, since it
    is not a file name.
    Writing this bullet moved the token sweep 793 → 798 and the line-citation count
    66 → 68 at 0 stale, with 84 prose files at 76 fully resolving, 66 owed files / 151
    citations and REVIEW (11) held. **Held only after a correction that is itself the
    finding:** the first draft backticked the bare names for the three per-run files,
    and the audit read two of them as unresolved path tokens — ROADMAP unresolved 1 →
    3, POINTER_STATUS REVIEW (11) → (13), 801 tokens — which is the mechanism behind
    the "carry the `/tmp/` prefix" rule F1 learned by hand. They are plain text now and
    ROADMAP's single pre-existing unresolved token (`line 891:
    lib/libresolv-2.28.so`) is again the only one. One more self-catch: this bullet
    carried the placeholder timestamp `14:4XZ` until the clock read 14:39Z; no commit
    ever held it.
    **F2 step 6, group D — the two rung-7 repack probes refuse an unpinned base
    (2026-09-21T18:26Z, BM000 lane).** Two tracked files, one fixed input:
    `/tmp/tc_iso_check/tc2.iso` named at `rung7/repack_v2.py:36` and
    `rung7/repack_v3.py:28`. These are *inputs*, so a `mktemp` would be theatre — the
    file has to exist before anything can read it. What the pair carries now is the
    base's recorded length and sha256, checked before a byte is patched
    (`rung7/repack_v2.py:41-42,45,48-49`, `rung7/repack_v3.py:33-34,39,42-43`), with
    the provenance comment pointing at `rung7/RECEIPT_TC_PROBE.md`'s artifact table.
    **The hazard, measured on HEAD:** the same script over a base truncated by one
    2048-byte sector — the interrupted-copy shape — returns **rc=0** and writes a
    plausible 28,131,328-byte medium, because all six of its asserts (`vmlinuz` head
    MZ at 9248768, cfg round-trip, extent overlap) sit below the cut. Post-fix the same
    input dies at rc=1 naming `18870272 B` and its hash, and writes nothing. The
    `os.path.exists` half of the fix is cosmetic — python already raises
    `FileNotFoundError` on a missing path — so the pin is the load-bearing half, stated
    that way rather than oversold. `rung7/repack_v2.py:104`, the assert that compares
    the working buffer's length to a fresh read of the same file it was loaded from,
    stays as written: the queue's word for it is report, not rename. The pin does bound
    it — "holds whatever `SRC` contains" now means "holds if `SRC` is the pinned base".
    **A finding the rename had nothing to do with:** v2 cannot run against the base it
    documents. Over the byte-verified good input HEAD's v2 dies at
    `AssertionError: ttyS0 getty missing from initramfs`, and the base's own member says
    so — 13,341,184 bytes, magic `070701`, `ttyS0` twice and `ttyS0::respawn` zero
    times, so the docstring's step-1 premise (tc2.iso "already carries the ttyS0 getty")
    is false and v2 is the superseded approach the receipt's v3 replaced. Its hardcoded
    member offset is not the bug: 116736 really is `CORE.GZ;1`'s extent (lba 57, size
    9131528, read back out of the base's directory record).
    **And the recorded medium was never re-derivable by re-running.** Two HEAD runs 3 s
    apart over the identical base differ in exactly **1** byte, at `0x1200004` — the
    appended extent's gzip-header MTIME that `gzip.compress` stamps from the clock — and
    today's run differs from the tracked recorded file in 3 bytes, all inside those 4.
    Zero those 4 bytes and the post-fix output, both HEAD runs and the recorded medium
    are byte-identical at 28,135,424 B, so the fix moved no verdict; the sound invariant
    here is mtime-normalized identity, not a hash.
    **Host-only because it is host-only:** the reach grep (`qemu|subprocess|socket|8769|
    livemap|paint|writeback|ssh|nbdkit`) is 0 hits across both files, and no lane script
    calls either one, so this is the first F2 group with no boot leg at all. Both shared
    names were read, never written: `/tmp/tc_iso_check/tc2.iso` still hashes to
    `445dbb53…` at mtime 2026-09-18 14:54:50 and the in-tree recorded medium to
    `c4654240…` at 16:50:38, and since the output path is cwd-relative every leg ran
    inside the run's own `mktemp -d`. One method slip kept rather than smoothed: the
    first post-fix batch built its script paths as `../../` + an absolute `$SB`, so all
    six legs exited 2 on "can't open file" — a check that reported nothing, caught by
    the empty cwd column and re-run.
    **Audit, measured twice after this totals sentence was written, both times
    unchanged:** 807 backticked path tokens (was 806), **94 line citations at 0 stale**
    (was 89 — the +5 are this bullet's own and every one resolves in range), 66 cited
    files outside HEAD at 151 citations, 84 prose files at 76 fully resolving, 2 skipped,
    ROADMAP unresolved still its single pre-existing token, POINTER_STATUS REVIEW (11)
    unmoved.
    - **F2 step 7, group E — the clean-room pair refuses a tree it cannot verify, and
      writes a record of its own (2026-09-21T19:06Z, BM000 lane).** One literal site,
      `rung6/evidence/cleanroom/bm602_cleanroom_pair.sh:17` at HEAD: `C=` pointed at a
      `git archive HEAD` clone under `/tmp` that no longer exists (`ls -d
      /tmp/bm653_clone*` → nothing), and the run's status record lived *inside* that tree.
      Tracked file, 39 → 54 lines, last touched `1e1218c5`. Post-fix `:22` keeps the fixed
      path as a default and honours `BM602_CLONE`, `:24-30` refuses before anything is
      touched when `$C/rung6` is absent and names the archive command that would supply it,
      and `:34` puts the record in a per-run temp which is deliberately **not** swept —
      it is the product, not scratch — with its path echoed at `:54`.
      **The hazard, measured with an inert stub standing in for the delegated gate (no
      boot):** against a shadow clone holding another run's status transcript, HEAD's script
      returns **rc=0** and its `: > "$S"` replaces those bytes — `12f7a5ca…` became
      `ec75ba3a…` — so a complete-looking clean-room pair ran and recorded itself over a
      tree of unverified vintage. The same shadow, run post-fix, leaves the foreign file at
      `12f7a5ca…`, writes its own record, and that record `diff`s empty against HEAD's
      transcript, so no verdict moved. `bash -n` rc=0; one `/tmp` literal left, by design.
      **Not oversold:** the absent-clone case is *already* loud on HEAD — rc=1 with two raw
      "No such file or directory" errors and nothing created — so the refusal buys an
      actionable message, not a silent-green turned red. The loud half of this item is the
      stale-tree case above.
      **One residual, reproduced rather than assumed.** The two boot logs the pair writes
      are relative names inside the input tree (logs/cleanroom_1.log, logs/cleanroom_2.log),
      not /tmp literals, so they stay in place — and they still race: five pairs of
      concurrent post-fix runs sharing one clone gave **1 of 10** records missing the three
      run-1 grep lines, while three solo runs and both solo controls were complete. The one
      real fix is to privatize those two names too (or to give each run its own clone),
      which is a second change to a historical script; reported, not taken.
      **Reach, followed one hop further than the file:** the pair script is 0-hit on the
      substrate grep, and so is `rung6/run_bm602_e2e.sh` — but that gate calls
      `bm602_gate.py` and `../rung9/bm903_anchor_boot.py` (qemu at `:47`), so it boots twice
      per run and guardrail 3 capped this group at (a)+(c) with a stub. Nothing else in the
      lane reads the status file or either log: the holder grep returns this script's own 6
      lines and two prose rows, and the durable record is the tracked
      `rung6/evidence/cleanroom/cleanroom_pair.txt`, whose header already states the scratch
      tree is gone. Report-only, out of envelope: `:23` hardcodes this repo's absolute path,
      the same class F1 gate 2 grepped for.
      **F2's envelope is now exhausted** — groups A, B1, B2, C, D, E landed at `1da04110`,
      `867e62f0`, `3383cc5e`, `ff1988ae`, `c40f8ce8` and here. What is left outside it is
      Jericho's list, not this item's: the two ruled-excluded sockets plus the third one
      `rung7/throughput_probe.py:7`, the pidfile, the parked rig-dir neighbours, the fixed
      gdb ports, the `/var/tmp` guest-side class, `pristine_reverify.sh:64`'s
      second-granularity name, and `run_gate.sh:19-21`'s kill of any live plugin nbdkit.
      One clock correction carried rather than edited into the committed record: the group D
      bullet above is headed `18:26Z` where its commit clock is 18:23:44Z and its DONE record
      says 18:24Z — a stale estimate at write time, left as written.
      **Audit, measured twice after this totals sentence was written, both times
      unchanged:** 811 backticked path tokens (was 807), **98 line citations at 0 stale**
      (was 94 — the +4 are this bullet's own and every one resolves in range), 66 cited
      files outside HEAD at 151 citations, 84 prose files at 76 fully resolving, 2 skipped,
      POINTER_STATUS REVIEW (11) unmoved. **That held only on the second draft:** the
      first backticked the two clone-internal log names, and the audit read
      logs/cleanroom_1.log as an unresolved path token — ROADMAP unresolved 1 → 2 and
      REVIEW (11) → (12) — the same mechanism group B1's bullet records, re-paid here
      because those two names live in a tree no checkout carries, so no prefix can make
      them resolve. They are plain text now, and ROADMAP's single unresolved token is
      again the pre-existing `line 891: lib/libresolv-2.28.so`.
  - **F2 step 5, group C — the rung-1 gate's server log and the plugin's trace go
    per-run (2026-09-21T17:48Z, BM000 lane).** Two tracked files, 4 sites:
    `run_gate.sh:32,33,64` and `pxc1_nbd_plugin.py:75` at HEAD. Post-fix,
    `run_gate.sh:15-16` makes one `mktemp -d` directory for the run, `run_gate.sh:24`
    extends the existing EXIT trap to remove it, and `run_gate.sh:38-39` +
    `run_gate.sh:69-70` give each nbdkit launch its own stderr file inside it and hand
    the plugin the trace name through `PXC1_NBD_TRACE`; `pxc1_nbd_plugin.py:78-86`
    resolves that variable, else makes a per-run directory of its own and registers the
    removal.
    **What the pair actually was is not a vacuity.** The shell `rm -f`'s
    `/tmp/pxc1_trace.log` while a *different process* — the plugin under nbdkit —
    appends to it, and HEAD's two launches (`:33` and `:64`) are byte-identical lines, so
    leg [6] truncated leg [1]'s server stderr. Nothing reads either name back: the
    gate's verdicts come from the tree-relative serial_g.log, serial_ra.log,
    serial_rb.log and serial_rg.log. This is the cross-run evidence class.
    **The second consumer is why an env var alone was not enough.**
    `rung7/boot_probe.sh:10` launches the same plugin, so the trace name had two writers
    and `run_gate.sh`'s delete took a rung-7 run's trace with it; and that file starts
    nbdkit under `env -i` (`rung7/boot_probe.sh:25`, to pin PATH past a venv python
    without numpy), so the override cannot reach the plugin on that path. Hence both
    halves: the gate passes a name, and the plugin's default stopped being shared.
    **Verified (a) + (c), plus the plugin half for real; no boot ran.**
    (a) pre, against a shadow planted with copies of the two real names (a 520 B trace
    `0551e6ca…` and 62 B of foreign stderr): HEAD's script with `/tmp/` rewritten into
    the shadow leaves the trace **gone** and the log holding the stub's 153 B — the
    foreign text destroyed. Its leg [0] ran for real (`nasm`, the codec, `expected
    CKSUM=5F3B`, the receipt's checksum) and leg [2] stops at the inert qemu model with
    rc=1; the post-fix script takes the identical path, so the comparison is on names,
    not on verdicts. (a) post, same rig: both plants intact (520 B `0551e6ca…` / 62 B
    `fbc03179…`) and the run's own `/tmp/pxc1_gate_XXXXXX/` holds the launch's stderr
    plus the trace the modelled plugin appended to — shell and plugin agreed on one
    name. The double-overwrite replayed from HEAD's own two lines, with a per-launch
    timestamp in stderr: after leg [1] the fixed name holds launch@1790012641907210797,
    after leg [6] it holds only launch@1790012642914017990 — 188 B, one line, the first
    one destroyed. The post-fix pair of lines gives two 163 B files, each keeping its own
    launch. **The plugin half was not modelled:** nbdkit 1.36.3, the real plugin and
    `qemu-io -c 'r 0 512'` against a sandbox socket, with `PXC1_NBD_TRACE` set, produced
    `pread off=0 n=512 data=fcfa31c08ed88ec08ed0bc007cfbbaf9` at that path — the same
    first line the 2026-09-20 leftover carries, so the variable does reach the
    interpreter nbdkit embeds; with it unset the plugin made exactly one `pxc1_nbd_*`
    directory and a SIGTERM'd nbdkit removed it (0 survivors), so the atexit path is
    measured too. (c): the only `/tmp` literal left in either file is `run_gate.sh:7`'s
    socket, which the 12:40Z ruling leaves fixed; `/tmp/pxc1_trace.log` now appears in
    code nowhere and only in prose (`RECEIPT.md:80` documents the old name, left as the
    point-in-time record it is), and `/tmp/nbdkit_gate.log` appears nowhere but this file.
    `bash -n` rc=0, `python3 -m py_compile` rc=0.
    **A hazard this run hit itself, and it is precisely this item's class:** the first
    replay evaluated HEAD's *unrewritten* `:33` once, so the real
    `/tmp/nbdkit_gate.log` (0 B, `e3b0c442…`) took a 188 B stub line. Restored to 0 B
    with its mtime back to `2026-09-20 22:36:17.938644451`; ctime and atime cannot be
    reverted, so it is reported rather than smoothed over. The trace file's sha is
    unchanged, which is what shows the delete side of the same replay stayed inside the
    shadow.
    **Not re-run, and why:** legs [2]-[6] boot qemu (`run_gate.sh:44,51,59,73`), and the
    gate's `cleanup` (`run_gate.sh:19-21`) kills *any* live nbdkit whose cmdline names
    the plugin — which is also how a concurrent `rung7/boot_probe.sh` server would die —
    before `rm -f`-ing the ruling-fixed socket. Running the full gate here could disrupt
    another session on a name F2 may not change, for evidence this group does not need.
    That cross-kill is reported, not fixed: it is not a file name.
    **Three decisions beyond the rename, each revertible on its own:** the trace
    `rm -f` is gone rather than redirected (a fresh directory has nothing to clear, and
    the delete was the destructive half); the two launches got distinct names instead of
    both truncating one, so leg [1]'s stderr is still readable after leg [6]; and the
    plugin's fallback is a temp directory, so a bare launch still traces, just not onto
    a shared name. Same trade-off groups B1 and B2 recorded: the scratch goes at exit,
    so a run's server stderr no longer persists for post-hoc reading — dropping the
    `rm -rf` from `run_gate.sh:24` is the one-line alternative.
    **Self-reference:** this bullet moved the token sweep 804 → 806 and the
    line-citation count 75 → 89 at 0 stale, with 84 prose files at 76 fully
    resolving, 66 owed files / 151 citations, 2 skipped, ROADMAP's single pre-existing
    unresolved token and REVIEW (11) held. The fourth measurement of the same trap:
    backticking the four serial-log names the gate reads added 16 check-4 citations
    (151 → 167), because each one resolves project-wide to another run's untracked
    output; they are plain text now and the total is back to 151.
    **F2 step 4, group B2 — the five boot-written probe logs go per-run
    (2026-09-21T16:26Z, BM000 lane).** Four tracked files: `bm903_time_to_prompt.py:24`,
    `bm903_tty_race.py:98`, `bm903_dbg_memcmp.py:27` and `bm903_px_memcmp.py:32` (plus
    that file's fixed serial log). Every one of them spawns `qemu-system-x86_64`, so
    guardrail 3 capped this group at (a) + (c): **no boot ran**, and the verdicts below
    come from an inert rig — `subprocess` stubbed, and every shared path textually
    redirected into a sandbox shadow planted with copies of the real 2026-09-19 bytes.
    **The group was not what step 1's label suggested.** Step 1 called all five sites
    "fixed names written by a boot and read back for the verdict", but only one is a true
    solo-run vacuity, because three of the four files `unlink` the name before writing
    it. Measured, not inferred:
    `bm903_dbg_memcmp.py` dumps into the fixed directory `/tmp/bm903_dbg` and never
    clears it, so with no qemu and no gdb alive HEAD's copy reports both regions
    "BYTE-IDENTICAL to the medium" off the `2026-09-19 17:37` dumps (4,280,992 B and
    9,260,807 B) and truncates their gdb.log to 0 B on the way. Post-fix the same rig
    says "NO DUMP (gdb failed)" twice — the stale verdict is unreachable — and a model
    of a gdb that *works* (the harness writes the bytes the probe itself expects into its
    per-run `/tmp/bm903_dbg_xxxxxxxx/`) restores both BYTE-IDENTICAL lines, so the fix
    moved no verdict and the RED direction still fires.
    The other three are a different harm: they delete **someone else's** evidence at a
    shared name. `bm903_px_memcmp.py` swept `OUT.glob('*.bin')` — in the planted shadow it
    took r0/r1/r2.bin and a planted foreign some_other_run.bin (9,260,807 B) with it and
    zeroed their gdb.log and qemu.log; post-fix all seven plants survive and the probe reports
    "NO DUMP … (this run's dir is removed at exit)" with `MEMCMP FAIL` / exit 1, and the
    working-gdb model gives the three BYTE-IDENTICAL lines and `MEMCMP PASS` / exit 0.
    `bm903_time_to_prompt.py` unlinked the previous run's transcript and then read the name
    back with no guard: with nothing at the other end it raised `FileNotFoundError` rather
    than printing NEVER — HEAD guarded the size with `log.exists()` and left the read beside
    it unguarded, which the stale file masked; `bm903_time_to_prompt.py:53-55` guard both
    now. Post-fix it prints
    "anchor NEVER (cap …) — transcript 0 B, handoff checkpoints present: False" for both
    runs. Against a qemu model that does produce serial, pre- and post-fix print the same
    line ("anchor at 0.0s — transcript 1289 B, … True"), so the verdict is invariant; what
    differs is that the pre-fix run overwrote `run1`'s 1,266 B transcript with `run0`'s
    1,289 B bytes. `bm903_tty_race.py` unlinks inside `boot()`, and the fixed base name
    makes two invocations delete each other's transcripts mid-run; post-fix the planted
    999 B foreign log survives and the line it prints is unchanged.
    **The sweep left the 2026-09-19 evidence exactly as it found it:** `sha256sum -c` over
    all 27 real shared names (both directories, the `bm903_dbg_*` files, both
    `bm903_time_run*` transcripts and the 16 logs under
    `/tmp/bm903_race_bm903_medium_*`, both media) → 0
    failures, with mtimes unchanged (`1789857454009858082`, `1789859919226620760`,
    `1789857699167250537`, `1789861803227285180`, …), and 0 survivors under the four new
    `/tmp/bm903_{dbg,px_memcmp,time,race}_*` prefixes once the harness exited. (c) holds:
    each old name has exactly one writer in `tools/bare_metal_poc .builder_queue` — its own
    probe — and `grep -rnF 'bm903_dbg/'` returns nothing at all (the dumps are composed
    from a variable, which is why the name never appears spelled out). Each per-run prefix
    keeps the substring `bm903_lane.py:35` scans qemu argv for, so the lane guard still
    sees these boots; F1 gate 4's constraint again.
    **Four decisions beyond the rename, each revertible on its own:** the three
    `unlink`/`glob` sweeps are gone rather than redirected (impossible in a fresh
    directory, and each was a cross-run delete); `bm903_dbg_memcmp.py` lost its
    `mkdir(exist_ok=True)` for the same reason; `bm903_time_to_prompt.py` now guards the
    read it used to make unguarded, because privatizing is what makes "no file at the
    name" the normal case; and, as in group B1, the directory is deleted at exit, so a
    real run's 13.5 MB of dumps and transcripts no longer persist for post-hoc reading —
    dropping the `atexit` register is the one-line alternative. Still fixed and still
    reported-not-swept: `PORT = 12472` and `PORT = 12474`, the same class as B1's 12470
    and `pristine_reverify.sh:64`. `python3 -m py_compile` rc=0 on all four files.
    **Self-reference:** this bullet moved the token sweep 798 → 804 and the line-citation
    count 68 → 75 at 0 stale, with 84 prose files at 76 fully resolving, 66 owed files /
    151 citations, 2 skipped and ROADMAP's single pre-existing unresolved token (the
    libresolv one at its line 891) all held. REVIEW (11) held only after the same
    correction group B1 recorded: the first draft backticked three bare per-run file
    names, the sweep read them as unresolved path tokens — ROADMAP unresolved 1 → 5,
    REVIEW (11) → (15), 808 tokens — and they are plain text now. Measured twice more
    after this totals sentence was written, both times 804 / 75 / REVIEW (11).

---

## Concurrency contract: three name classes (G3, 2026-09-22)

Written once, by the BM000 lane tick that landed G3, because four guards had grown on this
ladder and none of them was the same rule: `pristine_reverify.sh:200` skips, `run_gate.sh:22`
kills, `rung6/bm602_lane.py:16` / `rung6_5/bm653_lane.py:24` / `rung9/bm903_lane.py:35` scan
argv for a per-rung marker, and `rung8/bm802_boot_class.py:50` raises. The classes below decide
both how a name is built and what a clash means, so "a specific collision has been
demonstrated" stops being argued per site.

**Two questions place a name.** (1) Can any other process resolve this name while my run holds
it? If no, it is class 1 and no peer test is needed. (2) If yes: does the name mean *this
rung's* (a peer can see it by scanning a command line) or *this box's* (one per machine, so the
kernel must arbitrate)? Class 2 or class 3.

1. **Per-run — nobody else can resolve the name.** Built from `mktemp -d`, never from a fixed
   `/tmp` literal. `run_gate.sh:15` and `rung7/boot_probe.sh:22` are the landed shape.
   Constraint measured while landing G1 step 2: an EXIT trap expands its variable at *fire*
   time, so **one `mktemp -d` per process, or trap each one explicitly** — a second assignment
   silently leaks the first directory. Proof a fix owes: two runs print distinct names, and the
   first is still alive and still answering after the second binds.
2. **Lane-scoped, and it advertises itself in argv.** Shared by a *class* of runs, held while
   one of them is live. The rule is not "pick a unique name", it is **put a marker substring in
   the child's own argv so the guards can see you**: `rung8/bm802_boot_class.py:63` names its
   scratch media `bm903_bm802_*` for exactly that reason. A name in this class that no argv
   carries is invisible to every guard on the box.
3. **Machine-scoped, and it must refuse loudly.** One per box, shared by every tree on it: the
   gdb TCP ports (`rung9/bm903_capture.py:42` carries the map) and the AF_UNIX paths still
   attached by name. The kernel is the arbiter — `bind()` answers `EADDRINUSE` for a live peer
   *and* for a stale socket file alike — so the script's job is only to **not throw the answer
   away**. That is the whole reason `stderr=subprocess.DEVNULL` was a defect: a taken port came
   back `GDB_TIMEOUT_S` later as "gdb never stopped on the handoff", which reads exactly like a
   hung loader. Proof a fix owes: a held name makes the leg say so at startup, and a free name
   does not.

**A class-3 refusal outranks a leg result.** "The lane was busy" and "the boot is broken" are
different answers and only one of them is a gate RED. `rc_all` used to be last-write-wins, so a
refused leg 0 followed by a failed leg 1 returned 1, and even a clean run with one refusal
printed `RED`. Now a refusal is sticky: `rung9/bm903_capture.py:132` opens the flag,
`:155` sets it, `:221` returns 3 — this file's existing lane-busy code, the one `:128` already
returns before any leg starts. The forks inherit it, being generated text: rung 6 through
`rung6/bm602_construct.py:302` and rung 6.5 through `rung6_5/bm653_construct.py:308`, both
products re-generated and proven byte-equal to their own generators, which is also what keeps
the port map honest — the map only holds while the three files carry identical surrounding text.

**Where each G1/G2 site landed.**

| site | name claimed | class | state |
|---|---|---|---|
| `run_gate.sh:16` | `$SCRATCH/pxc1_nbd.sock` | 1 | landed; `rm -f` at `:24`/`:40` stays, it is the in-run restart |
| `rung7/boot_probe.sh:23` | `$SCRATCH/rung7_nbd.sock` | 1 | landed; `rung7_nbd` still in argv, so `:26-27` still sees peers |
| `rung7/throughput_probe.py:7` | `/tmp/r7_tp.sock` | 3 | **open** — a client attaching to a fixed name; G1 step 2 left it out by ruling |
| `rung9/bm903_capture.py:47` | 12468-9 | 3 | landed by G2, and the refusal is now sticky |
| `rung6/bm602_capture.py:53` | 12460-3 | 3 | same text, inherited through `D3` |
| `rung6_5`'s generated capture | 12464-7 | 3 | same text through `D4`; the product is gitignored, so its block is cited through `rung6_5/bm653_construct.py:308` |
| `rung9/probe34_capture.py:36` | 12440-1 | 3 | disjoint by the map, but **class 3 half-met**: `:74` still sends qemu's stderr to `DEVNULL` |
| `rung9/bm903_dbg_silence_probe.py:26` | 12470 | 3 | same: `:55` discards the refusal |
| `rung9/bm903_dbg_memcmp.py:20` | 12472 | 3 | same: `:55` discards the refusal |
| `rung9/bm903_px_memcmp.py:31` | 12474 | 3 | met: `:72` keeps a log, and `:58` holds the guard |

**What this section deliberately does not settle.** (a) **Abstain or preempt.**
`pristine_reverify.sh:199-201` skips whenever any nbdkit is alive; `run_gate.sh:21-22` and
`rung7/boot_probe.sh:26-27` kill peers machine-wide while the peer runs. Classes say *which*
names may be contested, not whether a run may clear one, and that stays Jericho's call. (b)
**Marker widening.** The three `live_boots()` guards match medium-name substrings, never ports,
so ports are class 3 by bind rather than class 2 by advertisement — and the guards remain
blind cross-rung, since no `MARKS` tuple covers another rung's marker. Measured while landing
G2: three captures each printed `lane clear` beside a live contending boot. (c) **Fixed names
inside the tree** (`nbdkit_rung7.log`, `serial_*.log`, rung 9's `HERE`-resident capture logs)
are class 3 in a place no `/tmp` sweep looked, and are queued nowhere. (d) The `/var/tmp`
guest-side class. None of these is fixable by citing this section; each needs an item.

---

## Milestones

- **M1 (2026-09-17, DONE):** pixels boot a CPU; loader-side decode; machine
  anchors measured. Rungs 1–2 gate-verified, rung 3 measured-probe.
- **M2:** ≥64 KB payload executes from pure pixels (Rungs 4–5).
- **M3 (2026-09-18, DONE):** pixel pipeline holds at ISO scale; nested-guest
  corroboration; format split (boot raw / archive PNG) pinned. (R7-TC-1
  probe legs, 0156493c.)
- **M4 (2026-09-19, DONE):** Linux kernel boots from a pixel medium
  (Rung 9). `tc@box` on serial from the PXC1 medium over ATA PIO with our
  own executed 16-bit stage2 building the protocol handoff — gate `bash
  rung9/run_bm903_e2e.sh` `42 pass, 0 red` ×2 (BM903, `d27f46c6`). TCG
  only; real silicon remains Rung 8.
- **M5 (2026-09-20, DONE):** corruption-tolerant boot (Rung 6, BM602) — the
  PXC2-E 7-plane medium, Hamming(7,4) executed in 16-bit; damaged media reach
  `tc@box` with a handoff byte-identical to the clean one. Parallel branch, so
  M4's kernel path is unchanged by it.
- **M5b (2026-09-20, DONE):** code that arrives as pixels *runs* (Rung 6.5,
  BM651) — rung 5's verified second image is executed, keeps a memory contract
  the loader checks on the way back in, and a pixel-corrupted image is refused
  before the instruction pointer ever reaches it. `rung6_5/run_bm651_e2e.sh`
  GATE651 PASS ×2. Closes TASK_BM503, the rung-5 stretch row.
- **M5c (2026-09-20, DONE):** code that arrives as *damaged* pixels runs
  (Rung 6.5 option C, BM653) — BM651's image carried in PXC2-E, 256 of its plane-1
  bytes destroyed on the medium, repaired by the executed decoder to the clean
  CRC, entered, and handing off a kernel state byte-identical to the undamaged
  medium's; the corrector-off twin refuses at the gate. `rung6_5/run_bm653_e2e.sh`
  2 of 2 passes clean ×46 identity checks. Two numbers the ladder should keep:
  a Hamming decoder can make an executable word *worse* and print
  `ECC=00000001` doing it, and an image that breaks the handoff it is supposed to
  leave alone still boots the box — the contract is liveness, not containment.
- **M6:** physical hardware boots from pixels (Rung 8).

## Critical Path

```
Rung 4 ──→ Rung 5 ──→ Rung 7 (scale probe, shim-allowed)
    │                   │
    │                   └──→ Rung 9 (kernel handoff, oracle-first) ──→ Rung 8 (hardware)
    └──→ Rung 6 (ECC, ✅ 2026-09-20)  Rung 6.5 (exec-from-data, ✅ 2026-09-20)
                └──────────┴──────────→ option C (BM652 designed ✅; BM653 filed)
                                    Rung 7B (inflate-in-firmware, unprioritized)
```
