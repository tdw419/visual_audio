# BM652 — Rung 6.5 option C design pass: what an executable image costs a self-repairing medium

**Asked by:** `ROADMAP.md` §Rung 6.5, the row BM650 filed (`BM650_SCOPING.md`
verdict table, option C: "FILED, worth more than A, costs a codec fork"), and
the same note's own admission — *"Option C's cost is not measured here. It needs
the payload builder forked, which is a design pass first."* This is that pass.

**Deliverable:** sizes, geometry, code cost and a host-side rehearsal of the
claim, measured from the landed trees. Nothing was booted and nothing was
written outside `rung6_5/scope652/`. Reproduce with `python3 bm652_scope.py`
(104 lines of output, `scope652/bm652_scope_output.txt`; two consecutive runs
are byte-identical once the replay timings are stripped, so the numbers below
are not a lucky pass). `rung6/` and `rung9/` are read-only inputs and are
**imported**, not copied — the same discipline BM602's codec used against rung 9.

## Verdict

**GO, and cheaper than BM650 feared — but not for the reason it expected.** The
image region costs **zero medium bytes, zero sectors, zero reads**, because
PXC1's payload has carried 49,152 B of bank padding since BM903 landed: three
whole groups that are read off the pixels, corrected by pass 1, summed into the
gate CRC, and then dropped at `PX_SINK` for want of a destination. Option C does
not add capacity to the ECC medium; it **employs capacity the medium already
wastes.** The "locked payload builder" turns out not to need unlocking either —
the fork is a 2,048 B post-build patch of one padding group plus a fourth row in
the sub-image table, and it can be expressed as a byte delta against the payload
BM903 booted, which a rewrite of `build_payload` could not.

What it does cost, and what no one could see from rung 5's 16-bit tree, is a
**mode**. The PXC2-E walk runs in flat-32 because int 13h cannot reach past
1 MiB, so by the time the image's bytes are in memory the loader is not in the
mode the image was written for. The leg therefore has to leave protected mode,
run BM651's image unchanged, and re-enter to finish the Linux handoff. That is
**96 B of the leg's 392 B** — trivial in bytes, and the whole risk of the row:
the image owns the machine in between.

| option | shape | verdict |
|---|---|---|
| **C1b** | walk → correct → gate → **drop to real mode → run BM651's img2 unchanged → re-enter flat-32 → build the handoff → boot** | **GO.** It is the only composition where all three rungs' claims survive intact: the pixels were wrong, the loader repaired them, the repaired bytes ran, *and* the kernel still gets the byte-identical handoff BM602 gated. |
| C1a | same, but halt after the image instead of booting | NO. It buys nothing rung 6.5 A did not already prove, and it throws away the leg that makes this base interesting: with the handoff still pending, `EXEC=OK` followed by handoff dumps **byte-identical to the clean boot** says the image gave the machine back. A halt forfeits that for 53 B. |
| C2 | a 32-bit image executed in flat-32, no mode switch | NO. Saves the 96 B of mode return and loses the only asset worth keeping: BM651's proven 2,048 B image and its four variants (`noecho`, `nombox`, `halt`), which exist precisely to show the loader's refusal checks are not vacuous. Writing a new image to avoid 96 bytes of `66 EA` is trading a measured thing for an unmeasured one. |

## Measured

| quantity | value | source |
|---|---|---|
| padding already in the payload | 829 claimed groups + **3 free** = 832; the free ones are `PATTERN` bytes, CRC'd and corrected, destined for `PX_SINK 0x34000` | §1, §2 |
| image region cost | **0 B of medium** — 23,863,808 B / 46,609 sectors / 5,824 reads either way | §1 |
| …and the ceiling | any image up to **6 groups = 96 KiB** is free; the 7th costs **114,688 B = 224 sectors = 28 reads (+0.48 %)**, because PXC1 pads to whole 4-group banks | §1, scanned not asserted |
| the fork's delta | **2,048 of 13,631,488 payload bytes differ**, all inside group 829's span; length unchanged | §2 |
| gate value | `EXPECTED_CRC 0x393950AA → 0x2C14707B`; `EXPECTED_EXEC_NID = EE1B` from the same build (and it is BM651's own `EE1B`, the NID on its landed transcripts) | §2 |
| where the image physically is | 4 contiguous 512 B runs, one per data plane, at LBAs **6649, 13305, 19961, 26617**, 3,407,872 B apart; byte 0 = pixel **x=3200, y=207, channel R** of the 4096-wide frame | §3 |
| replay: clean | `ECC=0 PAR=0`, CRC pass, `regions[0x50000][:2048] == img2` | §4 |
| replay: 256 B scratch in plane 1 | `ECC=256`, CRC pass, **image at dst byte-identical to img2** — every fourth byte of the image's first kilobyte was wrong on the medium and is right in memory | §4 |
| replay: same medium, pass 1 NOPed | `ECC=0`, `CRC=A315E8EB` → **refused**, image at dst differs | §4 |
| replay: 2 symbols in one codeword, inside the image | `ECC=2` (mis-fixed), `CRC=55AFFF65` → refused before the leg | §4 |
| replay: equal-triple blind spot, inside the image | `ECC=0 PAR=0` — what the clean medium prints — `CRC=24A8BF80` → refused | §4 |
| destination | `0x50000` (= BM651's `IMG2_SEG` paragraph, unchanged): no live region overlaps it; the map of 16 claims has **0 collisions** | §5 |
| 64 KiB constraint, measured | the GDT's 16-bit code selector is limit `0xFFFF`, so the mode-exit's landing label must be below `0x10000`; stage2 ends at `0x9fff` — **24,576 B of headroom** | §5 |
| leg cost | **392 B**: mode-exit 43, exec+receipt 155, re-entry 53, 16-bit helpers 79, strings 62 | §6, nasm's own list file |
| against the budget | **4,416 B free** in rung6's stage2 — matched baseline re-measured at **3,776 B of code**, which is exactly BM650's number for this file, so the method agrees with the ladder's books. 392 B = 8.9 % | §6 |
| control build | one named textual delta (`call bee_correct` → `times 5 nop`): **5 bytes differ, code still ends at 3,776 B**, so no relayout and every BM602 anchor still lines up | §6 |
| boots | 7, ~68 s one pass (BM602's own measured wall times for these shapes: 11.3–12.3 s to `tc@box`, 1.3 s for a gate refusal), ×2 passes, plus Tiny Core's autologin race | §7 |

## What the medium's geometry will and will not let the row claim

A contiguous run of damaged medium bytes lives in **one plane**, so it is one
symbol in each of many codewords — the class Hamming(7,4) over byte symbols
repairs. That is the 256 B scratch above, and it is why "the pixels were wrong,
the loader repaired them, and the repaired pixels ran" is a bootable claim
rather than a hope.

The converse has to be said out loud, because it is the temptation: damage that
hits the **same in-plane offset in two data planes** is two symbols in one
codeword — BM602's leg G, confidently mis-fixed. On this medium that shape is
four bytes **3.4 MB apart**, which is not a scratch. §4 booted-host-side both of
the classes the CRC exists to catch, now with the faults inside the bytes that
get executed: the gate refuses *before* the leg, so `EXEC=` never appears. That
ordering is the claim's spine: **the corrector decides whether the image is
intact, the gate decides whether the leg runs at all, and only `EXEC=OK` says the
two agreed about which bytes they were protecting.**

## Corrections the implementation row must not skip

**R-SCOPE-7 — the contract block belongs at the TOP of the group, not above the
image.** BM651 put it at `IMG2_SEG + IMG2_LEN` (offset 2,048) because its window
was exactly 2,048 B. Here the region is a whole 16 KiB group and the image is its
first 2 KiB: a block at +2,048 sits in the group's padding, and the next image
that grows past 2 KiB walks over it. `EXEC_ARGS equ GROUP_BYTES - 16` (linear
`0x53ff0`) is inside the group's window, above any image the group can hold, and
— unlike R-SCOPE-2 on rung 6.5 A — it is written **after** the walk finished
summing the CRC, so it cannot move a gate value at all.

**R-SCOPE-8 — the image may have destroyed the machine the re-entry needs.**
Between the exit and the return, the image owns everything: it can reload the
GDT register, clear A20 (the handoff writes above 1 MiB and the walk already
did), leave DS/ES/SS pointing at paragraphs, and clobber flags. The measured
re-entry reloads GDT, re-asserts port 0x92 bit 1, re-aims SS/ESP at
`STACK_TOP`, and restores `eflags=0x46` — it does not assume `retf` was polite.
53 B. This is the byte cost of the option, and it is not negotiable: the alter-
native is a kernel entered with the image's leftovers.

**R-SCOPE-9 — a hung image is now a failed Linux boot.** On rung 6.5 A the
verdict was the last thing stage2 printed, so a hang cost nothing downstream.
Here the handoff is pending, so `halt` takes Tiny Core with it and the absence
of `tc@box` is ambiguous unless the gate asserts the last anchor it *did* see
(`GATE2=PASS` and the `EXEC=` banner) before calling it a timeout. Same shape as
BM650's R-SCOPE-1, one rung up: place the leg after every receipt that must
survive it, and give the halt leg a structural claim rather than a diff.

**R-SCOPE-10 — replace BM602's payload assertion, do not delete it.**
`bm602_pxcodec.py` asserts `payload == rung9/bm903_px_payload.bin`: "the ECC
medium carries the bytes the proven medium carries" is true by construction, and
it is load-bearing. The forked codec keeps it in a bounded form — the two differ
in **N bytes, all inside the image group**, checked by scanning, not by prose
(N = 2,048 here, measured). A row that drops the assertion has stopped
measuring the same medium and started asserting a new one.

**R-SCOPE-11 — the control build is a named delta with a round trip, or it is an
edit to a gated loader.** The `BEE-OFF` variant is the row's non-vacuity
evidence — without it, "the corrector repaired the image" has no counterfactual.
It must be written the way BM602 wrote every delta (match exactly once,
round-trip back to the landed text byte-for-byte), and §6 already proves the
delta is size-neutral at 5 bytes, so the differ and BM602's identity legs
transfer unchanged.

**R-SCOPE-12 — every anchor that names `0x393950AA` is a build product.** The
gate constant changes with the payload (§2), so the consts script must emit it
from the patched bytes on every build (run-13), and the fork lives in
`rung6_5/` with its own `.inc`: rung6's landed tree keeps passing its own gate
against its own CRC, or this row has silently broken a closed rung.

## The row this designs

`TASK_BM653 — option C implementation`, one gated row in `rung6_5/` (name
reserved here; it forks `rung6/`, which stays read-only):

| file | what it is |
|---|---|
| `bm653_pxcodec.py` | imports `bm602_pxcodec` (which imports `bm903_pxcodec`): patches img2 into group 829, emits the 4-row sub-image table + the new `EXPECTED_CRC`, and the R-SCOPE-10 bounded-delta assertion |
| `bm653_construct.py` | named deltas onto rung6's `bm602_stage2_px.asm` — mode-exit, exec leg (BM651's text minus the copy-down), re-entry, `EXEC=` verdict strings — plus the `BEE-OFF` control delta; all round-tripping to rung6 byte-for-byte |
| `bm653_consts.py` | `-D` flags emitted from the patched payload and the image, both CRCs from one build |
| `bm653_img2.py` | the four BM651 variants, unchanged source, reused as-is |
| `run_bm653_e2e.sh` | 7 boots ×2: green, repaired (predicted `ECC=256`), BEE-OFF control, two-symbol refusal, blind-spot refusal, halt, scribbler — each against predictions written to a fixtures file **before** qemu runs, plus BM602's identity legs (transcripts + handoff dumps) between green and repaired |

The two legs BM650 could not have imagined are the two that make this row worth
booking: **the corrector-off control**, which is the whole difference between
"it ran" and "the repair is what let it run", and **the scribbler**, where an
image prints `EXEC=OK` and then trashes `HDR_SCRATCH`, and BM602's locked capture
proves the handoff differs. That pair says the thing neither rung 6 nor rung 6.5
can alone: repaired pixels ran, and the machine came back.

## What this pass cannot tell you

* **No boot was run**, so the mode-return is 96 B of hand-encoded `66 EA` and a
  defensive GDT reload that nothing has ever executed. R-SCOPE-6 is the lesson
  to bring to it: a measured idiom's contract includes the things it does not
  do, and only the boot says so. The replay proves the *bytes*; it cannot prove
  the *modes*.
* The §4 replays are `bm602_mkimg.guest_walk` — a Python mirror of the loader's
  loop, transcribed instruction by instruction and cross-checked by BM602 against
  the codec's algebra over all 3,407,872 codewords. It is the same evidence
  BM602 landed its fixtures on, and it is still not the guest.
* The per-leg seconds are BM602's measured wall times for the same shapes, not
  this medium's; the autologin race made BM602's pass B 340 s against pass A's
  296 s, and this row inherits that variance.
* Whether the image *should* be 96 KiB just because it is free is a product
  question with no geometry in it. The 2,048 B BM651 already proved is the
  recommendation.
* Nothing here touches rung 8. The silicon is Jericho's, and so is the decision
  to book BM653 at all.
