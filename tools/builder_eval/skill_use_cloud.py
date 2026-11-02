#!/usr/bin/env python3
"""skill_use_cloud.py — control arm for skill_use_test.py: same prompt, cloud model.

If the STRONG model also fails the oracle, the test is flawed (bad prompt/data), not evidence
about the local model. If the strong model passes and the local one fails, that is a real
capability gradient on "use this skill to build".

Usage: python3 tools/builder_eval/skill_use_cloud.py --model deepseek-chat
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from skill_use_test import (EXPECTED, RESULTS, SKILL, TASK, canvas_excerpt, extract_code,
                            meta_text, run_code)


def env_key(name: str) -> str:
    for line in (pathlib.Path.home() / ".hermes" / ".env").read_text().splitlines():
        if line.strip().startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--arm", choices=["skill", "noskill", "both"], default="both")
    args = ap.parse_args()

    key = env_key("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not found in ~/.hermes/.env")

    canvas, meta = canvas_excerpt(), meta_text()
    skill_text = SKILL.read_text()

    for arm in (["skill", "noskill"] if args.arm == "both" else [args.arm]):
        prompt = TASK.format(canvas=canvas, meta=meta)
        if arm == "skill":
            prompt = ("You have the following engineering skill. Follow its rules exactly.\n\n"
                      "===== SKILL: glyph-teleoperation =====\n" + skill_text +
                      "\n===== END SKILL =====\n\n" + prompt)
        body = json.dumps({"model": args.model,
                           "messages": [{"role": "user", "content": prompt}],
                           "max_tokens": 900, "temperature": 0.2}).encode()
        req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
        wall = time.time() - t0
        out = d["choices"][0]["message"]["content"]
        code = extract_code(out)
        nums, detail = run_code(code)
        expected = [EXPECTED[(27, 17)], EXPECTED[(29, 17)], EXPECTED[(31, 24)]]
        rec = {"model": args.model, "arm": arm, "wall_s": round(wall, 1),
               "response_chars": len(out), "code_chars": len(code),
               "printed": nums, "expected": expected, "oracle_pass": nums == expected,
               "detail": detail, "provider": "deepseek-api", "at": time.time()}
        print(f"=== arm={arm} model={args.model} ===")
        print(json.dumps({k: rec[k] for k in ("printed", "expected", "oracle_pass", "detail", "wall_s")}, indent=2))
        if arm == "skill":
            print("--- first 400 chars of emitted code ---"); print(code[:400])
        with RESULTS.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    print(f"\n[recorded] {RESULTS}")


if __name__ == "__main__":
    sys.exit(main())
