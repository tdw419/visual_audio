"""Attribute the SUITE-COLLECT-1 sweep delta file-by-file against the previous landing sweep."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load(p):
    recs = {}
    for line in (REPO / p).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            recs[Path(r["path"]).name] = r
    return recs


old = load("output/SUITE_FIX1_FINAL_SINK.jsonl")
new = load("output/SUITE_COLLECT1_FINAL_SINK.jsonl")
print(f"old files={len(old)} new files={len(new)}")
print(f"old collected={sum(r['counts']['collected'] for r in old.values())}")
print(f"new collected={sum(r['counts']['collected'] for r in new.values())}")

changed = []
for name in sorted(set(old) | set(new)):
    a = old.get(name, {})
    b = new.get(name, {})
    if a.get("verdict") != b.get("verdict") or a.get("counts", {}).get("collected") != b.get(
        "counts", {}
    ).get("collected"):
        changed.append((name, a.get("verdict"), b.get("verdict"), a.get("counts"), b.get("counts")))

print(f"\n--- changed ({len(changed)}) ---")
for name, va, vb, ca, cb in changed:
    print(f"{name:<52} {str(va):<12} -> {str(vb):<12} coll {ca} -> {cb}")

print("\n--- TIMEOUT/OOM/COLLECT-HANG records (new) ---")
for name, r in sorted(new.items()):
    if r["verdict"] in ("TIMEOUT", "OOM", "COLLECT-HANG", "SKIPPED"):
        print(f"{name:<52} {r['verdict']:<12} dur={r['duration_s']:.0f} coll={r['counts']['collected']}")
