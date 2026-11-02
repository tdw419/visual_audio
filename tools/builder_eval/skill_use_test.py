#!/usr/bin/env python3
"""skill_use_test.py — can a LOCAL model use the glyph-teleoperation skill to build?

Experiment design (bounded, oracle-checked, two arms):

  Arm A (skill)  : local model + SKILL.md + a real canvas read + real meta  -> decode markers, emit code
  Arm B (ablation): local model + the same data, NO skill                   -> same task

ORACLE (the only judge): the emitted function must reproduce the skill's verified mapping
    xy2d(128, x, y) identity orientation:   '>' (27,17) -> 750 · '@' (29,17) -> 754 · 'X' (31,24) -> 703
Grading is mechanical: run the model's code, compare the three words. A plausible-looking
essay scores zero; only the numbers count.

Why this shape: "can it build with the skill" is unanswerable from prose. This reduces it to a
machine-checkable artifact whose ground truth already exists in the repo (the skill's verified
mapping, measured 2026-09-11). It is the same falsifiability discipline as the builder benchmark.

Usage:
  python3 tools/builder_eval/skill_use_test.py --model qwen3-coder:30b
  python3 tools/builder_eval/skill_use_test.py --model qwen2.5-coder:14b --arm skill
Results append to tools/builder_eval/skill_use_results.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for p in (str(_REPO), str(_REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

SKILL = Path.home() / ".hermes" / "skills" / "geometry-os" / "glyph-teleoperation" / "SKILL.md"
RESULTS = _HERE / "skill_use_results.jsonl"
OLLAMA = "http://localhost:11434/api/generate"

EXPECTED = {(27, 17): 750, (29, 17): 754, (31, 24): 703}   # '>' argv, '@' result, 'X' exit

TASK = """You are working on the Glyph spatial OS substrate. A real snapshot has been read for you.

CANVAS (fixed-stride, Hilbert-mapped N=128, rows are y, columns are x):
{canvas}

SNAPSHOT META (from geos_surface_meta / the backing .npy):
{meta}

TASK: write ONE Python function `decode(x: int, y: int) -> int` that returns the MEMORY WORD
number for a canvas pixel (x, y), plus a `__main__` block that prints the words for the three
KNOWN MARKERS: (27, 17), (29, 17), (31, 24) — one integer per line, in that order.

Output ONLY a python code block. No prose, no explanation, no markdown outside the block.
"""


def canvas_excerpt() -> str:
    """A small real viewport around the three named markers."""
    from geos_observation_server import geos_read_surface
    return geos_read_surface(20, 12, 16, 16)


def meta_text() -> str:
    from geos_observation_server import geos_surface_meta
    return geos_surface_meta()[:1200]


def ollama(model: str, prompt: str, num_predict: int = 700) -> tuple[str, dict]:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_ctx": 32768, "num_predict": num_predict, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read().decode())
    return d.get("response", ""), d


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def run_code(code: str) -> tuple[list[int], str]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "candidate.py"
        f.write_text(code)
        try:
            p = subprocess.run(["/usr/bin/python3", str(f)], capture_output=True,
                               text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return [], "TIMEOUT"
        if p.returncode != 0:
            return [], f"exit {p.returncode}: {p.stderr.strip()[:200]}"
        nums = []
        for line in p.stdout.splitlines():
            line = line.strip()
            if re.fullmatch(r"-?\d+", line):
                nums.append(int(line))
        return nums, p.stdout.strip()[:200]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--arm", choices=["skill", "noskill", "both"], default="both")
    args = ap.parse_args()

    canvas = canvas_excerpt()
    meta = meta_text()
    skill_text = SKILL.read_text() if SKILL.exists() else ""
    if not skill_text:
        raise SystemExit(f"skill not found: {SKILL}")

    for arm in (["skill", "noskill"] if args.arm == "both" else [args.arm]):
        prompt = TASK.format(canvas=canvas, meta=meta)
        if arm == "skill":
            prompt = ("You have the following engineering skill. Follow its rules exactly.\n\n"
                      "===== SKILL: glyph-teleoperation =====\n" + skill_text +
                      "\n===== END SKILL =====\n\n" + prompt)
        print(f"\n=== arm={arm} model={args.model} (canvas {len(canvas)} chars, skill {len(skill_text)} chars) ===")
        t0 = time.time()
        out, raw = ollama(args.model, prompt)
        wall = time.time() - t0
        code = extract_code(out)
        nums, detail = run_code(code)
        expected = [EXPECTED[(27, 17)], EXPECTED[(29, 17)], EXPECTED[(31, 24)]]
        ok = nums == expected
        rec = {
            "model": args.model, "arm": arm, "wall_s": round(wall, 1),
            "response_chars": len(out), "code_chars": len(code),
            "printed": nums, "expected": expected, "oracle_pass": ok, "detail": detail,
            "eval_count": raw.get("eval_count"), "eval_tps": round(
                (raw.get("eval_count") or 0) / max((raw.get("eval_duration") or 1) / 1e9, 1e-9), 1),
            "at": time.time(),
        }
        print(json.dumps({k: rec[k] for k in ("printed", "expected", "oracle_pass", "detail",
                                              "eval_tps", "wall_s")}, indent=2))
        if arm == "skill":
            print("--- first 600 chars of the emitted code ---")
            print(code[:600])
        with RESULTS.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    print(f"\n[recorded] {RESULTS}")


if __name__ == "__main__":
    sys.exit(main())
