#!/usr/bin/env python3
"""BK-102 R1-wiring live-model efficacy probe (af3e lane, 2026-10-03 tick).

Question (from 23:0x receipt's honesty gap): SYSTEM_RULES lists only 7 color
words as RGB hints, but CSS-148 has 148 entries. Does the whitelisted 'color'
verb actually WORK live for table words the prompt does NOT name?

Method: run tools/map_intent.translate_free_text (LIVE ollama qwen2.5-coder:7b,
temp 0, format=json — the tool's own settings, unchanged) over a battery:
  - LISTED (control): words the prompt names (blue, red, green, purple, yellow, cyan, orange)
  - UNLISTED-COMMON: common table words NOT named in the prompt
  - UNLISTED-RARE: rare table words NOT named in the prompt
  - UNKNOWN: words not in CSS-148 (must yield stage=color error)
  - COMPOUND: multiword table entries ('light blue' style spacing)
Contract per leg:
  known word  -> ok=True, verb in COLOR_VERBS, args[1:4] == CSS-148 canonical RGB
  unknown word-> ok=False, stage == 'color'
No IPC execution (dry-run semantics only); no engine contact.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.map_intent import translate_free_text, OLLAMA_MODEL
from tools.named_colors import NAMED_COLORS

LISTED = ["blue", "red", "green", "purple", "yellow", "cyan", "orange"]
UNLISTED_COMMON = ["pink", "brown", "gray", "white", "black", "teal", "navy",
                   "gold", "silver", "magenta", "violet", "coral", "lime",
                   "maroon", "olive", "indigo", "beige", "tan", "salmon", "plum"]
UNLISTED_RARE = ["chartreuse", "firebrick", "thistle", "peru", "linen",
                 "orchid", "sienna", "tomato", "khaki", "ivory"]
UNKNOWN = ["cerulean", "ocean", "aquamarinelike", "blurple"]
COMPOUND = ["light blue", "dark green", "hot pink"]

def fmt_rgb(t):
    return [f"{c:.10g}" for c in t[:3]]

def probe(word):
    text = f"make node n1 {word}"
    r = translate_free_text(text)
    return text, r

def check(word, r, known):
    """Returns (verdict, detail)."""
    if not known:
        if r.get("ok") is False and r.get("stage") == "color":
            return "PASS", ""
        return "FAIL", f"expected stage=color refusal, got {json.dumps(r)[:140]}"
    if not r.get("ok"):
        return "FAIL", f"refused: {json.dumps(r)[:140]}"
    if r.get("verb") not in ("color", "clustercolor"):
        return "FAIL", f"verb={r.get('verb')!r}"
    want = fmt_rgb(NAMED_COLORS[word.replace(' ', '')] if ' ' in word
                   else NAMED_COLORS[word])
    got = [str(a) for a in r["args"][1:4]]
    if got != want:
        return "FAIL", f"RGB {got} != canonical {want}"
    return "PASS", ""

def main():
    print(f"model={OLLAMA_MODEL} temp=0 format=json (tool defaults, unchanged)")
    groups = [
        ("LISTED-control", LISTED, True),
        ("UNLISTED-common", UNLISTED_COMMON, True),
        ("UNLISTED-rare", UNLISTED_RARE, True),
        ("UNKNOWN", UNKNOWN, False),
        ("COMPOUND", COMPOUND, True),
    ]
    total = passed = 0
    for name, words, known in groups:
        print(f"\n== {name} ==")
        for w in words:
            text, r = probe(w)
            verdict, detail = check(w, r, known)
            total += 1
            passed += verdict == "PASS"
            got = r.get("args", r.get("error"))
            print(f"  {verdict:4} {w!r:20} verb={r.get('verb','-'):12} "
                  f"stage={r.get('stage','-'):8} args={got}"
                  + (f"  <- {detail}" if detail else ""))
    print(f"\nSUMMARY: {passed}/{total} PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
