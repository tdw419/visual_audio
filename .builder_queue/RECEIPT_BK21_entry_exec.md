# RECEIPT — BK-21: human entry surface gains exec ('x' promoted into build_dispatch_shell)

**Builder:** cron af3e62239ce2 | **Date:** 2026-09-24 ~11:2x CDT | **Base HEAD at claim:** 01f11374 (was df3389d4 at RED capture — rounds 9-11 landed by the seat lane mid-flight; re-based by re-running the full arc on the newer HEAD, see "Mid-flight landings" below)

**Status: LANDED** (code + gate + this receipt, one commit)

## What landed

BK-21 (systems/GLYPH_BACKLOG.md:48, sourced from
.builder_queue/RESEARCH_entry_surface_exec_gap.md): the SE021 exec verb is
now reachable from the HUMAN shell image. `build_dispatch_shell`
(experiments/glyph_interactive_shell.py) accepts
`runner_path`/`child_path`/`child_out_path` (ALL three or NONE — a partial
set is a loud ValueError at build time); when armed, `'x <child.npy>'`
dispatches through the item-11 grammar gate into a glyph exec branch:

- collect the line payload (child path) into a Region-B RAM buffer,
  delimiter-space stripped (r11 first-iteration flag), NUL-terminated;
- SYSCALL 0x12 RUN2 argv=[runner, child, child_out] (tools/glyph_isa_v2.py
  0x12 arm, unchanged);
- rc != 0 -> PRT RUN_DENIED_MARKER (loud, named);
- rc == 0 -> FILE_READ child_out -> PRT loop (child output in transcript).

The child path comes from the LINE PAYLOAD (per the BK-21 row spec) — a
user types `x child.glyph.npy`, no rebuild needed per child. Runner +
child_out are Region-B constants strictly ABOVE the plain shell's max_word
(window [1024,1280) + read buffers), so no pre-existing address changed
meaning; overflow-asserted (exec_max_word < 16384). The FS-window budget
assert for write/audio paths is untouched (L6 pins it). Default build (no
kwargs) is byte-identical to the pre-promotion image.

Containment is the engine's GLYPH_RUN_ALLOW allowlist, unchanged. No
engine (tools/glyph_isa_v2.py) lines modified.

## Gate

`tests/test_bk21_entry_exec.py` — 6 legs:

- L1 exec: 'x <child>' from the dispatch-shell image -> child PRT in transcript
- L2 control returns: subsequent 'e hello' echoes
- L3 allowlist deny, discriminating both directions (see Honesty: the SE021
  gate's '*' neuter is VACUOUS — `_get_run_allowlist` drops non-absolute
  entries, so '*' == empty set == deny. This gate flips deny->allow with a
  REAL grant of the runner realpath on the same image+line)
- L4 grammar: bare 'x' and 'xf oo' -> ERR:UNKNOWN_CMD, no child-out file
- L5 regression: e/s/w/r byte-exact on the promoted image
- L6 layout budget: long write path still raises the window AssertionError

## Evidence (real runs, this session)

RED (pre-landing tree: promotion stashed, gate present, `git stash push
experiments/glyph_interactive_shell.py -m bk21-promotion`):

    6 failed in 0.77s
    FAILED tests/test_bk21_entry_exec.py::test_l1_x_runs_child_from_dispatch_shell
    ... (all 6: TypeError — build_dispatch_shell() got an unexpected keyword
    argument 'runner_path'; the same tree answers live 'x ...' with
    ERR:UNKNOWN_CMD, per the research probe at HEAD 85662ba2)

GREEN (promotion applied, HEAD 01f11374):

    6 passed in 1.10s                       (BK-21 gate alone)
    111 passed in 3.09s                     (family: bk21 + se021-glyph-on-glyph
                                             + l1_personality + l2_files + l3_pipes
                                             + l4_desktop + bk15_file_list
                                             + bk22_multifile + interactive_shell)

Landing-defect fix inside the arc: the first GREEN attempt returned
ERR:RUN_DENIED with rc=1 from the runner — root cause measured via a
decode probe: the payload buffer held `' child.glyph.npy'` (leading
delimiter space; the item-11 payload convention stores the space, and 0x02
ring reads are verbatim). Fix: first-iteration flag in r11 drops exactly
one byte (the delimiter) before storing. Then 6/6.

## Mid-flight landings (parallel-session rule)

Rounds 9-11 (seat lane, commits 054bd05f..01f11374) landed while this
ticket was in flight. They name supply items 18-23 (BK-24/25, shell-native
swap, workbench) and do not touch glyph_interactive_shell.py, the exec
path, or this item; no RULING binds against BK-21 (the row itself notes
"no landed ruling records a decision to withhold 'x'"). The full arc was
re-run on HEAD 01f11374 after the landings: RED-by-stash re-verified
(6 failed), GREEN re-verified (6/6 + family 111).

## What this PASS does NOT prove

- No WGSL twin leg: 'x' is exercised on the CPU path only. RUN2/host
  process spawn is foreign to the shader threat model (0x07/0x12 precedent:
  the twin's NORMATIVE contract is -1) — but no twin-parity probe was run
  to pin that -1 on THIS dispatch image.
- The child runs in a fresh GlyphCPUv2 on the HOST interpreter (SE021's
  disclosed isolation delta — not a GO-5 proc tile). Phase-2 claim only;
  no Phase-3 (execution-inside) claim is made.
- L3's flip side proves the verb obeys a REAL grant; it does not prove the
  allowlist is secure against path games beyond realpath matching (that is
  the engine's landed containment, unchanged here).
- No rate/step numbers claimed — floors N/A (rule 1 not triggered).
