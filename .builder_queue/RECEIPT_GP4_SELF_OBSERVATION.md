# RECEIPT — GP-4 Self-Observation (the loop's own bytes in pixel space)

**Builder:** orchestrator cron `af3e62239ce2`, run 2026-09-17 ~23:00 CDT
**Branch:** `glyph-transpiler-autoloop` (main checkout; data/docs/builder_queue only)
**Spec:** `HERMES_GUEST_PROMPTING_ROADMAP.md` §GP-4; brief `.builder_queue/brief_gp4_self_observation.md`
**Gate:** `bash .builder_queue/run_gp4_legs.sh` → **GATE: GP4 ALL LEGS GREEN**, exit 0
**Status:** ✅ DONE — 3/3 legs green, both RED controls discriminating

## What was measured

The prompted hermes agent inside the pixel-booted guest:

1. **L1 — introspection.** Read its own `/proc/self/status` (Name/Pid/PPid/Umask/Threads/TracerPid)
   and `/proc/self/fd`, wrote the snapshot to `/var/tmp/gp4_1789617660/proc_snapshot.txt`, and emitted
   nonce `GP4N1-1789617660` to `nonce1.txt` + its own growing `self_log.txt`. The agent's own
   observation (recorded in the transcript): the `grep` reading `/proc/self/status` is itself the
   process it introspects — Name:grep, Pid 48384, fd 3 pointing at `/proc/48385/fd` (the ls fork).
2. **L2 — closure.** Host-side `locate_in_container.py verify` with EXPLICIT sha256 (host-computed
   from the literal the guest was told to write — NOT the guest's own sha256sum, which would let a
   lying guest self-certify): both `nonce1.txt` and the pre-append `self_log.txt` → `match: true`.
   All three files single-extent, frame 57 region. **The agent's own emitted bytes are provably in
   the pixel container, byte-exact.**
3. **L3 — growth.** Second nonce `GP4N2-1789617660` appended via a separate bridge call; pixel-side
   size 17 → 34 bytes; post-append sha `9c4b42bc…` verified in-container; pre-append sha
   `ff8567d7…` correctly REJECTED against the grown file.

## RED-first (the gate can fail)

- **RED-A** `corpus_build/gp4/red_a_wrongsha_verify.json` — all-zero sha against the snapshot →
  `match: false`. The verifier discriminates.
- **RED-B** `corpus_build/gp4/red_b_presha_vs_post.json` — the PRE-append sha asserted against the
  POST-append file → `match: false` (expected `ff8567d7…`, reconstructed `9c4b42bc…`). The growth
  assertion is not vacuous.

## Trap table (new entries this run)

- **`file:` sha256s mode parses `<hash> <name>` pairs** (`locate_in_container.py:218`) — pointing it
  at a file of bare nonce lines raises `ValueError: not enough values to unpack`, which FAILS CLOSED
  (crash, not false match). Correct outcome, unobvious cause; use explicit sha for single files.
- **Bridge output is decorated** (`📤 Running Hermes…`, agent prose); verdict-grepping the raw
  transcript false-fails. Gate greps for `✅ Success` / parses JSON artifacts, not free text.
- **hermes_run has a ~60s ceiling** — compound multi-file tasks time out whole. Split legs; don't
  widen (GP-1 brief's rule, re-bitten here once).
- The 36s settle (journal fold floor) before every container verify is load-bearing: both RED-B and
  L3 verify failed-fast on the first draft's missing wait (transient-exhausted, not corruption).

## Honest boundary — what this PASS does NOT prove

- **n=1, single-trial.** One session, one nonce pair, one host run. Jericho's rule: single-trial
  results are coin flips; this is an existence proof, not a characterized behavior.
- The agent's **reasoning** is not in pixel space — only the bytes it chose to emit. "Self-observation"
  here means: an agent's own computational side-effects (a /proc read, a log append) are exactly
  addressable and verifiable in the same substrate it runs on. The C-state claim (resident, oracle-
  gated) is NOT made; this is B-state teleop all the way down, witnessed from the host.
- The guest wrote its own sha256sum output during probing (earlier runs); the gate's closure sha is
  host-derived to avoid self-certification, but the *content* the guest wrote is still trusted to
  match the prompt (a malicious guest could write the expected bytes without "observing" anything).
- `/proc/self` introspection is of the transient `grep`/`ls` processes, not a persistent hermes
  process — the "agent introspects itself" framing is exact only at the syscall level.
- Guest scratch `/var/tmp/gp4_1789617266/` and `/var/tmp/gp4_1789617660/` (~few KB) left in place
  (no rm authority) plus GP-3's ~600MB — guest disk cleanup still needs Jericho.

## Files

- Gate: `.builder_queue/run_gp4_legs.sh` (committed)
- Evidence: `corpus_build/gp4/` (locate JSONs ×4, verify JSONs ×5 incl. both RED legs, bridge
  transcripts ×3, growth summary, expected literals) — committed
- Roadmap row GP-4: `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (status flip in the landing commit)
