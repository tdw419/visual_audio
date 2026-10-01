# BRIEF — gp3-geometry: extent-geometry classes through the pixel-address chain

## Title

BRIEF — gp3-geometry: deliberately construct the four unverified extent-geometry
classes (sparse, hardlink, truncate-then-rewrite, many-frame-span) in the pixel
guest, run each through the locate/verify chain, and record per-class
confirm-or-bug verdicts in a receipt.

## Spec pointers (read all four before starting)

1. `HERMES_GUEST_PROMPTING_ROADMAP.md` — GP-3 definition and the ordering note
   ("GP-3 next, highest bug-yield-per-effort, same shape as GP-2's win").
2. `docs/GUEST_AGENT_PIXEL_WORKFLOW.md` — the address chain (filefrag +
   /sys/block start → disk byte → frame/pixel), the `locate`/`verify`/`watch`
   commands, and the trap table (filefrag dialect anchoring, whole-block
   hashing, writeback barrier).
3. `tools/pixel_container/locate_in_container.py` — `$T locate` (extent map,
   frames + pixel spans) and `$T verify` (reconstruct from PNGs, barrier-aware).
4. `d39941d` commit message — the concurrency invariant this task must respect
   (timeouts > 34s; folds are whole-journal, ~34s floor).

## Scope (files this task may change)

POSITIVE (exclusive write set):
- `.builder_queue/brief_gp3_geometry.md` (this brief)
- `.builder_queue/RECEIPT_GP3_GEOMETRY.md` (new)
- `.builder_queue/probe_gp3_*.py` (own probes, if needed)
- `HERMES_GUEST_PROMPTING_ROADMAP.md` — GP-3 status line ONLY
- `corpus_build/gp3/` (new staging dir for guest-pulled artifacts: filefrag
  dumps, sha lists, small evidence files)
- `docs/GUEST_AGENT_PIXEL_WORKFLOW.md` — ONLY if a new trap is bitten and
  confirmed (append one trap-table row; no other edits)

NEGATIVE (must not change):
- `docs/SYSCALL_CORPUS_SCHEMA.md` (frozen)
- `tools/pixel_container/locate_in_container.py` — if the chain needs a fix,
  that is a NEW defect: file `.builder_queue/TICKET_GP3_<slug>.md` with RED
  evidence and STOP that leg; do not patch the tool in this task
- `tools/corpus/strace_to_json.py`, any `systems/` file, any core codec file
- No worktree needed: this task creates new data/docs only and touches no core
  codec component (same ruling as GP-1 batch 1)

## Gate command

```
bash .builder_queue/gate_gp3_geometry.sh; echo "exit=$?"
```
Expected exit code: **0** with 4 `PASS[gp3-<class>]` lines (one per class) plus
`RED-legs all discriminating`. The gate script itself lives in the write set.

## Gate clause (falsifiable criteria)

For EACH of the four classes (`sparse`, `hardlink`, `truncate_rewrite`,
`multiframe`), the gate checks against measured data in
`corpus_build/gp3/<class>/`:

1. **Artifact exists**: the guest-side `effects.sha256` lists ≥1 file, each
   with a 64-hex sha and a byte size.
2. **Locate succeeds**: `locate_in_container.py locate <guest-path>` output
   (saved as `locate.json`) contains ≥1 extent with frame + pixel span.
3. **Host container verify**: `locate_in_container.py verify <path> <sha>`
   (barrier taken, no `--no-barrier`) exits 0 — i.e. the file reconstructs
   byte-exact from PNGs alone.
4. **Class-specific assertion**:
   - `sparse`: `filefrag -v` dump (saved as `filefrag.txt`) shows FEWER
     extents than a same-size dense file would need, AND `du -b` vs
     `stat -c %s` differ by ≥8x (holes exist on disk); verify sha is of the
     LOGICAL content (written blocks only, per whole-block-hash trap).
   - `hardlink`: the same inode reached via 2 different paths verifies
     byte-exact at BOTH paths; `ls -i` (saved as `inodes.txt`) shows equal
     inode numbers.
   - `truncate_rewrite`: post-rewrite sha equals the sha of the NEW content
     (proving stale pre-truncate pixels are not served); a recorded
     pre-rewrite sha is ALSO present and DIFFERS.
   - `multiframe`: `locate.json` shows the file spanning > 3 frame
     boundaries (≥4 distinct frames), vs prior art's 3.
5. **RED legs (failure evidence, pre-run BEFORE trusting green)**:
   - `verify-sha-red`: run `verify` once with a deliberately wrong sha on a
     real file → must exit non-zero / report mismatch (proves gate 3 can fail).
   - `sparse-red`: assert `du -b <sparse> != stat -c %s <sparse>` would be
     violated by a dense file — probe a dense control file of the same size
     and show it FAILS the ≥8x sparseness assertion (proves gate 4-sparse
     discriminates sparse from dense).

A class whose leg cannot be completed (guest channel down after 3 retries,
disk exhaustion, tool defect) is recorded as `SKIP[gp3-<class>] reason=...`
in the receipt — that is a legitimate outcome for an exploratory class ONLY
if the failure is external (channel/environment); a mismatch INSIDE the
verify chain is a FINDING (bug), not a skip, and lands as a ticket.

## Definition of done

- Gate exit 0, receipt written with per-class tables (geometry measured,
  locate output, verify result, wall time), trap-table additions if any,
  and a "what this PASS does not prove" section.
- `HERMES_GUEST_PROMPTING_ROADMAP.md` GP-3 status line updated with the
  outcome (confirmed N classes / bugs found M) + receipt pointer.
- `git status --short` shows only in-scope files.
- One commit landing everything (brief + gate + probes + data + receipt +
  roadmap status), receipt discipline in the body (RED legs before GREEN).

## Interfaces LOCKED

`locate_in_container.py` CLI (locate/verify/watch), the address-chain math in
`docs/GUEST_AGENT_PIXEL_WORKFLOW.md` (block*4096 + partition_start*512), and
the guest channel contract (`guest_bridge.py hermes_run`, 90s host timeout)
are LOCKED. If a locked signature looks wrong: file
`REPAIR_PENDING_gp3_<topic>.md` with options cheapest-first, state it is a
skeleton-sign-off change, hold that leg, continue with the other classes.

## Never weaken a live guard

The writeback barrier (verify's default) and the whole-block-hash rule exist
because of recorded incidents. No `--no-barrier` in gate legs; no hash
widening to make a leg pass.

## Operational traps (each already bit a lane; costs a misdiagnosis)

- `hermes_run` waits max 90s host-side; keep each guest task < 60s guest time.
  For anything heavier: scp a probe script, then a minimal one-line prompt
  (batch-1 recovery pattern).
- After a guest write, allow ≥ 35s before container reads (fold ~34s floor).
  A verify fail right after a write is usually "fold in flight", not
  corruption. Client timeouts must exceed 40s.
- Disk space: check `df -h /var/tmp` in the guest BEFORE creating the
  multiframe file; pick a size that leaves > 20% free. If the guest disk is
  too small for ≥4 frames, say so in the receipt with the measured df — do
  not shrink the assertion silently.
- SSH known_hosts for [127.0.0.1]:2222 was refreshed 2026-09-17; if the guest
  rebooted again, the host key rotates — refresh, don't disable checking.
- Daemon down after a guest reboot: restart recipe in the roadmap's blocking
  gate section; MUST use the hermehome env or `hermes` is not on PATH.
