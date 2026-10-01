# RESEARCH — the stranger doc never mentions the interactive shell

**Tick:** 2026-09-22 ~23:2x CDT, builder cron af3e62239ce2. Trigger: PHASE 1c —
ledger STATUS ACTIVE, claim queue EMPTY (rounds 1–5 closed), no RULING newer
than HEAD 73b371a9 (newest RULING mtimes 2026-09-22 20:38, all pre-dating the
last five landings), monitor CLEAN queue=0. One research item per the standing
directive. Research only — nothing landed.

## The question

R5.3 day 1 recorded the verdict "no user surface exists yet." Since then the
lane landed the dispatch shell (item 9), the on-screen console (DTF-2), and the
floor transcript — so a surface DOES exist now. Question: can a stranger (or
Jericho on day 2) FIND it? The R5.2 rung's deliverable, `docs/START_HERE.md`,
is the doc a stranger is told to follow. Does it route a human to the
interactive shell?

## Method (what was measured/read, path:line)

1. **Doc scan (structural, countable):** `grep -rn 'glyph_interactive_shell'
   docs/` → **0 matches across all of docs/**. Per-file counts at HEAD
   73b371a9: `docs/START_HERE.md` **0**, `docs/ARCHITECTURE.md` **0**,
   `PRODUCT_ROADMAP.md` **0** (the command for the repo's own product rungs),
   vs `ROADMAP.md` (the old ISA roadmap) 4 mentions. The only .md files in the
   tree that name it outside .builder_queue/ history are ROADMAP.md:1767-1781
   and the mirrored skill copy `.agents/skills/glyph-teleoperation/SKILL.md`.
   `grep -n 'shell' docs/START_HERE.md` → no matches (exit 1).
2. **What START_HERE offers instead (read, docs/START_HERE.md:32-110):** two
   entry points — (1) the one-file installer (`glyphos_installer.py --json`),
   which boots a fleet demo and exits, and (2) `tools/glyph_run.py` on a
   checked-in example. Both are machine-facing: the demo is "the machine
   talking to itself" (Jericho's day-1 phrase), glyph_run runs a program *he*
   didn't write. The interactive path he actually sat at on day 1 —
   `python3 experiments/glyph_interactive_shell.py` with the e/s/w/r verbs —
   is the ONE surface where a human types and the machine answers, and the
   stranger doc does not know it exists.
3. **The surface works today (live, this tick):** `printf 'e hello\nquit\n' |
   timeout 60 python3 experiments/glyph_interactive_shell.py` → banner names
   all four verbs (the item-9 repoint landed), dispatch echo `  echo:  hello`
   (r5=32,104,101,108,111 byte-ring), console band PNG written, **exit 0**.
   The doc gap is the only gap left in the route from "clone" to "typing at
   it."
4. **The gate that perpetuates it:** `tests/test_r52_stranger_doc.py` extracts
   every bash block from START_HERE and executes it (executable truth — a good
   gate), but its scope is exactly the blocks present (:80 `for cmd, promised
   in paired_outputs(markdown)`). A doc missing a section passes green as long
   as what IS written is true — the gate checks truth, not coverage. Nothing
   in the gate or the R5.2 row requires the human-entry surface to appear.

## Findings with numbers

- 0 mentions of the interactive shell in all of docs/ (measured, grep above);
  0 in the repo-root product docs a newcomer reads first.
- 2 entry points offered by START_HERE, both non-interactive demos/tools.
- 1 working interactive surface exists (verified live this tick, exit 0) and
  is unreachable from the doc chain: START_HERE → BOX_ABI/ARCHITECTURE/
  RECEIPT_R* — none of which name it either.
- Blast radius is the product's own launch gate: R5.3 is ≥15 real-work days
  in 30, and day 1's friction was exactly "I don't know what to type / there
  is nothing to use." The mechanism landed; the wayfinding did not.

**Impression, not datum:** my judgment that this is the highest-value
remaining doc gap (vs BK-15/16/17/18/19 which add capabilities or fix
internals) rests on the day-1 use log being the only real-user friction datum
in the tree (`.builder_queue/R53_USE_LOG.md:24`) — a sourced signal, but a
priority call, not a measurement.

## The ONE candidate item (backlog format — proposal, NOT landed work)

| Field | Value |
|---|---|
| ID | BK-20 |
| Item | **Route the human entry surface through the stranger doc:** add a third entry-point section to `docs/START_HERE.md` — "### 3. Sit down at the shell (`experiments/glyph_interactive_shell.py`)": the exact command, a captured session transcript (e/s/w/r + quit) with the machine's real output, the four-verb cheat sheet, and where the audio/write artifacts land (`/tmp/glyph_sh_audio.wav`, `/tmp/glyph_sh_write.dat`, band PNG path as printed by the banner). Also link the shell from the "Where to read next" block. Doc-only; zero code change. |
| Gate spec | `tests/test_bk20_stranger_doc_shell.py` — L1: `docs/START_HERE.md` contains ≥1 bash block invoking `experiments/glyph_interactive_shell.py` (RED today: 0 matches, this receipt's grep is the RED evidence); L2: re-use the R5.2 executable-truth machinery (import `check_pairs` from `tests/test_r52_stranger_doc.py`) over a doc fixture where the shell section's bash block feeds `printf 'e hello\nquit\n' \| python3 experiments/glyph_interactive_shell.py` and the paired text block promises `echo:  hello` + `exit: 0` — executed live so the promise is real; L3: non-vacuity mutation — a doc copy promising `echo:  bogus` (machine will echo `hello`) → L2 fires; L4: the full standing R5.2 gate (`python3 tests/test_r52_stranger_doc.py` rc 0) stays green after the doc edit; L5: doc contains all four verb letters in its cheat-sheet lines (grep `e <text>`, `s <text>`, `w <text>`, `r`) so the "I don't know what to type" failure cannot recur silently. |
| Prereqs | None new — item 9 repoint landed (banner names the verbs, dispatch is default), DTF-2 console landed; live pipe verified exit 0 this tick. |
| Source | R53_USE_LOG.md:24 (day-1, "nothing to use") + RECEIPT_DTF1_repoint_entry.md + this receipt's doc-scan measurement. |
| Explicitly NOT this item | No change to the shell itself, the console, or the R5.2 gate's RED machinery; no claim that docs coverage replaces real usability (R5.3's operator entries remain the sole usability authority); not a rewrite of START_HERE's honesty section. |

## Honesty

- Research only — the diff this tick is this receipt + the backlog row +
  the ledger entry. No doc, gate, or engine line touched.
- Numbers are structural counts (grep match counts, block inventories) and
  one live shell run (exit 0) on this machine. No rate/ratio/frequency →
  rule 1 / floors_authoritative.json not triggered; no check_regime run.
- The grep counts are re-derivable in one command by a skeptical read:
  `grep -rc 'glyph_interactive_shell' docs/START_HERE.md docs/ARCHITECTURE.md`.
- NOT verified: whether ROADMAP.md (old ISA roadmap, not the product lane)
  counts as a route a newcomer would find; NOT verified: day-2 usability —
  only that the entry point is findable-in-principle once BK-20 lands;
  usability stays R5.3's.
- Re-research check (rule 5): BK-15/16/17 cover verbs, clock, and spec/
  dialect freshness; none covers the stranger doc's missing pointer to the
  interactive surface. No existing RESEARCH_*.md or backlog row overlaps.
