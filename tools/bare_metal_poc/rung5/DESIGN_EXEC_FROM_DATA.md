# DESIGN — Exec-from-data (rung-6 candidate; BM-503 un-blocker)

**Status:** design pass ONLY (roadmap BM-503D). Zero asm in this deliverable.
**Author:** builder cron af3e62239ce2, 2026-09-18.
**Inputs (read, not edited):** `rung5/stage2.asm` (481 lines, landed ea3cc949), `rung5/rung5_layout.inc`, `rung5/rung5_layout.py`, `rung5/RECEIPT_RUNG5.md`, `.builder_queue/RULING_SE021_release_by_measurement_20260918.md`, `tests/test_glyph_app_glyph_on_glyph.py` (the SE021 oracle gate).

## 0. Verdict (question 5, answered first)

**Worth a rung — conditional on the receipt protocol in §1.** A bare jump into a
decoded image is NOT worth landing: with no receipt it proves nothing measurable
(the boot either freezes or does not, and a freeze is indistinguishable from a
stage2 bug). The three-part receipt below is what converts "we jumped" into
evidence. Implement as **Rung 6** (control transfer), reusing the rung-5 medium
unchanged — it is an increment on rung 5's stage2, not a new payload scale.

This is the BIOS-level analog of SE021 glyph-on-glyph exec (RUN 0x07), which was
released as supply by `RULING_SE021_release_by_measurement_20260918.md`. The two
designs cross-reference in §5.

## 1. Receipt protocol under isolation: NONE (question 1)

**The problem, stated exactly.** After `retf` into img2, stage2 has no
containment: an img2 that segfaults (real-mode: hits a bad vector, clobbers its
own code, or simply halts) is indistinguishable from a stage2 that died after
its last print. No guest-side watchdog exists — rung discipline runs with
IF=0, and there is no timer leg to poll.

**The answer is a three-part receipt, split across the trust boundary:**

| Part | Emitted by | Proves | Anchor |
|---|---|---|---|
| Banner | img2, FIRST instruction path | img2's code actually executes | `IMG2EXEC BANNER NID=<8 hex>` over COM1 |
| Mailbox | img2, on finishing its contract | img2 ran to its designed END, not merely started | word `0x4B4F` ("OK", little-endian) stored at `IMG2_SEG:EXEC_MAILBOX` |
| Return receipt | **stage2**, after retf-back | control came back to the loader | `EXEC RECEIPT BANNER=seen MAILBOX=0x4B4F` → gate anchor `EXEC=OK` |

Design details, each tied to a measured lesson:

- **Banner carries a per-build nonce** `NID = low16(CRC32(img2)) ^ high16(...)`
  printed in hex. This is the SE021 `CHILD_OK` convention
  (`tests/test_glyph_app_glyph_on_glyph.py:48` — the child prints its own token;
  the parent asserts it) hardened twice over: the token is derived from the
  image's own CRC, so (a) a stale image's banner cannot be confused with the
  current one, and (b) the gate's non-vacuity leg (§4, leg b) has a
  host-arithmetic cross-check, the same pattern as rung-4/5 RED-A CRC refusals.
- **The gate anchor line is printed by STAGE2, not img2.** stage2 owns the
  verdict; img2 only contributes evidence (banner bytes, mailbox word). A stage2
  that never regains control prints nothing — the absence is the signal.
- **Refusal forms, enumerated** (stage2 prints exactly one):
  - `EXEC=NO-BANNER` — retf returned but the banner handshake failed (stage2
    can check this: img2 must NOT clear the serial ring; simplest contract:
    stage2 pre-places the expected NID string in RAM and img2's only job was to
    emit it — stage2 never parses serial, it compares the NID word it handed
    over against the NID word img2 wrote to mailbox slot 2 before returning).
  - `EXEC=BAD-MAILBOX <word>` — control returned, mailbox != 0x4B4F.
  - `EXEC=TIMEOUT` — **host-side only.** The gate caps qemu wall-clock (the
    rung-5 receipts already bound boot-to-receipt at ≤101 ms with a 50 ms poll;
    rung 6 re-uses that bound). A hung guest is detected from OUTSIDE, because
    no guest-side watchdog can exist under IF=0. This is honest: the timeout is
    gate infrastructure, not guest proof.
  - `EXEC=CRASH` — host-side: triple fault resets the VM; the serial log shows
    SeaBIOS re-starting (a second `PXC1-RUNG5`-less boot banner / boot-device
    line). The gate greps for the reset signature.
- **What the receipt proves / does not prove** (required by the gate clause):
  - PROVES: control transferred to bytes that were CRC-verified as
    pixel-decoded (the §3 gate runs first); the image executed far enough to
    emit its derived token and store the mailbox word; control returned via the
    contract of §2.
  - DOES NOT PROVE: any isolation (none exists — img2 could have trashed
    stage2's data and still returned); correctness of img2's computation beyond
    the two receipt tokens; anything about performance; no protected mode, no
    32-bit path.

## 2. Entry-state contract (question 2)

Written as two directions. Everything not listed is **unspecified** — img2 that
depends on an unlisted register value is a defective img2, by contract.

**stage2 → img2 (entry):**

| Item | Value | Why |
|---|---|---|
| CS:IP | `EXEC_SEG:0` (EXEC_SEG = IMG2_SEG = 0x5000), img2 assembled ORG 0 | see the copy-down step below |
| DS, ES | `EXEC_SEG` | img2's data is its own segment; matches stage2's own CS==DS discipline |
| SS:SP | **handed over unchanged**: SS=0, SP=0x7C00 | stage2's already-proven stack; it lives in conventional RAM below the boot sector, disjoint from both code segments. Do NOT allocate a stack in DST_SEG — stage2's 64 KB payload fills DST_SEG entirely (measured: PAYLOAD_LEN = 65536) |
| DFLAG | CLD (forward) | stage2 discipline |
| IF | 0 on entry; img2 may STI at its own documented risk | matches stage2; BIOS int 13h/10h remain callable either way (stage2 uses int 13h with IF=0 today) |
| Arg block | ES:SI → 4 words: `img2_len`, `medium_img2_base_lba`, `COM1`, `retf CS` (trampoline segment; IP follows at +6) | minimal, versioned by img2 reading word 0; future images grow it, never reorder |
| Clobber rights | img2 owns AX,BX,CX,DX,SI,DI,BP; **must not** modify SS:SP, the trampoline CS:IP, or the arg block | stage2 needs only those to print the receipt |

**The copy-down (exec address selection).** After the existing CRC gate passes,
the de-interleaved img2 window lives at `IMG2_SEG:2048` (measured,
stage2.asm `.img2_done`). Raw interleaved planes at `IMG2_SEG:0` are dead at
that point. Exec code is copied **down** 2048 bytes to `IMG2_SEG:0`, and img2
is entered at offset 0 — no ORG-offset arithmetic in the exec image, and the
old window `[2048,4096)` becomes scratch, which is exactly where the mailbox
word lives (`EXEC_MAILBOX equ 2048`, the first dead byte after the image).
One segment, no extra medium region, no PMM.

**Copy direction is load-bearing (found by the self-review, R-DESIGN-1):**
dst = src − 2048 with FULL overlap — a forward `rep movsw` reads each source
word AFTER a lower destination has already overwritten it, destroying three
quarters of the image. The copy must iterate BACKWARD: either `std` +
`rep movsw` + `cld`, or an explicit k-descending word walk
(`IMG2_SEG:2048+2k` → `IMG2_SEG:2k`, k = 1023..0) mirroring the landed
de-interleave precedent at `stage2.asm:108` (which already walks
k = PLANE_LEN−1 .. 0 for the same overlap reason).

**img2 → stage2 (exit):** `retf` with the trampoline CS:IP loaded from the arg
block, AX = the final mailbox word (redundant echo, for the log line). Any
other exit (halt, fall-through, wrong retf target) degrades to EXEC=TIMEOUT or
EXEC=CRASH on the host side — which is the isolation truth, stated rather than
hidden.

## 3. Integrity gating (question 3)

**Reuse, do not fork.** The exec image IS the img2 slot; there is no img3 and
no new medium region in the minimal design. stage2's existing CRC32 gate
(reflected zlib 0xEDB88320, in/out 0xFFFFFFFF — the rung-4/5 routine, measured
in stage2.asm `crc32_calc`) already refuses a bad image **before** the copy-down:

- Check location: stage2, after de-interleave, before the §2 copy-down — i.e.
  the jump is unreachable unless the CRC gate passed. This ordering is the whole
  point: no host-side verifier guards a decoded exec, so the guest-side gate
  must sit on the only path to the jump.
- Refusal format: the landed form `IMG2 FAIL CRC=<computed> EXP=<expected>`
  (computed-first — DEFECT-R4PRINT). No new string, no new anchor; the existing
  redA leg already exercises it. The exec leg's added anchors are only the §1
  receipt tokens.
- Build-time twin: `rung5_consts.py` already bakes `EXPECTED_IMG2_CRC` into the
  stage1/stage2 consts (`stage1_const.inc` rebuild lesson, gate5 run13 — consts
  are regenerated from the padded final image, never hand-edited). Rung 6 adds
  `EXPECTED_EXEC_NID` derived from the same CRC in the same script, so the
  banner cross-check is build-consistent by construction.
- If a FUTURE design wants an independent exec image (img3) on the medium, it
  extends `rung5_layout.py`'s region map (the disjointness gate already refuses
  overlaps at build time) and moves the write target up. Out of scope for the
  minimal design; named here so the extension path is written down.

## 4. Blast radius (question 4)

- **Rungs 1–4: zero.** No file under `rung1..4/` changes. stage1 is not
  rebuilt (rung 6 re-uses the rung-5 stage1 + medium; only stage2's payload
  grows, and the consts rebuild covers it — the run-13 lesson is that
  `stage1_const.inc` must be regenerated from the final padded stage2, which
  `rung5_consts.py` already does mechanically).
- **Rung 5:** `stage2.asm` grows one leg between the WRITE leg and the self
  receipt. Existing anchors are untouched and must stay byte-identical in the
  log: `PXC1-RUNG5`, `IMG2 CRC=`, `IMG2 SUM=`, `WRITE=OK`, `STAGE2 SIZE=`,
  `STAGE2 CKSUM=`, `GATE4=PASS`, `EXEC` (terminal token of the rung-4 line).
  The new gate anchors: `IMG2EXEC BANNER NID=`, `EXEC=OK` plus the four refusal
  forms of §1.
- **Gate script:** `run_gate5.sh` grows legs OR a new `run_gate6.sh` (decision
  at implementation; a separate script is cleaner for x2-consecutive bookkeeping
  and keeps the landed rung-5 gate frozen as its own receipt). Required legs:
  1. green: full boot → all rung-5 anchors byte-identical **plus** banner +
     `EXEC=OK`; x2 consecutive from clean.
  2. redA (CRC refusal): one-pixel img2 corruption → `IMG2 FAIL CRC=… EXP=…`
     with host arithmetic cross-check, **no** banner, **no** jump (no EXEC
     line at all).
  3. non-vacuity b (banner load-bearing): rebuild img2 WITHOUT the banner
     emitter → must report `EXEC=NO-BANNER` — proving the receipt detects an
     image that runs but does not identify itself.
  4. non-vacuity c (mailbox load-bearing): img2 variant that banners but
     skips the mailbox store → `EXEC=BAD-MAILBOX` with the actual word.
  5. timeout/crash leg: img2 variant that halts instead of retf → host-side
     `EXEC=TIMEOUT` within the poll bound (this leg also pins the bound).
  6. persistence leg re-run unchanged (write region disjointness is a
     build-time assert; §3 adds no region, so rung-5's disjointness receipt
     carries over verbatim — re-run, not re-derived).
- **SE021 / engine side: zero.** No engine, transpiler, WGSL or dispatch file
  is touched by rung 6; the arc gate is out of scope for the ladder lane
  (config/asm-only change precedent: INSTRUMENT-1 receipt discipline).

## 5. Cross-reference to SE021 (required by the row)

Both designs solve the same problem — *prove a thing you executed actually
ran, under no containment* — one level apart:

| | SE021 (glyph-on-glyph, RUN 0x07) | Rung 6 (exec-from-data, BIOS) |
|---|---|---|
| Executor | host interpreter dispatching a child glyph image | BIOS stage2 retf into a decoded image |
| "child ran" token | `CHILD_OK` text via PRT (`test_glyph_app_glyph_on_glyph.py:48`) | `IMG2EXEC BANNER NID=` over COM1, NID derived from the image CRC |
| "control returned" | separate oracle leg (`test_control_returns_to_shell_after_exec`, the leg whose 38-tick RED history the SE021 RCA records) | stage2's retf-back receipt + host timeout |
| Refusal loudness | allowlist denial loud (`test_allowlist_deny_loud_and_no_child_output`) | `EXEC=NO-BANNER / BAD-MAILBOX / TIMEOUT / CRASH`, computed-first CRC refusal |
| Containment | none at host-interpreter level; fences are convention | none; IF=0 discipline is convention |

The ruling's honesty section ("does not prove GPU parity, does not adjudicate
the 38-tick history") is the same shape as §1's proves/does-not-prove list.

## 6. Honest boundaries

TCG only (no hardware claims, no real-VGABOM timing); 16-bit real mode only;
no ECC; no Path-B compression; single medium, single boot chain; the
NID-from-CRC derivation is build-time host arithmetic — a guest-side
recomputation of the CRC by img2 (stronger: proves the image can verify ITSELF)
is a deliberate deferral, noted for the implementation row to consider as a
stretch leg; no measurement in this document — every number cited (layouts,
segments, payload size, poll bounds, anchor strings) is read from landed files
at commit ea3cc949 and cited to them, not run.
