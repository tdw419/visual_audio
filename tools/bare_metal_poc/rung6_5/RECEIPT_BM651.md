# RECEIPT — BM651 (Rung 6.5): bytes that arrived as pixels, executed, and were checked afterwards

**Row asked** (`ROADMAP.md` §Rung 6.5, `BM650_SCOPING.md` TASK_BM651): take
rung 5's second image — read from the medium, de-interleaved, CRC32-gated — and
*execute* it, with the loader checking afterwards that the image kept its side of
a contract. BM650 gave the verdict (GO on the rung-5 base, option B rejected,
option C filed) and the sizes. This is the implementation row.

**Answer (measured, this row):** it runs. 2,048 bytes that entered the machine as
pixels print `IMG2EXEC BANNER NID=EE1B` from inside their own code, leave the
mailbox word `0x4B4F` and echo their identity back in memory, and only then does
the loader print `EXEC=OK`. Three different ways of breaking that contract each
produce a different specified refusal on the wire — an image that runs but never
echoes gets `EXEC=NO-BANNER 0000 EXP=FC2B`, one that keeps the mailbox but not the
echo gets `EXEC=BAD-MAILBOX 0000 EXP=4B4F`, one that hangs is caught by nobody
inside the machine at all. And the safety half holds: flip one byte of the image's
pixels and the CRC gate refuses **before the image is ever entered** — no banner,
no write, no verdict. `rung6_5/run_bm651_e2e.sh` **GATE651 PASS ×2**, 7 boots,
143 s wall each, the two transcripts identical.

## Command and result

```
$ cd tools/bare_metal_poc/rung6_5 && bash run_bm651_e2e.sh
=== GATE651 PASS (143 s wall, 18 predictions fixed before the first boot, 7 boots) ===   # pass A
=== GATE651 PASS (143 s wall, 18 predictions fixed before the first boot, 7 boots) ===   # pass B
$ diff evidence/e2e_pass_A.txt evidence/e2e_pass_B.txt      # no output at all
```

Both passes were run from a directory with **every generated artifact deleted**
(`bm651_stage2.asm`, `bm651_consts.py`, the four `img2_*.bin`, the four media,
all `.inc`/`.lst`/`defs_*`/`.json`/`.png`/`.log`) — so the gate is self-contained:
it calls `rung5/rung5_layout.py` for the region-disjointness gate and the layout
`.inc`, regenerates the fork from its deltas, rebuilds, and boots. The two
transcripts are byte-identical down to the wall-clock line, and so are the
regenerated `bm651_stage2.asm`/`bm651_consts.py` (they came back with no diff
against the committed copies) — the build is deterministic end to end, which is
what makes the cross-run comparison a witness rather than a coincidence.

| leg | medium | expected before the boot | what the wire said |
|---|---|---|---|
| 1 GREEN-A | green | `IMG2 CRC=101BFE00`, `WRITE=OK`, receipt, banner `NID=EE1B`, `EXEC=OK`; no refusal label | all six present; line order WRITE < receipt < banner asserted numerically |
| 2 GREEN-B | *same file, no re-encode* | transcript identical to leg 1; img2 + marker region hashes unchanged | identical; `img2_sha=42bd1326…`, `marker_sha=5c06ab9d…` unchanged across the reboot |
| 3 RED-A | noecho | `EXEC=NO-BANNER 0000 EXP=FC2B`, **not** `EXEC=OK`, **not** `BAD-MAILBOX` | as named |
| 4 RED-B | nombox | `EXEC=BAD-MAILBOX 0000 EXP=4B4F`, **not** `EXEC=OK`, **not** `NO-BANNER` | as named |
| 5 HANG | halt | banner is the LAST line; line count = green − 1; no `EXEC=` of any kind | as named |
| 6 RED-CRC | green, 1 byte flipped at offset 66048 | `IMG2 FAIL CRC=0229EB69 EXP=101BFE00`, no banner, no `EXEC=`, no `WRITE=` | as named |
| 7 RE-GREEN | rebaked from the untouched PNG | identical to leg 1 | identical |

Legs 3 and 4 are the non-vacuity pair: each image fails exactly one of the two
loader checks and *passes the other*, so neither refusal can be an artifact of a
single catch-all, and neither check is doing both jobs.

## Files (all in `rung6_5/`; `rung5/` is a read-only input, untouched)

| file | what it is |
|---|---|
| `bm651_construct.py` | the fork: 5 named stage2 deltas + 4 consts deltas, each asserted to match exactly once, undone newest-first to reproduce `rung5/stage2.asm` and `rung5/rung5_consts.py` byte-for-byte |
| `bm651_stage2.asm` | generated loader. Outside the named blocks it *is* rung 5's text |
| `bm651_consts.py` | generated emitter: takes the image path as argv, adds `EXPECTED_EXEC_NID` beside the proven `EXPECTED_IMG2_CRC`, both from the same bytes |
| `bm651_img2.asm` | the executed image, one source four builds (`-DNO_ECHO`, `-DNO_MAILBOX`, `-DHALT`) |
| `bm651_img2.py` | builds the four, asserts the offsets agree **in both sources as text**, asserts `EXEC_ARGS` is out of reach of the copy-down, asserts 2,048 B and four distinct CRCs |
| `run_bm651_e2e.sh` | the gate: 4 builds, 18 pre-boot predictions, 7 boots, the hashes, the provenance check |
| `bm651_fixtures.txt` | those 18 predictions (4 NIDs, 4 image CRCs, 4 payload CRCs, 4 code sizes, `img2_base`, `wr_lba`), written before qemu is ever invoked |
| `evidence/` | `construct_deltas.txt`, `img2_variants.txt`, `build_sizes.txt`, `banner_provenance.txt`, `host_decode_green.txt`, `medium_hashes_after_boot2.txt`, `transcripts/<leg>.serial`, `e2e_pass_{A,B}.txt` (`*.log`/`*.bin`/`*.raw` are gitignored in this tree, so the receipts are kept as `.serial`/`.txt`) |
| `BM650_SCOPING.md`, `bm650_scope.py`, `scope/` | the scoping pass that preceded this row (separate commit) |

Reused by execution, not copied: `rung5/rung5_layout.py` (its build-time region
disjointness gate covers the write target), `rung5/rung4_pad.py`,
`rung5/rung4_consts.py`, `rung5/rung5_codec.py` (encode/bake/decode, argv-driven).
`rung5/stage1.asm` is assembled as-is with `-I .`, so it picks up this rung's
`stage1_const.inc` — one fewer fork, and stage1's own CRC gate is re-derived per
variant (rung-5's run-13 lesson).

## What was built

**The leg: 230 bytes.** Assembled against a matched baseline — rung 5's
`stage2.asm` with the identical define set minus the one define this rung adds:

| | code page | free in the 64 KiB payload |
|---|---|---|
| rung 5 | 796 B | 64,740 B |
| rung 6.5 (all four variants) | 1,026 B | 64,510 B |

BM650 predicted 279 B. The 49 B over-estimate is two things: the handover is a
5-byte `call 0x5000:0` where the probe budgeted push/push/jmp (11 B), and the two
refusal labels share rung 5's existing ` EXP=` string instead of carrying their
own. Both are the sort of thing you can only see once the instructions are the
ones that ship.

**The contract, checked as text.** `ARG_LEN@0, ARG_LBA@2, ARG_COM@4, ARG_CS@6,
ARG_NID@8, ARG_MBOX@10, ARG_ECHO@12`, mailbox word `0x4B4F`, block at
`EXEC_ARGS = IMG2_LEN*2 = 4096`. `bm651_img2.py` parses those equs out of the
loader source *and* the image source and refuses the build on drift — the two
sides of a wire format that lives in two files have no other referee.

**Ordering is the safety property, and it is asserted three ways.**
`.img2_ok` (CRC gate) → BM-502 write → self receipt → **exec**. The leg sits after
the gate so an unverified image is never in reach of the instruction pointer;
after the write because the copy-down overwrites `IMG2_SEG:[0,2048)`, which is the
write leg's bounce buffer (the medium has those bytes by then); after the receipt
so `STAGE2 CKSUM` still means what rung 5 said it means. Leg 1 checks the line
*numbers* on the wire, not just their presence, and leg 6 checks the consequence:
a pixel-flipped image produces no banner at all.

**The witness is the image's own voice.** `banner_provenance.txt`: the string
`IMG2EXEC BANNER NID=` appears exactly once in each variant's 2,048-byte image
and **nowhere** in that variant's padded 65,536-byte stage2 payload or its 512-byte
stage1. Without that check the banner would only prove stage2 ran.

**Nothing re-typed.** 5 + 4 deltas, each asserted exactly once, each undone
newest-first, both files reproduced byte-for-byte. The fork's green path still
prints rung 5's `IMG2 CRC`, `WRITE=OK` and `STAGE2 CKSUM … EXEC` anchors
unchanged, which is the point: legs 1 and 2 are also a re-run of BM-501 and
BM-502 on a payload that is now 230 bytes bigger.

**Reproducible from tracked inputs alone.** Every file this row reads —
`rung5/stage2.asm`, `rung5/stage1.asm`, `rung5_consts.py`, `rung5_layout.py`,
`rung4_pad.py`, `rung4_consts.py`, `rung5_codec.py` — is tracked in git, which is
what made the clean-room pair above possible at all. (BM903's receipt had to
record the opposite about its vendor media; this row inherits no unlanded input.)

## The guest's own numbers

```
green   code 1026 B  img2 crc 101BFE00  nid EE1B  STAGE2 CKSUM=1323  transcript 161 B
noecho  code 1026 B  img2 crc 92DD6EF6  nid FC2B  STAGE2 CKSUM=184F
nombox  code 1026 B  img2 crc 0C818841  nid 84C0  STAGE2 CKSUM=1364
halt    code 1026 B  img2 crc 85E95236  nid D7DF  STAGE2 CKSUM=177F
```

`nid = low16(CRC32(image)) ^ high16(CRC32(image))`, emitted by the same script
that emits `EXPECTED_IMG2_CRC` from the same bytes — a variant's image and another
variant's expectation cannot be paired by accident, and `IMG2 CRC=` / `NID=` on
one wire are two views of one hash.

Transcript growth: 161 B against rung 5's 128 B = **+33 B = 2.86 ms of wire** at
the 115200 8N1 divisor rung 5 programs (BM650 predicted 35 B / 3.0 ms). Every leg
finishes its output inside a second; the 20 s `timeout` is QEMU's, not the guest's.

## What the rig learned

**R-SCOPE-5 (correction to the design review, before code).**
`DESIGN_EXEC_FROM_DATA_REVIEW.md`'s item 8 concluded the copy-down must go
backwards because dst and src "overlap fully", and rewrote the design to use
`std`/`rep movsw`/`cld` on that basis. It does not: the de-interleaved image
already lives at `[2048,4096)` and the destination is `[0,2048)`. Disjoint. The
review's error was assuming an in-place move; the landed tree says otherwise at
`stage2.asm:94-96`. Forward `rep movsw` ships, and the leg `cld`s anyway so it
does not inherit a flag from a neighbour.

**R-SCOPE-6 (found by booting, not by reading).** stage1's
`push seg / push off / retf` at `rung5/stage1.asm:188-191` is the repo's landed
far-transfer idiom, and the first build copied it for the handover. It is a far
**jump**, not a call/return pair — nothing pushes a return address, so the
image's `retf` popped `IMG2_SEG:.back` and returned *into the image's own bytes*.
Wire, before the fix: two banners (`NID=EE1B` then `NID=0000`) and a tail of
serial garbage. A `call 0x5000:0` (opcode 9A) is both correct and four bytes
cheaper. Reusing a measured idiom is the right instinct; the idiom's contract
includes what it does *not* do.

**A fall-through that printed the right refusal for the wrong reason.** With the
handover fixed, green printed `EXEC=OK` and then fell straight into
`.exec_badmbx`, printing `EXEC=BAD-MAILBOX 4B4F EXP=4B4F` — the values correct,
the branch wrong, caught only because the leg asserts refusals are *absent* on
green. Had that grep been missing, the rung would have shipped a loader whose
success path always ends in a refusal.

**DEFECT-R651-1 (gate, not guest).** Leg 5 first tried to diff the hang
transcript against green "up to the handover". That can never pass: every variant
embeds its own image CRC, `IMG2 SUM`, `STAGE2 CKSUM` and NID, so lines 2–6 differ
*by construction*. Replaced with the claim that actually holds — the banner is
the last line the loader ever emitted, and the line count is green's minus the
verdict green got. A cross-variant "identical up to here" is a category error
worth naming, because rung 6's identity legs make "byte-identical transcripts"
feel like a free assertion.

**Gate plumbing, three times.** The matched-baseline line read `defs_green.txt`
before any build had written it; the closing `ls evidence` echo made two runs of
an identical gate differ by one word (the second run's own transcript file); and
— the one that mattered — **the first ×2 was not clean-room.** Legs 1–7 passed
twice with a stale `rung5_layout.inc` sitting in the directory, left there by
BM650's scope probe: the gate never invoked `rung5_layout.py`, so it was *reading*
an artifact instead of producing one, and a fresh checkout would have died on the
first consts call. Fixed, and the pair re-run from a wiped directory. A green that
depends on a leftover file is not a green — and rung 5's trap 10, the build-time
write-target disjointness assert, silently stops running if nobody calls the
script that holds it. Neither of the other two touched a leg's meaning, and no
guard was weakened anywhere in this row.

## Honest boundaries

- **This is a liveness contract, not authentication.** The mailbox and the echoed
  NID prove the image ran and returned; an adversary who can write the pixels can
  write an image that keeps both. The only backstop against a *hostile* image is
  the CRC the loader already checked, and it is checked against a constant baked
  into the payload. Say "the medium can carry code that runs", not "the medium
  can carry code safely".
- **A hung image is undetectable from inside.** Leg 5 is a host-side absence
  claim at a 20 s budget. `rc=124` is *every* leg's exit status — the loader's own
  end state is a `hlt` loop — so the signal is the missing verdict, and there is
  no guest-side watchdog in this design that could produce one.
- **The executed image has the machine.** IF=0 across the handover (R-SCOPE-3),
  `SS:SP` left at `0:0x7C00`, every GPR free, no isolation of any kind. The leg
  hands over control because that is the claim; rung 9's kernel handoff is the
  scaled version of the same act.
- **Sizes stay rung-5-scale.** 2,048 B image, 64 KiB payload. Nothing here says
  anything about executing a 12 MiB kernel out of pixels; that medium geometry is
  rung 9's and rung 6's territory.
- **The contract is a convention between two files in this directory.** The
  offset table is cross-checked as text at build time and the image's own banner
  is checked for provenance, but there is no schema, no version word, and no
  length negotiation at runtime: `ARG_LEN` is handed over and never read. A second
  image author outside this tree gets no compatibility signal beyond the CRC.
- **Static legs re-verified; nothing re-measured from rung 5's receipts.** The
  layout disjointness, bake identity and host decode ran here, on this build.
  Rung 5's own gate was not re-executed (rung5/ is read-only and unchanged); the
  `WRITE=OK` in leg 1 is the fork's write leg, which is the relevant claim.

## Status

TASK_BM651 **CLOSED GREEN ×2**. Rung 6.5 option A is landed and gated. Option C —
execute an image off the PXC2-E self-repairing medium, so the claim becomes
"pixels that had to be *repaired* to CRC correctly, then ran, and said so" —
remains filed in `BM650_SCOPING.md` and needs its own design pass, because it
touches the locked payload builder in `rung9/bm903_pxcodec.py`.
