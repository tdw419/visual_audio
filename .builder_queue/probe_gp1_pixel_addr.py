#!/usr/bin/env python3
"""Add pixel_addr to effects.json for captures verified against the container."""
import json
import subprocess
import sys

for cap, gpath in [("cap1", "/var/tmp/gp1/data.bin.gz"),
                   ("cap4", "/var/tmp/gp1/dance.final")]:
    r = subprocess.run(["/usr/bin/python3",
                        "tools/pixel_container/locate_in_container.py",
                        "locate", gpath], capture_output=True, text=True)
    if r.returncode != 0:
        print(cap, "locate FAIL", r.stderr[-200:])
        sys.exit(1)
    loc = json.loads(r.stdout)
    p = f"corpus_build/{cap}/effects.json"
    e = json.load(open(p))
    e["effects"][0]["pixel_addr"] = {"frames": loc.get("frames"),
                                     "extents": loc.get("extents")}
    open(p, "w").write(json.dumps(e, indent=2) + "\n")
    print(cap, "pixel_addr added: frames", loc.get("frames"))
