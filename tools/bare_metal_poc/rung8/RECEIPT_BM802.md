# RECEIPT_BM802 — Fault-sensitivity map (Rung 8 hardening)

Run: `rung8/bm802_overnight.sh` (agent-free, unattended), completed
2026-09-20T03:52:56-05:00. `BM802_RUN_STATUS.txt`: **DONE**, rows=363,
planned=306, rc=0. Driver exited cleanly (pid not alive). Three runs on one
append-only row file: the first map (193 boots, closed 2026-09-19T23:05), the
region split (69), and the header census plus its rechecks (101) — all in
`bm802_sweep_rows.txt` (363 JSONL boots).

## Method (one line)
Single known-good medium; one payload byte XOR'd `0xA5` (3 bits) at a
named offset, fixture (`bm802_fixture.py`) re-bakes the loader's
EXPECTED_CRC to the CRC the corrupted payload computes, so the guest
gate stays a **real** check that signs off on the fault. What is
measured is boot tolerance, not gate detection (that split is BM903 L6).
Primitive: stage2 band is outside the CRC and breaks the loader directly;
payload regions are behind the rebaked gate.

## Verified before believing (per lane discipline)
Cross-checked the derived map against the raw rows, not just its summary:
- **Controls 3/3 at stage>=5:** control-0/1/2 all stage 5, `CONTROL-OK`;
  median ~11.0 s. Fault budget 38 s = 3× that median (measured ceiling,
  not chosen). PASS.
- **Both gate-on legs `refused` + `gate-MISMATCH`:** gateon-0 (payload
  2156880) and gateon-1 (payload 8939395) → stage 1, `refused`,
  `gate-MISMATCH`. Non-vacuity holds. PASS.
- **All 12 coverage regions sampled** (plus the method region):
  stage1-mbr(16) stage2-code(37) stage2-crc-table(16) stage2-pad(11)
  setup-bootsect(8) setup-header(30) setup-code(31) pm-kernel(22) pm-pad(6)
  initrd(24) initrd-pad(7) filler-sink(6), and setup-header-census(89) on
  stride 1. 303 distinct perturbed offsets, each inside exactly one region.
  PASS.
- **Recheck legs reported:** every fatal census leg (12) plus 8 earlier
  SENSITIVE/SLOW legs re-run at 3× the budget (114 s) → 0 came alive, all
  20 `DEAD`. So SENSITIVE means a stopped boot, not a slow one. PASS.
- Fault-width legs (1-bit vs 3-bit at named offsets): width-initrd INERT,
  width-pm-kernel SENSITIVE, width-stage2-code INERT. Reported.

## What the map shows
Per-region single-byte sensitivity (samp → SENSITIVE/INERT):

| region | kind | bytes | samp | SENS | INERT | fatal% |
|---|---|---|---|---|---|---|
| stage1-mbr | band | 512 | 16 | 3 | 13 | 19% |
| stage2-code | band | 2,320 | 37 | 16 | 21 | 43% |
| stage2-crc-table | band | 1,024 | 16 | 16 | 0 | 100% |
| stage2-pad | band | 4,848 | 11 | 0 | 11 | 0% |
| setup-bootsect | payload | 497 | 8 | 0 | 8 | 0% |
| setup-header | payload | 119 | 30 | 3 | 27 | 10% |
| setup-header-census | payload | 119 | 89 | 12 | 77 | 13% |
| setup-code | payload | 15,768 | 31 | 0 | 31 | 0% |
| pm-kernel | payload | 4,280,992 | 22 | 16 | 6 | 73% |
| pm-pad | payload | 11,616 | 6 | 0 | 6 | 0% |
| initrd | payload | 9,260,807 | 24 | 7 | 17 | 29% |
| initrd-pad | payload | 12,537 | 7 | 0 | 7 | 0% |
| filler-sink | payload | 49,152 | 6 | 0 | 6 | 0% |

Headline: **weighting each region uniformly between its samples, 5.82 MB
of the 13.64 MB medium (42.6%) sits on a byte where a single-byte fault
stops the boot.** The CRC table itself is the sharpest signal — 16/16
offsets fatal (worst stage 1): corrupting the gate's own lookup table
always refuses the handoff. pm-kernel (73% fatal, worst stage 2) and the
executable stage2 code (43%) are the structural hot spots; the pads and
the filler-sink came back all-INERT across their samples.

The `setup-header-census` row is a check on this table's own method, not
extra coverage — see the addendum, and read every fatal% above as a sample
from a region, not as that region's rate.

## What the map CANNOT show
1. **RECOVERED is structurally empty.** Nothing on this medium can repair
   a fault until **Rung 6** is funded and built (ECC scoped in
   `rung6/BM601_ECC_SCOPING.md`, GO recommended, unimplemented). The
   three-way SENSITIVE/INERT/**RECOVERED** split from the filing is, on
   today's build, a two-way split; every "would an ECC have saved this
   boot" question is out of scope and unanswered here. This receipt does
   **not** rule on Rung 6 funding — it only shows what the map is blind
   to until that decision.
2. **This is a shape, not a census.** 303 distinct bytes perturbed out of
   **13,640,192** (0.0022% of the medium). The 42.6% figure assumes each
   region is uniform between its samples; the all-INERT verdicts on wide
   regions are thin (pm-pad/filler-sink/initrd-pad: 6–7 samples over
   ~12 KB each, setup-bootsect 8 over 497 B, setup-code 31 over 15.7 KB).
   INERT here means "not seen to matter in these samples," **not** "no
   fault here matters." A fatal byte can sit between two sampled offsets —
   and the addendum's census shows that it does: on the one window where
   this was checked byte by byte, the stride used everywhere else in this
   table found 3 of the 15 fatal bytes.
3. **Single-fault only.** Real media decay (USB bit-rot, bad flash
   sectors) arrives in bursts and adjacent bytes; multi-byte and
   clustered faults are unmeasured, so this understates the tail risk.
4. **Gate-fooled regime by construction.** Because the fixture rebakes
   the CRC to match, this sweep models the pessimistic case where the
   integrity gate is tricked into accepting a corrupt payload. On a real
   in-the-wild corrupt medium the CRC would not match and the guest
   refuses — which is exactly the 2 gate-on legs. The map therefore
   characterizes *kernel/boot tolerance downstream of a fooled gate*, not
   how often the gate catches a fault (BM903 owns that).

## Addendum (2026-09-20): one row of this receipt was wrong, and the fix
## measured something worth more than the correction

**What was wrong.** The first map reported `kernel-setup` as one region —
16,384 B, 32 samples on a 512-byte stride, 0% fatal — and this receipt said
the setup header "came back all-INERT". That was an artifact of the plan, not
of the medium: the region lumped the 119-byte zero-page handshake (payload
0x1f1..0x268, which `bm903_stage2_px.asm:183` copies into the zero page) in
with 16 KB of real-mode code the handoff never executes, and a 512 B stride
walked almost entirely through the dead part.

**The correction cost 69 boots** (gap-fill): the region is now
`setup-bootsect` (0/8), `setup-header` (3/30 on a 4 B stride) and
`setup-code` (0/31). The header is not inert: 3 of 30 stride samples were
fatal and the worst of them stopped the boot at stage 0 — the loader's own
magic check. It is also the region whose structure (fixed-size kernel fields,
not a byte stream) makes a fixed stride most likely to lie, so it is where
the method got checked.

**Then the census asked the method itself** (89 further boots + 12 rechecks,
region `setup-header-census`, stride 1 over the bytes the 4 B stride skipped;
deliberately excluded from the weighted headline because it re-covers the
same 119 bytes). Result:

| window reading | fatal |
|---|---|
| stride 4 B, 30 samples (the map's row) | 3 → 10% |
| census, the other 89 bytes | 12 → 13% |
| **whole window, byte by byte** | **15 of 119 = 12.6%** |

The stride **recalled 3 of the 15 fatal bytes.** It missed them because a
fixed stride over a structured region aliases: samples begin at 0x1f1, so
every sample is ≡1 (mod 4) — exactly one byte per 4-byte field, and one of
eight for the 8-byte fields. Where the other bytes of a field are fatal and
the sampled one is not, the region under-reads. So: the per-region fatal% in
this receipt are samples, not rates, and for the question Rung 6 asks they
are a floor. (Total distinct medium bytes perturbed is now 303, still
0.0022% of it.)

**Why the fatal bytes are the ones they are** — `bm802_header_fields.py`,
rc=0, no boots spent. After the copy, stage2 re-pins 14 fields inside the
window from its own constants (`mov byte/word/dword [ZP_ADDR + …]`), so a
medium fault there is overwritten and cannot reach the kernel. Every one of
the 15 fatal bytes sits in a field the loader does *not* re-pin, and all 15
belong to exactly four fields:

| field | fatal bytes | what the fault does |
|---|---|---|
| `header` = 'HdrS' (4 B at 0x202) | 4 of 4 | the loader's own second check fires: `GATE2=PASS` then `BM903-S2 HDRS CHECK FAIL`, stage 0 |
| `hardware_subarch` (4 B at 0x23c) | 4 of 4 | 0 → 0xa5/0xa500/0xa50000/0xa5000000; handoff builds, then silence (stage 2) |
| `setup_data` (8 B at 0x250) | 5 of 8 (bytes 0,4,5,6,7) | a list pointer the kernel walks |
| `init_size` (4 B at 0x260) | 2 of 4 (bytes 2,3) | 0x959000 → 0x309000 (declares *less* than it needs) or → 0xa5959000 |

The field names are not asserted from memory: they are licensed by three
values only the kernel puts where it puts them, read from the medium by the
same script (`'HdrS'` at 0x202, `initrd_addr_max` = 0x7FFFFFFF at 0x22C,
`cmdline_size` = 2047 at 0x238, plus `kernel_alignment` a power of two at
0x230). If those stop holding the script says so rather than naming fields.

**The finding inside the finding is on the INERT side.** `setup_data` is NULL
on this medium (eight zero bytes at 0x250). It is fatal at bytes 0 and 4-7 but
*inert* at 1, 2 and 3, which put the pointer the kernel walks at 42,240 /
10,813,440 / 2,768,240,640 — the last of them five times past this VM's 512 MB
of RAM (`bm802_boot_class.py:66`), so "it landed in low, already-mapped RAM"
is not an explanation that covers all three. What *is* measured is that all
three boots finished. Same for the six sampled bytes of `pref_address`, and
for both low bytes of `init_size`, which move it by at most 23 KB out of
9,801,728 while byte 2's 68% cut (0x959000 → 0x309000) is fatal. Real,
CRC-approved, gate-approved corruption that reaches a `tc@box` prompt. That
is the concrete case for the sentence at the bottom of this receipt — an
INERT byte is not a harmless byte, it is a fault nobody is looking at.

**Then the initrd row became the strongest case here** —
`bm802_archive_local.py`, rc=0, no boots spent. `initrd` reads 7 fatal in 24:
seventeen boots ran their scripts to completion with a byte flipped inside
`core.gz`. The ladder cannot distinguish "that byte did not matter" from "the
box booted a root filesystem it never verified", so the same 24 archives were
decompressed on the host — zlib's DEFLATE, the gzip trailer checked by hand,
and the extracted newc cpio walked so a damaged byte can be named by the file
carrying it:

| leg group | the archive's own verdict | extracted filesystem |
|---|---|---|
| 17 INERT | CRC mismatch, 17 of 17 | 1 to 4 bytes differ; length unchanged |
| 7 SENSITIVE | 6 CRC mismatch, 1 never inflates (the gzip magic itself) | 344 K to 11.5 M bytes differ |

So the SENSITIVE/INERT split tracks *how far the damage cascades through the
DEFLATE bit stream, and which file the blast lands in* — not whether the root
filesystem changed. 16 of the 17 INERT boots sit on a corrupted `*.ko.gz` that
this boot never loads; the 17th ran its whole boot on a corrupted
`lib/libresolv-2.28.so`. All 17 completed, and the medium's CRC gate signed
every one: the gate covers the bytes on the medium, while the archive trailer
is a second check over the *unpacked result* that nothing downstream
consults. That is the case for Rung 6 stated as a measurement: decay here does
not make a box that will not boot, it makes a box that boots something else.

(One correction inside this leg, because the first version of the probe got it
wrong: it reported a uniform ~48 KB output shortfall on every corrupt leg.
That was the probe losing the final 64 KiB input chunk when zlib raised, not a
property of the medium. Hand-parsing the trailer is what makes the "length
unchanged" column above true.)

**One observability limit, stated rather than papered over.** Past
`HANDOFF BUILT` the ladder has a single signal — silence. The kernel
registers its ttyS0 console long after the fields above are consumed, so
none of the fatal legs printed `Kernel panic`, `Oops` or any other diagnosis
text (checked: zero of them did). Stage 2 therefore means "the kernel never
reached the point of talking", which conflates a hang, an oops and an early
panic; the *field* that died is named by the arithmetic above, the *how* is
not observable from serial here.

**Timeout control for these legs:** all 12 fatal census legs were re-run at
3x the 38 s budget and stayed down, as did every earlier recheck — 20 of 20
across the map, 0 revived.

## Read against the Rung 6 case

A large SENSITIVE area (pm-kernel, stage2 code, the CRC table) is the
argument FOR paying +75% medium capacity for Hamming(7,4): decay then
equals a box that will not boot. A large INERT area is the argument that
some medium can go unprotected — and the warning: an INERT byte is a
fault the CRC gate happily signs off on. **Silence is not the same as
correctness.** The addendum's initrd leg puts a number on that: 17 of 24
initrd boots completed on a root filesystem whose own archive CRC failed,
so on this medium the dominant failure mode is not a dead box but a box
running bytes nobody verified. Funding decision stays with Jericho; this
is measurement, not a ruling.

## Artifacts
- `rung8/bm802_fixture.py` (gate-off rig, 5-leg selftest, 0 red),
  `rung8/bm802_boot_class.py` (the deterministic stage ladder),
  `rung8/run_bm802_sweep.py` (plan/boots/summary), `rung8/bm802_overnight.sh`
  (driver; header comment documents the relaunch command)
- `rung8/bm802_header_fields.py` — the addendum's mechanism leg: parses the
  loader's re-pinned fields out of `bm903_stage2_px.asm`, pins the kernel
  field layout from values in the medium itself, and exits non-zero if a
  fatal offset ever falls inside a field the loader overwrites. rc=0.
- `rung8/bm802_archive_local.py` + `rung8/bm802_archive_check.txt` — the
  initrd leg of the addendum: re-inflates the 24 corrupted `core.gz` images
  host-side, checks the gzip trailer by hand, and names the cpio entry each
  damaged output byte sits in. rc=0.
- `rung8/bm802_pin_bitest.py` — proves the stage1 pin below bites: builds the
  clean fixture, rebuilds against a deliberately wrong sha, and takes the
  AssertionError. rc=0.
- `rung8/bm802_sweep_rows.txt` (363 boots, append-only) — raw evidence
- `rung8/bm802_sensitivity_map.txt` — derived table, METHOD CHECK block,
  non-vacuity and recheck legs
- `rung8/BM802_RUN_STATUS.txt`, `bm802_overnight.log` — run bookkeeping
- Per-boot serial transcripts: `/tmp/bm802_rig/transcripts/` (scratch, not
  in the repo — 363 logs of a boot that mostly says nothing)

## 2026-09-20, later: the rig's stage1 check stopped reading a working file

`bm802_fixture.build()` used to compare its assembled stage1 against
`rung9/bm903_stage1.bin` — a build output nothing tracks — behind
`if ...exists():`. In a clean checkout the guard was false and the comparison
disappeared without a word; in a dirty one it silently followed whatever rung9
had last rebuilt. It now asserts the sha256 of the bytes *this rig* assembles
(`STAGE1_SHA`), which needs no ancestor file and is the stronger check: it also
fires if nasm or its flags change. `python3 bm802_fixture.py` 5/5 ok in 0.8 s,
`rig equivalence` among them — the emitted medium is unchanged, so no sweep row
moves. Found while closing the same class under BM653/BM602 (ROADMAP
TASK_BM001); the sweep itself was not re-run for it, because nothing this rig
writes into the medium depends on that line.

## 2026-09-20, later again: rung 8 from a clean tree, and 12 rows that match the lane's

The row that assembles its own medium is the one that can tell whether a
pristine checkout's ancestor bytes *are* the lane's, so rung 8 was run in a
`git archive HEAD` tree fed with nothing but `rung7/core.gz` and
`reproduce_prereqs.sh` (capture: `bm802_pristine_preflight.txt`). Its four host
legs came back rc=0 — fixture selftest 5/5 with `BM802 FIXTURE TALLY: 0 red`,
and its equivalence leg asserts `control fixture == rung9/bm903_medium_px.raw`
byte for byte over 13,640,192 B; the pin bitest took its AssertionError; the
setup-header and archive legs held. Then a bounded boot preflight
(`--limit=3 --recheck=2`, 12 boots, ~7 min, into the preflight's own files) put
12 rows next to the landed 363: **all 12 verdicts agree, and every fault offset
and computed gate value agrees.** Eleven agree on stage too; the twelfth is the
Tiny Core autologin race (stage 6 with the shell prompt, stage 5 without — the
same "the boot went on" either way), and the derived budget differs per run
(38.1 s there, 47.1 s here) because each run re-derives it from its own three
controls. What was *not* re-run is the 319-boot map: `--dry` re-derived its
plan and geometry exactly, and spending the printed ~165 min of TCG again would
re-measure a shape that has not moved.
