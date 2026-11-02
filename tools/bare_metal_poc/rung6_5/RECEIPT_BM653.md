# RECEIPT — BM653 (Rung 6.5 / option C): pixels that had to be *repaired* to CRC correctly, then ran, and said so

**Row asked** (`ROADMAP.md` §Rung 6.5, designed in `BM652_SCOPING.md` §"The row
this designs"): take BM651's executed image off the rung-5 medium and put it on
rung 6's **self-repairing** PXC2-E medium, so the claim becomes "bytes that
arrived wrong, were fixed by an executed Hamming decoder, CRC'd clean, and then
were *jumped into*". BM652 produced the design and the priced sizes and filed two
things it could not prove: the mode-return had never executed (§"What this pass
cannot tell you": *"the replay proves the bytes; it cannot prove the modes"*), and
the seconds were BM602's shapes, not this medium's. This is the implementation
row, and both of those are now measured.

**Answer (measured, this row):** it runs, and the repair is what let it run. The
2,048-byte image is interleaved across the medium's four data planes, so plane 1
carries every fourth byte of it; damage **256 consecutive plane-1 bytes at the
start of the image's group to 0xFF** — a quarter of the image's first kilobyte,
256 of its executed bytes wrong on the wire — and it still arrives at `0x50000`
as the image BM651 wrote:
`ECC=00000100` (= 256, the number the design predicted before any boot),
`GATE2 CRC=2C14707B EXP=2C14707B`, `GATE2=PASS`, `IMG2EXEC BANNER NID=EE1B`,
`BM903-S2 EXEC=OK`, `HANDOFF BUILT`, `tc@box`. The handoff the loader then builds
is **4,096 bytes of zero page and 512 of cmdline byte-identical to the clean
medium's**, captured at the kernel entry by BM602's locked gdb fork — so the
*repaired* boot is not merely a boot that happened to work, it is the same
machine state as the undamaged one. The corrector-off control on the identical
medium — five NOPs where `call bee_correct` was — refuses at
`CRC=F0050680 EXP=2C14707B` 1.3 s in, prints no banner and no verdict, and its
transcript is the clean boot's up to the CRC line. Then the two things this row
was really for: the **two-symbol leg shows the decoder making the image
strictly worse** (2 damaged bytes in, 3 wrong bytes out, the third one *written*
by the "fix", `ECC=00000001` printed as though it had helped), and the
**scribbler** keeps every word of BM651's contract, prints `EXEC=OK`, and rewrites
2 bytes of the kernel header band out of the 4 it poisons — which the capture
sees. `run_bm653_e2e.sh` **2 of 2 passes clean**, 46 identity checks green / 0
red per pass, run from a directory with every generated artifact deleted — and
then re-run after defect #11 below, which is the pair this receipt quotes: **2 of
2 clean, 566 s, 49 identity checks green / 0 red per pass**.

## Command and result

```
$ cd tools/bare_metal_poc/rung6_5 && bash run_bm653_e2e.sh
...
PASS 1: clean
PASS 2: predictions re-derived from a clean rebuild are byte-identical to pass 1's, apart from the replay-duration line
PASS 2: clean
================================================================
2 of 2 passes clean, 566 s wall
dumps landed: 18 files
evidence: evidence/bm653 (8 entries, plus transcripts/ and dumps/)
BM653_RUN_STATUS=GREEN
```

That is the shipped pair, run after defect #11's fix. The pre-fix pair was
**2 of 2 clean in 334 s** with 46 checks; `evidence/bm653/` holds only the later
one, because the landing overwrites rather than accumulates — the earlier pair's
record is preserved in this file's own history at commit `0c1a334d`.

Each pass is 5 static stages → a pinned-reference preflight → 7 boots → 49
identity checks → BM602's own clean regression, and the pass loop **compares pass
2's predictions file to pass 1's** (`cmp -s`, with the single
`host_replay_seconds` line stripped) before accepting the pair — so "it was green
twice" cannot mean "it re-predicted itself twice". Both passes were run from a
directory in which every generated artifact had been deleted (`build/ fixtures/
captures/ scope653/`, the four `.inc`, the images, the fork `.asm`s, the fixtures
JSON, `evidence/bm653/`).

Normalising the pass stem and every duration and boot-count out of
`evidence/bm653/e2e_pass_1.txt` and `_2.txt` makes the two 24-line records
**byte-identical** — 7 boots and 49 identity checks and the regression agreeing
line for line, with only the clock differing.

## Files (all in `rung6_5/`; `rung6/` and `rung9/` are read-only inputs, untouched)

| file | what it is |
|---|---|
| `bm653_pxcodec.py` | patches BM651's image into padding group **829 of 832**, emits the 4-row sub-image table and the new `EXPECTED_CRC`, and asserts the R-SCOPE-10 bounded delta against rung6's payload |
| `bm653_construct.py` | 7 named deltas onto `rung6/bm602_stage2_px.asm` (exec contract header, 4th sub-image row, the exec leg, a 16-bit hex helper, the verdict strings, the witness words) + the 1-delta `BEE-OFF` control + 7 deltas on rung6's capture fork; every one matching exactly once and round-tripping byte-for-byte |
| `bm653_img2.py` | BM651's four variants rebuilt to its landed `evidence/img2_variants.txt`, plus one new variant (the scribbler) from one named delta onto BM651's source |
| `bm653_mkimg.py` | the 7 media and **every prediction**, from two independent replay implementations, before qemu is named anywhere |
| `bm653_gate.py` | one boot, BM602's eight loader checks unchanged, plus the exec-line and ordering checks this row adds |
| `bm653_identity.py` | rung9's T1–T4 normaliser on all seven transcripts against the clean boot, and the executed handoff dumps against each other and against BM903's and BM602's landed dumps |
| `bm653_refs.py` | pins BM903's three leg-0 handoff dumps into `evidence/refs/` with a sha256 manifest, and `--check`s them before the boots — added after finding #11 |
| `bm653_size.py` | the leg's code cost, measured on the fork that shipped, using BM650's and BM652's own scanners |
| `bm653_lane.py` | refuses to boot if any bm903/bm602/bm653 qemu is alive |
| `bm653_longwatch.py` | **not part of the gate**: 8 alternating full-window boots that ask the one question leg 7 cannot — what the kernel does with a handoff the image rewrote |
| `run_bm653_e2e.sh` | the pair, the cross-pass prediction comparison, and the landing of `evidence/bm653/` |
| `evidence/bm653/prereq_pristine.txt` | the record of the row's **second** pristine run — this time over a tree built only by `../reproduce_prereqs.sh` — plus that script's four refusal tests |

## What was built

**The medium.** PXC2-E, 4 data + 3 parity planes, 23,863,808 B / 46,609 sectors /
5,824 reads, carrying rung 9's 13,631,488 B payload **unchanged in length** and
BM651's 2,048 B image in the group that used to be padding. Delta against
`rung6/bm602_px_payload.bin`: exactly **2,048 of 13,631,488 bytes differ, all
inside `[0xcf4000, 0xcf4800)`** — nothing else on the medium moved. Image group
829 → `0x50000`, plane-0 chunk at LBA 6649, gate CRC `2C14707B`, exec NID `EE1B`.
The execution costs **zero medium bytes**: it spends one of the three padding
banks the payload already wasted.

**The loader.** 7 deltas, 21,462 B of gated text → 30,056 B (+8,594 B of *text*;
the code cost is below). After `GATE2=PASS` it leaves flat-32 with hand-encoded
`66 EA` + `dw .rm_entry, 0x0008`, runs the image in real mode under BM651's
14-byte contract block at `EXEC_ARGS = 16368` inside its own 16,384 B group,
`call 0x5000:0`, then defensively re-enters 32-bit and only then builds the zero
page, cmdline and register handoff. The control fork is `call bee_correct` →
`times 5 nop`: 5 bytes, **same code end**, so the pair differs in behaviour and
not in size or geometry.

**The images.** BM651's four variants rebuilt here and checked against its landed
evidence — green `101BFE00`/`EE1B`, noecho `92DD6EF6`/`FC2B`, nombox
`0C818841`/`84C0`, halt `85E95236`/`D7DF` — plus the scribbler (`30B1B0EC`/`805D`),
which differs from green at **120 bytes inside the same 2,048**, whose delta
undoes to `bm651_img2.asm` byte-for-byte, and whose contract offsets
(`ARG_NID=8`, `ARG_MBOX=10`, `ARG_ECHO=12`, mailbox `0x4B4F`) are cross-checked as
text against both sources. The banner string `IMG2EXEC BANNER NID=` appears
exactly once in each image, in **no** stage1/stage2 build, and **not** in the
8 KiB of the medium ahead of the pixel band — so a wire banner can only mean the
repaired pixels executed.

**The size.** Baseline `rung6/bm602_stage2_px.asm`: code end 3,776 B — exactly
BM652 §6's number for the same file, so the two scanners agree. This fork: 4,128
B. **The leg costs 352 B**, against BM652's priced estimate of 392 B (−40 B, 90 %
of the estimate). Control: +0 B against the fork. 4,064 B of the 8,192 B stage2
container still free, 50.4 % used.

## What each leg is allowed to prove

| leg | medium / loader | predicted before any boot | what the wire said |
|---|---|---|---|
| 1 `exec_green` | clean PXC2-E + green image | `ECC=0 PAR=0`, `CRC=2C14707B EXP=2C14707B`, `PASS`, banner `EE1B`, `EXEC=OK`, handoff, `tc@box` | all six, in that byte order; 11.3–11.5 s |
| 2 `exec_image_repaired` | **256 consecutive plane-1 bytes of the image group stuck at 0xFF** | `ECC=00000100 PAR=00000000`, CRC back to the clean constant, `PASS`, `EXEC=OK`, `tc@box`, and the handoff equal to leg 1's | as named; `boots=2` on pass 1 (the autologin coin, §below) |
| 3 `exec_beeoff_control` | **identical damage**, corrector NOP'd out | `ECC=0 PAR=0`, `CRC=F0050680 EXP=2C14707B`, `FAIL`, no banner, no `EXEC=`, no handoff | 1.3 s, refused; the 40 B after its cut line carry no verdict |
| 4 `exec_two_symbol_in_image` | faults in planes 0 **and** 1 of one image codeword (word 100) | `ECC=00000001`, `CRC=7B010EBF` refused, no `EXEC=` | as named — and `img_wrong=3` where 2 bytes were damaged |
| 5 `exec_blind_spot_in_image` | one equal fault in each of d0/d1/d2 of one codeword (word 200): every syndrome zero | `ECC=0 PAR=0` — the clean medium's own counters — `CRC=11947ADB`, refused | as named; 3 image bytes stay wrong |
| 6 `exec_halt` | clean medium carrying the HALT variant | gate `PASS`, banner `D7DF`, and **no `EXEC=` line of any kind** | 45.0 s of host patience; the transcript ends at the banner |
| 7 `exec_scribbler` | clean medium carrying the SCRIBBLE variant | `PASS`, `EXEC=OK`, `HANDOFF BUILT`, and the zero page differing at `0x1f1 1B→EF`, `0x1f4 2A→DE` | exactly those 2 of 4,096 bytes; 4,094 identical; all 25 registers identical |

Leg 3 is the row's non-vacuity control and the reason leg 2 means what it says: same
medium, same damage, only the corrector removed, and the boot dies at the gate.
Legs 4 and 5 are the two known failure classes of Hamming(7,4) over byte symbols,
both moved *into the executable region* so that what the gate stops is
specifically an image from ever being entered.

**The identity half, 49 checks.** (A) transcripts: rung9's own `bm903_norm_transcript.py`
T1–T4, imported by path. Every leg's transcript equals the clean boot's up to its
cut point, with **every differing byte inside one of four whitelisted fields**
(`ECC=/PAR=`, `GATE2 CRC=/EXP=`, `GATE2=`, `BANNER NID=`), each field equal to the
pre-boot prediction, the two refusals' verdict asserted as the *following* line,
and the tail after each cut checked for a verdict the leg is not supposed to
reach. The anchor legs are compared whole, because T4 cuts a normalized
transcript before `tc@box` can ever appear in one. (B) dumps:
`bm602_capture.py` — rung6's fork of rung9's locked session, re-forked here by 7
deltas — run twice per medium. `leg0 == leg1` strictly on all three media
(determinism), then
`repaired == green` **byte-identical** (4,096 B zero page, 512 B cmdline, 25
register fields), then **both** equal BM903's PXC1 and BM602's PXC2-E reference
dumps — 18 dump files, and the scribbler differing at exactly its 2 predicted
bytes against all three references. The BM903 side of that is checked against
this row's **pinned** copy (`evidence/refs/`, defect #11), and the 3 extra checks
in the 49 are the sha256 verifications that those three reference files are still
the bytes BM903 landed.

## The guest's own numbers

```
leg                       pass 1 wall  boots   pass 2 wall  boots   wire
exec_green                   11.8 s       1      101.9 s       3    ECC=0 PAR=0 CRC=2C14707B PASS -> tc@box
exec_image_repaired          56.6 s       2      192.2 s       5    ECC=00000100 CRC=2C14707B PASS -> tc@box
exec_beeoff_control           1.3 s       1        1.3 s       1    CRC=F0050680 -> refused, 1.3 s
exec_two_symbol_in_image      1.3 s       1        1.3 s       1    ECC=00000001 CRC=7B010EBF -> refused
exec_blind_spot_in_image      1.3 s       1        1.3 s       1    ECC=0 PAR=0 CRC=11947ADB -> refused
exec_halt                    45.0 s       1       45.0 s       1    banner, then nothing
exec_scribbler                1.3 s       1        1.5 s       1    EXEC=OK, HANDOFF BUILT, poisoned
refs preflight                0 s                     0 s           3 pinned BM903 dumps, sha256 intact
identity                                  17 s                   17 s   GREEN 49  RED 0
bm602 clean regression                      12 s (1 boot)         12 s (1 boot)
```

Pass 2 is the autologin race in one place: the clean boot needed **3** attempts
and the repaired one **5** (8 allowed), every one of them a correct loader run
that simply did not get a shell on `ttyS0` inside 45 s — the same measured rates
BM903 booked (3/8, 5/8). The pair before that needed 1 and 2. No leg ever
exhausted its attempts, and the boots' *wire* columns are identical across both
passes, which is the part the row claims.

The design cell's `predicted ECC=256` and the wire's `ECC=00000100` are the same
number written two ways. The cell's "≈68 s per pass from BM602's measured walls"
came out at **74 s of boots on a clean pass**, of which the halt leg alone is
45 s. Everything above that is a wait this row chose: two 45 s halt legs per
pair, plus autologin re-boots — **one** extra boot in the 334 s pair, **seven** in
the 566 s one, all of them inside the 8 allowed, and the 1.3 s refusal legs are
what the row costs when the coin does not move.

**What the decoder did on leg 4, named.** Replaying the same medium twice — once
through `bm602.guest_walk` (a mirror of the loader's loop) and once through
`bm653_mkimg.walk_bee_off` (an independent model with pass 1 absent), which is
also how leg 3's `F0050680` was derived:

| | pass 1 off | pass 1 on | image bytes wrong |
|---|---|---|---|
| leg 4 two-symbol | `CRC=286FD2AD` | `ECC=00000001`, `CRC=7B010EBF` | **2 → 3**, at `400, 401, 402`; byte 402 is one the *fix wrote* |
| leg 5 blind spot | `CRC=11947ADB`, 3 wrong | `ECC=0 PAR=0`, `CRC=11947ADB`, 3 wrong | **3 → 3** at `800, 801, 802` — the two rows are *identical*, so pass 1 provably did nothing at all |
| leg 2 repaired | `CRC=F0050680`, 256 wrong at `1, 5, 9, 13, …` | `ECC=00000100`, `CRC=2C14707B` | **256 → 0**, back onto the clean constant |

That is the sharpest thing this row measured: on a real double fault in the
executable region the corrector does not fail to help, it **makes the image
worse and reports one symbol repaired**. `ECC=` on the wire is a count of what
the decoder did, never a promise that it was right; only the CRC is that.

**And the full window, 8 boots.** Each leg's own budget ends the moment its
checkpoint appears, so leg 7 has never seen a kernel verdict. Run separately,
alternating, 75 s each, one transcript file per boot (landed in
`evidence/bm653/longwatch/` — by hand, since the gate deliberately does not run
this probe):

```
boot  medium            wall     tc@box   bytes   loader marks
1     exec_green        11.3 s   YES      1,355   enter@0.3 walk@1.3 verdict/banner/exec/handoff@1.3
2     exec_scribbler    11.3 s   YES      1,353   identical
3     exec_green        75.1 s   NO       1,106   identical   -- ends: login[497]: root login on 'tty1'
4     exec_scribbler    11.8 s   YES      1,365   identical
5     exec_green        11.3 s   YES      1,355   identical
6     exec_scribbler    11.8 s   YES      1,365   identical
7     exec_green        11.3 s   YES      1,355   identical
8     exec_scribbler    11.8 s   YES      1,400   identical
```

4 of 4 scribbler boots reach a shell; 3 of 4 green boots do, and the one that
does not lost Tiny Core's autologin tty1/ttyS0 coin — the same race that costs
this row's anchor legs a re-boot, and it landed on the *clean* medium. Normalising
kernel timestamps and the `login[PID]` field, boot 1 and boot 2 are **31 lines
each and identical** except the loader's own `GATE2 CRC=/EXP=` and `BANNER NID=`
pair, which differ because two different images ran. Nothing in the guest's
report says the handoff it was handed had been rewritten.

## What the rig learned

Eleven defects, all of them in this row's tooling (the tenth found by a
side-probe, the eleventh by running the row from a pristine checkout after it
had been committed, the other nine in the gate), each fixed by making the check
say what it means rather than by loosening it:

1. **The identity script's token pattern matched the normaliser's own
   placeholders.** `bm903_norm_transcript.py` had already replaced the counter
   field with `ECC=<HEX8>`, so the pattern that was supposed to collapse
   comparable fields collapsed nothing, and the first run came back 6 RED for a
   reason that was about the checker. Replaced with one `FIELD` regex used twice:
   `finditer` to bound where a difference may live, `sub` to prove nothing else
   differs.
2. **`tc@box` can never appear in a normalized transcript** — rung9's T4 cuts at
   the login/issue banner, which is *before* the prompt. The anchor legs were
   then "proving" that neither the clean boot nor the repaired one reached a
   shell. Fixed by comparing anchor-required legs as whole blobs.
3. A refusal leg cannot share a prefix with a passing leg that contains
   `GATE2=FAIL`; the cut point moved to the CRC line and the verdict is asserted
   as the line that *follows* it, with its bytes named in the check.
4. Consequence of (3): the repaired leg reported "never printed `tc@box`" on both
   sides of a comparison that had been silently cut at a refusal.
5. **`run_leg` ended in `return 0`** with a comment saying the caller counts — so
   a red boot could not turn a pass red. A gate whose failure path returns
   success is the same class of bug as a guard that never fires.
6. `bm653_size.py`'s first draft contained `assert x if hasattr(...) else True` —
   a check that cannot fail. Replaced with `assert base == 3776`, which is the
   line that makes BM650's and BM652's scanners cross-agree in the evidence.
7. **The medium read its image from a file BM651 also writes.** `bm653_pxcodec.py`
   opened `img2_green.bin` from disk, and BM651's row writes that name, in that
   directory. The clean-room pair died on it at 13 s — the *good* outcome; the
   bad one is a stale image silently patched into a 23 MB medium while every
   prediction downstream was computed from the fresh one. Now the build produces
   the image itself and asserts any on-disk copy equals it byte-for-byte.
8. A fixture key called `generated_at_s` held a **duration**, so the cross-pass
   comparison had an unnameable exempt line. Renamed `host_replay_seconds`, which
   makes it exactly one duration, exempt for a stated reason, and nothing else.
9. **The repaired leg's prose contradicted its own numbers.** The fault string
   said "1,024 bytes of the executed image are wrong"; its `image_bytes_wrong`
   field said 256, and the assertion 40 lines below proves the differing indices
   are `[4k+1 for k in range(256)]`. Both are true of different things — 1,024
   *medium-span* bytes, 256 *image* bytes — and the string named the wrong one.
   Now derived from the count that is asserted. Deliberately applied only after
   the in-flight pair had finished, so editing a prediction string could not
   trip the cross-pass comparison it was measured against.
10. **A side-probe let two runs share one log path.** The long-watch script named
    its transcript after the *medium*, not the boot, so a second invocation
    truncated the first one's file mid-run: the paired logs came back with a
    green transcript ending in `VFS: Cannot open root device` — a message that
    appears in **none** of the eight boots once each has its own file. Two runs
    writing one file is not a slow boot, it is a fabricated finding, and it was
    believed for about as long as it took to look. Every per-boot artifact is now
    named with its index.
11. **The identity stage's reference was not a reference.** It compared the
    executed handoff against `rung9/bm903_px_{zp,cmdline,regs}_leg0.bin` — files
    `rung9/run_bm903_e2e.sh` **writes at its own capture legs**, untracked and
    not ignored (rung9 force-added its `oracle_*` and `bm903_zp_*` dumps and its
    `bm903_px_regs_*.json`, but not the two `bm903_px_*_leg0.bin` siblings this
    row needed). So "byte-identical to the handoff BM903 gated" was checked
    against bytes a later rung-9 run may rewrite, and against nothing at all in
    a clean checkout. Found by extracting `git archive HEAD tools/bare_metal_poc`
    to `/tmp` and running the row there: its 5 static stages and all 7 boots came
    back PASS at the lane's numbers, and identity died 160 s in with
    `GREEN 40 RED 2` — after the pass it had already paid for. Fixed by pinning:
    `bm653_refs.py` copies the three dumps to `evidence/refs/` with a sha256
    manifest, `bm653_identity.py` re-checks each sha before trusting a byte,
    `bm653_refs.py --check` runs as a preflight before the boots (0 s), and the
    re-pin path **refuses** when source and pin disagree — tested by flipping one
    byte in a copy: 1 RED, `rc=1`, `refs.json` unchanged. Identity is now
    **49 checks** per pass (46 + the 3 pin verifications), and the pair below was
    re-run after this fix.

## Honest boundaries

- **`ECC=` is a count, not a verdict.** PXC2-E has no uncorrectable signal
  (BM602's boundary, inherited unchanged), and leg 4 shows why that is not merely
  a gap: the decoder can be *actively harmful* and print `ECC=00000001`. Nothing
  in the machine distinguishes "repaired" from "mis-repaired"; only the CRC does,
  and only because it is checked against a constant baked into the payload.
- **The contract is a liveness promise, not a sandbox — and this breach is
  inert.** The scribbler keeps the mailbox word, the echoed NID and the return,
  prints `EXEC=OK`, and *then* rewrites the kernel header band. 2 of its 4
  poisoned bytes reach the zero page (`0x1f1 loadflags 1B→EF`, `0x1f4
  raw_root_dev 2A→DE`); the other 2 are predicted away before the copy, and that
  prediction is what the capture checked. What the kernel makes of it is not a
  question this row leaves open, because the shipped leg cannot ask it — it stops
  watching at 1.3 s, long before a boot could fail. `bm653_longwatch.py` does:
  8 alternating boots, 4 green and 4 scribbler, same boot function, 75 s each.
  **Every scribbler boot reached `tc@box` at 11.3–11.8 s**, with all six loader
  marks at the same 0.3 s/1.3 s as clean, and a paired green/scribbler guest log
  is **line-for-line identical** (31 lines each, timestamps and PIDs normalised)
  apart from the loader's own `CRC=`/`EXP=` and `NID=` fields — which differ
  because different images ran. No `VFS: Cannot open root device` in any of the
  eight. The one boot that failed to print a shell was a **clean** one, which
  lost Tiny Core's autologin tty1/ttyS0 coin. So the channel from an executed
  image into the protocol handoff is open and byte-exact, and on this kernel this
  particular 2-byte corruption costs nothing observable. The scribbler proves the
  **absence of a sandbox**, not the presence of damage, and must not be quoted as
  though it showed a box that would not come up.
- **Leg 6's only judge is the host giving up.** `EXEC=HALT` is an *absence*
  observed after 45 s. Nothing inside the machine distinguishes a hung image from
  a slow one, and the budget is a number this row chose; a longer one would have
  produced the same verdict for a different reason.
- **The mode-return is now proven to work, not proven to be robust.** BM652's
  unexecuted 96 B of `66 EA` and its defensive GDT reload ran: leg 1 and leg 2
  both reach `tc@box` and both produce a handoff whose 25 register fields are
  identical to BM903's and BM602's landed dumps (`rip=0x100000 rsi=0x13ab0
  rsp=0x1f784 cr0=0x11 eflags=0x46`). That is the modes, on this medium. What it
  does *not* cover is an image that leaves the machine in some other mode — the
  re-entry is unconditional and unverified, and no leg tests it.
- **Predictions come from models of the loader, not from the loader.** Two
  independent implementations (`guest_walk`, instruction-by-instruction mirror;
  `walk_bee_off`, second author's data-plane-only decode) reduce the chance of
  the two halves agreeing for the wrong reason, and every delta round-trips
  byte-for-byte against the shipped file — but a bug shared between the model and
  the asm would still pass. The boots are what break the tie, and they agree.
- **Seven legs are not a fuzz campaign.** Each is one named, pre-decided fault at
  one word of one group. This row shows the two known blind classes are refused
  in the executable region, and that the executable region can be poisoned past
  the contract; it bounds no probability of undetected image corruption.
- **Scale stays rung-6.5's.** 2,048 B of hand-written 16-bit and a three-field
  contract. Nothing here says a 12 MiB kernel can execute off a repaired medium;
  the payload geometry is identical to BM602's and the exec window is one padding
  group.
- **Recorded deviations from the design's five-file plan.** (a) `bm653_consts.py`
  was folded into `bm653_pxcodec.py`, so both gate constants come out of one
  emitter and cannot disagree about which payload they describe. (b) The capture
  fork is 7 named deltas on **rung6's** `bm602_capture.py` rather than a fresh
  fork of rung9's, which keeps BM602's locked-session semantics and inherits its
  lane assumptions. (c) That lane asymmetry is one-directional: `rung6/bm602_lane.py`
  does not know about bm653's qemu, so a bm602 run will not see this row booting;
  `bm653_lane.py` checks all three. (d) The leg cost is **measured at 352 B
  against BM652's priced 392 B** — the estimate was good to 10 %, and the row
  reports the measurement. (e) `0x393950AA`, the anchor every leg's `.inc` is
  built around, remains a build product, as BM652 required.
- **What "reproducible" costs this row, measured from `git archive HEAD`.** BM653
  is not self-hosting from git alone, and neither is any rung above it. The
  payload chain reads `rung7/core.gz` (9,260,807 B — untracked, not ignored,
  sha256 `7f1e370d…b5a2`; BM903 booked that gap and named it TASK_BM001's), plus
  four ancestor **build products** a descendant gate reads as landed but only its
  own rung regenerates: `rung9/bm903_stage1.bin`, `rung9/bm903_px_payload.bin`,
  `rung6/bm602_px_payload.bin`, and `rung6/fixtures/` (the regression leg's
  media). The order that closes it is a script now —
  `tools/bare_metal_poc/reproduce_prereqs.sh`, first run by hand on 2026-09-20
  and checked in the same day: `core.gz` →
  `rung9`: `bm903_mkimg.py`, `bm903_mkimg_px.py`, `bm903_pxcodec.py` → `rung6`:
  `bm602_pxcodec.py`, `bm602_mkimg.py` → `rung6_5`: `run_bm653_e2e.sh`. That
  reproduces the ancestor payloads **sha256-identical to the lane's**
  (`e6ebe1ab6574…`, both `rung9/bm903_px_payload.bin` and
  `rung6/bm602_px_payload.bin`) — the point
  worth having, because R-SCOPE-10's "exactly 2,048 bytes differ" is a claim
  about a byte-exact ancestor, not about whatever was on disk. The static stages
  and all seven boots of the row then passed in the checkout at the lane's
  numbers; the only thing git did not carry was defect #11's reference dumps,
  which are pinned now. Re-archived after the pin, that checkout runs the whole
  pair **green: 2 of 2 clean, 439 s, 49/0 identity checks per pass**, and its
  18 executed-handoff dump files and its `fixtures_predictions.json` are
  **byte-identical to the lane's** — which is the strongest reproducibility
  claim available here: the same tracked tree, in a different directory,
  predicts the same numbers and captures the same machine state. What that
  checkout wrote is landed beside the lane's records as
  `evidence/bm653/cleanroom_pass_1.txt`, `cleanroom_pass_2.txt` and
  `cleanroom_fixtures_predictions.json`; the scratch tree itself was deleted
  (92% full), so those three files are the reviewable residue.
- **The prerequisite chain, as a script, and this row over the tree it made.**
  `tools/bare_metal_poc/reproduce_prereqs.sh` is the order above as one command
  with a verdict of its own: it refuses unless `rung7/core.gz` is present and
  matches its pinned sha, runs the five ancestor steps, re-pins the six byte
  landmarks downstream rows measure against (naming the step that owns any file
  it cannot reproduce), and hashes the six generated-but-tracked files before
  and after so a regeneration cannot quietly rewrite the checkout. Measured cold
  in a fresh `git archive HEAD tools/bare_metal_poc` tree with nothing added but
  `core.gz`: `PREREQ_STATUS=GREEN`, 35 s, 12/12 legs, no tracked file moved — and
  this row's pair then ran over that tree **2 of 2 clean, 372 s,
  `IDENTITY: GREEN 49 RED 0` on both passes, 18 dumps landed**, captured as
  `evidence/bm653/prereq_pristine.txt` together with the four refusal tests that
  show the script's own checks bite (wrong `core.gz`, absent `core.gz`, a
  flipped landmark pin, a hand-edited `.inc`; each exits 1). The tree also shows
  what git still does not carry: `rung7/` has no tracked file, so a clean
  checkout has no `rung7/` directory to receive `core.gz` until one is made.
- **Emulation only.** TCG `qemu-system-x86_64`, `-M pc`, no KVM, no interrupt
  state, IF=0 across the handover. Real silicon is Rung 8, and it is unchanged by
  anything here.

## Status

TASK_BM653 **CLOSED GREEN ×2** (2026-09-20), green a third time from a
pristine `git archive HEAD` checkout (2 of 2, 439 s) with dumps and predictions
byte-identical to the lane's, and a fourth from a checkout brought up by
`reproduce_prereqs.sh` alone — no hand-run recipe, nothing in the tree but the
commit and `core.gz` (2 of 2 clean, 372 s, `IDENTITY: GREEN 49 RED 0` both
passes; `evidence/bm653/prereq_pristine.txt`). Rung 6.5 option C is landed: an
image that arrives as damaged pixels on a self-repairing medium is repaired by an
executed decoder, gated by CRC, jumped into, checked against a contract on the
way back in, and then hands off a kernel state byte-identical to the one an
undamaged medium produces. Rung 6.5 is now closed on both of its options (A:
BM651; C: this). The remaining rungs are 8 (silicon — measured only, hardware
designation outstanding) and whatever the next scoping pass asks for.
