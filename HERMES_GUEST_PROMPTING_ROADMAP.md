# Hermes Guest-Prompting Roadmap

**Goal:** learn more about the virtio_pixel/COW-journal stack (and eventually
the guest's own self-observation) by prompting hermes with real natural-language
tasks *inside* the V5 guest VM, and watching what real Ubuntu userspace does —
rather than hand-writing more fixtures. Channel: `guest_bridge.py hermes_run
"<task>"` (host) → `.hermes_guest_context/host_command.json` (shared 9p dir)
→ in-guest daemon → `guest_response.json`.

Status date: 2026-09-17. Owner: (unassigned). Prior art: `d39941d` (concurrency
stress, GP-2 below) is the only item in this menu actually run and verified.

## Why this menu matters to GlyphLang (strategy, 2026-09-17)

No fork — the prompting work is Glyph's test-corpus generator and runtime
reference. Landing spots: GP-1 syscall traces → GlyphIR differential tests
(GH-15 infra) as a third ground truth beside QEMU lockstep; the
pixel-address + addr2line debug chain → WGSL runner dev loop (targets
#88-class bugs via the existing GH-4 three-way lockstep); GP-4 self-
observation → Ouroboros / `@>` intervention-opcode prototype. GP-1 note:
capture syscall traces machine-readable (JSON), not prose — they are
destined for differential tests. Contract now exists:
`docs/SYSCALL_CORPUS_SCHEMA.md` + `tools/corpus/strace_to_json.py`
(proven on real guest traces 2026-09-17: round-trip byte-identical,
EACCES + unfinished-pair + hex-ret gates all RED→GREEN tested).

---

## Menu

- **GP-1 — Corpus growth by variety.** Prompt hermes with varied tasks
  (compress a file, watch a directory, spawn a child process, hit a permission
  error) and capture the real syscall sequences that come out. Coverage was
  22/29 syscalls at last capture; this is how `renameat2`/dir_ops surfaced
  previously — faster than guessing what the shim needs to imitate. Status:
 **queued** → **batch 1 DONE (2026-09-17)**: 5 captures (gzip, dir-watch,
 spawn/pipe, rename dance, env probe), 4357 syscalls, all schema gates +
 tamper/empty legs green; receipt `.builder_queue/RECEIPT_GP1_CORPUS_BATCH1.md`.
 → **batch 2 DONE (2026-09-17)**: 5 captures (denied-access probe with real
 EACCES, AF_UNIX socket echo, mmap RW, tar.gz tree roundtrip, dd block I/O),
 3996 syscalls, all schema gates + tamper/empty legs green; container verify
 match:true on 4/5 artifacts; receipt
 `.builder_queue/RECEIPT_GP1_CORPUS_BATCH2.md`. Orphaned-execution overwrite
 trap measured and documented (stale pairing, not chain corruption). Further
 batches remain queued (optional, additive).

- **GP-2 — Concurrency stress on the writeback≠fold boundary.** Fire several
  rapid, independent file operations through hermes and verify the COW
  journal / `locate_in_container.py` barrier holds under racing writers.
  Status: **✅ DONE (2026-09-16, commit `d39941d`)**. 4 concurrent lanes,
  4 simultaneous `compact_journal` folds, all `match: true` byte-exact, no
  barrier warnings. Findings folded into the invariant doc: folds are
  whole-journal (count-independent duration, ~34s floor observed at 1/147/1377
  entries) — which is *why* the barrier's global-mtime wait is sound under
  concurrency (any fold implies every waiter's data folded). Also caught an
  operational trap: clients must use timeouts >34s or they will see a false
  "backend down" while queued behind a fold.

- **GP-3 — Extent-geometry classes.** Prompt hermes to deliberately construct
  sparse files, hardlinks, truncate-then-rewrite, and files spanning far more
  than 3 frame boundaries. Verified geometry so far only covers tiny/ASCII,
  tiny/random, and huge/multi-extent (n=3). Each new class either confirms the
  chain or finds the next real bug, same pattern that produced GP-2's findings.
  Status: **queued** → **✅ DONE 2026-09-17 (builder cron af3e62239ce2)**: 4/4
  classes evidenced, gate exit 0, RED legs discriminating. locate+barrier-verify
  held on dense/hardlink/truncate/multiframe (256MiB → 4 frame boundaries,
  byte-exact from PNGs). Sparse class FOUND A REAL LIMIT: container verify of
  sparse files cannot match (hole bytes ≠ guest zeros) — ticketed
  `.builder_queue/TICKET_GP3_sparse_verify_holebytes.md` (options a/b/c, (a)
  recommended). Receipt `.builder_queue/RECEIPT_GP3_GEOMETRY.md`.

- **GP-4 — Self-observation.** Prompt hermes to introspect its own process
  (`/proc/self/`, its own growing log file) and watch that region of pixel
  space. First step toward the loop closing on itself — an agent whose own
  computation is visible in the same substrate it's reasoning about. Status:
  **queued**, lowest priority (exploratory, not correctness-bearing).
  → **✅ DONE 2026-09-17 (builder cron `af3e62239ce2`)**: 3/3 legs green,
  exit 0, both RED controls discriminating. The guest agent read its own
  `/proc/self/status`+fd, emitted nonces to its own growing log; host-side
  `verify` with host-computed explicit sha256 confirmed the agent's bytes
  byte-exact in the pixel container (`match: true`), and a second append
  grew the log 17→34 bytes in pixel space with the pre-append sha correctly
  rejected (RED-B) and an all-zero sha rejected (RED-A). Receipt
  `.builder_queue/RECEIPT_GP4_SELF_OBSERVATION.md` (honest boundary: n=1;
  bytes in pixel space, not the agent's reasoning; B-state throughout).

---

## Blocking gate — guest channel health — ✅ RESOLVED 2026-09-17 (~01:45)

Original findings (2026-09-16, kept for the record): stale context files
(08-29/08-30), `hermes_run` ping timing out at 90s, SSH host-key mismatch.
The corruption hypothesis is **dead**: guest `dmesg` shows **0** ext4 errors.

**Root cause (measured, all three symptoms one cause):** the *guest OS*
rebooted ~21:54 inside the long-running QEMU process (guest uptime 3:52 vs
QEMU's 16:53 start). Fresh boot → new SSH host key (the mismatch); in-guest
`guest_context_daemon` never restarted after the reboot (the timeout + stale
state). `/host_zion` was NOT the problem — systemd automounts it on access.

**Fix applied + verified (receipts):**
1. Daemon restarted inside the guest under the REQUIRED env
   (`export HOME=/var/tmp/hermehome PATH=/var/tmp/hermehome/.local/bin:$PATH`)
   — first attempt without it failed: daemon ran but `hermes` not on PATH
   (`Errno 2`). guest_state.json heartbeat mtime < 5s old. ✔
2. End-to-end oracle: `guest_bridge.py hermes_run` → hermes wrote
   `PING-OK-1789609806` to `/var/tmp/ping.txt`; host read the exact bytes back
   over ssh. The channel that timed out now round-trips. ✔
3. `ssh-keygen -R "[127.0.0.1]:2222"` refreshed known_hosts; next connection
   clean. ✔
4. Trap hit again while fixing: `pkill -f guest_context_daemon` self-matched
   the invoking shell (trap table, line 157 — third recorded bite). Split
   kill and start into separate calls.

Gate cleared — GP-3 is next per the order below.

---

## Order of operations once the gate clears

1. Confirm daemon responsiveness (`hermes_run "echo ping"` returns promptly).
2. GP-3 next (highest bug-yield-per-effort, same shape as GP-2's win).
3. GP-1 (corpus breadth, additive, no urgency).
4. GP-4 last (exploratory, not gating anything else).
