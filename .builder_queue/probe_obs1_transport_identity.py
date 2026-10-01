#!/usr/bin/env python3
"""Orchestrator non-vacuity probe for OBS-1 (out-of-tree, does not touch the repo).

Spawns the REAL geo-obs server over stdio against a hand-made publish dir
(image + sidecar naming write_id 7 / writer "probe-writer"), then spawns a
NEUTERED COPY of the same server (write_id/writer forced to None). If the real
one reports 7 and the neutered one reports None, then the gate's L1 assertion
(write_id == expected, writer == expected, md5 == served file) is discriminating
and not vacuous.
"""
import asyncio, hashlib, json, os, shutil, sys, tempfile
from pathlib import Path

import numpy as np

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
SERVER = REPO / "tools" / "geos_observation_server.py"

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pub = Path(tempfile.mkdtemp(prefix="obs1_probe_pub_"))
np.save(pub / "kernel_memory.npy", np.zeros(16384, dtype=np.uint32))
(pub / "surface.meta.json").write_text(json.dumps(
    {"write_id": 7, "writer": "probe-writer", "written_at": "probe"}))
served_md5 = hashlib.md5((pub / "kernel_memory.npy").read_bytes()).hexdigest()

neutered = Path(tempfile.mkdtemp(prefix="obs1_probe_neutered_")) / "server.py"
src = SERVER.read_text()
assert 'source["write_id"] = sidecar_data.get("write_id")' in src, "probe: anchor line not found"
neutered.write_text(src
    .replace('source["write_id"] = sidecar_data.get("write_id")', 'source["write_id"] = None')
    .replace('source["writer"] = sidecar_data.get("writer")', 'source["writer"] = None'))


async def read_meta(server_path: Path):
    params = StdioServerParameters(
        command="/usr/bin/python3", args=[str(server_path)],
        env={"PATH": os.environ["PATH"], "GEOS_IMAGE_DIR": str(pub)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=30)
            res = await asyncio.wait_for(
                session.call_tool("geos_surface_meta", {"vx": 0, "vy": 0, "w": 80, "h": 25}),
                timeout=30)
            return json.loads(res.content[0].text)


real = asyncio.run(read_meta(SERVER))
fake = asyncio.run(read_meta(neutered))

rs, fs = real["source"], fake["source"]
print("REAL      :", json.dumps({k: rs[k] for k in ("write_id", "writer", "image_md5", "sidecar_file")}))
print("NEUTERED  :", json.dumps({k: fs[k] for k in ("write_id", "writer", "image_md5", "sidecar_file")}))
print("served md5:", served_md5)

ok = (rs["write_id"] == 7 and rs["writer"] == "probe-writer"
      and rs["image_md5"] == served_md5 and rs["sidecar_file"] == "surface.meta.json"
      and fs["write_id"] is None and fs["writer"] is None)
print("PROBE VERDICT:", "DISCRIMINATING (identity flows over the transport and the check would go red if it stopped)" if ok else "INCONCLUSIVE")
shutil.rmtree(pub, ignore_errors=True)
shutil.rmtree(neutered.parent, ignore_errors=True)
sys.exit(0 if ok else 1)
