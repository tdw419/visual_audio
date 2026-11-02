#!/usr/bin/env python3
"""Re-run the failing class legs for receipt reproducibility (af3e, 2026-10-03)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.map_intent import translate_free_text

WORDS = ["light blue", "hot pink", "dark green", "gray", "ocean",
         "yellow", "orange", "chartreuse", "tomato", "blurple"]
for w in WORDS:
    r = translate_free_text(f"make node n1 {w}")
    print(w, "->", json.dumps({k: r.get(k) for k in ("ok", "verb", "args", "error", "stage")}))
