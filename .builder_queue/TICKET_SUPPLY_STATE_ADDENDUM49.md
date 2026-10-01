# ADDENDUM 49 — 26th tick (2026-09-16 01:4x CDT, builder cron af3e62239ce2)

**Delta this tick: the staged fix option (a) is DISPROVEN by measurement;
option (c) is PARTIALLY DISPROVEN. The RCA's row-length story is also
stale — the mechanism is aliasing, not path length.**

1. **Maildrop polled FIRST: `(no messages)`** on `tools/geos_mailbox.py
   list --to hermes` AND `--all`. No Jericho ruling has arrived.

2. **Sibling diffs re-measured, unchanged at the canonical baseline**
   (`git diff --numstat`): shell **332+/1-**, WGSL **157+/2-**, engine
   **48+/1-**, CPU **5+/3-**, loop 14+/1-. Content-quiet again.

3. **SE021 gate re-run FRESH: 1F/3P, 40th consecutive red** — same :158
   signature (`['CHILD_OK', '']`) on HEAD `fd308f4`.

4. **NEW MEASUREMENT (probe `output/se021_probe3_test.py`, harness =
   the gate's own fixture via `from
   tests.test_glyph_app_glyph_on_glyph import child_env`)**:
   - turn 0 (`x`) ends pc=(12,102), running=False, 8 output bytes —
     clean.
   - turn 1 (`e hello`) ends **pc=(4,68)**, running=False, 0 outputs.
   - The image pixel AT the stop pc: `(4,68)` = **(0,0,67)** = 0x43
     `'C'`, next pixel (5,68) = (0,0,0) — i.e. turn 2 decoded the first
     byte of turn 1's `CHILD_OK` FILE_READ payload as its next
     instruction. **Mechanism confirmed byte-exactly at the CURRENT
     sibling WIP, not just the older snapshot.**
   - Layout at current WIP: `experiments/glyph_interactive_shell.py:178`
     `xread_addr = 1024 + DISPATCH_BUF_CAP + 2 = 1090` — the exec-branch
     FILE_READ dest is STILL inside the GH-8b window [1024,1280)
     (`tools/glyph_isa_v2.py:668`). The v4 relayout moved the dests to
     window offsets 0 and 66 but did NOT move them OUT of the window, so
     whatever row the window starts at, FILE_READ still writes instruction
     pixels.
   - Lit-pixel census rows 60–83 (probe #1): EVERY row 60–83 carries
     19–22 lit pixels, so the program fills rows well past the window's
     rows regardless of external path length. **The old RCA's
     "pytest-length paths push the prologue into row 68" story is stale:
     the v4 layout bakes the program tall enough that overlap is
     structural, and (per the earlier /tmp short-path passes recorded in
     addendum 47's history) the current red may no longer be
     path-length-dependent at all.** Option (a)'s premise is false at the
     current tree; option (c) (relocate code below the window) may help
     only if the code region can be guaranteed below the window's rows
     for ALL baked path lengths — which is option (b)'s invariant,
     enforced.

**Conclusion: the sibling's v4 fix did not remove the aliasing — it moved
it. The staged option list needs a re-ruling; the honest recommendation
now: the FILE_READ dest buffers must live OUTSIDE [1024,1280) AND the
build must assert no instruction row overlaps the window's pixel rows
(old (a) + (b) together). HOLD continues — escalation to Jericho STANDING
(3-way call unchanged). Nothing committed except this addendum.**
