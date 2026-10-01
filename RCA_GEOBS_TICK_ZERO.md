# RCA — "tick=0, machine not stepping" was a TOOL bug; the phantom "0→1 advance" was two sources

**Filed:** 2026-09-18 ~06:2x CDT · **Fixed by:** host session ("you lead" delegation,
standing defect-fix grant) · **Gate:** `tests/test_gh24_s2_mcp_server.py` 6 legs green
(12/12 with bridge tests)

## Symptom

Every supply addendum for weeks recorded the substrate as
"tick=0, machine not stepping" via the `geos_surface_meta` MCP tool.
Addendum 280 (2026-09-18 03:27) then recorded tick **0 → 1** while image
bytes, write_id, and mtimes were all frozen — flagged as "consistent with
an annotated tick, not measured execution" and left unresolved.

## Root cause (measured, not inferred)

`tools/geos_observation_server.py` served `tick` from
`project_metadata(memory, ...)` **without a `tick=` argument**, so the MCP
tool returned the bridge's hardcoded default (`tick: int = 0`,
`tools/geos_ascii_bridge.py:96`) on every call, forever, regardless of
machine state.

Meanwhile the REAL tick state has always had two legitimate sources:

1. **Machine counter** — word 732 of `kernel_memory.npy` (currently 0;
   the machine has genuinely never stepped).
2. **Sidecar stamp** — `tools/geos_emit.py:152` writes
   `tick = int(mem[732]) + 1` into `surface.meta.json` at write time
   (currently 1: the emitter stamped "this write lands as tick 1").

Addendum 280's "advance" compared these two different sources across two
different reads (addendum 279 read the tool's hardcoded 0; addendum 280
read the sidecar's emitter-stamped 1). No tick ever advanced. No machine
behavior anomaly exists — but every historical "tick=0" reading through
the tool was tool output, not machine state.

## Fix

`tools/geos_observation_server.py` (`geos_surface_meta`):

- `tick` now comes from **word 732 of the loaded image** — the same word
  the emitter reads — masked to u32, 0-safe for short memories.
- New `source.sidecar_tick` field (always present, `null` when no
  sidecar) carries the sidecar's write-time stamp for provenance.

Before the fix, `tick=1, machine stepped` could never be expressed by
this tool; now `tick` and `sidecar_tick` are distinguishable facts.

## Verification

- New gate leg `test_s2_tick_from_machine_counter_word732`:
  machine tick served from word 732 (value 5 fixture); sidecar
  provenance carried when present, `null` when absent; short memory
  degrades to 0 without raising. RED on pre-fix code (served 0).
- Full file gates: `tests/test_gh24_s2_mcp_server.py` +
  `tests/test_gh24_ascii_bridge.py` = 12 passed.
- Live channel (post watchdog respawn, pids 654214→…, 774998→…):
  `tick(tool now): 0 | sidecar_tick: 1 | write_id: 73 | image_md5: 3744eaa7…`
  — i.e. the honest state: machine not stepped, sidecar stamp preserved.

## Blast radius / consumer audit

`project_metadata` call sites: `geos_observation_server.py:150` (fixed),
`geos_ascii_bridge.project_surface` (already passes tick through),
`tools/gh26_glass_box_scenario.py` (passes tick explicitly; untouched).
No other consumers of the tool's `tick` field were found in-repo.

## Consequences for the record

- **Sentinel RED and "machine not stepping" both stand** — this RCA
  changes the *provenance* of the tick readings, not the machine-state
  conclusion. Word 732 = 0 was, and remains, the true state.
- Historical addenda that cited "tick=0" via this tool cited tool output;
  their other measurements (md5, write_id, word decodes) are unaffected.
- The addendum-280 "channel/view mismatch" flag is RESOLVED by this RCA;
  no unknown mechanism remains.
