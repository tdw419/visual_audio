# RESEARCH — "the compiler assumes you already speak its language": measured dialect-documentation drift + error quality

**Tick:** 2026-09-22 ~21:5x CDT, builder cron af3e62239ce2. Trigger: PHASE 1c —
ledger STATUS ACTIVE, claim queue EMPTY (rounds 1–3 closed), no RULING newer
than HEAD 2908ff6e (newest RULING mtimes 20:38, pre-landing), monitor CLEAN
queue=0. One research item per tick; nothing engine-semantic landed this tick.
Rule-5 check: this is NOT a re-research of BK-15 ("ls") or BK-16 ("time") —
those cover the shell-surface halves of day-1 friction; this tick covers the
THIRD clause of the same R53_USE_LOG.md:24 line, which no existing RESEARCH_*
or backlog row addresses.

## The question

Day 1 (R53_USE_LOG.md:24), Jericho's full verdict: *"…the demo is the machine
talking to itself, and **the compiler assumes you already speak its language**.
No user surface exists yet."* BK-15/16 answered "no user surface." What does
the language half measure to — can a stranger actually learn the `.glyph`
dialect from the tree, and what happens when they get it wrong?

## Method (what was read/measured, path:line)

1. **Does a language doc exist?** Yes: `docs/spec/GLYPH_ISA_SPEC_v1.0.md`
   (331 lines, GL-2 of systems/GLYPH_OSS_ROADMAP.md:37, status 🟡 DRAFT).
   Its own audience contract (spec :11-13): "this document alone should be
   enough to write an independent interpreter or assembler… If you find
   yourself needing to read the Python source, that is a bug in this spec."
2. **Probe script:** `.builder_queue/probe_day1_language_dialect.py`
   (re-runnable, one command, exit 0 this tick). It mechanically extracts
   the engine opcode table (`tools/glyph_isa_v2.py` `OPCODES`, :150ff) and
   pinned palette (`FIXED_COLORS`, :227ff), extracts the spec's §3.2/§3.3
   text, and runs live error-quality probes through `tools/glyph_run.py`.
3. **Discovery check:** does the stranger's entry doc link the language doc?
   `grep -n "spec" docs/START_HERE.md` → **0 hits**; README.md likewise has
   no glyph-dialect pointer (grep "glyph" README.md → 0 hits).

## Findings (numbers, with derivations)

1. **Engine opcodes: 36. Spec names 30 — 6 engine opcodes are absent from
   the spec entirely: `MUL, JNZ, JNE, CMP3, JLT, JGT`** (probe output;
   these are SE024/SE025's additive jumps + MUL, landed after the spec
   draft b059539a). A spec-only author cannot use them and — the trap —
   learns JZ as the only conditional jump, the exact inverted-sense
   tripwire SE024 was landed to mitigate (glyph_isa_v2.py:161-176 records
   an ISA-maintainer session biting it 2026-09-16).
2. **Palette drift, including one factual color bug:** spec :151 claims
   "all 30 opcodes are permanently pinned"; the engine's FIXED_COLORS has
   26 entries, of which **6 are absent from the spec's palette table** and
   **1 is WRONG: SYSRET spec 255,99,72 vs engine 255,99,71** (tomato).
   Pinned colors exist precisely so "WebGPU decoders hardcode these values
   without external database lookups" (spec :153-155) — a twin/decoder
   written from the spec mis-decodes every SYSRET by one blue bit. The
   spec's own status line says the code is authoritative, so this is a
   spec bug, not an engine bug.
3. **Error quality, live probes (real exits through tools/glyph_run.py):**
   - x86-style `mov r5 5` → exit 2, `glyph_run: compile failed: KeyError: 'mov'`
   - unknown op `FOO r5 5` → exit 2, `KeyError: 'FOO'`
   - wrong operand count `ADD r5` → exit 2, `IndexError: list index out of range`
   - undefined label → exit 2, `ValueError: Undefined label ':nowhere'` (the one good message)
   A newcomer's first-contact error is a raw Python exception naming an
   internal container — no "did you mean", no pointer to the spec, no
   list of valid opcodes. (Mechanism: the assembler's operand decode
   indexes `self.opcode_map.opcode_to_rgb(opcode)` directly,
   glyph_isa_v2.py:421, and the KeyError leaks through
   glyph_run.py:_compile's bare raise path.)
4. **Discovery failure:** the ONE doc that teaches the language is linked
   from nowhere a stranger would read — START_HERE.md (R5.2, "documentation
   a stranger can follow") lists PRODUCT_ROADMAP/BOX_ABI/ARCHITECTURE/
   receipts as "where to read next" (:121-127) but not docs/spec/.

**Rule-1 note (NUMBERS ARE CLAIMS):** every number above is a structural
count (mechanical extraction, probe script named, re-runnable) or a live
exit code from a named command this tick — none is a rate/ratio/frequency,
so floors_authoritative.json citation is not required; no floors-window
dependency. Impression flagged as impression: "assumes you already speak
its language" is n=1 user-day evidence, directional not statistical.

## The ONE candidate item (backlog format — proposal, NOT landed work)

| Field | Value |
|---|---|
| ID | BK-17 |
| Item | **ISA spec freshness + dialect error quality**: (a) sync `docs/spec/GLYPH_ISA_SPEC_v1.0.md` to the engine — add MUL/JNZ/JNE/CMP3/JLT/JGT to §3.2 semantics + §3.3 palette, fix SYSRET 255,99,72→255,99,71, bump the "30 opcodes" claim to the true count; (b) link the spec from `docs/START_HERE.md` "Where to read next"; (c) assembler/glyph_run error contract: unknown mnemonic → `unknown opcode '<tok>' — see docs/spec/GLYPH_ISA_SPEC_v1.0.md §3.2 (valid: …)` instead of a leaked KeyError/IndexError. Doc-sync + error strings only; zero engine semantics change. |
| Gate spec | `tests/test_bk17_spec_freshness.py` — L1: mechanically extract engine OPCODES and assert every opcode is named in the spec (RED today: 6 absent). L2: extract FIXED_COLORS and assert spec palette presence + exact RGB per entry (RED today: 6 absent + SYSRET mismatch). L3: live glyph_run probe on an unknown opcode → exit 2 with stderr naming the token AND the spec path (RED today: KeyError leak). L4: mutation non-vacuity — delete one opcode's spec mentions from a doc copy → L1 fires. |
| Prereqs | Spec exists (b059539a, a32b43a3); extraction method proven (probe_day1_language_dialect.py); no engine change; SE024/SE025 landed and stable. |
| Source | R53_USE_LOG.md:24 third clause (Jericho day-1); this receipt's probe measurements; spec's own audience contract (:11-13) already failing by its own standard. |
| Explicitly NOT this item | BK-15/BK-16 (shell surface); a higher-level language or transpiler UX (R2.3 landed the C/Rust story); touching engine opcode semantics or colors (spec-side only per the spec's own code-is-authoritative rule). |

## Honesty

- Research proposes, never lands engine or doc changes this tick — zero
  production lines touched. The SYSRET color mismatch is REPORTED, not
  fixed; whether spec or engine "wins" is Jericho's (spec says code is
  authoritative, but a32b43a3 pinned the palette as GLS-1.0 — a real
  sign-off decision).
- Single machine, single process for the probe legs; the glyph_run error
  probes exercised the CPU-oracle path only, no WGSL leg (none needed —
  the finding is assembler/doc surface).
- The 6-opcode drift is *expected* staleness (spec draft predates
  SE024/SE025), not rot from neglect — but the spec's own audience
  contract makes staleness a spec bug regardless of cause.
