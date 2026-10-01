# RECEIPT — GP-1 Corpus Batch 2 (va-syscall-corpus/1)

**Builder:** orchestrator cron `af3e62239ce2`, run 2026-09-17 04:1x–04:4x CDT
**Branch:** `glyph-transpiler-autoloop` (main checkout; new data/tooling only)
**Contract:** `docs/SYSCALL_CORPUS_SCHEMA.md` (frozen, untouched)
**Status:** ✅ DONE — 5/5 captures pass all four schema gates + 2 batch negative legs

## Captures (staging: `corpus_build/`, dirs `b2cap*`)

| # | dir | workload | total | converted | skipped_unfinished | guest sha | container verify |
|---|-----|----------|-------|-----------|--------------------|-----------|------------------|
| 1 | `b2cap1b` | denied-access probe (urandom copy + mode-600 head + missing-dir ls) | 685 | 651 | 34 | `b96279ff…` | ✅ match:true frame 39 |
| 2 | `b2cap2` | AF_UNIX socketpair DGRAM + SOCK_STREAM bind/listen/connect/accept4 echo | 666 | 666 | 0 | `8382bad3…` | (sha gate; not container-verified) |
| 3 | `b2cap3` | 4KB file mmap write/flush/read-back | 612 | 612 | 0 | `a5d3f832…` | ✅ match:true frame 57 |
| 4 | `b2cap4` | tar czf of nested tree + listing + extract (archive/recursive getdents) | 1519 | 1183 | 336 | `8c7a5f0c…` | ✅ match:true |
| 5 | `b2cap5` | dd 64KB bs=512 conv=notrunc,sync + mode-000 cat (EACCES) + sync | 916 | 884 | 32 | `5c711b5a…` | ✅ match:true frame 39 |

Count identity (`converted + skipped_unfinished == total`) holds for all 5
(`python3 .builder_queue/probe_gp1_b2_summary.py` → `ALL_GATES: PASS`).
Round-trip: 5 sampled lines per capture, `args_raw` verbatim in `trace.log` — all PASS.

## New syscall surface vs batch 1

Batch 1 covered gzip, dir-watch poll, pipe geometry, rename dance, env probe.
Batch 2 deliberately targets classes batch 1 did not touch:
- **Error paths with named errnos:** `EACCES` (cap5 openat on mode-000),
  `ENOENT` (73 in cap1b), `ENXIO`, `ENOTTY` — batch 1's EACCES gate had never
  actually captured a real EACCES; cap5 has one.
- **AF_UNIX networking:** `socketpair`, `socket`, `bind`, `listen`,
  `connect`, `accept4`, `sendto`, `recvfrom` (cap2).
- **mmap-heavy I/O:** 36 `mmap(` lines incl. file-backed read/write map (cap3).
- **Archive/recursive tree walk:** tar+gzip create/list/extract over a
  directory tree (cap4).
- **Block-oriented copy:** `dd` with `conv=notrunc,sync` + `sync` (cap5).

## Batch histogram (top 10) / totals

```
TOP10: openat 550, mmap 439, fstat 432, close 430, newfstatat 389,
       read 330, rt_sigaction 258, write 161, lseek 123, ioctl 83
BATCH total syscalls: 3996
```

## Negative legs (RED-first)

- **Tamper leg** (`.builder_queue/probe_gp1_b2_negative.py` Leg-N): one byte
  flipped in a copy of b2cap3's `mmap.bin` → sha verify RED
  (`706eacb00a76… != a5d3f832f672…`); pristine GREEN. The host-side byte
  verify is the discriminating gate (consistent with batch 1's finding that
  count identity alone is not corruption-sensitive).
- **Empty-workload leg** (Leg-E): 0-byte `trace.log` → converter emits
  `total=0, converted=0` → per schema rule 4, not a capture; nothing committed. PASS.

## Substrate tie-in (optional `pixel_addr`)

`locate_in_container.py locate` + `verify` run for cap1b (frame 39),
cap3 (frame 57), cap5 (frame 39), cap4 (f3.txt after extract) — all
`match: true` reconstructing bytes from container PNGs alone.

## Operational finding (recorded, not a defect in the corpus)

**Orphaned-execution overwrite trap:** a host-side timed-out `guest_bridge.py
hermes_run` prompt (60s bridge cap) still completes in the guest later. My
first cap1 dispatch timed out host-side, was re-dispatched via the scp+script
recipe, and the orphan finished afterward — overwriting `cap1_denied.bin` and
`effects.sha256` with a SECOND execution's bytes. Measured effect: the
guest's live file sha (`d053…`) matched the container recon (`match:false`
only against the stale capture-time sha `d5f…`), i.e. the pixel chain was
sound and the *pairing* was stale. Batch-1's receipt already noted "dispatch
timed out host-side but completed guest-side"; batch 2 confirms it can
corrupt capture pairing. Mitigation applied: capture re-run (cap1b) with
unique paths and no concurrent prompts; both superseded artifacts removed.
**Rule for batch 3+:** after any host-side timeout, WAIT for the orphan to
drain (or pkill it in-guest) before re-dispatching to the same paths, or use
unique paths per attempt.

## Deviations / notes

- cap1 was superseded by cap1b after the orphan-overwrite above; cap1's
  directory was removed, nothing from it committed.
- cap4 used `tar tzf` + extract-to-`extracted/` instead of `rm -rf tree`
  (host guard bans recursive deletes; also avoids destroying the input).
- cap5's `chmod 000` probe file is restored to 644 after the trace so the
  directory stays usable; the EACCES is inside the traced window.
- `chmod`/`fchmod` surface appears in cap5 — bonus coverage.

## Probe defect found + fixed on re-verification (2026-09-17, orchestrator cron af3e62239ce2)

First independent re-run of `probe_gp1_b2_summary.py` this tick returned
`ALL_GATES: FAIL` (g2=FAIL on b2cap1b/b2cap2/b2cap3) while direct
`sha256sum` of all five artifacts matched their `effects.sha256` lines
exactly. Root cause is in the probe, not the data: `arts[0]` took the first
entry of an unordered `iterdir()` that excluded `trace.*`/`effects.sha256`
but NOT `task.json` — in b2cap1b/b2cap2/b2cap3, `task.json` sorted first, so
gate 2 hashed the pairing metadata against the guest artifact sha (same
probe-targeting-defect class recorded on GP-1 batch 1 and SUITE-HEAVY-1).
Fix (both `probe_gp1_b2_summary.py` and `probe_gp1_b2_gates.py`): the
artifact is the file NAMED by `effects.sha256`'s path field; `task.json`
added to the exclusion set; gates probe's stale `b2cap1` → `b2cap1b`.
RED before (this tick's own run): `ALL_GATES: FAIL`, g2=FAIL ×3, hashing
`task.json` in every failing capture. GREEN after: summary probe
`ALL_GATES: PASS` (5/5 captures, g1/g2/g3 PASS, TOTAL 3996) and gates
probe 10/10 PASS exit 0. The tamper/empty negative legs
(`probe_gp1_b2_negative.py`) re-ran GREEN this tick and target bytes, not
directory order — unaffected. Receipt's batch verdict stands unchanged;
only the verification probes were mis-aimed.

## What this PASS does NOT prove

- Same as batch 1: real guest workloads, but a minimally populated Ubuntu
  (no GUI apps, no systemd-heavy churn).
- `skipped_unfinished` pairs (cap4: 336 — tar/gzip contention) are counted,
  not silent, but their bodies are excluded (v1 contract).
- cap2's sha gate passed host-vs-guest, but its artifact (55B stdout log) was
  not container-verified — the capture is syscall-ground-truth, not a
  substrate claim.
- No GH-15 consumer wired yet; analysis-readiness is per the schema only.
- n=1 per workload class; traces characterize the guest's strace-visible
  behavior for these exact commands, not the commands in general.
