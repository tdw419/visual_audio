# TICKET — GP-3 finding: container verify of sparse files mismatch (hole bytes ≠ guest zeros)

**Filed:** 2026-09-17, builder cron af3e62239ce2, GP-3 geometry class run
**Severity:** real chain limitation, low urgency (verify of sparse guest files is
the only affected path; dense/hardlink/truncate/multiframe all byte-exact)

## Symptom (measured, this run)

- Guest file `/var/tmp/gp3_1789615295/sparse/sparse.bin`: 64MiB logical,
  3 written 4KiB blocks at logical offsets 0 / 8192 / 16383 (rest = holes).
- Guest sha256: `e2c0c762a4c823da…` (holes read back as zeros in the guest).
- Host container verify (`locate_in_container.py verify`, barrier taken):
  reconstruction hashes `28cd6ed52391ef92…` → **match: false**.
- `locate` itself is CORRECT: 3 single-block extents, frames 131/132, spans exact.
- Dense 64MiB control file verifies `match: true` on the same run — the barrier,
  writeback, and reconstruction pipeline are healthy. The mismatch is specific to
  the hole class.

## Root cause (chain math, not yet probed to block level)

Container frames are never zero-initialized for unwritten disk regions, and the
tool reconstructs the whole logical file size from pixel bytes. A hole region's
container bytes hold pre-image garbage (whatever was in those frames before),
while the guest reads holes as zeros. Whole-block-hash trap documented for small
files generalizes: any byte NOT covered by a live extent is unreliable.

## Options (cheapest first)

1. **(a) Document-only:** record in `docs/GUEST_AGENT_PIXEL_WORKFLOW.md` trap
   table: "verify sparse files at extent granularity, not whole-file" — callers
   pass `file:sha256s` per-extent hashes. No code change.
2. **(b) Tool change:** `verify` computes expected hash treating non-extent
   logical regions as zeros AND warns when the file is sparse (filefrag hole
   count > 0). Needs read-side access to extent map it already parses.
3. **(c) Zero-fill policy:** container backend zero-fills fresh frames. Largest
   change; touches the backend; likely unjustified for one class.

Recommendation: (a) now, (b) if GH-15 differential tests ever consume sparse
fixtures. This is a design decision on a shared tool → NOT self-implemented
per AGENTS.md (verify semantics are consumed by other lanes).

## What this ticket does NOT claim

- Have not probed whether the mismatching bytes are exactly the hole regions
  (consistent with, but not proven by, the dense-control discrimination).
- Have not tested files with holes AND post-hole appended data.
