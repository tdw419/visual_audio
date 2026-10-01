#!/usr/bin/env python3
"""Draft ONE .glyph tile locally; the machine oracle is the judge.

in : routine spec + >=2 verification points (seed -> expected r10)
out: accepted tile + receipt JSON, or exit 3 with the per-draw reject reasons.
"""
import argparse, hashlib, json, os, random, subprocess, sys, time, urllib.request

sys.path.insert(0, "tools")
sys.path.insert(0, "tools/glyph_gpt")
from atlas import run_generated

OLLAMA = "http://localhost:11434/api/generate"
ISA = """Glyph tile text format (one instruction per line):
  :label
  LDI rN <imm> = load an immediate (decimal or 0x) into rN | ADD rD rS = rD += rS
  SUB rD rS = rD -= rS | RET = end the tile
Registers are r0..r31. r10 holds the input value. Emit ONLY the tile text, no fences, no prose."""

# Measured 2026-09-12: a SHARED shift denial fixed SHL (1/6 -> 5/6) but left SHR at 0/6,
# because the two ops have different bugs — SHL's is a repeat-prior (SHL rD rD x N to
# fake a multi-bit shift), SHR's is value-as-count (SHR r10 r10, shifting a register by
# its own current value). Naming each op's specific pattern reached 24/24 (100%,
# tools/builder_eval/ollama_tile_sample_shrdenial.json, coincidence-checked two
# independent ways). Keep both denials explicit rather than relying on the model
# generalizing one op's fix to the other.
SHIFT_RULE = """
SHL rD rCount shifts rD left by the amount in rCount, in ONE operation. rCount MUST be
a register loaded via LDI to hold the shift amount K, DIFFERENT from rD. NEVER write
`SHL rD rD`. NEVER repeat SHL to simulate a multi-bit shift.
SHR rD rCount shifts rD right by the amount in rCount, in ONE operation. rCount MUST be
a register loaded via LDI to hold the shift amount K, DIFFERENT from rD. NEVER write
`SHR rD rD` (shifting a register by its own current value is always wrong). NEVER
repeat SHR to simulate a multi-bit shift."""


def oracle(tile_text, seed_val):
    r = run_generated(f"LDI r10 {seed_val}\n" + tile_text)
    rf = r.get("registers_full") or []
    ran = bool(r.get("halted")) and not r.get("faulted")
    if len(rf) > 10:
        return ran, rf[10], r.get("error")
    if ran:
        raise ValueError("executed but receipt carries no r10")
    return False, None, r.get("error")


def extract(text):
    import re
    m = re.search(r"```[a-z]*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def ask(model, prompt, temperature, max_tokens=512):
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": temperature, "num_predict": max_tokens}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        d = json.loads(resp.read().decode())
    return d.get("response", ""), d.get("eval_count", 0), time.time() - t0


def judge(tile, points):
    """Accept only if the tile matches EVERY verification point (>=2 kills lucky bugs)."""
    details = []
    for v, want in points:
        ok, got, err = oracle(tile, v)
        details.append({"v": v, "want": want, "got": got, "ok": bool(ok and got == want),
                        "err": None if ok else str(err)[:120]})
        if not details[-1]["ok"]:
            return False, details
    return True, details


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--points", required=True, help="v:expected_r10,v:expected_r10 (>=2)")
    ap.add_argument("--draws", type=int, default=4)
    ap.add_argument("--model", default="qwen3-coder:30b")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--isa", default="minimal", choices=["minimal", "minimal_shift"])
    ap.add_argument("--feedback", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--log", default="output/draft_ladder_log.jsonl")
    a = ap.parse_args()

    points = []
    for part in a.points.split(","):
        v, want = part.split(":")
        points.append((int(v), int(want)))
    if len(points) < 2:
        print("REFUSED: need >=2 verification points (one point can be a lucky bug)")
        return 2

    isa = ISA + (SHIFT_RULE if a.isa == "minimal_shift" else "")
    history, receipt = [], {"spec": a.spec, "points": points, "draws": []}
    for i in range(1, a.draws + 1):
        prompt = f"{isa}\n\nTASK: {a.spec}\n"
        if a.feedback and history:
            for h in history:
                prompt += f"\n--- attempt {h['draw']} ---\n{h['tile']}ORACLE: {h['why']}\n"
            prompt += "\nFix the problem the oracle reported. Emit only the corrected tile.\n"
        prompt += "\nTile:"
        text, tok, wall = ask(a.model, prompt, a.temperature)
        tile = extract(text)
        good, details = judge(tile, points)
        why = "ok" if good else "; ".join(f"v={d['v']} want={d['want']} got={d['got']}" for d in details)
        receipt["draws"].append({"draw": i, "accept": good, "details": details, "tile": tile,
                                 "tok": tok, "wall": round(wall, 2)})
        history.append({"draw": i, "tile": tile, "why": why})
        print(f"  draw {i}: {'ACCEPT' if good else 'reject'}  {wall:.2f}s {tok}tok  {why[:90]}")
        if good:
            break
    accepted = receipt["draws"][-1]["accept"]
    receipt["accepted"] = accepted
    if accepted:
        receipt["tile_sha256"] = hashlib.sha256(receipt["draws"][-1]["tile"].encode()).hexdigest()[:16]
    if a.out:
        with open(a.out, "w") as fh:
            if accepted:
                fh.write(receipt["draws"][-1]["tile"])
        with open(a.out + ".receipt.json", "w") as fh:
            json.dump(receipt, fh, indent=2)
    # Cumulative rung log: the production signal for the ladder. Recorded on BOTH paths so the
    # escalation branch (rc=3) is measured too, not just the successes.
    try:
        os.makedirs(os.path.dirname(a.log), exist_ok=True)
        with open(a.log, "a") as fh:
            fh.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "rung": "ollama_draft_tile",
                "model": a.model,
                "isa": a.isa,
                "draws_attempted": len(receipt["draws"]),
                "oracle_passed": accepted,
                "points_evaluated": len(points),
                "tile_sha256": receipt.get("tile_sha256"),
                "cost_usd": 0.0,
                "duration_s": round(sum(d["wall"] for d in receipt["draws"]), 2),
            }) + "\n")
    except OSError as exc:
        print(f"  (rung log not written: {exc})", file=sys.stderr)
    if accepted:
        print(f"DRAFT ACCEPTED draw={len(receipt['draws'])} tile={a.out} sha={receipt.get('tile_sha256')}")
        print(receipt["draws"][-1]["tile"])
        return 0
    print(f"DRAFT NONE after {a.draws} draws — escalate (no tile written)")
    return 3


if __name__ == "__main__":
    sys.exit(main())
