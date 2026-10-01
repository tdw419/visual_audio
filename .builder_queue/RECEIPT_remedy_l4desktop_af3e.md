# REMEDY RECEIPT — remedy-L4_desktop (evidence 2079c461)

Builder: af3e (cron af3e62239ce2) · 2026-09-27 ~20:4x CDT · HEAD at claim
65b97f11 (mailbox re-verified: newest RULING mtime 1790550013 < HEAD commit
time 1790559415 — clean; QUEUE_STATE all landed except the two pending
remedy tickets; standing order taken: lowest-order pending = this one).

## The advisory

System-1 (qwen2.5-coder:7b, 2026-09-27T19:30:56Z, conf 0.95) adjudicated
`overclaim` on RECEIPT_L4_desktop.md: "the receipt claims a defect fix and
behavioral change, but the evidence only shows green passes without any
RED-first failure evidence or discriminating negative controls."

**Verdict on the advisory: CONFIRMED.** The L4_desktop receipt's only RED
leg was a collection ImportError on the pre-landing tree (module absent).
That proves the gate can detect an absent module — it says nothing about
the receipt's actual landing-time fix (the `session_root` persistence in
`DesktopEnv.restore`, glyph_desktop_env.py:189/208-210). That fix shipped
with zero discriminating evidence: no run ever showed the gate failing
against the pre-fix behavior. Same vacuous-verification class the item26
advisory flagged, different leg.

## Measured (this tick, HEAD 65b97f11 tree)

Mutation: `restore()` ignores the persisted `session_root` and mints a
fresh `L1Session()` — the exact pre-fix behavior the receipt describes
("restore() minted a fresh L1Session root, so files saved before
save_session were unreachable"; glyph_desktop_env.py:210, one line).

- RED run (mutation applied): **1 failed, 10 passed in 0.14s** —
  `test_l4s_session_save_restore_roundtrip` at tests/test_l4_desktop.py:124:
  `AssertionError: assert 'ERR:NOENT:memo.txt' == ' persisted body'`.
  This is the receipt's own documented pre-fix symptom, byte-for-byte
  (`cat memo.txt` → ERR:NOENT). The rest of the gate (10 legs) passes under
  the mutation, which correctly localizes the discriminating power to the
  persistence leg — the only leg that exercises the mutated mechanism.
  Tail: output/REMEDY_l4desktop_MUTATION_RED.txt.
- GREEN (mutation reverted, `git diff experiments/glyph_desktop_env.py`
  empty): **11 passed in 0.12s**. Tail: output/REMEDY_l4desktop_GATE_GREEN.txt.

## Outcome

The gate's N2 leg (`test_l4s_restore_refuses_mutated_payload`) does NOT
cover this mechanism (it mutates ring lines, not the root) — but the
roundtrip leg DOES go RED under the exact mutation, so the fix is now
backed by a discriminating control: the gate fails against the pre-fix
behavior and passes against the landed behavior. No code changed; this
remedy supplies the missing RED evidence and re-anchors the receipt's
"Landing-time defect found + fixed in-session" section on a measured arc.

## What this PASS does NOT prove

- Only the session_root-persistence mechanism was mutation-tested. The
  receipt's other claims (editor GPU-syscall I/O, console isolation) have
  their own in-gate legs (N1 neutered-GPU, N2 corrupted persistence),
  which were not re-mutation-tested this tick — N1/N2's own discriminating
  power is asserted from the original receipt, not re-shown.
- The Tk/pixel surface remains operator-eyes PENDING (unchanged from the
  original receipt).
- System-1's advisory was addressed by a builder process, not re-run as
  enforcement; the re-audit verdict is appended below.
- The 0.12s/0.14s wall-clocks are pytest wall-times on the host, not
  floor-authority measurements; no rate claim is made (rule-1 floors do
  not attach — no rate/ratio cited as load-bearing).

## Receipt hygiene

Revision pinned: HEAD 65b97f11 at claim, tree clean on
experiments/ and tests/ before the mutation. Both tails kept verbatim
under output/. Probe files: none created (mutation was a one-line edit,
reverted); nothing else touched.
