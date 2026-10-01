#!/usr/bin/env python3
"""Backfill write_id 71 into the spine registry (repair of the transient
unattributed flag on the 2026-09-17 SE021 maildrop re-emit).

Sole action: register the ArchiveRecord described by the EXISTING sidecar
(/tmp/geos_observation/surface.meta.json) into WriteRegistry. No image bytes
are read or written; the sidecar is read-only input. Refuses if write_id 71
is already present (idempotent) or if the sidecar identity is missing.
"""
import json
import sys
from pathlib import Path

SIDECAR = Path("/tmp/geos_observation/surface.meta.json")
IMAGE = Path("/tmp/geos_observation/kernel_memory.npy")
REG = Path("/tmp/glyph_spine_index.jsonl")

meta = json.loads(SIDECAR.read_text())
if meta.get("write_id") != 71:
    sys.exit(f"REFUSE: sidecar write_id is {meta.get('write_id')!r}, expected 71")

if '"write_id": 71' in REG.read_text() or '"write_id":71' in REG.read_text():
    sys.exit("REFUSE: write_id 71 already present in registry")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.geos_archive import ArchiveRecord  # noqa: E402
from tools.geos_registry import WriteRegistry  # noqa: E402

rec = ArchiveRecord(
    write_id=meta["write_id"],
    writer=meta["writer"],
    image_path=str(IMAGE),
    sidecar_path=str(SIDECAR),
    bytes_len=meta["bytes_len"],
    written_at=meta["written_at"],
)
reg = WriteRegistry(index_path=str(REG))
reg.register(rec, origin_id=str(IMAGE.parent))
print(f"OK: write_id 71 registered, writer={meta['writer']}, bytes_len={meta['bytes_len']}")
