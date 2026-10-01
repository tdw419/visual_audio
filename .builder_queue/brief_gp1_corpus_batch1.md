# BRIEF — gp1-corpus: generate the first syscall corpus batch via prompted hermes in the pixel guest

## Title

BRIEF — gp1-corpus: generate 5 varied-task syscall captures from real Ubuntu
userspace in the pixel-booted guest, per the frozen va-syscall-corpus/1
contract, each passing all acceptance gates.

## Authority

Jericho, 2026-09-17, in-channel: "can we get the builder to work on this
roadmap?" — roadmap = HERMES_GUEST_PROMPTING_ROADMAP.md (repo root), item GP-1.

## Spec pointers (read all four before starting)

1. `HERMES_GUEST_PROMPTING_ROADMAP.md` — GP-1 definition (§GP-1), task menu,
   and the GlyphLang strategy note (traces feed GH-15 differential tests;
   JSON, not prose).
2. `docs/SYSCALL_CORPUS_SCHEMA.md` — the contract (va-syscall-corpus/1).
   FROZEN: do not edit. If the contract blocks you, file a defect instead.
3. `tools/corpus/strace_to_json.py` — the only converter. Proven on 1,196
   real guest lines (round-trip byte-identical, EACCES, unfinished pairs,
   hex rets).
4. `docs/GUEST_AGENT_PIXEL_WORKFLOW.md` — guest channel usage, daemon env
   requirement, trap table.

## WHERE YOU ARE

Main checkout, `/home/jericho/projects/zion/projects/visual_audio`. No
worktree needed: this task creates NEW data/tooling files only and touches no
core codec component.

## MEASURED STATE (do not re-derive; verified 2026-09-16/17)

- Guest VM up (QEMU pid 343702-era boot), guest rebooted ~21:54 Sep 16.
- GP-0 gate RESOLVED: in-guest `guest_context_daemon` running (pid 18738-era)
  under the required env (`HOME=/var/tmp/hermehome`,
  `PATH=/var/tmp/hermehome/.local/bin:$PATH`); oracle round-trip proven
  (PING-OK byte-exact readback). SSH known_hosts refreshed for [127.0.0.1]:2222.
- strace 6.8 present in guest (`/usr/bin/strace`).
- Converter + schema proven end-to-end on 3 real traces (normal, EACCES
  failure, threaded/unfinished-pairs).

## Operational traps (each one already bit a lane; costs you a misdiagnosis)

- Bridge `hermes_run` waits max 90s host-side. Keep each guest task small
  (<60s guest time); if it times out, split the task, don't raise timeouts.
- After guest writes, allow ≥35s before host-side `verify`:
  `compact_journal` folds serialize at a ~34s floor regardless of entry
  count. A verify fail/timeout right after a write is usually "fold still
  in flight", not corruption.
- If the daemon is found down (guest rebooted again): restart recipe is in
  `HERMES_GUEST_PROMPTING_ROADMAP.md` §Blocking gate (RESOLVED receipt) —
  nohup under the hermehome env above. Do NOT start it without that env;
  bare `hermes` is not on the guest's PATH.
- `pkill -f guest_context_daemon` self-matches the invoking ssh shell
  (trap table, 3 recorded bites). Split kill and start into separate calls.
- Client HTTP timeouts to the backend (port 8769) must exceed ~40s or you
  will time out while queued behind a fold.

## Scope

POSITIVE (exclusive write set — everything else is forbidden):
- `corpus/` — NEW directory tree: one subdir per capture, each containing
  `task.json`, `trace.log`, `trace.json`, `effects.json` exactly per schema.
- `.builder_queue/probe_gp1_*.py|sh` — your own RED-first probes.
- `.builder_queue/RECEIPT_GP1_CORPUS_BATCH1.md` — receipt.
- `HERMES_GUEST_PROMPTING_ROADMAP.md` — GP-1 section status lines ONLY
  (mark batch done + receipt pointer). Do not restructure the doc.
- `TICKET_SUPPLY_STATE_ADDENDUM*.md` — next addendum number, noting supply
  consumed (one line; this lane's ledger, keep it accurate).

NEGATIVE (must not touch):
- `docs/SYSCALL_CORPUS_SCHEMA.md`, `tools/corpus/strace_to_json.py` (frozen
  contract; defect if wrong).
- `guest_bridge.py`, `guest_context_daemon.py`, anything under
  `tools/pixel_container/`, `tools/glyph_gpt/`, `systems/`, `voicebook/`,
  `.rts/`, `rs_fixtures.json`.
- GP-3 / GP-4 work (separate briefs follow after this batch lands).
- The SE021 maildrop question (stays Jericho's; do not ack, do not rule).

## Task list (batch 1 — 5 captures, sequential, one bridge call at a time)

Guest-channel ownership: this brief owns the guest channel for its duration.
1. Compress a file: create ~200KB of random data in the guest, gzip it.
2. Watch a directory: run a short inotifywait loop (or a Python
   inotify-lite via os.scandir polling at 100ms) while another guest shell
   creates/deletes files in the watched dir.
3. Spawn a child: a small shell pipeline (`ls -la /etc | head -5 > out.txt`)
   — captures fork/exec/pipe/wait geometry.
4. Rename dance: create a file, rename it twice, append, rename again —
   renameat2 surface.
5. Env probe: a guest process that reads and writes a small env-dependent
   output file (getenv/cwd variations).

Each capture: dispatch via `python3 guest_bridge.py hermes_run "<task>"`,
with strace attached in the guest per the schema's capture recipe
(`strace -f -ttt -T -s 256 -o trace.log <workload>`), then pull artifacts,
convert with `tools/corpus/strace_to_json.py`, and host-side verify the
effect file bytes with `tools/pixel_container/locate_in_container.py verify`
(respecting the 35s fold floor).

## Gates (RED-first — every gate must be shown able to fail)

Per capture, all four schema acceptance gates must pass, plus:
- Negative leg (once per batch, recorded in the receipt): tamper one pulled
  trace byte and show `strace_to_json.py` count-identity or the verify gate
  goes RED on the tampered copy, GREEN on the pristine one. A gate that
  cannot fail is decoration; prove yours can.
- Empty-workload leg (once per batch): dispatch a hermes task that provably
  did not run (daemon down simulation is NOT required — simply convert an
  empty trace.log) and show the schema's "empty capture is not a capture"
  rule fires (0 syscalls → reject).

## DONE WHEN

1. `corpus/` holds 5 capture subdirs, each passing all gates; count identity
   holds for every converted trace.
2. `effects.json` in every capture carries the sha256 that host-side verify
   confirmed against the pixel container.
3. Receipt `RECEIPT_GP1_CORPUS_BATCH1.md` lists: per-capture syscall counts,
   top-10 syscall histogram across the batch, gate results, negative-leg
   evidence, and any deviation notes.
4. Roadmap GP-1 status lines updated; supply addendum filed.
5. All of it committed (prefix `feat(corpus):` per capture or one batch
   commit — your call, but commits must pass the repo's standard gates).

On any blocker (daemon down beyond recovery recipe, bridge dead, contract
conflict): STOP, write the receipt with FAIL status and evidence, file a
defect. Do not widen scope to fix the guest stack.
