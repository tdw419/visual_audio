#!/usr/bin/env python3
"""Re-encode the DEFECT-22 ticket as UTF-8 (ensure_ascii=False), keeping this tick's keys.

The update script wrote it with json.dumps' default ensure_ascii=True, which rewrote every
line carrying an em dash / arrow as \\uXXXX escapes: valid JSON, but it churned 45 unrelated
lines of a file the loop reads as a ledger. JSON semantics are unchanged (loads identically).
"""
import json
import pathlib

T = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio/.builder_queue"
                 "/DEFECT-22_arc_legA_instability.json")
d = json.loads(T.read_text())
T.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print(f"re-encoded {T} ({T.stat().st_size} B, {len(d)} keys, ensure_ascii=False)")
