#!/usr/bin/env python3
"""Append this tick's ledgers to .builder_queue/DEFECT-22_arc_legA_instability.json.

Tick 2026-09-13 12:2x CDT, builder cron af3e62239ce2.
Adds: landing verification of the previous tick's telemetry unit, the two arc runs
(1 capture + 1 plain, both background), and the measured worker-scope memory cap.
Keeps the file valid JSON; every number below was produced by this tick's own runs.
"""
import json
import pathlib

P = pathlib.Path(__file__).resolve().parent / "DEFECT-22_arc_legA_instability.json"
d = json.loads(P.read_text())

d["landing_verified_2026_09_13_1225"] = (
    "b9e1a09 (arc sidecars carry their environment) + 9bd8dd2 (journal, docs-only: 2 files, "
    "REPAIR_PENDING_worker_cgroup_memory_limit.md + roadmap journal) RE-RUN, not trusted: "
    "`bash tools/gate_arc_lega_telemetry.sh` -> rc=0 on my own run at 9bd8dd2, legs L1 (fields compared against "
    "independent re-reads), L1b mutant, L1c mem_peak liveness, L2 dry-run sidecar (dry_run=True rc=None crashes=0), "
    "L3 journal seam both directions (stub N=3 -> 3 + PRESSURE=yes; stub N=0 -> 0 and no marker), L4 naming + capture "
    "gates both exit 0. `git status --short --untracked-files=no` empty before and after."
)

d["runs_2026_09_13_1225"] = (
    "2 background arc leg A runs at 9bd8dd2, BOTH rc=0 / 325 passed / 1 skipped / 1 deselected / 0 crashes "
    "(each of these is a command + its own artifact, not a rate): "
    "(a) SEED=2026091304 under the CAPTURE instrument -> 126.75 s, segv_caught=false, sidecar "
    "output/arc_lega_capture_seed2026091304_9bd8dd2.json; (b) SEED=2026091305 plain -> 127.09 s, sidecar "
    "output/arc_lega_seed2026091305_9bd8dd2.json. Both were the FIRST runs whose sidecars carry the new env "
    "telemetry on a real pytest run (the landed unit had only been exercised through stubs and TELEMETRY_ONLY=1). "
    "Order coverage: fresh seeds sample fresh pytest-randomly orders, capture series now covers 6 orders "
    "(1914088745, 1208765432, 2026091301/02/03/04). Series: capture 6 runs / 0 disturbed, plain post-194844c "
    "13 runs / 0 disturbed, whole series n=19 / 2 disturbed, both at 194844c -- still two one-offs, NOT a rate."
)

d["scope_cap_measured_2026_09_13_1225"] = (
    "The telemetry's first real-run readings name the constraint that OOM-killed this loop's runs. Both sidecars "
    "report the run's OWN cgroup: hermes-worker-proc_c52c7f53674c.scope and hermes-worker-proc_06a553377acb.scope, "
    "each with mem_limit_bytes = 4,294,967,296 (exactly 4 GiB). Peak after the run: 3,929,948,160 B (91.5% of cap, "
    "capture/gdb path) and 2,970,484,736 B (69.2%, plain path) from fresh scopes (peak-before 17.4 MB / 16.1 MB). So a "
    "canonical arc leg A run drives its own worker cgroup to 2.97-3.93 GB against a 4 GiB HARD cap, ~365 MB (8.5%) of "
    "headroom in the heavier sample; the ~1 GB spread between two samples says the peak is not a stable constant "
    "(n=2, two observations, not a rate). The 05:11:50 pytest victim (anon-rss 4,173,724 kB) and the 11:28 sweep's "
    "worst child (3,470,616 kB) are the same class as these peaks. SOURCE OF THE CAP (named, not guessed): "
    "tools/process_registry.py:273-308 wraps every BACKGROUND local executor in `systemd-run --user --scope "
    "--unit=hermes-worker-<id> --property MemoryMax=<n> --property OOMPolicy=kill`, with n from "
    "_worker_memory_max_bytes() (:107-136) = tighter of the gateway cgroup's memory.max and half of physical RAM, "
    "capped at 4 GiB (_WORKER_MEMORY_MAX_CAP_BYTES :106); intent stated at :82-95 (an OOM must kill the worker, never "
    "the gateway control plane). MEASURED ASYMMETRY: a FOREGROUND command inherits hermes-gateway.service "
    "(/proc/self/cgroup; memory.max = max), the background form gets the 4 GiB OOMPolicy=kill scope -- both runs above "
    "were background. CORRECTION to REPAIR_PENDING_worker_cgroup_memory_limit.md option 3: the cap is NOT reachable by "
    "config; TERMINAL_LOCAL_MEMORY_MAX_MB is honoured only when it TIGHTENS ('an oversized override cannot widen host "
    "risk', :114-119), so raising it for builder lanes is a Hermes-runtime code change or upstream PR. Consequence for "
    "this ticket (correlation only, no causal claim): a worker-scope OOM during a capture run would kill gdb + pytest "
    "together and lose precisely the evidence the instrument exists to collect, and the sidecar that would record it "
    "is written only if the process survives. Details appended to REPAIR_PENDING_worker_cgroup_memory_limit.md."
)

d["next_step_2026_09_13_1225"] = (
    "UNCHANGED and still ARMED: the defect's next RED needs `SEED=<seed> bash tools/arc_lega_capture.sh` and a sidecar "
    "reading capture.segv_caught=true with a non-null si_addr/pc_symbol. 2 more fresh orders were sampled this tick "
    "(no crash), which does not change the bound. New operational note, free to use: heavy verification launched as a "
    "BACKGROUND worker runs against a 4 GiB OOMPolicy=kill cap ~0.4 GB away in the worse sample, while the same "
    "command run FOREGROUND inherits the uncapped gateway scope."
)

P.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("keys:", len(d))
print("valid:", bool(json.loads(P.read_text())))
