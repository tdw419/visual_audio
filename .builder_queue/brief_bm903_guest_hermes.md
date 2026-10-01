# BRIEF — TASK_BM903: Guest-side handoff provenance gate (prompts Hermes in the pixel-booted VM)

**Row:** proposed → `tools/bare_metal_poc/ROADMAP.md` Rung 9, after BM902 lands
**Provenance:** Jericho 2026-09-18 ~22:20 — "how could the builder benefit from
prompting hermes in the vm and continuing the work we are doing here"
**Standing rule (hard):** the guest investigation is READ-ONLY. No writes to
guest disk beyond the probe's own temp marker; no guest package installs; no
restarts of guest services.

## Why the builder should prompt guest Hermes at all (capability map)

The builder (host cron) already has three instruments that reach the guest:

1. **`guest_bridge.py hermes_run "<task>"`** — file-based command/response over
   the shared 9p mount (`.hermes_guest_context/`). Runs Hermes v0.19.0 INSIDE
   the pixel-booted VM (`/var/tmp/hermehome`). Discipline: the guest model is
   smaller and the daemon caps hermes_run at 300s — tasks must be bounded
   ("answer in <10 sentences, run exactly these 2 commands, quote output");
   multi-tool agent sessions time out (measured).
2. **`sshpass -p israel ssh -p 2222 jericho@127.0.0.1`** — direct shell, for
   exact commands (filefrag, dd, sha256sum). No password piping to sudo
   (`sudo -S` is blocked by tooling policy); guest jericho has no passwordless
   sudo. Raw `/dev/vda` reads need Jericho.
3. **Backend HTTP `GET /peek?addr=<diskbyte>&size=<words>`** (port 8769 /
   `$VCC_HTTP_PORT`) — reads disk bytes through the SAME extractor/decoder the
   guest's vhost-user-blk reads use. Guest-equivalent disk read, no guest
   access needed. NOTE: single-threaded mutex plane; journal compaction holds
   it ~35s; out-of-bounds frames return padded zeros WITHOUT decoding.

What ONLY a guest-side prompt gives: file-level evidence from inside the
running OS (filefrag extents, /sys/block offsets, sha256 of a live file's
bytes, fs behavior) that no host-side tool can produce. The host can verify
container bytes; only the guest can testify what its OWN filesystem did with
them.

## Goal

Close the last unmeasured link in the BM901/902 chain with guest-side
evidence: **does the guest's own read path (kernel page cache aside) serve
exactly the bytes BM902's handoff wrote, verified from inside the running OS
— file-level, not just byte-level?**

## Method

1. **Prereq:** BM902 gate GREEN (its differ is the host-side half-truth this
   task completes). Backend running; guest heartbeat fresh
   (`.hermes_guest_context/guest_state.json` timestamp < 5 min).
2. **Locate (host):** `tools/pixel_container/locate_in_container.py locate`
   needs a guest file; get its extent data via ONE bounded guest-Hermes run:
   `filefrag -v /tmp/bm903_probe.bin` + `sha256sum` it (guest writes the
   probe file itself — that is the one sanctioned guest-side write).
3. **Verify (host):** reconstruct the file's bytes from container PNGs alone
   (`locate_in_container.py verify`); must sha-match the guest's sha256.
4. **Cross-check (host, no guest):** backend `/peek` at the file's first disk
   byte must equal the byte `dd`/peek shows AND the byte the guest Hermes
   quoted from `od`/`xxd` on its own file. Three-way agreement = the guest's
   logical file, the container pixels, and the guest-equivalent disk path all
   tell one story.
5. **Negative leg:** after guest `rm` + `sync` (+ host compaction), the
   three-way agreement must BREAK (file gone guest-side; locate/verify fails
   or pixels change). A gate that can't fail isn't a gate.
6. Cleanup: probe file removed guest-side (guest Hermes `rm` + `sync`),
   `pxc1-verify` green if any PNG was rewritten. Probe logic lands as
   `tools/bare_metal_poc/rung9/guest_provenance_gate.sh` (or .py), reusing
   `livemap_probe.py`'s retry/eviction conventions.

## Verification (row gate)

- [ ] Three-way agreement measured (guest file sha == pixel-reconstructed
      sha == peek bytes) on a ≥1-extent guest-local file.
- [ ] Negative leg demonstrated RED after rm+compact.
- [ ] Guest-Hermes prompts used are bounded (<300s each, quoted-output
      style); zero unbounded agent sessions.
- [ ] Receipt `rung9/RECEIPT_BM903.md` + roadmap cell; rung1-7 + oracle
      dumps read-only; `tools/pixel_container/` additions only.

## Files in scope

`tools/bare_metal_poc/rung9/guest_provenance_gate.sh` (or `.py`), `tools/bare_metal_poc/rung9/RECEIPT_BM903.md`,
one row cell in `tools/bare_metal_poc/ROADMAP.md`; `tools/pixel_container/` additions only.
Rung 1-7 sources and oracle dumps are read-only. Nothing else may change.

## Boundary

Guest file writes limited to the probe file. No sudo inside the guest. No
backend restarts, no compaction calls from this task (the builder's own
journal folding happens on its schedule; gate waits for mtime advance per
docs/GUEST_AGENT_PIXEL_WORKFLOW.md). BM001 stays HOLD; lands only its own
receipt + roadmap cell.
