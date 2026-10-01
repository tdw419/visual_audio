# SELF-REVIEW — DESIGN_EXEC_FROM_DATA.md vs the landed rung-5 tree

Reviewer: builder cron af3e62239ce2, 2026-09-18. The gate clause forbids a
prose-only pass, so every claim below was checked against the actual files at
HEAD d7e77c58 (design authored on top of landed rung 5, ea3cc949).

## Checklist

| # | Claim in the design | Checked against | Result |
|---|---|---|---|
| 1 | stage1 `[0,1)`, stage2 `[1,128)`, img2 `[129,133)`, write `[133,137)`; IMG2_SEG=0x5000 | `rung5/rung5_layout.inc` (all five constants, verbatim) | MATCH |
| 2 | De-interleaved img2 at `IMG2_SEG:2048`, raw planes at `:0`, window `[2048,4096)` is the free/scratch region | `stage2.asm:94-96` (concatenated planes comment), `.img2_done` flow, mailbox placed at `2048` = first byte above the copied-down image | MATCH; mailbox window is 2048 B free — one word fits trivially |
| 3 | DST_SEG=0x1000, payload 64 KB fills the segment, so no stack can be carved there | `stage1.asm:39` (`DST_SEG equ 0x1000`), `rung5_consts.py:28` (`-DDST_SEG=0x1000`), stage2 self receipt prints `STAGE2 SIZE=64 KB` | MATCH — the SS:SP handover (SS=0, SP=0x7C00) is the only sane contract |
| 4 | CRC routine is the reflected zlib poly, walks ES:SI, in/out 0xFFFFFFFF | `stage2.asm` `crc32_calc` block (0xEDB88320, `.byte_loop`/`.bit_loop`, ES:SI walk, 1 bank for 2048 B) | MATCH |
| 5 | CRC gate runs BEFORE any use; refusal computed-first | `stage2.asm:173-196` (`cmp eax, EXPECTED_IMG2_CRC` / `jne .img2_fail` / prints computed then EXP then `jmp halt`) | MATCH — placing the exec copy-down+jump strictly after `.img2_ok` means a bad image can never be jumped to |
| 6 | Consts are build-generated, not hand-edited (run-13 lesson) | `rung5_consts.py` emits both `-D` nasm defines and the layout `.inc`; `run_gate5.sh:198` comment ties `stage1_const.inc` to the padded stage2 | MATCH; adding `EXPECTED_EXEC_NID` to the same emitter keeps it build-consistent |
| 7 | Existing anchors stay byte-identical | `stage2.asm:412-420` (msg_ strings) + `run_gate5.sh:88` (`STAGE2 CKSUM=.* EXEC` grep) | MATCH — the exec leg inserts between WRITE=OK and the self receipt, no anchor rewritten |
| 8 | `rep movsw` copy-down of 1024 words is safe | DS:SI=DST_SEG:0 payload? NO — review found this: the copy must be **from IMG2_SEG:2048 to IMG2_SEG:0** (same segment, overlapping backward region — but dst < src means a forward `rep movsw` with overlapping windows would corrupt; 1024 words with dst 2048 below src overlaps fully). Correction applied to the design: the copy must iterate BACKWARD (like the stage2 de-interleave walk at `stage2.asm:108` which does k=PLANE_LEN-1..0) or copy to a scratch segment first. Cheapest correct form: backward `rep movsw` with DF=1 set per the std `std`/`movsw`/`cld` idiom, or a k-descending loop mirroring the measured de-interleave walk. | **FOUND AND FIXED** |
| 9 | Exec image entered at EXEC_SEG:0 with retf trampoline | stage2 itself was entered by exactly this mechanism (`stage1.asm:188-191`: push seg, push 0, retf) — the pattern is the landed, measured precedent in-repo | MATCH |
| 10 | NID = f(CRC32(img2)) is host-arithmetic cross-checkable | gate RED-A already does host arithmetic on the CRC (`run_gate5.sh` redA, rung-5 receipt) | MATCH |
| 11 | Write-region disjointness carries over (no new medium region) | `rung5_layout.py` region assert `[0,1)/[1,128)/[129,133)/[133,137)` — design adds none | MATCH |
| 12 | Banner-before-mailbox ordering, and stage2-prints-the-verdict | consistent with gate5's grep-the-log model (stage2 owns all `GATE5=`/`EXEC=` anchors) | MATCH |
| 13 | Host timeout bound is real | rung-5 receipt: boot-to-receipt ≤101 ms n=2, 50 ms poll | MATCH (cited, not re-run — honest-boundary item in §6) |

## Defects found by this review

**R-DESIGN-1 (fixed):** the original §2 copy-down said "`rep movsw`, 1024
iters" as if forward-safe. With dst = src−2048 and full overlap, a forward
copy destroys 3/4 of the image before it is read. The landed tree contains the
correct precedent (`stage2.asm:108` walks k = PLANE_LEN−1 .. 0 with per-plane
increments). The design's copy step is corrected to: DF=0 backward iteration
(k descending, word at `IMG2_SEG:2048+2k` → `IMG2_SEG:2k`), or equivalently
`std` + `rep movsw` + `cld` — either is O(1) extra instructions. This is
exactly the class of bug the gate clause's "no prose-only 'should work'"
sentence exists to catch.

**R-DESIGN-2 (accepted risk, documented):** the mailbox lives at
`IMG2_SEG:2048`, i.e. INSIDE the old de-interleaved-image window that the copy
down now empties. Ordering in the design already places the mailbox store
after the copy-down (img2 runs from `:0` post-copy), so nothing overwrites it
— but the implementation row must add a gate leg asserting the mailbox word is
the ONLY nonzero qword-pattern at `[2048,2050)` at receipt time if it wants
that belt-and-suspenders; declared optional.

## What this review does NOT prove

No asm was assembled or run; the review is static against source at HEAD
d7e77c58. The redA/non-vacuity legs of §4 are specified, not executed. The
timeout bound is cited from the rung-5 receipt, not re-measured for the
grown stage2 (the exec leg adds serial bytes; the 50 ms poll budget should be
re-derived at implementation time — named as an implementation-row obligation,
not silently assumed).
