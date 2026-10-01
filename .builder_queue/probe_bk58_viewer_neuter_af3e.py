#!/usr/bin/env python3
"""Neuter launchClassFor in the TEMP-COPY viewer (RED leg for the checklist)."""
from pathlib import Path

p = Path("/tmp/bk58_checklist/tools/build_map_viewer.html")
src = p.read_text()
target = ('if (cell.type === "commit") return "glyphdbg";\n'
          '      if (["clean", "defect", "noise"].includes(cell.type))'
          ' return "ollama";\n      return null;')
neutered = src.replace(target, 'return null;')
assert neutered != src, "neuter replace failed - pattern not found"
p.write_text(neutered)
print("neutered copy written:", len(src), "->", len(neutered))
