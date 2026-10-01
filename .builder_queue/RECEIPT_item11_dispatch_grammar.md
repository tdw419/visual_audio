# RECEIPT — CLAIM QUEUE ROUND 6, ITEM 11: dispatch grammar collision

**Landed:** 2026-09-23, builder cron af3e62239ce2 (Glyph GPU OS product lane)
**Tree:** HEAD at claim `154d0700` (Jericho's supply commit); fix lands this commit
**Supply:** `.builder_queue/PRODUCT_LANE_STATE.md` CLAIM QUEUE ROUND 6 item 11
(commit 154d0700, 2026-09-23 07:36 CDT — Jericho-flagged day-2 landmine)

## What was wrong

The dispatch shell's glyph program branched on the FIRST byte of each turn's
line only (SE020 chain, `build_dispatch_shell` in
`experiments/glyph_interactive_shell.py`). Any English sentence whose first
letter matched a command char was silently misexecuted — no error anywhere:

| Pipe | Parsed as | Live-reproduced effect (pre-fix, this tick) |
|---|---|---|
| `what time is it` | `w` + `hat time is it` | FILE_WRITE `b'hat time is it'` to `/tmp/.../w.dat`, output `['']` |
| `seems fine to me` | `s` + `eems fine to me` | AUDIO_OUT 15-byte WAV (silent speech), output `['']` |
| `read me the news` | `r` + garbage | PRT of the file's prior content `[' stale prior content']` |

RED probe (re-runnable): `.builder_queue/probe_item11_grammar_red.py`
→ pre-fix exit 1 with all three misexecutions cited; post-fix exit 0.

## The fix (option (a)+(b) combined, implemented IN the glyph program)

Grammar gate inserted in `build_dispatch_shell` between the first-byte fetch
(`LD r6 r1`) and the e/s/w/r dispatch chain:

1. **Length read** — `LD r9` from RAM word `INPUT_LEN_ADDR>>2` (8284), the
   harness's per-turn line length (`run_turn` rewrites it every turn —
   authoritative, never stale).
2. **Bare command rule** — `len == 1` jumps to `:bare_cmd`: only bare `r`
   (the one documented zero-payload command) is legal; bare `w/s/e/x/…`
   fall through to the error marker.
3. **Delimiter rule** — `len > 1` peeks byte 1 DIRECTLY from the harness
   input ring (`LD` from word `INPUT_DATA_ADDR>>2 + 1` = 8289, NOT the 0x02
   scratch buffer — the syscall consumes ring bytes, so the scratch copy can
   never be re-read; peeking the ring consumes nothing) and requires it to
   be `' '` (0x20), else `JNZ :err_cmd` → `ERR:UNKNOWN_CMD`.
4. **Payload convention** — unchanged and now documented: payload is ALL
   bytes after byte 0, verbatim (`'w  x'` writes `'  x'`, `'e hello'`
   echoes `' hello'`). No silent byte shifting.
5. **Help text** — `__main__` banner now states the grammar contract.

Mechanism note (fenced speculation, not load-bearing): the fix is purely
additive glyph-asm instructions in the experiment shell's program; the
engine (`tools/glyph_isa_v2.py`), the syscall arms, and the WGSL twin are
untouched — no new opcode, no new syscall, no ISA change.

## Gate

`tests/test_item11_dispatch_grammar.py` (NEW, force-added past
.gitignore:101) — 8 legs:

- **G1** ×3 (RED-first): the three natural-sentence pipes must produce
  `ERR:UNKNOWN_CMD`, no file written, no WAV produced, no echo.
- **G2**: bare `r` still round-trips; bare `w/s/e/x` all error loudly.
- **G3**: SE020 four-command session byte-identical to before.
- **G4**: `'w  x'` writes `'  x'` (double space preserved — payload verbatim).
- **G5**: `r` following a longer line is not contaminated by stale ring bytes.
- **Mutation/non-vacuity**: pre-SE020 always-echo shell fails the G1 shape.

Gate arc (all run this tick, this process):

- **RED, current tree at claim:** `4 failed, 4 passed` (G1×3 + G2 RED on
  pre-fix build).
- **Stash-discrimination RED:** `git stash` of the fix → same 4 failed/4
  passed; `git stash pop` → restored.
- **GREEN post-fix:** `8 passed in 0.14s`.
- **Probe flip:** `.builder_queue/probe_item11_grammar_red.py` exit 1 (pre)
  → exit 0 (post), all three pipes now `ERR:UNKNOWN_CMD`, nothing written,
  no WAV.

## Transcript (re-runnable, exit 0)

`.builder_queue/transcript_item11_grammar.py` — before/after generator for
each natural-sentence pipe. Post-fix output (pasted):

```
pipe1 'what time is it' -> out=['ERR:UNKNOWN_CMD'] file_written=False
pipe2 'seems fine to me' -> out=['ERR:UNKNOWN_CMD'] audio_produced=False
pipe3 'read me the news' -> out=['ERR:UNKNOWN_CMD']
pipe4 legit session -> out=[' hello', '', '', ' payload text'] wav_decode=b' hi there' file=b' payload text'
TRANSCRIPT: PASS
```

Live human-entry pipe through `experiments/glyph_interactive_shell.py`
(batch stdin): `e hello` → ` hello`; `what time is it` → `ERR:UNKNOWN_CMD`
(named, nothing written); `w note` → file `b' note'`; `r` → ` note`.
Exit 0.

## Regression

- Standing SE020/shell/console gates:
  `test_glyph_app_shell_dispatch.py + test_glyph_interactive_shell.py +
  test_glyph_text_console.py` → 25 passed.
- Extended family (adds echo/voice apps, R5.2 stranger doc, this gate):
  40 passed.
- Standing DTF transcripts re-run at HEAD+fix, all exit 0:
  `transcript_dtf_floor.py` (DTF_FLOOR_TRANSCRIPT PASS),
  `transcript_dtf1.py` (DTF1_TRANSCRIPT PASS).
- Zero engine/codec/WGSL files touched → no worktree isolation required
  (AGENTS.md blast-radius rule); no floors/rate claims → rule-1 N/A.

## What this PASS does NOT prove

- WGSL twin: the dispatch shell is a host-engine experiment program; the
  twin never executes it (each row's own gate carries twin legs). No shader
  claim made.
- The typo-tolerance question (should `wnote` suggest `w note`?) is out of
  scope — the contract is fail-loud, not fuzzy-match.
- BK-16 (clock command) remains backlog — this grammar fix is explicitly
  NOT a substitute, per the supply item's own note.
- Acoustic legibility of spoken payloads untouched (DTF receipts' domain).

## Ledger

PRODUCT_LANE_STATE.md: round-6 item 11 marked landed; queue returns to
empty; next supply from R5.3 friction, Jericho directive, or a ruling.
