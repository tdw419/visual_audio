# REMEDY RECEIPT — remedy-DTF_floor (evidence 33b1e687)

Builder: af3e (cron af3e62239ce2) · 2026-09-27 ~21:0x CDT · HEAD at claim
84236753 (mailbox re-verified: newest RULING mtime 1790550013 < HEAD commit
time 1790559885 — clean; QUEUE_STATE exactly one pending item = this ticket,
claim_order -2; standing order 4d7f98df: last of the three remedy-* tickets).

## The advisory

System-1 (qwen2.5-coder:7b, 2026-09-27T23:00:13Z, conf 0.90) adjudicated
`overclaim` on RECEIPT_DTF_floor.md: "claims a bug fix for the
'ERR:UNKNOWN_CMD' issue, but does not provide evidence of a RED-first
failure before the fix or any discriminating negative controls."

**Verdict on the advisory: REBUKED — the flagged evidence exists in the
receipt and was re-proven live at HEAD this tick.** Two specific
mis-readings, then the measured arc.

### 1. The receipt DOES carry RED-first + discriminating controls

- RED leg, receipt :47-58: corrupted expectation
  (`out[2] == " cat cow"` instead of `" cat dog"`) in an otherwise identical
  run → `[FAIL] DTF-1 L4 read round-trip`, `DTF_FLOOR_TRANSCRIPT FAIL`,
  `EXIT=1` — pasted verbatim in the receipt.
- Landing-time REDs, receipt :60-68: two RED runs preceded the green (the
  first draft hard-coded ASCII; the machine disproved it — VGA atlas
  missing `_` → band shows `ERR:UNKNOWN?CMD`; AUDIO_OUT PRTs nothing →
  speak turn is an empty band line).
- Discriminating mutation, receipt :43-45 and transcript
  .builder_queue/transcript_dtf_floor.py:136-140: the neutered
  always-echo build (build_shell) echoes `z bogus command` verbatim with
  the marker ABSENT — the transcript cannot pass vacuously on dispatch.
- The advisory's "claims a bug fix for ERR:UNKNOWN_CMD" is also a
  mis-parse: the receipt claims NO bug fix — it documents a FONT COVERAGE
  GAP found at landing and explicitly did NOT fix it (:69-76, "filed as
  candidate queue supply"). The gap was later closed by a separate rung
  (85662ba2, BK-19 font atlas 95/95), which is why the band decodes the
  full marker at HEAD today.

### 2. Re-measured at HEAD 84236753 (this tick, both tails in output/)

- RED re-run: the committed transcript copied, ONE expectation corrupted
  (`' cat dog'` → `' cat cow'`, the receipt's own mutation), executed —
  **13 legs PASS, exactly 1 FAIL**:
  `[FAIL] DTF-1 L4 read round-trip — ' cat dog'`,
  `DTF_FLOOR_TRANSCRIPT FAIL (1 leg(s): DTF-1 L4 read round-trip)`,
  **EXIT=1**. Localization exact: only the leg whose expectation was
  corrupted fails; all 13 others (blank-sentinel, write-on-disk, speak
  decode, loud marker, band decode, DTF-3 2/2, DTF-4 6/6, always-echo
  mutation) pass under it. Tail: output/REMEDY_dtffloor_MUTATION_RED.txt.
- GREEN re-run: unmutated committed transcript — **all 14 legs PASS,
  EXIT=0**, `DTF_FLOOR_TRANSCRIPT PASS — all four floor rows exercised in
  sequence`. Tail: output/REMEDY_dtffloor_GATE_GREEN.txt.
- Independently re-confirmed this tick: the band decodes
  `'ERR:UNKNOWN_CMD'` WITH the underscore (DTF-1 L5 PASS line) — at the
  939391d5 landing the band showed `ERR:UNKNOWN?CMD`; the delta is the
  later BK-19 atlas extension (85662ba2, 2026-09-23), a drift the
  receipt's `_font_expect` derivation absorbs by construction.

## Outcome

The advisory's failure-mode claim ("no RED-first evidence, no
discriminating negative controls") is factually wrong for this receipt:
both were in the original landing AND reproduce live at HEAD. No code
changed; no expectation edited in the committed transcript; the mutation
lived only in a throwaway untracked copy, deleted after the run. This is
an evidence-rebuke, not a remediation — the standing order's
"remediated or evidence-rebuked" clause applies.

## What this PASS does NOT prove

- Only the receipt's RED leg mutation (corrupted L4 expectation) was
  re-run at HEAD. The two landing-time REDs (font-coverage and
  silent-AUDIO_OUT disprovals) are attested from the receipt's record —
  their original output tails predate this tick and were not
  regenerated (the atlas gap they prove is since FIXED, so they cannot
  re-run green-tree anyway).
- The always-echo discriminating leg and DTF-2 pixel-mutation leg pass
  as in-gate legs; neither was independently re-mutated beyond what the
  transcript itself does.
- System-1 was not re-asked to re-adjudicate (screener rerun this tick
  reproduced the same overclaim@0.90 verdict against the same
  evidence_hash; re-litigating the classifier's read is Jericho's call,
  not the builder's).
- No rate claims → rule-1 floors N/A. Tk/pixel surface still
  operator-eyes PENDING (unchanged from the original receipt).
- receipt-hygiene: revision pinned (HEAD 84236753 at claim); the tracked
  tree gained only this receipt, the two tails, QUEUE_STATE flip, and
  the ledger entry.
