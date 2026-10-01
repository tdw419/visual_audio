# RESEARCH — closing the day-1 user-surface gap: a second shell verb on the shader path

**Tick:** 2026-09-22 ~17:1x CDT, builder cron af3e62239ce2. Trigger: PHASE 1c —
ledger STATUS ACTIVE, claim queue genuinely EMPTY (all rounds closed, no open
RULING newer than HEAD 3d0b09d5, newest RULING 09-21 14:59), monitor CLEAN
queue=0. One research item per tick; nothing engine-side landed this tick.

## The question

What single, concrete item would most directly fix the friction Jericho
recorded on day 1 of R5.3 (the gate that decides the project)?

## Method (what was read/measured, path:line)

1. **The friction signal (primary):** `.builder_queue/R53_USE_LOG.md:24` —
   Jericho's day-1 line, in his own words: *"the shell only repeats you, the
   demo is the machine talking to itself... No user surface exists yet."*
   His two real requests: "list the files in my home directory" and
   "what time is it". This is the only line in the use log and the only
   real-user friction datum in the tree.
2. **What the shell actually dispatches today** — measured by REPLAYING his
   exact request-shape through the live engine (not reading prose):
   - `experiments/glyph_interactive_shell.py:226-241`: the exec shell
     (`build_exec_shell`) dispatches exactly 5 verbs — e/s/w/r/x — on the
     first byte; everything else falls through to
     `DISPATCH_ERROR_MARKER` (:72).
   - Live run this tick: `repl(lines=['time','ls',...], image=build_exec_shell(...), fs_pix_enabled=True)`
     → `['ERR:UNKNOWN_CMD', 'ERR:UNKNOWN_CMD']` for both of Jericho's
     day-1 request-shapes. Confirmed exit 0 (machine fine; surface absent).
   - The plain echo shell is weaker still: `repl(lines=['e hi'])` echoes the
     line back verbatim including the 'e' — measured `['e hi']` this tick.
3. **Why "what time is it" fails:** the engine has no clock.
   `grep -cin "time()|clock|rtc" tools/glyph_isa_v2.py` → **0**. There is no
   time source in the machine to expose.
4. **Why "list files" fails:** the host-side engine (0x03/0x04 FILE_WRITE/
   FILE_READ, `tools/glyph_isa_v2.py:1437`, `:1505ff`) touches host files via
   `_read_path`, but `grep -cin "listdir|scandir|readdir|getdents"
   tools/glyph_isa_v2.py` → **0**. No enumeration syscall exists:
   `docs/SYSCALL_ABI_SPEC.md` has exactly 13 ABI blocks
   (0x01–0x09, 0x10–0x12) and none is a directory list.
5. **Which of his two requests is closable:** FILE_READ (0x04) exists and is
   RAM-homed (spec :109-125), the interactive shell already drives it (the
   'r' verb, `glyph_interactive_shell.py:309-324`). What's missing is (a) an
   enumeration surface and (b) a verb that answers "what's here". A clock
   syscall would need a new time source designed in — strictly larger blast
   radius, no existing engine surface to extend.
6. **Shader-path honesty check:** `tools/wgsl_glyph_isa_v2.py:775-800` shows
   the twin implements 0x02 READ over the box_mmio ring (SE022a) — the input
   plumbing a richer shell needs exists on BOTH engines. 69 test files
   reference `run_wgsl`; 8 reference `input_ring` — the WGSL leg of a
   shell-verb item is routine parity work, not new substrate.

## Findings (numbers, with derivations)

- Shell verb count: **5** (measured from the dispatch chain source at
  `glyph_interactive_shell.py:226-241`); unknown-command coverage of a
  two-request natural-language probe: **2/2 requests → ERR:UNKNOWN_CMD**
  (live replay, exit 0).
- Directory enumeration syscalls in the engine: **0**
  (grep count, `tools/glyph_isa_v2.py`); ABI spec blocks: **13**, none an
  enumeration/list (count from `docs/SYSCALL_ABI_SPEC.md`).
- Clock/time syscalls in the engine: **0** (same grep method).
- Rule-1 note (NUMBERS ARE CLAIMS): all numbers above are **structural
  counts** (grep/file:line derivations, command named per number) or live
  replays on this machine — none is a rate/ratio/frequency, so no
  floors_authoritative.json citation is required; there is no floors-window
  dependency in this receipt. Impression flagged as impression: day-1's
  "nothing to use" is one user-day of evidence, n=1 — treated as directional,
  not statistical.

## The ONE candidate item (backlog format — proposal, NOT landed work)

| Field | Value |
|---|---|
| ID | BK-15 |
| Item | **`ls` for glyph-sh: SYSCALL_FILE_LIST (0x13) + a `files` shell verb** — Python engine handler enumerates host files whose `realpath` is under a `GLYPH_RUN_ALLOW`-scoped root (same containment model as 0x07/0x12), returns NUL-separated names into a RAM dest buffer; WGSL twin returns -1 as its NORMATIVE contract (host FS enumeration is foreign to the shader threat model — exact precedent: 0x07/0x12, landed 09-22); shell gains a first-byte verb that lists the baked/known files in the box's FS window. Answers "what is here" — half of day 1's failed request pair, on the engine that already owns host-FS truth. |
| Gate spec | `tests/test_bk15_file_list.py`: L1 create 2 files via 0x03, call 0x13 on the scoped root, both names present in dest buffer, NUL-separated, count in rd; L2 path outside the allow-scoped root → -1 (containment, loud); L3 empty root → count 0, empty buffer, no crash; L4 twin parity leg via GlyphRunner.run_wgsl: 0x13 → rd == 0xFFFFFFFF (-1), asserted as the NORMATIVE contract + rot-guard `<!--ABI 0x13>` block in SYSCALL_ABI_SPEC.md parsed by the existing pillar21 machinery; L5 non-vacuity mutation: neutering the handler's enumeration (return empty) turns L1 RED. |
| Prereqs | None new — 0x03/0x04 RAM-homed and green; containment model landed (0x07/0x12, 97b7732d); rot-guard machinery landed (24 legs green). |
| Source | R53_USE_LOG.md:24 (Jericho day-1); this receipt's replay measurements. |
| Explicitly NOT this item | A clock ("what time is it") — needs a new time source designed into the machine first; larger, separate row. Natural-language input — the shell's first-byte dispatch is a separate usability lane. |

## Honesty

- Research receipts propose, never land engine code — nothing engine-side
  changed this tick (ledger + this file + backlog row only).
- What the replay PASS does NOT prove: that `files` as a verb is the *right*
  UX (first-byte dispatch vs named-verb is a design call for Jericho); that
  an enumeration syscall is safe against host-side path tricks beyond the
  allow-scoped-root model as specified (the gate's L2 leg tests the spec'd
  containment, not an adversarial audit); n=1 friction evidence.
- Filed to `systems/GLYPH_BACKLOG.md` as BK-15 — backlog is
  NOT-claimable-without-Jericho per its header rules, so this stays a
  proposal until he approves it.
