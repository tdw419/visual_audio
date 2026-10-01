# RESEARCH — the "what time is it" half of day-1 friction: a clock surface (BK-16 proposal)

**Tick:** 2026-09-22 ~21:4x CDT, builder cron af3e62239ce2. Trigger: PHASE 1c —
ledger STATUS ACTIVE, CLAIM QUEUE genuinely EMPTY (rounds 1–3 all closed in the
ledger), no RULING_* newer than HEAD 18215029 (newest RULING mtimes 20:38,
pre-landing), monitor CLEAN queue=0. Prior research tick (17:1x) filed BK-15 —
the "list the files" half of Jericho's day-1 line. This tick researches the
OTHER half. One research item per tick; nothing engine-side landed.

## The question

Day-1 use log (`.builder_queue/R53_USE_LOG.md:24`, Jericho, in his own words)
records exactly two real requests. BK-15 answers the first ("list the files").
The second — **"what time is it"** — has no backlog row, no syscall, no shell
verb anywhere in the tree. What is the cheapest gated item that answers it?

## Method (what was measured/read, path:line — every derivation re-runnable in one command)

1. **Friction signal (primary):** `.builder_queue/R53_USE_LOG.md:24` — the only
   line in the 30-day use log, and the only real-user friction datum in the
   tree. Jericho's exact words for this half: *"what time is it"* — typed at
   the interactive shell by his own hand, echoed back verbatim.
2. **Live re-verification at HEAD 18215029, this tick** (not quoted from the
   17:1x research — replayed fresh):
   `repl(lines=["time","t","what time is it"], image=build_dispatch_shell(...), fs_pix_enabled=True)`
   from `experiments/glyph_interactive_shell.py` → **all three shapes returned
   `ERR:UNKNOWN_CMD`** (exit 0; machine fine, surface absent — same shape as
   the ls finding).
3. **Defect observed while replaying:** the third request-shape — a multi-word
   unknown verb line — falls through dispatch to the FS-write path:
   `FILE_WRITE: 14 bytes` ("hat time is it", verb byte stripped) landed
   silently in the shell's notes file. A mistyped command that looks like a
   sentence is silently persisted instead of erroring loudly. Recorded as an
   observation for the BK-15/16 implementer; NOT filed as a separate defect —
   one research item per tick, and this is a record-not-claim tick.
4. **What exists today (grep-derived, one command each):**
   - `grep -o "0x[0-9A-Fa-f]*" docs/SYSCALL_ABI_SPEC.md | sort -u` →
     {0x01–0x09, 0x10, 0x11, 0x12}. Implemented set. **0x13 = BK-15's proposed
     SYSCALL_FILE_LIST; 0x14 is the next free number.**
   - `grep -in "clock\|epoch\|time" systems/GLYPH_BACKLOG.md` → zero rows; the
     only "time" hits are prose ("time is the product's launch criterion").
     No clock/timesyscall surface exists anywhere in the backlog.
   - `experiments/glyph_interactive_shell.py:238-241`: dispatch is 5 verbs on
     the first byte (e/s/w/r/x); everything else → `ERR:UNKNOWN_CMD`
     (`DISPATCH_ERROR_MARKER`, :72) — or the silent FS-write fallthrough above.
   - Host wall-clock is available to the Python engine's syscall handlers the
     same way 0x03/0x04 file I/O is (host-side handler arms in
     `tools/glyph_isa_v2.py`); the WGSL twin precedent for host-only surfaces
     is settled: **twin returns -1 as NORMATIVE contract** (0x07/0x12 codified
     09-22, ledger item 8; BK-15's L4 uses the same pattern).

## Findings

- The friction is real, small, and unaddressed: 1 user, 1 line, 2 request
  shapes, 1 answered (BK-15, unclaimed/unfunded), 1 with zero tree coverage.
- **Numbers policy:** this receipt's load-bearing facts are existence claims
  (dispatch table contents, syscall-number occupancy, backlog grep), each
  re-derivable in one command. The "1 user / 1 line / 2 requests" counts are
  direct file reads of R53_USE_LOG.md (wc -l / read), not measured rates — no
  rule-1 floors apply because no rate, ratio, or cost is cited. No floors
  authority number appears in this receipt.
- The full fix shape mirrors BK-15 exactly (proven pattern, lowest risk):
  **SYSCALL_CLOCK (0x14)** — Python engine returns Unix epoch seconds (plus
  microseconds in a second word, if a two-word ABI is wanted — decision for
  the implementer's spec pass) into rd or a RAM dest; WGSL twin returns -1 as
  its NORMATIVE contract (host wall-clock is foreign to the shader threat
  model — same reasoning as 0x07/0x12/BK-15, codified 09-22); glyph-sh gains a
  `time` verb that formats the returned epoch as human-readable text via the
  existing PRT path.
- Non-obvious design constraint found this tick: **the shell image is baked,
  not live** — `build_dispatch_shell` assembles a static glyph program, so the
  `time` verb must (a) go through a real syscall each turn (epoch read at
  syscall time, not bake time), or (b) the verb handler must rebuild. Option
  (a) is the only honest one and is what the syscall shape already is.
- Adjacent finding, worth a line in the implementer's spec: multi-word unknown
  commands silently FS-write (observation above). If BK-15/16 land a `files`/
  `time` verb pair, the loud-error contract should cover the whole first-byte
  dispatch, not just the 5 known verbs.

## The concrete candidate (backlog format, filed as BK-16 in systems/GLYPH_BACKLOG.md)

| Field | Value |
|---|---|
| ID | **BK-16** |
| Item | `time` for glyph-sh: **SYSCALL_CLOCK (0x14)** — Python engine returns Unix epoch seconds (word 1) + microseconds (word 2, optional, spec-pass decision) into rd/RAM dest; WGSL twin returns -1 as NORMATIVE contract (0x07/0x12 precedent, 09-22); glyph-sh gains a `time` verb formatting epoch → human-readable over PRT |
| Gate spec | `tests/test_bk16_clock.py` — L1: 0x14 returns epoch within [before, after] wall-clock bounds, both words; L2: twin parity via run_wgsl, 0x14 → rd == 0xFFFFFFFF asserted as NORMATIVE + `<!--ABI 0x14>` rot-guard block in SYSCALL_ABI_SPEC.md; L3: glyph-sh `time` verb round-trip: repl(["time"]) output parses as a timestamp and lies within wall-clock bounds of the turn; L4: mutation probe — neuter the epoch read (return 0) → L1 RED (gate can fail); L5: multi-word unknown line ("what time is it") → loud ERR, NOT a silent FS-write (closes the fallthrough observation) |
| Prereq | 0x03/0x04 RAM-homed handlers (landed); pillar21 rot-guard machinery (landed); BK-15's twin-contract codification pattern (landed 09-22) |
| Source | R53_USE_LOG.md:24 (Jericho day-1) + this receipt |

## What this tick did NOT do

- No engine code touched, no shell verb landed, no spec edit — research
  receipts propose, they never land engine code (directive clause 5).
- Did NOT verify BK-15/16 against a live GPU run_wgsl leg — twin behavior is
  a proposal, its -1 contract is asserted from the codified 0x07/0x12
  precedent, not measured on this tick.
- Did NOT file the silent-FS-write fallthrough as a standalone defect ticket —
  it is recorded here and folded into BK-16's L5; Jericho may prefer it
  separate.
- One research item per tick: BK-15's own gate legs were not re-audited.
