# RECEIPT — SPINE-R2-WIREIN: publish-path registry append + operator retention CLI

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` → `SPINE-R2-WIREIN`
**Ruling:** `.builder_queue/RULING_spine_wirein.md` — **OPTION 2** (ruled 2026-09-13; clears
`.builder_queue/REPAIR_PENDING_spine_wirein_design.md`)
**Promotion:** `652e177` (roadmap row added, ⏳ queued, promotion provenance in the row)
**Implemented by:** `agy` (Antigravity CLI) from `.builder_queue/brief_spine_r2_wirein.md`
(`output/agy/agy_impl_20260913_073106.log`, exit 0, 327 s) — never committed by the delegate
**Verified by:** orchestrator (builder cron `af3e62239ce2`), all numbers below are my own runs
**Date:** 2026-09-13 · **Host:** `/usr/bin/python3` 3.12

## What was built

| File | Change |
|---|---|
| `tools/geos_emit.py` | +63/−2: `GeosEmitter.__init__` gains `registry_path` / `origin_id` (env `GEOS_REGISTRY_PATH` / `GEOS_ORIGIN_ID`, default registry `/tmp/glyph_spine_index.jsonl`); the publish path (`_commit`) appends exactly one line to the `WriteRegistry` in a `try/except` — on any failure the sidecar gains `unattributed: true` + `unattributed_reason` and the publish still succeeds; `GeosEmitter.publish` / module-level `publish()` aliases added |
| `tools/geos_retain.py` | NEW (351 lines): operator CLI over `tools/geos_archive.py` — `--plan` / `--apply` / `--keep-last N` / `--max-bytes B` / `--tag-exclude T` / `--known-writers` / `--archive-dir` / `--registry-path` / `--plan-file`; exit `0` ok · `2` refused · `1` internal; **inert default** |
| `tests/test_spine_r2_wirein.py` | NEW gate, six legs verbatim from the ruling (tmp fixtures only) |

`tools/geos_archive.py` and `tools/geos_registry.py` were **not touched** (the ruling's fence: their API is
the oracle).

## Evidence (orchestrator's own runs)

**RED before the fix** — gate file absent: `/usr/bin/python3 -m pytest tests/test_spine_r2_wirein.py -q` →
`no tests ran in 0.06s`, **rc=4** (`output/spine_r2_gate_RED_module_absent.txt`).

**GREEN after** (`output/spine_r2_gate_green.txt`):

```
tests/test_spine_r2_wirein.py -q          6 passed in 0.35s          rc=0
tests/test_spine_r1_*.py -q              50 passed in 0.34s          rc=0
tools/geos_spine_verify.py               PASS — structure locked, pure core discriminating, stubs typed   rc=0
tests/test_gh26_*.py tests/test_obs1_mcp_transport_identity.py tests/test_defect20_write_identity.py -q
                                         48 passed in 13.52s         rc=0   (emit-path consumers, no regression)
```

**Non-vacuity (out-of-tree probe, `.builder_queue/probe_spine_r2_nonvacuity.sh`,
`output/spine_r2_nonvacuity_probe.txt`)** — the live module was mutated and restored byte-identical between
probes (`md5 52ab0bb1d9388077583209147647b7f8` before and after each):

| Probe | Gate result |
|---|---|
| baseline | 6 passed |
| A: drop `meta["unattributed"] = True` | **1 failed, 5 passed** — leg 1 goes RED |
| B: skip `reg.register(...)` | **2 failed, 4 passed** — legs 1–2 go RED |
| after byte-identical restore | 6 passed |

**CLI smoke (independent of the gate):** `--help` rc=0; `--apply --archive-dir <empty tmp> --registry-path
<tmp>` → prints `Default is inert: --apply with no policy flags evicts nothing.` and **rc=0**, no files
created.

**Scope check:** `git status --short` → exactly `M tools/geos_emit.py` plus the two new files
(`tools/geos_retain.py`, `tests/test_spine_r2_wirein.py` — force-added because `.gitignore`'s `test_*.py`
rule hides it). No core file (`tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`,
WGSL shaders) touched → no worktree isolation needed.

## Honest boundary — what this does NOT prove

1. **The append is not atomic or locked.** Two concurrent publishers can interleave writes to the registry
   file; the ring's own ruling explicitly left DEFECT-20's unlocked counter alone, and this work inherits that
   boundary. Not tested under concurrency.
2. **The default registry path is `/tmp/glyph_spine_index.jsonl`** — the implementer's parameter, not the
   ruling's. Every publish that does not set the constructor arg / `GEOS_REGISTRY_PATH` appends there; in a
   tmpfs wipe the index vanishes (the archives themselves do not).
3. **Refusal detection is registry-cross-reference + known-writer based**; a plan that evicts an archive whose
   registry line was never written (e.g. the append failed, `unattributed: true`) is NOT cross-referenced —
   the CLI cannot refuse what the index does not know.
4. **Torn-line / power-loss consistency is not tested** (the delegate names this too), and the registry stays
   append-only — no compaction or pruning is exercised.
5. **The six legs are the ruling's legs.** No leg asserts the retention *policy arithmetic* beyond
   keep-last/max-bytes as the CLI wires it (`tools/geos_archive.retention_plan` remains the tested core from
   SPINE-R1).
6. The `publish()` name-alias additions (`GeosEmitter.publish`, module-level `publish`) are the delegate's
   convenience additions; the pre-existing entry point `emit()` is unchanged, and no caller in the repo was
   re-pointed.

## Not verified this tick

- The canonical arc (leg A 52 files / leg B) was **not** run this tick: the changed file is only on the
  emit/publish path, and its three consumer suites (48 tests) plus the spine suites were run instead.
  Substitution stated plainly rather than implied.
- No WGSL/GPU leg, no QEMU lockstep, and no canvas read beyond `geos_surface_meta` (see the roadmap journal
  entry for this tick: machine still not stepping).
- DEFECT-22 (intermittent arc crash) is untouched by this change and remains open.
