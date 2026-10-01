# RECEIPT — DEFECT-22: what the memory cap actually does, and the arc record it was destroying

**Tick:** builder cron `af3e62239ce2`, 2026-09-13 13:0x CDT. **Head at start:** `070e004`.
**Verdict:** two measured findings, one of them a real instrument hole; the hole is fixed and gated in this
commit. The defect itself (SIGSEGV) is **not** reproduced and its mechanism stays **undiagnosed**.
**Teleop:** no substrate read this tick — this is tree-side verification work, not a B-state session.

## Supply, re-measured before acting (not copied from prose)

* `python3 tools/supply_census.py` → **TOTAL=59 OPEN=0**.
* `systems/GLYPH_BACKLOG.md` re-read in full: 15 ids (BK-1..BK-14 + OBS-1), every one promoted and landed.
* The standing prompt's "RULINGS awaiting implementation" line is **stale**: DEFECT-17 option (d) landed
  `7a4208a` (row 339 `✅ done`, `tests/test_defect17_x31_refusal.py` 11/11) and DEFECT-18 option (a) landed
  `11fe1ac` (row 340 `✅ done`). Live supply is still **the DEFECT-22 ticket only** (queue=1 = the monitor's
  level trigger).

## Why this experiment, and not a 14th green arc run

The ticket has carried, since 12:05, a **correlation**: the two disturbed runs of 2026-09-13 sit inside an
active worker-cgroup memory-pressure window, and leg A drives its own cgroup to 91.5 % of the 4 GiB cap.
Correlation with no mechanism is not evidence, and one property of the mechanism had never been measured:
**what failure shape does the cgroup cap produce for this workload?** A cgroup cap is enforced by the kernel
OOM killer — SIGKILL — so if that holds, cap pressure cannot produce the defect's SIGSEGV at all.

Instrument: `.builder_queue/probe_defect22_pressure_class.sh` (committed), same leg-A command in two transient
user scopes, `MemoryMax=2200M`, differing only in `OOMPolicy`. Raw stdout: `output/d22_pressure_class_probe.txt`.

| arm | OOMPolicy | systemd-run rc | sidecar | oom_kill_delta | journal_oom_kill_delta | PRESSURE |
|---|---|---|---|---|---|---|
| negative control (`output/arc_lega_seed2026091305_9bd8dd2.json`, ordinary run) | — | 0 | present, full | 0 | 0 | absent |
| **A** | `continue` | **137** (SIGKILL) | present, `rc=137`, 54 s | **1** | **1** | **PRESSURE=yes** |
| **B** | `kill` (mirrors the Hermes worker scope) | 137 | **ABSENT** | — | — | never printed |

### Finding 1 — the cap's failure shape is SIGKILL, not SIGSEGV

Arm A: `mem_peak_bytes == mem_limit_bytes == 2306867200` (2200 MiB, the cap reached exactly), `rc=137`,
`rc_is_sigsegv=False`, and the shell's own line `Killed  "$PY" -m pytest …`. So the class the ticket has been
correlating with the defect fails by **SIGKILL**. **Consequence, stated as narrowly as the evidence allows:
the worker memory cap's *enforcement mechanism* cannot produce DEFECT-22's signature.** The pressure
correlation must therefore be restated — it is not "the cap killed it", because that failure is 137, and the
observed disturbance was 139 inside CPython's eval loop. Pressure-induced allocator pathology short of the cap
is not excluded by this measurement; the cap's own path is.

This also **first exercises the telemetry's non-zero path on a real kernel OOM**: `oom_kill_delta=1`,
`journal_oom_kill_delta=1` and `PRESSURE=yes` had only ever been demonstrated against stub journals
(`gate_arc_lega_telemetry.sh` L3) and dry runs. The negative control above shows the marker is discriminating,
not decorative.

### Finding 2 (the instrument hole) — a cap OOM inside a worker scope destroys the arc's verdict

Arm B: **`SIDECAR=ABSENT`** — the only survivor is the 769-byte partial `.txt` pytest log
(`/tmp/d22_pressure_B/arc_lega_seed2026091306_070e004.txt`); no machine-readable record, no `rc`, no `PRESSURE`
marker. Under `OOMPolicy=kill` the kernel kills the **whole scope**, including the shell that writes the sidecar
after pytest returns. The Hermes worker scope is exactly that configuration —
`tools/process_registry.py:273-308` wraps background local executors in
`systemd-run --user --scope --unit=hermes-worker-<id> --property MemoryMax=<n> --property OOMPolicy=kill`
(4 GiB cap measured live in the sidecars) — and leg A's own peak against it is **2.97–3.93 GB**. So this is a
*latent* hazard armed at 8.5 % headroom in the heavier sample: when the condition the ticket suspects most
occurs, the loop's primary verification instrument reports **nothing at all**. It is the same class of loss
SUITE-ISO-2 fixed for the pytest harness (`--sink`), never checked for the arc.

## The fix (one gate-able step, one commit)

`tools/arc_lega.sh` writes a **start record** to the same per-run sidecar path *before* pytest starts —
`{"state": "RUNNING", seed, head, started_utc, rc: null, …}` — which the normal exit overwrites with the full
record (`"state": "DONE"` added to both the dry-run and the final writer). A killed run now leaves a parseable
JSON naming its seed and head, i.e. a replayable "this run existed and was killed" instead of nothing.
Written with `printf`, not `$PY`: a third interpreter invocation would have to be routed by the stub-PY legs in
`tools/gate_arc_lega_naming.sh`.

Gate `tools/gate_arc_lega_record_survival.sh`, rc=0, `output/d22_record_survival_gate.txt`:

* **L0 premise** — the pinned pre-fix runner (`070e004`) really lacks the start record (else the RED leg is stale).
* **L1 RED (falsifier)** — pinned pre-fix runner, `MemoryMax=1200M OOMPolicy=kill` → `systemd-run rc=137`,
  **sidecar_count=0**: the property was genuinely absent. RED measured, not asserted.
* **L2 GREEN** — working-tree runner, identical scope → `rc=137`, sidecar present and parses:
  `state=RUNNING seed=2026091307 head=070e004 started_utc=2026-09-13T18:07:59Z`.
* **L3 no-regression** — `TELEMETRY_ONLY=1` dry run → rc=0, sidecar `state=DONE dry_run=True rc=None`.
* **L4 no-regression** — `gate_arc_lega_naming.sh` rc=0 and `gate_arc_lega_telemetry.sh` rc=0 (both do subset
  key checks, so the added key is additive by construction, and both were re-run, not assumed).

Real uncapped leg-A run after the fix (normal path, not the dry run), `SEED=2026091308` → **rc=0,
325 passed / 1 skipped / 1 deselected, 125.37 s, crashes=0, state=DONE, oom_kill_delta=0, no PRESSURE marker**
(`/tmp/d22_postfix/…`; deliberately out-of-tree so a deliberate kill can never enter the arc ledger).

## What this PASS does NOT prove

* It does **not** fix the OOM and does not make the arc fit its cap — it preserves a *name* for a lost run.
* It was measured through a transient user scope configured **identically** (`MemoryMax` + `OOMPolicy=kill`),
  **not** through the Hermes `process_registry` wrapper; the production properties are the same and are read from
  source, but the wrapper path itself was not exercised.
* Only `tools/arc_lega.sh` is fixed. `tools/arc_lega_capture.sh` writes its own sidecar the same way and is
  **not** fixed — named as a follow-on, not silently covered.
* Caps chosen (1200M gate, 2200M probe) are **below** the production 4 GiB: they force the OOM to make the
  property observable; they are not a claim about when production OOMs.
* **n is one run per arm** — two observations, not a rate; and the defect's own SIGSEGV was **not** reproduced
  (still 0 disturbances in the post-`194844c` series).
* Ledger after this tick: plain post-`194844c` **14 runs / 0 disturbed** (13 + the post-fix run above); capture
  series 6 runs. Whole series n=20 / 2 disturbed, both at `194844c` — still two one-offs, no rate claimed.

## Standing state (unchanged, and it is Jericho's call)

Roadmap 0 open rows; backlog exhausted; queue=1 == the DEFECT-22 ticket, so `state=REPAIR_PENDING` remains a
level trigger cleared only by retiring that ticket to `.builder_queue/resolved/` or by new supply. The pending
pick is unchanged: renew lane supply / accept DEFECT-22 as a documented stability bound and release the trigger /
re-point or slow the cron.
