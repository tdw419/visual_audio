# RECEIPT — OBS-1: MCP-transport write identity gate

Row: **OBS-1** in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (promoted `a48297b`, closed with this receipt)
Authority: `.builder_queue/RULING_lane_supply_20260912.md` § Ruled now (the lane-supply ruling at
`994d2dd` authorized exactly this one item when the self-hosting lane reported 0 open rows)
Landed: 2026-09-12 by builder cron `af3e62239ce2` (delegated to `agy` from
`.builder_queue/brief_obs1_mcp_transport_identity.md`; gate re-run, probes and receipt by the
orchestrator)

## The gap this closes

The DEFECT-20 write identity (`write_id` / `writer` / `image_md5`) was only ever exercised by
**importing the tool in-process** — `tests/test_defect20_write_identity.py:46` does
`from tools.geos_observation_server import geos_surface_meta`. Nothing drove the server the agent
actually talks to: the `geo-obs` MCP server over stdio (`tests/test_gh24_s2_mcp_server.py:21` records
"no stdio"). A regression in the tool boundary or in the served `source` block would have gone
unnoticed by every gate in the tree.

## Mechanism (new file, nothing else touched)

`tests/test_obs1_mcp_transport_identity.py` (422 lines) — spawns the committed server and speaks real
MCP to it:

```python
StdioServerParameters(command="/usr/bin/python3",
                      args=[str(REPO / "tools" / "geos_observation_server.py")],
                      env={"PATH": ..., "GEOS_IMAGE_DIR": str(pub)})
stdio_client(params) -> ClientSession(session) -> session.initialize() -> session.call_tool(...)
```

The temp publish dir is created with the landed fixture pattern from
`tests/test_defect20_write_identity.py:54-84` (`preemptive_kernel_image` + `build_default_atlas()` →
`GlyphRunner(...).drive(publish_dir=...)` → `*.meta.json` removed → `GeosEmitter(publish_dir, ack_file)`
publishes with an explicit `writer`). Because the child process gets `GEOS_IMAGE_DIR` in its own
environment, the transport — not the parent process's import state — decides what image is served.

## Legs and evidence

| Leg | Asserts | Evidence |
|---|---|---|
| L1 transport positive | `source.write_id == 1`, `writer == "obs1-stage-a"`, `image_md5` == md5 of the served `kernel_memory.npy`, non-null `sidecar_file`; `geos_read_surface` over the SAME session returns the ASCII canvas (not JSON, not `GEOS_OBSERVATION_UNAVAILABLE`) | PASSED |
| L2 monotonic over the transport | a second publish in the same session (`writer="obs1-stage-b"`) → `write_id == 2`, new writer, md5 moved to the new image and differs; `load_archived_write(1)`/`(2)` still retrieve both writes byte-distinguishable, word 750/754 values byte-exact | PASSED |
| L3 negative leg, loud | image with NO sidecar → `write_id`/`writer`/`sidecar_file`/`image_md5` all `None` (absence reported, not invented) **and** the real `tools.geos_witness.take_witness(750, expect_write_id=1, image_dir=<bare>)` raises the named `WitnessMismatch` whose message carries `WITNESS_MISMATCH`, the served `None` and the expected `1` | PASSED |
| L4 not vacuous | the L1 check helper passes on the real transport payload and RAISES on a synthetic payload with `write_id=None` and on a wrong `writer`; the L3 refusal helper raises on the real bare-dir witness and does NOT raise when the synthetic payload's `write_id` matches the expectation | PASSED |

Gate command (the row's clause):

```
/usr/bin/python3 -m pytest tests/test_obs1_mcp_transport_identity.py -q
```

- RED first — `output/obs1_gate_run1_red.txt`: `ERROR: file or directory not found:
  tests/test_obs1_mcp_transport_identity.py`, pytest **exit 4** (the artifact is the gate; absent
  module = red).
- GREEN — `output/obs1_gate_run2_green.txt`: 4 passed, **exit 0** (leg-by-leg `-vv`:
  `test_l1_transport_positive`, `test_l2_monotonic_over_transport`, `test_l3_negative_leg_loud`,
  `test_l4_not_vacuous_probes` — all PASSED, 2.58 s).
- Focused regression — `output/obs1_regression.txt`: DEFECT-20 write identity + GH-26 live surface +
  GH-24 S2 MCP server + OBS-1 = **18 passed / 0 failed, exit 0** (run under `/usr/bin/python3`, the one
  interpreter that has `mcp`).
- venv behaviour — `.venv/bin/python -m pytest tests/test_obs1_mcp_transport_identity.py -q` →
  **4 skipped, no error** (the module's `skipif` mirrors `tests/test_gh26_live_surface.py:115-116`), so
  an arc run on the wrong interpreter does not turn into a collection failure.

## Orchestrator non-vacuity probe (beyond the gate)

`.builder_queue/probe_obs1_transport_identity.py` → `output/obs1_orch_probe.txt`. Out-of-tree, never
touches the repo: a hand-made publish dir (image + sidecar naming `write_id 7` / `writer
"probe-writer"`) is read over stdio from (a) the committed server and (b) a copy of the same server with
the sidecar read neutered to `None`.

```
REAL      : {"write_id": 7, "writer": "probe-writer", "image_md5": "50ed0637…", "sidecar_file": "surface.meta.json"}
NEUTERED  : {"write_id": null, "writer": null, "image_md5": "50ed0637…", "sidecar_file": "surface.meta.json"}
PROBE VERDICT: DISCRIMINATING (identity flows over the transport and the check would go red if it stopped)
```

So L1's identity assertion is discriminating against the real mechanism, not merely against the
fixture's own belief. The repo tree was not modified by the probe.

## Honest boundaries (what this receipt does NOT claim)

- The gate runs **only** under `/usr/bin/python3` (py3.12, the interpreter that has `mcp`); on the repo
  `.venv` it is 4 skips. An arc green therefore does **not** cover this gate — that is the same
  interpreter split the lane-supply note already flagged, not something this gate removes.
- L4 discriminates the **check helpers** (WF-1 `L1b` style), not the server; the server-level
  falsification is the out-of-tree probe above, run by the orchestrator rather than by the gate.
- The gate drives the **emitter** publish path (`GeosEmitter`). The launcher publish path identity
  (DEFECT-20's second half, `runner.py::_publish()`) is not re-driven over the transport.
- `geos_read_surface`'s canvas assertion is a **liveness** check (text, not JSON, not the
  unavailable sentinel); it is not a canvas-content oracle.
- Not verified this tick: the full arc suite (only the focused 18-test set was run — no engine, baker,
  transpiler or shader file changed), GPU legs, and every `GLYPH_OSS_ROADMAP.md` item (out of this
  lane's scope by that file's own house rule).
