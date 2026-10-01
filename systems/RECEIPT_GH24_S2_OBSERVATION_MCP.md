# RECEIPT: GH-24 S2 — geos_read_surface MCP Server

**Date:** 2026-09-10
**Branch:** glyph-transpiler-autoloop
**Roadmap row:** GH-24 Spatial Observation Bridge, stage S2

## What landed

| File | Role |
|---|---|
| `tools/geos_observation_server.py` | MCP stdio server (`geo-obs`): `geos_read_surface(vx,vy,w,h)` raw canvas tool + `geos_surface_meta` JSON sidecar tool |
| `tests/test_gh24_s2_mcp_server.py` | Gate: 5 legs |
| `~/.hermes/config.yaml` | `mcp_servers.geo-obs` registered (`/usr/bin/python3`, timeout 60, enabled) |

## Design decisions

1. **State source = newest committed kernel memory image on disk.** The
   server reads `GEOS_IMAGE_DIR/kernel_memory.npy` (exact name preferred)
   or the newest `*.npy` by mtime. This satisfies the monitoring
   invariant by construction: a file on disk is a committed tick boundary
   — no live process, no mid-task speculative registers, zero GPU.
   Snapshots are produced by whoever runs the kernel (test harness or
   future runner hook) via `np.save(mem)`; the server is a pure reader.
2. **Dual-artifact rule enforced at the protocol layer.**
   `geos_read_surface` returns the fixed-stride string directly — it is
   never JSON-wrapped, so 2D Hilbert adjacency survives for attention.
   `geos_surface_meta` is the only JSON surface (boxes + tick + source).
3. **Interpreter pin: `/usr/bin/python3` (3.12).** The `mcp` package
   (2.0.0, FastMCP) lives in `~/.local/lib/python3.12/site-packages`,
   NOT in the hermes-agent venv (3.11) and not importable by the bare
   `python3` on PATH in cron context (which resolves to the hermes venv).
   Same interpreter pattern as the rag/wiki MCP servers (shebang `env
   python3` under the user session resolves to 3.12; cron context does
   not, hence the absolute path).
4. **Viewport clamping** — out-of-range `(vx,vy,w,h)` clamps to the
   N×N canvas; a fully off-canvas request returns an all-dot view rather
   than raising. Missing image state returns
   `GEOS_OBSERVATION_UNAVAILABLE` (canvas tool) or `{"error": ...}`
   (sidecar), never an exception.

## Gate legs (tests/test_gh24_s2_mcp_server.py — 5/5)

1. Raw canvas never JSON-wrapped, fixed-stride (25×80), byte-exact vs
   `tools/geos_ascii_bridge.project` on identical memory.
2. Sidecar legend matches landed ABI (BOX2 rect (736,767), TABLE
   (1568,1583)), per-box lit-word counts correct, `source` provenance
   included.
3. Newest `*.npy` by mtime wins when no exact-name file exists.
4. Missing state degrades cleanly (`GEOS_OBSERVATION_UNAVAILABLE`).
5. Out-of-range viewports clamp; no exceptions.

## End-to-end stdio verification (the real transport)

`/tmp/geos_stdio_gate.py` drove the server over stdio exactly as Hermes
will (initialize → tools/list → tools/call × 2):

```
initialize OK: geo-obs
tools: ['geos_read_surface', 'geos_surface_meta']
geos_read_surface: byte-exact vs projector, 25x80 fixed stride
geos_surface_meta: sidecar OK, BOX2=2 lit words, TABLE=1, source age 0.3 s
STDIO GATE PASS
```

## Regression

- `tests/test_gh24_s2_mcp_server.py` + `tests/test_gh24_ascii_bridge.py`:
  11/11 pass.
- Full arc GH-15→GH-24 at pre-S2 HEAD (6702299): **109 passed / 0 failed**
  (59s). S2 adds host-side tooling only — no kernel/engine/image changes,
  arc count unchanged (109 = the arc's full test population; the
  roadmap's earlier 179/209 counts include GH-1..14 suites).

## Notes for downstream (S3)

- `geos_emit` stays HUMAN-GATED per roadmap; this server is read-only.
- Snapshot production: any runner session can publish observability by
  writing `kernel_memory.npy` to `GEOS_IMAGE_DIR` (default
  `/tmp/geos_observation`) after a tick boundary. Consider adding this
  to `run_gate_gh18.sh` or the cron harness so live canvases accumulate.
- New Hermes sessions pick up `geo-obs` on next gateway/config reload;
  the server is safe to start with no image present.
