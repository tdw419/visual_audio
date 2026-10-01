#!/usr/bin/env python3
"""local_scaffold_trial.py — can a LOCAL model close a real glyph-system gate WITH the scaffold?

Same question as the agy benchmark, asked of Ollama: give the model a task, run the gate,
feed the failure back, retry. One shot measured 578/578/688 (wrong curve variant); the open
question is whether feedback closes the gap, which is exactly what the scaffold bought agy.

Task: implement decode(x, y) -> word per the glyph-teleoperation skill's verified mapping.
Gate: decode(27,17)==750, decode(29,17)==754, decode(31,24)==703  (known ground truth)
"""
import argparse, json, pathlib, re, subprocess, sys, time

VECTORS = [(27, 17, 750), (29, 17, 754), (31, 24, 703)]
SKILL = pathlib.Path("/home/jericho/.hermes/skills").rglob("glyph-teleoperation/SKILL.md")

TASKS = {
    # task A: counter-prior convention (curve orientation) — measured 0/3
    "hilbert_decode": (
        """Implement a Python function:

    def decode(x: int, y: int) -> int:
        \"\"\"Return the memory word number for pixel (x, y) on the 128x128 surface.\"\"\"

Use the skill's VERIFIED mapping. Return ONLY a python code block.""",
        "print([decode(x, y) for x, y in [(27, 17), (29, 17), (31, 24)]])",
        lambda out: out == [750, 754, 703],
        [750, 754, 703],
    ),
    # task B: an unrelated counter-prior convention (channel order, not curve orientation)
    "bgr_pack": (
        """Implement a Python function:

    def pack_bgr(r: int, g: int, b: int) -> bytes:
        \"\"\"Pack one pixel as 3 bytes in the frame format used by the VAC24 substrate:
        blue channel first, then green, then red. Each channel is one byte.\"\"\"

Return ONLY a python code block.""",
        "print([list(pack_bgr(r, g, b)) for r, g, b in [(255, 0, 0), (0, 255, 0), (10, 20, 30)]])",
        lambda out: out == [[0, 0, 255], [0, 255, 0], [30, 20, 10]],
        [[0, 0, 255], [0, 255, 0], [30, 20, 10]],
    ),
}


def find_skill() -> str:
    for p in SKILL:
        return p.read_text()
    for base in (pathlib.Path.home() / ".hermes" / "skills", pathlib.Path("/home/jericho/zion")):
        for p in base.rglob("glyph-teleoperation/SKILL.md"):
            return p.read_text()
    return ""


def call(model: str, prompt: str, num_predict: int = 900) -> tuple[str, float, int]:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.2, "num_ctx": 32768, "num_predict": num_predict}})
    pf = pathlib.Path("/tmp/_local_scaffold_payload.json")
    pf.write_text(payload)
    t0 = time.time()
    out = subprocess.run(["curl", "-s", "--max-time", "900", "http://localhost:11434/api/generate",
                          "-H", "Content-Type: application/json", "--data-binary", "@" + str(pf)],
                         capture_output=True, text=True).stdout
    wall = time.time() - t0
    try:
        d = json.loads(out)
        return d.get("response", ""), wall, d.get("eval_count", 0)
    except Exception:
        return "", wall, 0


def extract_code(reply: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.S)
    return m.group(1) if m else reply


def check(code: str, probe: str, oracle):
    pathlib.Path("/tmp/_local_scaffold_candidate.py").write_text(
        code + "\n\nif __name__ == '__main__':\n    " + probe + "\n")
    r = subprocess.run([sys.executable, "/tmp/_local_scaffold_candidate.py"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return False, ("crashed: " + r.stderr.strip()[-300:]), None
    try:
        got = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return False, ("unparseable output: " + r.stdout.strip()[-200:]), None
    return bool(oracle(got)), "", got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-coder:30b")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--task", default="hilbert_decode", choices=sorted(TASKS))
    a = ap.parse_args()

    task_text, probe, oracle, want = TASKS[a.task]
    skill = find_skill()
    print(f"task={a.task}  skill loaded: {len(skill)} bytes")
    base = f"{skill}\n\n---\n\n{task_text}" if skill else task_text
    prompt, history = base, []
    for i in range(1, a.attempts + 1):
        reply, wall, toks = call(a.model, prompt)
        code = extract_code(reply)
        ok, err, got = check(code, probe, oracle)
        print(f"attempt {i}: {'PASS' if ok else 'FAIL'}  got={got} want={want}  "
              f"{wall:.1f}s {toks} tok")
        history.append({"task": a.task, "attempt": i, "pass": ok, "got": got,
                        "want": want, "wall_s": round(wall, 1)})
        if ok:
            pathlib.Path("/tmp/_local_scaffold_winner.py").write_text(code)
            break
        detail = err if err else f"expected {want}, got {got}"
        prompt = (base + f"\n\n---\n\nYour previous attempt produced this code:\n\n```python\n{code[:4000]}\n```\n\n"
                  f"The gate FAILED: {detail}\n\n"
                  "Fix it. Return ONLY the corrected code block.")
    out = pathlib.Path(f"/tmp/_local_scaffold_trial_{a.task}.json")
    out.write_text(json.dumps(history, indent=1))
    print("result:", "PASS" if any(h["pass"] for h in history) else "FAIL",
          f"({sum(h['pass'] for h in history)}/{len(history)} attempts)  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
