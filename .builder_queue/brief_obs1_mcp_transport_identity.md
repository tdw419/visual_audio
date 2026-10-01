# Brief — OBS-1: MCP-transport write-identity gate

Repo: `/home/jericho/projects/zion/projects/visual_audio` (branch `glyph-transpiler-autoloop`).
Roadmap row: **OBS-1** in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (line 334, promoted at `a48297b`).

## Deliverable (one new file)

`tests/test_obs1_mcp_transport_identity.py` — a dedicated gate. **Create no other file and modify no
existing file.** In particular do NOT edit `tools/geos_observation_server.py`, `tools/geos_emit.py`,
`tools/geos_witness.py`, any engine/baker/transpiler file, or any roadmap doc. If you believe one of
those needs a change, STOP and report instead (see "Hard stop" below).

Do **not** run `git add`/`git commit` — the orchestrator commits.

## Why this gate exists

`tests/test_defect20_write_identity.py` exercises the DEFECT-20 write identity by importing
`geos_surface_meta` **in-process**. The transport the agent actually uses — the `geo-obs` MCP server
over stdio — has no gate (`tests/test_gh24_s2_mcp_server.py:21` records "no stdio"). So a regression in
the tool boundary or `_get_source_info` served over the real transport would go unnoticed.

## Gate command (this is the gate; it must pass)

```
/usr/bin/python3 -m pytest tests/test_obs1_mcp_transport_identity.py -q
/usr/bin/python3 -m pytest tests/test_obs1_mcp_transport_identity.py -v     # leg-by-leg evidence
```

Interpreter trap: `mcp` is installed for `/usr/bin/python3` (py3.12) only. The repo `.venv/bin/python`
cannot import it. So:
- import the MCP client lazily and guard the module with
  `pytest.mark.skipif(not _mcp_available(), reason="mcp unavailable (run under py3.12)")`, mirroring
  `tests/test_gh26_live_surface.py:115-116` — the venv arc run must not error;
- the four legs must report **PASSED** (not skipped) under `/usr/bin/python3`, and your reported
  evidence must be the `-v` run that shows them executing.

## Transport mechanics (the real transport, not an import)

Spawn the committed server exactly as a client would and speak MCP to it over **stdio**:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command="/usr/bin/python3",
    args=[str(REPO / "tools" / "geos_observation_server.py")],
    env={"PATH": os.environ["PATH"], "GEOS_IMAGE_DIR": str(pub)},   # pub = the publish dir
)
async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("geos_surface_meta", {"vx": 0, "vy": 0, "w": 80, "h": 25})
```

Run the async client from a sync test with `asyncio.run(...)`. The tool returns text content: parse
`result.content[0].text` as JSON. Assert `list_tools()` contains `geos_surface_meta` so a dead or
mis-arg'd server cannot pass vacuously, and give the subprocess a real timeout (e.g. 60 s) so a hang
is a loud failure, not an infinite test.

Note: the server reads `GEOS_IMAGE_DIR` from its own environment (`tools/geos_observation_server.py:36`
and `:72`), so the env above is what points the transport at your temp publish dir — do not set the
parent process's env and hope.

## Fixture (reuse the landed pattern — do not reinvent it)

Copy the setup shape from `tests/test_defect20_write_identity.py:54-84`:

- `_bake(tmp)`: `preemptive_kernel_image(build_default_atlas(), timer_quantum=20, out_path=tmp/"gh26.glyph.npy")`
- `_publish_dir(tmp)`: `GlyphRunner(img, ram_words=16384).drive(publish_dir=pub, max_instructions=60000)`,
  assert `receipt["halted"] and not receipt["faulted"]`, then delete `pub/*.meta.json` so the emitter's
  write_id counter starts at 1.
- `_acked(tmp)`: `tmp/".geos_emit_ack"` containing `ACK_SENTINEL` (the human gate satisfied on disk).
- Publishes: `GeosEmitter(publish_dir=pub, ack_file=ack)` with `writer=...` passed through the intent
  (see `tools/geos_emit.py:104-112,227`; the intent's optional `"writer"` field is the identity fact).

## Legs

- **L1 — transport positive.** Emitter publish #1 with `writer="obs1-stage-a"`. Over stdio,
  `geos_surface_meta` must report `source["write_id"] == 1`, `source["writer"] == "obs1-stage-a"`,
  `source["image_md5"] == hashlib.md5((pub/"kernel_memory.npy").read_bytes()).hexdigest()`, and a
  non-null `source["sidecar_file"]`. Also call `geos_read_surface` once over the same session and
  assert it returns the ASCII canvas text (not an error string, not JSON) — the identity-surfacing tool
  and the canvas tool must both work through the transport.
- **L2 — monotonic over the transport.** In the same session, publish #2 with a different writer; the
  next `geos_surface_meta` must report `write_id == 2` and the new writer, with `image_md5` equal to the
  md5 of the newly served `.npy` (the transport must not serve a stale identity). Optionally also assert
  `geos_witness.load_archived_write(1)` still retrieves stage-a's bytes — the earlier write stays
  retrievable.
- **L3 — negative leg, loud.** Point a second server session's `GEOS_IMAGE_DIR` at a directory holding an
  image and **no sidecar**. Assert (a) `source["write_id"] is None` and `source["writer"] is None` — the
  transport reports the absence rather than inventing an identity — and (b) an identity-demanding read
  refuses loudly: a subprocess (or in-process) call to
  `tools/geos_witness.take_witness(750, expect_write_id=1, image_dir=<bare dir>)` raises the named
  `WitnessMismatch`. The assertion must be on the *named* exception type and its message, so a different
  failure (e.g. `RuntimeError: Cannot take witness`) does not satisfy the leg.
- **L4 — the gate is not vacuous.** In-gate discriminating probes, documented as such:
  (a) run the L1 identity check as a helper over the *real* transport payload → passes, then over a
  synthetic payload with `write_id=None` → the helper must raise, proving the check discriminates;
  (b) same for L3: the refusal helper must raise on the real bare-dir witness and must NOT raise on a
  synthetic payload whose `write_id` equals the expectation. Do not monkeypatch the server; probe the
  checks themselves (this mirrors the WF-1 `L1b` style probe).

## Hard stop

If the transport genuinely does not surface the identity, or any leg fails for a reason inside
`tools/` — **STOP, change nothing in `tools/`, and report exactly what you measured** (command, output,
file:line). A real defect is a finding, not something to fix in this brief. Two delegation attempts are
the budget for this row; a wrong guess costs more than a clean stop.

## Report back

1. Files changed (exact paths) — expected: exactly one new test file.
2. The verbatim `-v` gate output showing L1..L4 PASSED (last ~20 lines are enough).
3. Anything you did NOT verify.
