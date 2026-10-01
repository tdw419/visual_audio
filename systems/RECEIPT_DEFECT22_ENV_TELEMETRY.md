# RECEIPT — DEFECT-22 arc-run environment telemetry

**Ticket:** `DEFECT-22` (`.builder_queue/DEFECT-22_arc_legA_instability.json`, keys `attribution_2026_09_13_1205`,
`instrument_gap_2026_09_13_1205`, `ledger_2026_09_13_1205`).
**Brief:** `.builder_queue/brief_defect22_env_telemetry.md` (passes `python3 tools/check_brief.py` → PASS, 0 invalid).
**Head:** `5b423d0` · **Date:** 2026-09-13 · **Seat:** orchestrator (builder cron `af3e62239ce2`); implementation
delegated to `agy` (`output/agy/agy_impl_20260913_120155.log`, exit 0, 644 s), every number below re-run by the
orchestrator on the resulting tree.

## Why this unit exists (the measurement, not a hypothesis)

1. **No code difference in the crash path.** `git diff --stat 194844c HEAD -- tools/glyph_isa_v2.py
   tools/glyph_gpt tools/rv64i_to_glyph.py tests/test_gh22_device_driver_abi.py pytest.ini conftest.py` prints
   **nothing**, and `git rev-parse 194844c:tests/test_gh22_device_driver_abi.py HEAD:…` returns the same blob
   `750f867e0b04209bd1536bf67700af1b4c391035` twice. So the 2-of-5 concentration of DEFECT-22's disturbances at
   `194844c` cannot be a property of the tree — it is a property of *when* those runs happened.
2. **The window had OOM kills in it.** `journalctl -k --since '2026-09-13 05:00' --until '2026-09-13 05:35'` holds
   43 oom/kill lines: `05:11:50` memcg OOM in `hermes-worker-proc_723a5350c03f.scope` (killed `pytest`,
   `anon-rss:4,173,724 kB`) and `05:32:44` in `hermes-worker-proc_ff4c23113043.scope` (33 kill lines, incl. `agy`).
   The DEFECT-22 core is stamped **05:18:10** — between the two.
3. **The gap that made that unattributable:** the arc sidecar recorded `loadavg_before` and nothing about memory, so
   a `rc=139` could not be told apart from a `rc=139` that happened while the kernel was killing its siblings.

## Deliverables

| Path | Role | Status |
|---|---|---|
| `tools/arc_env_telemetry.sh` | collector — one JSON line on stdout, 9 keys (cgroup, mem limit/current/peak/swap-max, `oom_kill_total` from `memory.events`, loadavg, journal OOM window, timestamp), loud on stderr never fatal, `TELEMETRY_ONLY=1`, `TELEMETRY_JOURNAL_CMD` seam | NEW |
| `tools/arc_lega.sh` | wire-in: `env_before`/`env_after` + `oom_kill_delta` + `journal_oom_kill_delta` in the sidecar; greppable `env:` line with `PRESSURE=yes`; `TELEMETRY_ONLY=1` dry-run | MODIFIED |
| `tools/arc_lega_capture.sh` | same wire-in for the live SIGSEGV capture instrument | MODIFIED |
| `tools/gate_arc_lega_telemetry.sh` | gate, 6 legs (L1 compared-to-source, L1b non-vacuity, L1c `mem_peak` liveness, L2 dry-run sidecar, L3 journal seam both directions, L4 no regression) | NEW |

The normal path is byte-for-byte preserved apart from the added telemetry: `tools/arc_lega.sh` still ends
`echo "  log=${LOG} sidecar=${JSON}"` / `echo "$ENV_LINE"` / `exit "$RC"`, so the exit-code contract, seed handling
and no-clobber artifact naming are unchanged.

## Gate evidence

### 1. RED — orchestrator, before implementation (gate file absent)

```
$ bash tools/gate_arc_lega_telemetry.sh ; echo rc=$?
bash: tools/gate_arc_lega_telemetry.sh: No such file or directory
rc=127
```
(`output/d22_env_telemetry_gate_RED_absent.txt`)

### 2. RED — delegate's own RED phase (collector + gate present, arc scripts not yet wired)

```
-- L2 leg: dry-run sidecar (TELEMETRY_ONLY=1)
   exit code:        0 (expected 0)
   .txt logs written: 1 (expected 0)
   matching sidecars: 1 (expected 1)
   L2 FAIL: .txt log was created during TELEMETRY_ONLY=1
```
**Label:** observed by `agy` at 12:0x and transcribed from its log — the orchestrator did **not** re-observe this
intermediate state (it is a transient of the delegate's own workspace). Its purpose here is only to show the L2 leg
is discriminating; the orchestrator's own RED is §1 and its own discriminating legs are §3–§4.

### 3. GREEN — orchestrator's own run on the resulting tree

```
$ bash tools/gate_arc_lega_telemetry.sh ; echo GATE_RC=$?
   L1 PASS   (live fields, cgroup values compared against independent re-reads)
   L1b PASS  (mutant collector with mem_peak_bytes=0 fails L1; repo copy restored, md5 14c2289abacea54331f260f1b64fca8e)
   L1c PASS  (mem_peak rose 130.5 MB across a 130.0 MB allocation)
   L2 PASS   (dry_run=True, rc=None, crashes=0, 0 .txt logs, 1 sidecar)
   L3 PASS   (stub N=3 → window 3 + PRESSURE=yes; stub N=0 → 0, no marker)
   L4 PASS   (gate_arc_lega_naming rc=0, gate_arc_lega_capture rc=0)
-- gate rc: 0 (0 = every leg PASS)
GATE_RC=0
```
(`output/d22_env_telemetry_gate_GREEN.txt`) — the landed gate never weakens the two neighbouring gates: it re-runs
them and reports their exit codes (L4).

### 4. Orchestrator's independent probes (beyond the gate's own legs)

```
$ TELEMETRY_ONLY=1 OUTDIR=/tmp/d22orch.29yh SEED=777 bash tools/arc_lega.sh
arc leg A :: seed=777 head=5b423d0 rc=null crashes=0 secs=0
env: oom_kill_delta=0 journal_oom_kill_delta=0 mem_peak=52074303488 loadavg_after=0.54 1.41 2.00
arc_dry_rc=0        # files: 1 sidecar, 0 .txt ; name still arc_lega_seed777_5b423d0.json
                    # sidecar: dry_run=True rc=None crashes=0 ; env_before carries all 9 keys

$ TELEMETRY_JOURNAL_CMD=/tmp/d22_orch_journal_stub.sh bash tools/arc_env_telemetry.sh <1h ago>
{"cgroup": ".../hermes-gateway.service", "mem_limit_bytes": null, "mem_current_bytes": 35665960960,
 "mem_peak_bytes": 52074303488, "mem_swap_max_bytes": null, "oom_kill_total": 0, "loadavg": "0.54 1.41 2.00",
 "journal_oom_kill_window": 3, "at_utc": "2026-09-13T17:13:12Z"}

$ TELEMETRY_ONLY=1 TELEMETRY_JOURNAL_CMD=/tmp/d22_orch_journal_stub.sh ... bash tools/arc_lega.sh
env: oom_kill_delta=0 journal_oom_kill_delta=3 mem_peak=52074303488 loadavg_after=0.54 1.41 2.00 PRESSURE=yes
```
Both directions of the `PRESSURE` marker are therefore observed first-hand by the orchestrator (present with a
stubbed 3-kill journal window, absent with the real empty window), and the collector's count is exact (3 of 3).

## Scope check

`git status --short` on the landing: `M tools/arc_lega.sh`, `M tools/arc_lega_capture.sh`,
`?? tools/arc_env_telemetry.sh`, `?? tools/gate_arc_lega_telemetry.sh`,
`?? systems/RECEIPT_DEFECT22_ENV_TELEMETRY.md` — plus this tick's ticket/brief/artifact files. No engine, transpiler,
ABI, baker, WGSL or `tests/` file was touched; `pytest.ini` is unchanged (`git diff 194844c HEAD -- pytest.ini` is
empty, checked this tick). No arc run was needed for this unit and none was spent on it.

## What this does NOT prove

1. **No causality.** No telemetry field causes, explains or cures the SIGSEGV. The fields make a future RED
   *attributable*; they say nothing about what faulted at 05:18:10.
2. **n=2, not a rate.** The 05:11:50 / 05:32:44 OOM events and the 05:18:10 core are two observations inside one
   window. Jericho's rule applies: label it a correlation, claim no rate and no causality.
3. **Retention bound.** `journal_oom_kill_window` can only see what the kernel journal still holds; a rotated ring
   buffer reports 0, which is indistinguishable from "no OOMs" — the field is evidence of presence, never of absence.
   The cgroup's own `memory.events` counter (`oom_kill_total`) is the monotonic field and does not rotate.
4. **Scope of the counter measured on this run.** The orchestrator's own probes ran in
   `/user.slice/.../hermes-gateway.service` (`mem_limit_bytes: null` — a cgroup with no limit), whereas the 05:11/05:32
   OOMs happened in `hermes-worker-proc_*.scope`. The collector reads `/proc/self/cgroup` of the *run*, so a cron-run
   arc attributes to the worker scope — but that also means this receipt's own numbers characterise the gateway
   scope, not a cron worker's limited scope, and no probe of a *limited* scope was run.
5. **`mem_peak_bytes` is cgroup-lifetime, not run-window.** It only ever rises, so it bounds "the worst this cgroup
   ever got", not "what this run used" — the delta fields (`oom_kill_delta`, `journal_oom_kill_delta`) are the
   run-scoped ones.
