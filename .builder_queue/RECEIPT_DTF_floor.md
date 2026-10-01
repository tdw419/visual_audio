# RECEIPT — DTF floor exit: end-to-end floor transcript (desktop-floor exit artifact #1)

**Date:** 2026-09-22 ~21:2x CDT
**Builder:** af3e62239ce2 (Glyph GPU OS product lane)
**Base revision:** HEAD beff1abe (this lane's DTF-4 landing; re-verified per the
parallel-session rule; no RULING_* newer than HEAD — newest mtimes 20:38,
pre-landing; ledger STATUS ACTIVE; monitor CLEAN queue=0)
**Authority:** AMENDMENT_DTF1_desktop_floor.md, "Floor exit criteria" —
`RECEIPT_DTF_floor.md` exercising all four rows in sequence, plus each row's
own gates.
**Scope touched:** `.builder_queue/transcript_dtf_floor.py` (NEW, re-runnable),
this receipt, `PRODUCT_ROADMAP.md` (P2.5 status annotation),
`PRODUCT_LANE_STATE.md` (ledger). No engine, shader, transpiler, codec, or
protected-asset changes.

## What ran (one command, one process)

```
.venv/bin/python .builder_queue/transcript_dtf_floor.py   # exit 0
```

Legs, in order (full PASS lines in the transcript log):

- **T0 blank-sentinel (RED-first discipline):** the console band is decoded
  BEFORE any turn runs — empty, as the amendment's DTF-2 gate leg (a) requires.
- **DTF-1 (one dispatch-shell instance, 5 turns, no restart):**
  `e build floor` → `' build floor'`; `w cat dog` → disk bytes `b' cat dog'`
  byte-exact; `r` → `' cat dog'` round-trip; `s speak me` → WAV 15876 samples
  @ 44100 Hz, `Phy16Tone.decode == b' speak me'`; `z bogus command` →
  `ERR:UNKNOWN_CMD` (loud, named).
- **DTF-2:** the SAME session's PRT stream renders into the pixel band and
  decodes back glyph-side: `' build floor\n\n cat dog\n\nERR:UNKNOWN?CMD'`.
  The `?` is the documented missing-font replacement for `_` (the VGA atlas
  carries 85 glyphs; the bracket/brace family [ \ ] ^ _ ` { | } ~ is absent) —
  the band is a faithful record of what the machine printed, not of ASCII.
  Composed observation (program + band) built; band persisted to PNG.
- **DTF-3:** the binding BK-7 gate (`tests/test_bk7_fs_grow.py`) —
  write, append 2×, whole-file read-back byte-exact; delete → hole; reuse.
  2 passed in 0.08s (this process, via subprocess).
- **DTF-4:** the binding BK-11 gate (`tests/test_bk11_coreutils.py`) —
  cat/echo/wc/cmp/head, 3 fixtures each, byte-exact vs native, wc green
  (no waiver). 6 passed in 22.88s.
- **Mutation (RED) leg:** the neutered always-echo build (build_shell) echoes
  `z bogus command` verbatim with the marker absent — the transcript
  discriminates dispatch from always-echo; it cannot pass vacuously.

## RED leg (rule 4, shown before trusting GREEN)

Corrupted expectation (`out[2] == " cat cow"` instead of `" cat dog"`) in an
otherwise identical run:

```
[FAIL] DTF-1 L4 read round-trip — ' cat dog'
DTF_FLOOR_TRANSCRIPT FAIL (1 leg(s): DTF-1 L4 read round-trip)
EXIT=1
```

The transcript fails on a false expectation against the live machine.

## Landing-time defects found and held (disclosed, not hidden)

1. First expectation draft hard-coded the ASCII marker `ERR:UNKNOWN_CMD` and
   the speak turn as visible output. Both wrong against the machine: `_` is
   not in the font atlas (band shows `ERR:UNKNOWN?CMD`), and AUDIO_OUT PRTs
   nothing (the speak turn contributes an empty band line). Fixed by deriving
   the expected band text from the font's actual coverage and the PRT stream's
   actual behavior — the band is checked against what the machine prints, not
   against prose. Two RED runs preceded the green.
2. The FONT COVERAGE GAP itself is pre-existing (documented in
   RECEIPT_DTF2_text_console.md: "Font coverage is 85 glyphs; the ASCII
   bracket/brace family renders as `?`") — but this transcript is the first
   artifact where a session's own output (`ERR:UNKNOWN_CMD`) hits it. The
   unknown-cmd error — arguably the most important string on the floor —
   displays with a hole in it. NOT fixed here (font atlas extension is an
   engine-adjacent change outside this receipt's scope); filed as candidate
   queue supply.

## What this PASS does NOT prove

- **Per the amendment's binding wording:** this transcript certifies
  CORRECTNESS of the legs, NOT USABILITY. It does not substitute for,
  precede in authority, or diminish the operator's day-2 R5.3 entry. The
  companion agent pre-verification receipt (RECEIPT_DTF_agent_use.md, the
  seat-lane batch pattern) remains a separate, still-open artifact.
- Batch/pipe mode only; no human at a tty.
- The band is glass-TTY (host-side renderer over the PRT stream); no
  twin-side rendering claim. DTF-3/DTF-4 legs run via their standing pytest
  gates in subprocesses, not re-derived glyph-side here.
- No rate claims → floors/check_regime N/A (rule 1 not triggered).
- Single host; the WGSL twin is not exercised in this transcript (each
  component row's own gate covered twin legs where required: DTF-2 parity,
  DTF-3 probe).

## Floor state

All four DTF rows DONE, each with its own gate green at HEAD, plus this
end-to-end transcript. P2.5 floor exit criteria: MET (in the checkable sense
the amendment defines). R5.3's 30-day clock untouched per the amendment's
clock-handling clause.
