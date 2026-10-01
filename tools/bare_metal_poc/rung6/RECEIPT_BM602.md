# RECEIPT — BM602 (Rung 6): a medium that repairs itself, and the gate that still refuses

**Row asked** (`ROADMAP.md` §Rung 6, `rung6/BM601_ECC_SCOPING.md` §5): "flip N
specified corrupted pixels and still boot byte-identical; N+1 → specified
refusal." BM601 scoped the code and recommended option A — Hamming(7,4) over
byte symbols, three parity planes, +75% capacity — and said implementation was
its own gated row. This is that row, built and measured.

**Answer (measured, this row):** it boots. One whole 4 KiB plane chunk destroyed
(`ECC=00000FF4`) and a 128 KiB single-plane erase-block loss
(`ECC=0001FE1C` = 130,588 symbols) each still reach `tc@box` on serial, with
every counter the host replay named **before** qemu started, a serial transcript
byte-identical to the clean boot apart from those counters, and an executed
handoff — 4 KiB zero page, 512 B cmdline, all 25 register fields — byte-identical
to the clean boot **and** to BM903's landed 42-leg PXC1 medium. What must not
boot does not: a two-symbol codeword is mis-fixed and refused at the predicted
CRC, a three-equal-fault codeword is invisible to the corrector (`ECC=0`, like
the clean medium) and still refused, and a PXC1 medium handed to this loader is
refused by container tag in 0.3 s instead of failing one walk later as an
unexplained CRC mismatch. BM903's own gate and own medium re-run inside the same
invocation and are unchanged.

## Command and result

```bash
bash tools/bare_metal_poc/rung6/run_bm602_e2e.sh
```

Two consecutive full runs on the final code, both green: `GREEN 15  RED 0
skipped 0` in each (`bm602_e2e_passA.log` 08:32:47→08:34:37, 110 s;
`bm602_e2e_passB.log` 08:34:37→08:40:17, 340 s — the difference is the guest
autologin race, below, not the loader). Before the last leg was added, the same
gate scored `GREEN 14 RED 0` twice more (08:18:41→08:23:32 and
08:26:57→08:30:19), so no stage is green once by luck. Every RED leg fired
inside a run that ended green, and the two RED stages seen while building this
row were both bugs in the rig, not in the loader — they are listed under *What
the rig learned* because that is the part that does not fit in a tally.

The `evidence/` record below was re-landed on 2026-09-20 by the pair described
in the addendum: `GREEN 15 RED 0` twice, `IDENTITY: GREEN 32 RED 0` twice, 8.5
min and 3.5 min (pass A paid two autologin re-boots on `chunk_plane0_stuckff`
and `erase_block_128k`, 57 s legs; pass B booted all seven once and paid three
attempts on BM903's own anchor). All 18 landed handoff dumps are byte-identical
to the ones they replaced; the only files that moved are the five raw
`.serial`s and their leg reports, and they moved in the banner and prompt lines
the race adds, not in the compared 917 B.

## Files (all inside the row's scope, `rung6/`; `rung9/` is a read-only input)

| file | role |
|---|---|
| `bm602_pxcodec.py` | the PXC2-E medium: imports `rung9/bm903_pxcodec.py` and calls it (does not copy it), adds the three parity planes, the container tag, the layout `.inc`, and a 10-class corrector selftest |
| `bm602_construct.py` | writes the loader: 11 stage2 deltas + 2 stage1 deltas + 10 capture deltas onto rung9's text, each asserted to match exactly once, and **round-tripped** — undoing them newest-first must give rung9 back byte for byte |
| `bm602_stage2_px.asm`, `bm602_stage1.asm`, `bm602_capture.py` | generated; do not hand-edit, edit the delta list |
| `bm602_mkimg.py` | assembles (warning-free or no deal), replays the walk *including pass 1* on the host, and writes `bm602_fixtures.json` + 8 fixture media **before** any boot |
| `bm602_gate.py` | one fixture → one boot → the wire compared against that file; also the DEFECT-R4PRINT byte-offset order check |
| `bm602_identity.py` | BM601 §5 legs 1–2 in their strongest form: transcripts and handoff dumps byte-identical |
| `bm602_lane.py` | boot-lane guard, bidirectional: watches `bm903` *and* `bm602` qemu |
| `bm602_measure_corrector.py` | the executed corrector's assembled size, standalone |
| `run_bm602_e2e.sh`, `run_bm602_unattended.sh` | the row gate and a sleep-inhibited detached driver over it |
| `evidence/` | the landed record: `e2e_pass_A.txt` / `e2e_pass_B.txt` (the two GREEN 15 runs, every status line), `identity.txt` (GREEN 32), `codec_selftest.txt`, `construct_deltas.txt`, `mkimg_replay.txt` (the three static stages), `legs/<fixture>.txt` (the gate report behind the table below), `transcripts/<fixture>.serial` (the raw material of the byte-identity claim), `dumps/` (the 18 handoff dumps: zp 4 KiB, cmdline 512 B, regs JSON, per leg per boot), and `refs/` (the pinned BM903 leg-0 handoffs the B+ half compares against — see the addendum). `logs/`, `captures/` and `*.raw` are gitignored, so `evidence/` is what a reviewer can actually read — every claim below is checkable from it, e.g. `cmp evidence/dumps/bm602_px_erase_block_128k_zp_leg0.bin evidence/refs/bm903_px_zp_leg0.bin`. |

Untouched by this row: `rung9/*`, the shim, `locate_in_container`, every live
gate. rung9's tree is read, and `bm602_construct.py`'s round-trip is the check
that it was read faithfully.

## What was built

| quantity | PXC1 (landed, BM903) | PXC2-E (this row) |
|---|---|---|
| payload | 13,631,488 B / 832 groups | **the same bytes** — `cmp` byte-identical to `rung9/bm903_px_payload.bin`, sha256 `e6ebe1ab…be4ac0e` |
| planes | 4 data | 4 data + 3 parity (p1=d0^d1^d3, p2=d0^d2^d3, p4=d1^d2^d3) |
| medium | 26,641 sectors / 13,640,192 B | 46,609 sectors / 23,863,808 B (**+75.0%** capacity, 10,223,616 B parity) |
| ATA reads per group | 4 × 8 sectors | 7 × 8 sectors (5,824 reads/boot) |
| CRC32 gate | `EXPECTED_CRC 0x393950AA` | unchanged — parity is derived and never CRC'd; the gate still sums 13,631,488 decoded, corrected bytes |
| container | — | `'PXC2'` = `0x32435850` at MBR offset `0x180`, written by stage1, read back by stage2 from the BIOS copy at `0x7C00` |
| stage2 text | 15,920 B | 21,462 B (+5,542 B) through 11 named deltas |
| corrector | — | **236 B assembled** (228 B code + 8 B counters) vs BM601's 244 B standalone estimate — 4.9% of the 4,848 B BM601 measured free in the 8,192 B image |

Code size was never the constraint and is not now. The cost is capacity and
reads, exactly as the scoping pass said it would be.

## Prediction before boot, in three implementations that must agree

`bm602_mkimg.py` replays the loader against the numbers in
`bm602_px_layout.inc` — the same text the asm `%include`s — and runs pass 1
twice: once by the codec's algebra, once as an instruction-by-instruction
scalar transcription of the asm's own `cmp/jne` dispatch (its registers named
`al/ah/bl` as in the file). Both must produce the same counters, the same
bytes, and — for the two-symbol class — agreement on *which* byte the
corrector wrongly corrupts. Measured in this run's `evidence/mkimg_replay.txt`:

```
host replay of the 7-plane walk + pass 1: payload restored, ECC=0 PAR=0,
  CRC=393950AA == the gate constant (1.1 s); 0 of 832 groups needed the
  instruction-exact write order, 832 groups took the chunk-level skip and were
  spot-checked the slow way every 64th group
scalar-vs-codec over all 3,407,872 codewords of the real payload: same counts,
  same bytes (1 s), plus the two-symbol class agreeing on WHICH byte it wrongly
  corrupted
chunk-level skip vs per-offset scalar on the 128 KiB fault: ECC=0001FE1C
  PAR=00000000 both ways (1 s unpaced)
```

The corrector's own selftest pins ten codeword classes: clean, each of the four
data symbols, each of the three parity planes, a two-symbol codeword
(confidently mis-fixed), and the equal-triple fault whose three syndromes are
all zero (reported as clean). The last two are the gate's job, and both are
executed refusal legs below rather than a host-side hope.

## What each leg is allowed to prove

| stage | mechanism | verdict on the wire |
|---|---|---|
| S1 codec | 7 planes carry the landed PXC1 payload; 10-class selftest; layout `.inc` + meta emitted | GREEN |
| S2 construct | 11 + 2 + 10 deltas, each matching exactly once, all three files round-tripping to rung9 byte-for-byte | GREEN |
| S3 mkimg | warning-free nasm, tag read back out of the assembled MBR, host replay of walk + pass 1, 8 fixtures and their predictions written | GREEN |
| S4 control | rung9's **own** `bm903_px_corrupt.py` builds the corrupt PXC1 medium and predicts its CRC — this row does not predict its own regression numbers | GREEN |
| B1 `pxc1_front_end` | a PXC1 medium under this loader | `CONTAINER=00000000 EXP=32435850`, nothing after it, 0.3 s |
| B2 `two_symbol_collision` | faults in d0 and d1 of one codeword | `ECC=00000001` (mis-fixed), `GATE2 CRC=B72A10FD EXP=393950AA`, `GATE2=FAIL`, no handoff, no anchor |
| B3 `blind_spot_equal_triple` | the same value in d0, d1, d2 of one codeword: all three syndromes zero | `ECC=00000000 PAR=00000000` — the clean medium's own counters — and still `CRC=8E53C9D5` → refused |
| B4–B8 recovery | clean, PB0 chunk stuck-FF, PB1 chunk stuck-00, PP2 parity chunk stuck-FF, 128 KiB single-plane erase block | each reaches `tc@box`, each with the predicted `ECC`/`PAR`/CRC |
| ORDER | byte offsets in the transcript | counters before the gate line, gate line before the verdict (DEFECT-R4PRINT) |
| I-A transcripts | rung9's `bm903_norm_transcript.py` (T1–T4), imported by path, run on `logs/<fixture>.serial` | 913 B compared per pair; every differing byte inside the 25 B `ECC=`/`PAR=` field at the same offset, value = predicted; tokenising that one line makes each repaired transcript **byte-identical** to the clean one |
| I-B dumps | `bm602_capture.py` — rung9's locked gdb session forked by 10 named deltas | leg0 == leg1 strictly (determinism); clean == each repaired medium, strict, no normalization; and all three == the pinned BM903 leg-0 handoffs `evidence/refs/bm903_px_zp_leg0.bin`, `..._cmdline_leg0.bin`, `..._regs_leg0.json` (25/25 register fields, `rip=0x100000 rsi=0x13ab0 rsp=0x1f784 cr0=0x11 eflags=0x46`) |
| R1 | BM903's own anchor boot, its own policy (8 × 45 s) | reaches `tc@box`, 11–12 s |
| R2 | BM903's own gate on a corrupt PXC1 medium | refuses at `CRC=6AB8F2D3`, the value rung9's own predictor derived, `EXP=393950AA`, no handoff, no anchor |

ECC cannot buy a boot the old gate would have refused: the old gate runs
unchanged, in the same invocation, against both of its own media.

## The guest's own numbers

From the two final passes' gate lines (`evidence/legs/<fixture>.txt` and the
status lines in `evidence/e2e_pass_A.txt` / `_B.txt`; `wallA`/`wallB` include any
re-boots the leg needed):

```
leg                     wallA    bootsA   wallB    bootsB  wire
pxc1_front_end           0.3 s      1      0.3 s      1    CONTAINER=00000000 EXP=32435850, then nothing
two_symbol_collision     1.3 s      1      1.3 s      1    ECC=00000001 CRC=B72A10FD -> refused
blind_spot_equal_triple  1.3 s      1      1.3 s      1    ECC=00000000 CRC=8E53C9D5 -> refused
clean                   11.3 s      1     12.3 s      1    ECC=00000000 PAR=00000000 -> tc@box
chunk_plane0_stuckff    11.5 s      1     11.0 s      1    ECC=00000FF4 -> tc@box
chunk_plane1_stuck00    11.3 s      1     56.1 s      2    ECC=00000FF5 -> tc@box
parity_chunk_stuckff    11.8 s      1     12.0 s      1    ECC=00000000 PAR=00000FF2 -> tc@box
erase_block_128k        11.5 s      1     56.6 s      2    ECC=0001FE1C -> tc@box
```

The walk itself is not the cost: `trace` on every leg shows stage2 entering at
0.3 s and `PIXEL WALK DONE` — 46,592 sectors read across 5,824 ATA commands,
pass 1 over 3,407,872 codewords, 13,631,488 bytes de-interleaved and CRC'd — at
1.3 s. Seven planes instead of four buys **no measurable boot-time penalty** at
this scale. What varies is the ~10 s of kernel and initramfs after the handoff,
and the anchor legs may re-run up to 8 times because Tiny Core's autologin wins
the tty1/ttyS0 argument about half the time (BM903 measured 3/8 and 5/8): the
boots=2 legs above are that coin, and an earlier pass took 101.6 s over three
boots on one of them. No leg that got a *loader* line wrong is ever retried.

## What the rig learned

Eleven defects, all of them in this row's tooling, each fixed by making the
check say what it means — recorded because a green tally with this history
should not be read as a straight line:

1. `bm602_construct.py`: the header delta **deleted** `STACK_TOP equ 0x1f784`,
   which the proven loader references twice; and a delta written with `'''`
   closed by `''` + `'))` was a SyntaxError.
2. The "read all planes" delta omitted `mov dword [px_plane], eax` and matched
   nothing — the delta list now has to quote the proven file verbatim, which is
   the point of asserting an exact single match.
3. A `BEE_WORDS equ` assert anchored on `$` while the asm line carries a
   trailing comment.
4. `bm602_mkimg.py` rebuilt the CRC'd stream from the sub-image regions and so
   **lost the three bank-padding groups** that land in the sink: 13,582,336 B
   against 13,631,488. The stream is now assembled in walk order, and the
   codec's sub-image table is cross-checked against the `.inc` notation.
5. The scalar-vs-codec probe applied its fault to one buffer set and handed the
   *already repaired* buffers to the codec — each implementation now gets its
   own copy of the same corrupted state.
6. `apply_fault(start_word=9000)` named a group but spilled into the next
   chunk; the word range is now asserted.
7. **`bm602_gate.py` wrote qemu's serial transcript into the same file the leg
   report was redirected to.** Two writers at independent offsets over a
   truncate: the boot verdicts stayed valid, but the raw material for the
   byte-identity leg was garbage. Transcripts are now `logs/<fixture>.serial`,
   written by qemu alone.
8. **`--resume` matched the word GREEN inside a status line that contains both
   verdicts** (`identity rc=1 IDENTITY: GREEN 20 RED 6`), so a resume pass
   skipped a RED stage and reported the whole run green. The guard reads `rc=0`
   now. A guard satisfied by the word it is judging is not a guard.
9. `bm602_identity.py` demanded that the whole 25-byte counter field differ,
   when only the digits that change differ (3 B for `0xFF4` against
   `0x00000000`). The assertion is containment inside the field, at the same
   offset, at the same total length — and the transcripts are compared strictly
   everywhere else.
10. The same file required `loader_meta.captured_by` to differ when comparing
    two dumps made by the *same* fork — where nothing can differ — and printed
    that as if the registers had moved. It now separates the two failures.
11. The regression block gave BM903's control one 45 s boot although BM903
    measured the autologin race losing about half of them, and parsed
    `GATE2 CRC=…` with `awk '{print $2}'`, which returns `CRC=…`. Both now use
    the same 8-attempt policy and sed capture groups, with the `EXP=` value
    asserted too.

Two of these (7 and 8) would have produced a **false green** on the row's
headline claim. They were caught by reading the evidence files rather than the
tally line — which is the only reason to keep per-leg transcripts at all.

## Addendum (2026-09-20): the reference the B+ half trusts is pinned, then landed

BM653's pristine-checkout run found a defect class, not a BM653 bug: a
descendant gate that compares against an *ancestor's working output*. Rung 6 has
the same dependency, and this row was the ancestor-side example. B+ asked
whether BM602's repaired handoff equals BM903's, by reading
`rung9/bm903_px_{zp,cmdline}_leg0.bin` and `..._regs_leg0.json` — which are
`run_bm903_e2e.sh`'s capture OUTPUTS, not its sources. In this tree they exist
and a later rung-9 run rewrites them; in a clean checkout two of the three do
not exist at all (the root `.gitignore` excludes `*.bin`), and only the regs
JSON is tracked — its committed bytes measured equal to the pin, which is why
the pin was safe to make. Either way "identical to the handoff the 42-leg
medium produced" was a claim about bytes the reviewer could not see.

Fixed in two steps, both measured rather than asserted.

1. **Pin.** `RUNG9_REF_SHA` names the three sha256s and `bm602_identity.py`
   checks them before trusting a byte of the reference; a moved reference is a
   RED that says so, not a comparison against different bytes. Identity checks
   go 29 → 32. A full pair on that change: `BM602_RUN_STATUS=GREEN` twice,
   `GREEN 15 RED 0` each, `IDENTITY: GREEN 32 RED 0` each, the two pass records
   agreeing on every verdict with only the autologin re-boots (1 vs 2 on five
   of the seven legs) and the raw serial lengths differing.
2. **Land.** The row now reads a verbatim copy from its own
   `evidence/refs/`, with `refs.json` recording source, date and byte counts,
   and `rung6/.gitignore` carrying `!/evidence/refs/*.bin` so the two binary
   references are tracked without `git add -f` — an exception that survives the
   next `git add` rather than a one-time force. The pin still rules: a landed
   copy whose sha moves is as RED as a live one.

The migration is a change of *source*, not of *comparison*: the identity stage
run before it and the run after it differ in exactly one line, the B+ heading
(plus per-capture wall clocks), and both score `GREEN 32 RED 0`. What this row
gives up is stated rather than glossed: drift in rung9's *live* dump no longer
reaches this check — it is caught by rung9's own gate. What it keeps is the byte
claim, now checkable from a tree that has never run rung9's boots.

Distinguish, for the ratification this row feeds into: a **build input** from
the ancestor (`rung9/bm903_px_payload.bin`, `bm903_stage1.bin`) is legitimate as
long as a named command regenerates it, which the ROADMAP recipe does; a
**reference** a gate measures against must be pinned and landed. What neither
may be is a conditional — `if the file exists, compare` is a check that
quietly stops existing.

**Both sides of that measured in a clean tree, one variable apart.** A
`git archive HEAD` checkout that had been given the ancestor recipe — so it held
`bm903_px_payload.bin` and `bm903_stage1.bin`, and the tracked regs JSON, but
neither ignored `_leg0.bin` dump — ran this gate twice. With the row as
committed before the addendum: `IDENTITY: GREEN 23 RED 2`, both REDs "no landed
reference to match", and the row finishing `BM602_RUN_STATUS=RED (1 legs)` only
after paying for all seven boots. Copy in the pinned, landed reference and the
same tree runs `GREEN 15 RED 0` with `IDENTITY: GREEN 32 RED 0`, and its 18
handoff dumps are **byte-identical to the ones landed above** — as are its
predictions, once the two host-replay timing fields are removed. Two things ride
on that: the reference gap was the only thing missing, and the row's byte claims
survive a tree that has never run rung9's boots. The driver and an extract of
both runs are landed at `evidence/cleanroom/`.

One rig wart the same run exposed, recorded rather than fixed: the shell labels
*any* identity failure "a repaired boot is not the clean boot", so a missing
reference reads as an accusation about the medium. The `[RED]` lines above the
summary name what actually failed; the label stays, because re-wording one gate
string costs a full re-verification of a row that is otherwise green.

**The pinned references were then re-derived from their producer.** A pin nobody
can regenerate is a frozen accident, so `run_bm903_e2e.sh` was run — in a fresh
`git archive HEAD` tree fed with nothing but `rung7/core.gz` and
`reproduce_prereqs.sh` — twice: `42 pass, 0 red` on both passes, with the two
deliberately-RED legs firing identically (same zeropage offset `0x244`, same
guest-vs-host CRC cross-check). The three dumps that gate rewrote there hash
`bc2431d7be0ab1d2`, `30cd829f2a88c80c`, `935d5fe1c23f878e`: the three values in
`evidence/refs/refs.json`, byte for byte, the regs JSON included. What the B+
half trusts is therefore rung 9's output *as produced from the commit*, not a
copy of one lucky run in this lane's directory. Capture:
`evidence/cleanroom/bm903_pristine_pair.txt`.

## Honest boundaries

* **TCG only.** No silicon. Rung 8's box is still designated by Jericho, and
  everything here is an emulated IDE medium.
* **The fault model is per-plane confinement.** Every recovery leg damages one
  plane over a chunk- or erase-block-aligned span, which is what makes one
  symbol per codeword the worst case. A *column* fault — all four planes at the
  same in-plane offset, the class BM601's option C (RS(255,223) + interleaving)
  exists to survive — is not injected anywhere in this row and is not covered
  by option A. That is the scoping pass's boundary, restated rather than
  assumed away.
* **The corrector has no uncorrectable verdict, by design.** Two of the ten
  selftest classes are silent or confidently wrong. Both are now refused on the
  wire, but they are refused *because a CRC32 covers all 13,631,488 payload
  bytes* — a corruption that happens to preserve that CRC (about 1 in 2^32 for
  a random fault) would still build a handoff. ECC behind a checksum is not
  error-free; it is error-visible, and only down to the checksum's own strength.
* **The medium is not healed.** Repair happens in RAM on every boot; nothing is
  written back, there is no scrub, no bad-block remap, no counter of surviving
  syndromes. A medium with more than one damaged symbol per codeword boots
  until it does not, and the second class is refused.
* **+75% capacity is permanent.** 23,863,808 B for a 13,631,488 B payload. The
  cheaper option B (one parity plane plus per-chunk CRC locator, +25.4%) was
  not built, and the column-fault class that would justify option C was not
  measured.
* Faults are stuck-at-0x00, stuck-at-0xFF and single-byte XOR flips, at
  chunk/erase-block granularity, in one plane or one codeword at a time — BM601
  §1's model. No wear curve, no multi-plane coincidence, no timing-dependent
  read fault.
* Reproduce: `nasm`, `qemu-system-x86_64`, `gdb` and the `rung9/` tree are
  required; the gate refuses to start if another `bm903`/`bm602` qemu is alive,
  and `bm602_construct.py` must be run before editing any generated `.asm`. In a
  clean checkout this row also needs two of rung9's *build products*
  (`bm903_px_payload.bin`, `bm903_stage1.bin`), which nothing tracks and which
  the ancestor steps regenerate byte-identically — `bash
  tools/bare_metal_poc/reproduce_prereqs.sh`, one command with its own
  `PREREQ_STATUS` verdict, is that list (the TASK_BM001 bullet in `ROADMAP.md`
  records what it was measured to do). What it no longer needs is a rung9
  *capture output*: that dependency is what the addendum removes.

## Status

Rung 6 is built and measured in emulation. The medium that was 4 planes is 7,
the loader that BM903 gated is the same text plus eleven named deltas that
round-trip away again, and a box whose disk has lost a 4 KiB read chunk or a
128 KiB erase block still reaches `tc@box` with a handoff indistinguishable —
byte for byte — from the one the undamaged medium produced, and from the one
rung9 landed on 2026-09-19. The faults this code cannot fix are refused by name
and by number, predicted before the boot that confirmed them.
