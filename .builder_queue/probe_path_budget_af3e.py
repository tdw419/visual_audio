# probe_path_budget_af3e.py — Phase-1c research probe: where does the L1
# FS-window path budget actually bind? (rule-6: measured numbers only)
import os
import sys

sys.path.insert(0, "experiments")
from glyph_interactive_shell import build_dispatch_shell  # noqa: E402

results = []
for base in ["/tmp", "/tmp/glyph_wb_c22b", "/tmp/glyph_workbench_root_longname",
             "/var/tmp", "/home/jericho/projects/zion/projects/visual_audio"]:
    root = os.path.join(base, "x")
    w = os.path.join(root, "w.dat")
    a = os.path.join(root, "out.wav")
    try:
        img, layout = build_dispatch_shell(write_path=w, audio_path=a, return_layout=True)
        results.append((base, len(w), "OK", layout["path_cap"]))
    except AssertionError as e:
        results.append((base, len(w), "ASSERT", str(e)[:70]))
    except Exception as e:  # noqa: BLE001
        results.append((base, len(w), type(e).__name__, str(e)[:70]))

for base, n, status, detail in results:
    print(f"{base!r:55s} len(path)={n:3d}  {status}  {detail}")
