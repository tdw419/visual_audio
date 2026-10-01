# BRIEF — SWEEP-CONTAIN-1: `tools/suite_sweep.sh` must REFUSE when it cannot widen

**Roadmap row:** `SWEEP-CONTAIN-1` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (state `⏳ queued`, promoted `e99ad48`).
**Spec pointer — READ FIRST (binding, do not re-litigate):** `.builder_queue/RULING_worker_memory_containment.md`
§ "(a) Heavy sweeps … (b) The harness must preflight and REFUSE. (c) Defaults". The ruling has already decided the
mechanism; there is **no design question left**. Secondary context: `.builder_queue/REPAIR_PENDING_worker_cgroup_memory_limit.md`
(the OOM measurements this exists to stop).

## The defect in one paragraph

`tools/suite_sweep.sh:23` says *"Preflight: what is the enclosing scope's cap? Refuse loudly if we cannot widen it."*
The code does not do that. When `systemd-run --user --scope` is unavailable (`:28`) it prints a `WARN` (`:34`) and
`exec`s the command anyway (`:35-36`) **inside the 4 GiB `hermes-worker-*.scope` cap** — the exact failure the wrapper
was written to prevent (three measured `CONSTRAINT_MEMCG` OOM events on 2026-09-13, one of which killed `ollama` and an
`agy` delegate). It also accepts `-w 12`, the worker count ruling (c) prohibits, and never checks that
`budget / workers >= 1 GiB`. The ruling's (a) is landed; (b)+(c) are not.

## Files in scope (positive)

1. `tools/suite_sweep.sh` — **the only implementation file.** Keep it bash, stdlib-only, and keep the file's
   existing CLI contract byte-for-byte compatible: `suite_sweep.sh [-b 12G] [-w 4] [--] <command...>`, the existing
   `enclosing scope memory.max = …` stderr line, and the `SWEEP_BUDGET` / `SWEEP_WORKERS` env exports.
2. `tests/test_sweep_preflight.py` — **NEW** gate test (legs L1–L5 below). `.gitignore`'s `test_*.py` rule hides it;
   just create it (the orchestrator force-adds it at commit time).
3. `tests/fixtures/suite_sweep_prefix_1833ba0.sh` — **NEW.** The exact pre-fix script, created with
   `git show 1833ba0:tools/suite_sweep.sh > tests/fixtures/suite_sweep_prefix_1833ba0.sh`; L5 runs it as the
   discriminating control.

**MUST NOT change (negative scope):** any other file in the repo; every existing test and every existing gate;
`tools/glyph_isa_v2.py`, `tools/rv64i_to_glyph.py`, `tools/glyph_gpt/**`, `runner.py`, any WGSL shader or
`glyph_dispatch/**`; `~/.hermes/scripts/suite_sweep.sh` (out-of-tree — the **orchestrator** mirrors the final script
there after the gate is green; do not touch it). Do not weaken any existing guard to make a leg pass.

## Required behaviour (the contract your gate must falsify)

- **R1** Resolve the enclosing scope's cap from `/sys/fs/cgroup${ENCLOSING}/memory.max` where
  `ENCLOSING=$(cat /proc/self/cgroup | cut -d: -f3)`; the literal `max` means unlimited. Add ONE documented env
  override for tests/operators, `SWEEP_CAP_FILE` (default = that cgroup path), and print the resolved value **and the
  path it was read from** on stderr, so the default path is itself assertable.
- **R2** If widening is unavailable (`systemd-run --user --scope -p MemoryMax=1G --quiet /bin/true` fails) **and**
  `BUDGET > CAP`: print a refusal line naming the requested budget, the resolved cap, its path and the worker count,
  and **exit non-zero without executing the command**. Exit code non-zero and stable (use `3`); nothing may run.
- **R3** If widening is unavailable and `BUDGET <= CAP`: proceed (it cannot make the scope worse) — non-zero refusal
  here would be a false alarm.
- **R4** `-w` greater than 4 → refuse (non-zero, message naming the max); the default stays `4`.
- **R5** `budget / workers < 1 GiB` → refuse (non-zero, message naming both numbers). `1 GiB` exactly is acceptable.
- **R6** An unparseable/zero/negative `-b` value → refuse with a usage-style error, non-zero (do not silently default).
- **R7** When widening **is** available the successful path is unchanged: one `systemd-run --user --scope` with
  `-p MemoryMax=$BUDGET -p MemoryHigh=$BUDGET --setenv=SWEEP_BUDGET=$BUDGET --setenv=SWEEP_WORKERS=$WORKERS --quiet -- <command...>`,
  exec'd, exit code passed through.
- **R8** Accept `K`/`M`/`G`/`T` suffixes (1024-based) and plain byte counts; keep parsing in bash (no python).

## Gate — run these exact commands, expect 0 failures

```
python3 -m pytest tests/test_sweep_preflight.py -q
python3 -m pytest tests/test_suite_iso_harness.py -q
```

Gate clause: `tests/test_sweep_preflight.py` carries exactly **five** legs, all PASS
(L1 refuse-nowhere-to-widen; L2 widening path unchanged/positive; L3 worker cap; L4 per-child cap + bad budget;
L5 non-vacuity against the pre-fix fixture), and `tests/test_suite_iso_harness.py` (existing neighbour harness)
stays green. Legs must be hermetic: no network, no GPU, no LLM, no reliance on the real enclosing scope — drive the
script with a `PATH`-shim directory (a fake `systemd-run` that succeeds or fails on demand and records its argv) plus
`SWEEP_CAP_FILE` pointing at a temp file, and assert on the shim's recorded argv. L2 must assert the recorded argv
contains `MemoryMax=<budget>`, `MemoryHigh=<budget>`, `--setenv=SWEEP_BUDGET=<budget>`, `--setenv=SWEEP_WORKERS=<n>`,
`--quiet`, `--` and the command.

## Failure evidence (RED first — mandatory, paste both tails)

1. Create the test **before** fixing the script, then run `python3 -m pytest tests/test_sweep_preflight.py -q` against
   the UNMODIFIED `tools/suite_sweep.sh` and paste the failing tail: L1/L3/L4 must FAIL there (today the wrapper runs
   the command instead of refusing). Record the sha256 of the unmodified script.
2. L5 is the gate's own non-vacuity leg and must be **DISCRIMINATING**: the pre-fix fixture must *not* refuse
   (`-b 12G` under a 4 GiB `SWEEP_CAP_FILE` runs the command, rc 0) while the fixed script refuses (rc != 0, command
   did not run) in the same scenario. A leg that cannot tell them apart is decoration.
3. After the fix, paste the GREEN tail of both gate commands. Also assert explicitly that the refusal path never
   executes the command (the shim/command marker file must be absent), not merely that the exit code is non-zero.
4. Record the fixture's sha256 in the test and assert it, so the pre-fix control cannot silently drift.

## Definition of done

The two gate commands exit 0 with `tests/test_sweep_preflight.py` carrying five passing legs; the RED tails from step 1
of "Failure evidence" and the GREEN tails from step 3 are pasted in the report; `tools/suite_sweep.sh` is the only
implementation file touched; the tree is left **uncommitted** for the orchestrator.

Pre-fix fixture reference (measured by the orchestrator, use it as your drift check):
`git show 1833ba0:tools/suite_sweep.sh` → sha256 `826a9cdb0f912d8cabbcffd79957f6eaf740bd3c23fcdfe51520d3f7a41f4f69`.

## Constraints

- **Interfaces are LOCKED** (the CLI contract in file 1's list above). If you believe a locked interface is wrong, do
  NOT change it: write `.builder_queue/REPAIR_PENDING_sweep_contain1_<topic>.md` with 2–4 options cheapest-first,
  state that it is a skeleton-sign-off change, and stop.
- **Do NOT commit.** Leave the tree dirty; the orchestrator runs the gate itself and commits.
- Do not run the full test suite or any sweep — the two gate commands only (context budget).
- Report: the gate tails, the sha256 values, any file:line you touched, and what the PASS does NOT prove.
