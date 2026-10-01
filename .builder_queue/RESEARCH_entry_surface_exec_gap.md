# RESEARCH — the human shell cannot exec: TASK_SE021's 'x' is unreachable from the entry surface

**Date:** 2026-09-23 ~11:5x CDT | **Builder:** af3e62239ce2 | **HEAD:** 85662ba2
**Trigger:** PHASE 1c — STATUS ACTIVE, CLAIM QUEUE EMPTY, no RULING newer than
HEAD (newest RULING mtimes 2026-09-22 20:38, pre-landing), monitor CLEAN
queue=0 (monitor diff this tick = this lane's own item13 landing, self-generated).
Tick-type check before starting: BK-15/16/17 not yet claimed (backlog, not
claimable without Jericho); no supply round landed since SUPPLY_ROUND7.json.
One research item per tick.

## Question

Day-1 (R53_USE_LOG.md:24) called the product "the machine talking to
itself." The exec capability that would let a human hand the machine a
program — glyph-on-glyph exec, TASK_SE021 — is landed and gated, but is it
reachable from the surface a human actually sits at?

## Method (path:line, re-derivable in one command each)

1. `experiments/glyph_interactive_shell.py:740` — `__main__` builds
   `build_dispatch_shell(write_path, audio_path)`. That is the human entry
   surface (item 9 / DTF-1 follow-through).
2. Mechanical extraction of the dispatch shell's first-byte compare chain:
   `python3 -c` over the `build_dispatch_shell` source, regex
   `LDI r7 (\d+)`, ints < 128 → **{32, 101, 114, 115, 119}** = space, 'e',
   'r', 's', 'w'. No 120 ('x').
3. The 'x' branch exists only in `build_exec_shell` /
   `_build_exec_shell_pass` (`LDI r7 120` at
   experiments/glyph_interactive_shell.py:240; SYSCALL 0x12 RUN2 at :343 →
   `tools/glyph_child_runner.py`). Gated by
   tests/test_glyph_app_glyph_on_glyph.py (3 legs, all on build_exec_shell).
4. Callers of `build_exec_shell`: grep over the tree (excluding .venv) →
   only its own gate and two `.builder_queue/probe_se021_*` scripts. No
   human-facing caller.
5. Live probe at HEAD 85662ba2:
   `printf 'x tools/glyph_child_runner.py\nquit\n' | python3
   experiments/glyph_interactive_shell.py` → `echo: ERR:UNKNOWN_CMD`,
   exit 0. The loud-error grammar (item 11) works as designed — the point
   is that a legitimate command is on the wrong side of it.

## Findings

- The shell has FIVE verbs from the human seat: e/s/w/r + quit. Exec ('x')
  is not one of them, despite being landed, gated, and documented in the
  gate's own docstring as "the dispatch shell ... gains an 'x' command"
  (tests/test_glyph_app_glyph_on_glyph.py:3 — the docstring's claim about
  which builder function got the verb does not match the shipped surface).
- Consequence: day-1's third clause ("nothing to use — the shell only
  repeats you") is still literally true from the human seat. A user cannot
  hand the machine a .glyph program without writing their own Python that
  imports build_exec_shell — which is exactly the "compiler assumes you
  already speak its language" barrier day-1 named, one level up.
- This also orphans an entire landed capability class: BK-11 coreutils /
  glass-box stage "stranger's C program runs on the machine" has no
  human-facing door even once its artifacts exist.

## Candidate item (backlog format, filed as BK-21 in systems/GLYPH_BACKLOG.md)

Promote the 'x' verb into build_dispatch_shell: same RUN2 block
(SYSCALL 0x12, rc gate, RUN_DENIED_MARKER, child_out FILE_READ + PRT loop)
already proven in _build_exec_shell_pass:327-370, re-targeted at the
dispatch shell's layout (paths baked as constants; runner path baked
default tools/glyph_child_runner.py, child path taken from the line
payload — payload length must respect the FS-window assert at
glyph_interactive_shell.py:438-441, so long child paths → loud ERR, not a
write past 1280). Bare 'x' and multi-char-without-space stay ERR:UNKNOWN_CMD
per the item-11 grammar.

## Honesty

- Research only: no engine/shell/doc line touched this tick.
- No floors/rule-1 citation triggered: no rate/ratio/cost claimed; findings
  are structural (one grep, one AST-level constant extraction) plus one
  live shell run (exit 0, echo captured above).
- Priority call ("highest-value remaining surface gap") is impression, not
  datum; nearest real friction datum remains R53_USE_LOG.md:24 (day 1,
  operator's own words).
- What this does NOT establish: whether 'x' was deliberately withheld from
  the dispatch shell (no ruling or receipt says so; nothing in
  PRODUCT_LANE_STATE.md or the SE021 row records an exclusion decision) —
  flagged as a question the promotion gate must answer before landing.
