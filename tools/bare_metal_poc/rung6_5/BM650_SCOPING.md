# BM650 — Rung 6.5 scoping pass: exec-from-data, sized before it is written

**Asked by:** `ROADMAP.md` §Rung 6.5 ("Implementation is its own gated row;
scoping pass (sizes, budget) required before code, same as Rung 6"), on top of
the design pass `rung5/DESIGN_EXEC_FROM_DATA.md` (edafa7fd, BM-503D) and its
self-review `rung5/DESIGN_EXEC_FROM_DATA_REVIEW.md`.

**Deliverable:** sizes and budget, measured. No boot was run and nothing was
landed outside this directory: the leg is *assembled* here
(`scope/probe_exec_leg.asm`) so that its cost is a number from nasm rather than
a paragraph. Reproduce with `python3 bm650_scope.py` (writes only `scope/`).

## Verdict

**GO on the rung-5 base, with three corrections below, and option C filed
separately.** Code size is not a constraint at this base — not close:
the entire leg, code and strings, is **279 B against 64,740 B free** (0.43%).
What the scoping pass did find is that the design's own entry-state table is
wrong about one row, that the byte it wants to reuse as scratch is not free at
the time the design thinks it is, and that the ladder now has two other loaders
whose 8 KiB images would also fit the leg but have nothing in them to execute.

| option | base | verdict |
|---|---|---|
| **A** | rung5's chain, delta-forked into `rung6_5/` | **GO.** It is the only base with a decoded real-mode image to jump into, and it is where the design was written. |
| B | rung9's PXC1 chain | NO. Bytes fit (4,848 B free), but stage2's "exec" there is Linux's protocol handoff — the leg would be a second, smaller copy of Rung 9. |
| **C** | rung6's PXC2-E chain: put a real-mode image *on the ECC medium* and execute it | **FILED, worth more than A, costs a codec fork.** "Pixels that had to be repaired to CRC correctly then *ran*, and said so" is the composition rung 6 and rung 6.5 each almost claim. It needs a new region in `rung9/bm903_pxcodec.py`'s `build_payload` — the locked payload builder — so it is its own design pass, not this row's extra leg. |

## Measured

| quantity | value | source |
|---|---|---|
| rung5 stage2 code | 796 B | `nasm -f bin stage2.asm $(rung5_consts.py 65536)`, warning-free |
| its image | 65,536 B (128 sectors; tail is `rung4_pad.py`'s A5/5A/… pattern) | `rung5_layout.inc` `PAYLOAD_SECTORS equ 128` |
| free before the leg | **64,740 B (98.8%)** | measured, above |
| leg: arg-block + NID hand-off | 54 B | `scope/probe_exec_leg.asm`, addresses off nasm's own list file |
| leg: backward copy-down (1024 words, `std`/`rep movsw`/`cld`) | 25 B | same |
| leg: jump + receipt (mailbox cmp, NID-echo cmp, 3 branches, `EXEC=OK`) | 90 B | same |
| leg: verbose banner receipt (got-then-EXP) | 30 B | same |
| leg strings (banner + 3 refusal forms) | 80 B | same |
| **leg total** | **279 B = 199 B code + 80 B text** | same |
| stage2 with the leg | 1,075 B, 64,461 B still free | arithmetic on the two rows above |
| rung9 PXC1 stage2 | 3,344 B code / 4,848 B free | assembled here; **reproduces BM601's landed 4,848 exactly** — the measurement method checks against the ladder's own books |
| rung6 PXC2-E stage2 | 3,776 B code / 4,416 B free | same; the ECC fork spent 432 B, of which 236 B is the executed corrector |
| transcript growth on the green path | 35 B = **3.0 ms of wire** at the 115200 8N1 divisor rung5 programs | counted from the strings; rung5's own boot-to-receipt was ≤101 ms with a 50 ms poll |
| boots the row needs | 7 (green ×2, redA, no-banner, no-mailbox, halt, persist) | all 16-bit; no Tiny Core, so no autologin race and no anchor budget — Rung 6's slowest single leg was longer than this whole row will be |

## Corrections the design needs before code

**R-SCOPE-1 — put the leg AFTER the self receipt, not between WRITE and it.**
The design's §4 says the leg "grows one leg between the WRITE leg and the self
receipt". With that placement, an img2 that halts takes `STAGE2 SIZE=` and
`STAGE2 CKSUM=` down with it, and the halt leg's transcript is
indistinguishable from a rung-5 regression — the exact ambiguity the row exists
to remove. After the self receipt, a hang leaves every landed anchor intact and
the *absence* of `IMG2EXEC BANNER`/`EXEC=OK` is a clean signal. Placement is
free here: the self-receipt block ends by leaving DS=DST_SEG and the leg sets DS
and ES itself anyway.

**R-SCOPE-2 — the bytes below 2048 are the write bounce buffer, not dead.**
The design's copy-down justification says "raw interleaved planes at `:0` are
dead at that point". At the insertion point `IMG2_SEG:0..2048` holds the
*marker payload copy* that `rung5/stage2.asm:212-213` bounced in, for the EDD write at
`:231`.
Copying down over it is still correct — the write has completed and been
verified — but it is correct **only because the leg comes after `.wr_ok`**,
which is now an ordering constraint with a reason attached, not a coincidence.
Add to the leg's selftest: nothing re-issues int 13h after the copy-down.

**R-SCOPE-3 — the entry table says IF=0; the landed loader says IF=1.**
`rung5/stage2.asm:37` is `cli`, `:42` is `sti`, and nothing between there and the
insertion point (line 238) touches the interrupt flag. So img2 would run with
interrupts enabled and the BIOS timer tick firing inside the uncontained image —
which is a different (weaker) claim than "IF=0" and must not be inherited by
accident. Either 1 byte (`cli` before the jump) buys the design's own table, or
the receipt states IF=1 as the contract. Recommend the byte: the whole point of
the row is that the entry state is *known*.

**R-SCOPE-4 — `EXEC` is already a rung-5 token.** `msg3 db ' EXEC', 13, 10, 0`
ends the rung-4 self-receipt line, and `run_gate5.sh:88` greps
`STAGE2 CKSUM=.* EXEC`. A new `EXEC=OK` anchor is a different string, but every
grep in this row must be anchored (`(^|[^A-Z])EXEC=OK`) or it will be satisfied
by the old line. This is the same failure class as BM602 defect #8 — a guard
matched by a word it was never looking at.

## The contract block, fixed concretely (the design left "slot 2" ambiguous)

14 B of the 2,048 B window above the copied-down image, at `IMG2_SEG:2064`;
word 0 is a length so a later image grows the block instead of reordering it:

| off | word | owner |
|---|---|---|
| `+0` | `2048` = img2 length | stage2 writes, img2 reads |
| `+2` | `129` = medium LBA the image came from | same |
| `+4` | `0x3F8` = COM1 | same |
| `+6` | `0x5000` = trampoline CS for the `retf` | same |
| `+8` | `EXPECTED_EXEC_NID` = `low16(CRC32(img2)) ^ high16(…)` | stage2 writes; img2 prints it |
| `+10` | mailbox; img2 stores `0x4B4F`, stage2 clears before the jump | the "ran to the end" token |
| `+12` | NID echo; img2 copies word `+8` here | the "ran at all" token, in memory so stage2 can refuse without parsing serial |

`EXPECTED_EXEC_NID` is emitted by `rung5_consts.py` beside `EXPECTED_IMG2_CRC`
from the same `img2.bin` bytes, so the banner cross-check is build-consistent by
construction (the run-13 lesson: consts are regenerated, never hand-edited).
`rung5_consts.py` already asserts `len(img2.bin) == IMG2_LEN`, so each of the
four img2 variants must assemble *and* pad to exactly 2,048 B.

## What this pass cannot tell you

* No boot was run, so the ≤101 ms bound is cited from rung5's receipt and the
  3.0 ms of added wire is arithmetic — the implementation row re-measures both.
* The 279 B is the leg's cost with rung5's `puts`/`puthex4`/`puthex8` reused. If
  the implementation needs a `puthex` variant that takes the NID from memory
  rather than AX, that is a few more bytes against 64,461; it is not a risk.
* The probe sizes are of *this* implementation of each block. A different
  implementation is a different number; the number that matters is that the
  order of magnitude is three digits, not four.
* Whether the jump actually works is not scoping's to know. Everything the
  design claims about `retf` being the landed pattern is true — `stage1.asm:188-191`
  enters stage2 by exactly that mechanism — but stage2 entering img2 is still a
  boot, and boots are the row.
* Option C's cost is not measured here. It needs the payload builder forked,
  which is a design pass first, and it is the claim the ladder would actually
  remember ("the pixels were wrong, the loader fixed them, and the fixed pixels
  ran").

## Post-implementation addendum (TASK_BM651, 2026-09-20)

What the row measured against what this pass predicted. Full detail and the
transcripts: `RECEIPT_BM651.md`, `evidence/`.

| this pass said | the row measured |
|---|---|
| leg 279 B (199 code + 80 text) | **230 B**, against a matched baseline (rung5's own `stage2.asm` at the identical defines minus `EXPECTED_EXEC_NID`): code page 796 → 1,026 B, free 64,740 → 64,510 B |
| green path +35 B of transcript = 3.0 ms | **+33 B = 2.86 ms** at 115200 8N1 (161 B vs rung5's 128 B, counted from the landed receipts) |
| 7 boots, no anchor budget | 7 boots, 143 s wall, GATE651 PASS ×2, transcripts identical between the two passes |
| "whether the jump actually works is not scoping's to know" | Correct, and it bit: see R-SCOPE-6 |

**R-SCOPE-5 — the design review's copy-down hazard does not exist.**
`DESIGN_EXEC_FROM_DATA_REVIEW.md` item 8 rewrote the design's copy step to go
backwards on the grounds that dst and src "overlap fully". They do not: the
de-interleaved image is at `IMG2_SEG:[2048,4096)` and the destination is
`[0,2048)`, disjoint by construction (`rung5/stage2.asm:94-96`, the DEFECT-R5DEINT
fix is what created that arrangement). The row ships a forward `rep movsw`. The
review caught a hazard by reading the design's prose instead of the tree, and
the correction it "found and fixed" was itself the bug -- which is the same
failure mode R-SCOPE-1..4 were, pointed the other way.

**R-SCOPE-6 — `push seg / push off / retf` is a far JUMP; it has no return.**
The precedent at `rung5/stage1.asm:188-191` is landed and measured, and the
first build of the leg copied it. The image ran, printed its banner, executed
its contract, and its `retf` returned to `IMG2_SEG:.back` -- an offset in
*the image's own bytes*, because that is the segment that was pushed. On the
wire: `IMG2EXEC BANNER NID=EE1B` then `IMG2EXEC BANNER NID=0000` then serial
garbage, and no `EXEC=` verdict, forever. `call IMG2_SEG:0` (opcode 9A, 5 B)
pushes `CS:IP`, which is what a `retf` pops. Reusing a measured idiom is the
right instinct; the idiom's contract includes the thing it does not do, and
only the boot says so.

**Two more that the gate owed the row.** The success path fell through into its
own refusal labels, so green printed `EXEC=OK` *and* `EXEC=BAD-MAILBOX 4B4F
EXP=4B4F` -- values correct, branch wrong; only the leg's "refusals must be
absent on green" grep caught it. And leg 5 was first written as a transcript
diff against green, which can never pass: every variant embeds its own image
CRC, `IMG2 SUM`, `STAGE2 CKSUM` and NID, so lines 2-6 differ by construction
(DEFECT-R651-1; now a structural claim -- banner is the last line, line count
is green's minus the verdict).

