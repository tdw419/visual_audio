# RECEIPT — DTF-1 glyph-sh v1 dispatch (desktop floor rung 1)

**Landed:** 2026-09-22, builder cron af3e62239ce2 (GPU OS product lane).
**Authority:** AMENDMENT_DTF1_desktop_floor.md (RATIFIED, commit 4e3c30a2,
2026-09-22 17:19 CDT), row "DTF-1"; base spec
`.builder_queue/brief_se020_shell_dispatch.md` + ROADMAP.md TASK_SE020 row
(ROADMAP.md:1765, read first per the brief's own instruction).
**Revision:** HEAD 4e3c30a2 at tick start; no tree changes were needed
(see "Already-built state" below). This receipt + the roadmap promotion are
the landing.

## Already-built state (measured, not assumed)

DTF-1's implementation is TASK_SE020, landed 2026-09-15 as commit `2227ebc5`
("feat(se020): glyph-sh v1 — dispatch on first byte (e/s/w/r), gate 17/17
green", orchestrator-verified per the ROADMAP row's Status line). The
amendment activates a rung whose code already exists on this branch — the
amendment's NOTE (Jericho) makes the brief "a SPECIFIED DESIGN, not a
ruling; this amendment is the approval that activates it". Nothing was
re-implemented; this session MEASURED it at HEAD and produced the required
receipt, which the SE020 landing never carried under the DTF-1 name.

## Gate (amendment text, run this session at HEAD 4e3c30a2)

`/usr/bin/python3 -m pytest tests/test_glyph_app_shell_dispatch.py
tests/test_glyph_interactive_shell.py tests/test_glyph_isa_v2.py -q`

- RED-first leg (rule 4): test file moved out of tree → pytest exits with
  `ERROR: file or directory not found: tests/test_glyph_app_shell_dispatch.py`,
  `no tests ran` — the gate refuses to pass without the dispatch test
  present. (The amendment's own RED-first clause: "its absence is the RED
  leg".)
- GREEN: `17 passed in 0.30s`, rc 0, at HEAD.

## Receipt artifact (amendment requirement: transcript of all five legs on
## ONE shell instance, no restart between commands)

Generator: `.builder_queue/transcript_dtf1.py` (kept in-tree, re-runnable).
Run output (abridged; syscall trace omitted, full leg lines verbatim):

```
=== DTF-1 one-instance transcript (build_dispatch_shell) ===
turn 'e hello'              -> ' hello'
turn 's hi there'           -> ''
turn 'w payload text'       -> ''
turn 'r'                    -> ' payload text'
turn 'z bogus command'      -> 'ERR:UNKNOWN_CMD'

--- leg verification ---
L1 echo: out[0] == ' hello' (expect ' hello')
L2 speak: wav 15876 samples @ 44100 Hz, decoded=b' hi there'
L3 write: /tmp/dtf1_receipt_tc6bzywc/w.dat bytes=b' payload text'
L4 read:  out[3] == ' payload text' (round-trip of b' payload text')
L5 unrecognized: out[4] == 'ERR:UNKNOWN_CMD' (DISPATCH_ERROR_MARKER='ERR:UNKNOWN_CMD')

--- mutation (RED) leg: neutered always-echo build (build_shell) ---
neutered turn -> ['z bogus command']
marker absent in neutered output: True; echoed verbatim: True

DTF1_TRANSCRIPT PASS
rc=0
```

One `repl(lines=[...])` run, one `build_dispatch_shell` image, five turns
in sequence with no restart — all five legs in a single transcript, per the
amendment's receipt clause. The mutation leg is the non-vacuity proof: the
neutered always-echo build echoes the line verbatim and never emits
`ERR:UNKNOWN_CMD`, so the gate discriminates dispatch from always-echo.

## What this PASS does NOT prove

- Batch mode only — no real-tty human session (the pytest-safe,
  batch-never-touches-stdin invariant held; carried over from the SE020
  receipt verbatim, still true).
- AUDIO_OUT verified by host-side `Phy16Tone.decode`, not acoustic playback.
- No WGSL-twin leg: the amendment's DTF-1 gate text does not require one
  (twin parity is a DTF-2 requirement); the dispatch shell is assembled
  glyph code executed by GlyphCPUv2, and the engine-level twin gates
  (test_glyph_isa_v2 coverage, pillar21 rotguard) are green separately.
- No rate claims → floors N/A (rule 1 not triggered).
- Fixed-path single-file FS turns; directories/pipes remain post-floor
  (amendment defers them).

## Floor state after DTF-1

| Amendment row | State |
|---|---|
| DTF-1 dispatch shell | **DONE this receipt** |
| DTF-2 in-image text console | next, claimable next tick |
| DTF-3 FS grow | blocked by DTF-2 order, not by tech |
| DTF-4 coreutils vol. 1 | depends on DTF-3 |

R5.3 clock untouched (amendment clock-handling clause: no manufactured
entries; day 1 stands).
