# BRIEF — GP-4 SELF-OBSERVATION: guest agent introspects its own process through the pixel substrate

**Row id:** GP-4 (HERMES_GUEST_PROMPTING_ROADMAP.md §GP-4, "Self-observation", status queued).
**Mode:** orchestrator-implemented (delegation retired 2026-09-15). Guest channel health gate: RESOLVED
2026-09-17, round-trip re-verified this promotion (guest `hermes_run` echo returned `ping-44505`).

## Spec (read first)

`HERMES_GUEST_PROMPTING_ROADMAP.md` lines 66–68: "Prompt hermes to introspect its own process
(`/proc/self/`, its own growing log file) and watch that region of pixel space. First step toward the
loop closing on itself — an agent whose own computation is visible in the same substrate it's reasoning
about." GP-4 is explicitly **exploratory, not correctness-bearing** — its deliverable is EVIDENCE that
the loop can close on itself, with the same verification honesty as GP-2/GP-3.

## Scope (positive — exclusive write set)

- `corpus_build/gp4/` — all measured evidence (locate JSONs, observation transcripts, RED-leg outputs)
- `.builder_queue/RECEIPT_GP4_SELF_OBSERVATION.md` — the receipt
- `HERMES_GUEST_PROMPTING_ROADMAP.md` — ONLY the GP-4 status line
- guest-side scratch files under `/var/tmp/gp4_<ts>/` inside the pixel guest (no repo writes from the guest)

## Scope (negative — must NOT touch)

- `tools/pixel_container/locate_in_container.py` — read-only instrument (GP-3 ticket options a/b/c are
  pending a ruling; do not pre-empt them)
- No engine/codec/WGSL files; no `voicebook/`, `.rts/`, `rs_fixtures.json` (protected)
- No `rm` inside the guest (agent guard + no cleanup authority; timestamped dirs only)
- No growth of the guest log file beyond a bounded append (the log must GROW, not balloon — cap ~64KB)

## The experiment (three legs, one closure claim)

**L1 — self-process introspection (guest side).** Prompted hermes (via `guest_bridge.py hermes_run`)
reads its own `/proc/self/` evidence: `status` (Pid, Umask, Threads), a bounded slice of its own
`/proc/self/fd/` listing, and appends a unique nonce line to its own growing log file
`/var/tmp/gp4_<ts>/self_log.txt`. All bytes it "thought about" exist on the pixel disk.

**L2 — pixel-space localization (host side).** `tools/pixel_container/locate_in_container.py locate`
on (a) the `/proc`-derived snapshot file the guest wrote (json, small) and (b) the appended log file.
Expected: single-extent geometry for both (fresh small files). The nonce bytes are the SAME bytes the
guest agent emitted — closure of guest-cognition → disk-bytes is asserted by byte-exact comparison
between the guest-echoed nonce and the host-read container bytes (`verify` with the file's sha256).

**L3 — the log GROWS in pixel space (the watch leg).** After L2, the guest appends a SECOND distinct
nonce. `locate_in_container.py watch` (or diff of two locate maps) must show the pixel-side change
tracked: new bytes at a NEW file offset, same inode, both nonces verifiable. This is the "growing log
file" clause of the spec row, measured rather than narrated.

**RED-first (the gate must be able to fail):** (1) a `verify` with a deliberately wrong sha256 must
report `match: false` (GP-3's sparse finding shows verify semantics have known limits — the control
here is dense small files, the healthy class); (2) the L3 closure assertion must fail if the second
nonce's bytes are NOT found at the post-append offset — simulate by asserting against the pre-append
locate map first (expect FAIL), then against the post-append map (expect PASS).

## Gate command

```
bash .builder_queue/run_gp4_legs.sh   # runs all legs; exit 0 + receipt values only on full pass
```

Gate clause: exit 0; every locate/verify JSON in `corpus_build/gp4/` shows the expected match status;
both nonce byte-exactness comparisons hold; the pre-append RED leg actually failed (recorded).

## Definition of done

Receipt `RECEIPT_GP4_SELF_OBSERVATION.md` with: method, raw locate JSON paths, nonce values, the RED
legs pasted, honest caveats (what this does NOT prove — e.g. the agent's *reasoning* is not in pixel
space, only the bytes it emitted; single-trial n=1 labeling), and the GP-4 status line updated.

## Soft contract lines

Interfaces are LOCKED: the only instrument is the committed `locate_in_container.py` (read-only) and
`guest_bridge.py` — no signature change, no new engine surface. Never weaken a live guard to make a
leg pass: if the wrong-sha verify unexpectedly returns `match: true`, that is a finding to ticket,
not a gate to route around.
