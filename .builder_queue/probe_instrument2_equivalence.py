"""Corpus-wide equivalence check: HEAD classifier vs the fixed classifier.

Compares the closed/open sets over the live roadmap AND the frozen snapshot.
Expectation: the live corpus is UNCHANGED (the guard only refuses a citation
shape that no live cell currently contains, because commit 3356436 removed it);
the frozen snapshot stays 0 open. Prints any row that changed classification.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
HEAD_SRC = subprocess.run(["git", "show", "HEAD:tools/supply_census.py"],
                          capture_output=True, text=True, cwd=str(REPO), check=True).stdout

sys.path.insert(0, str(REPO))
import importlib.util


def load(tag: str, source: str):
    spec = importlib.util.spec_from_loader(tag, loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__dict__["__file__"] = str(REPO / "tools" / "supply_census.py")
    exec(compile(source, f"<{tag}>", "exec"), mod.__dict__)
    return mod


head = load("head_sc", HEAD_SRC)
new = load("new_sc", (REPO / "tools" / "supply_census.py").read_text(encoding="utf-8"))

targets = [
    "systems/GLYPH_SELF_HOSTING_ROADMAP.md",
    "tests/fixtures/roadmap_snapshot_a697a4e.md",
]
for rel in targets:
    p = str(REPO / rel)
    h, n = head.census(p), new.census(p)
    print(f"== {rel}")
    print(f"   HEAD: total={h['total']} open={h['open']}")
    print(f"   NEW : total={n['total']} open={n['open']}")
    flipped = (set(h["open"]) ^ set(n["open"])) | (set(h["closed"]) ^ set(n["closed"]))
    print(f"   flips: {sorted(flipped) if flipped else 'none'}")
