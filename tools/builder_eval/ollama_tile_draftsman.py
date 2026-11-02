#!/usr/bin/env python3
"""ollama_tile_draftsman.py — can Ollama draft .glyph tiles that pass the GlyphCPUv2 oracle?

The one role where a local model's weaknesses stop mattering: candidate generation under a
bit-exact machine gate. This measures acceptance across MULTIPLE routines (not one), and
compares against GlyphGPT's 9% corpus baseline.

Design:
  - For each routine: N candidates from Ollama, each wrapped in an LDI prologue that seeds
    r10, then assembled+executed by run_generated (the real oracle).
  - ACCEPT = the tile halts, does not fault, and leaves the EXPECTED value in the output
    register. Syntax-only success is not acceptance.
"""
from __future__ import annotations

import argparse, json, pathlib, sys, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "glyph_gpt"))

ISA = """Glyph tile text format (one instruction per line, two-space indent optional):

  :label
  The ONLY opcodes that exist (25): ADD AND CALL CALLR CMP HALT JMP JMPR JZ KJMP
  LD LDI OR POP PRT PUSH RET ROTR SHL SHR ST SUB SYSCALL SYSRET XOR.
  There is NO MUL, NO MOV, NO NEG opcode in this ISA.
  LDI rN <imm> = load immediate (decimal or 0x) | ADD rD rS = rD += rS
  SUB rD rS = rD -= rS | RET = end the tile

Registers are r0..r31. r10 holds the input value when your tile starts.
Emit ONLY the tile text. No fences, no prose, no explanation."""

ISA_MIN = """Glyph tile text format (one instruction per line):
  :label
  LDI rN <imm> = load an immediate (decimal or 0x) into rN | ADD rD rS = rD += rS
  SUB rD rS = rD -= rS | RET = end the tile
Registers are r0..r31. r10 holds the input value. Emit ONLY the tile text, no fences, no prose."""
_SHAPES = ("\n  LD rD [rA] = load from memory (NOT a register copy)\n"
           "  ST [rA] rS = store to memory (NOT a register copy)\n"
           "  ADD/SUB take REGISTER operands only; load constants with LDI first.")
ARMS = {"minimal": ISA_MIN, "minimal_fb": ISA_MIN, "manifest": ISA, "manifest_shapes": ISA + _SHAPES}

# routine -> (spec, seed, expected register value after the run)
ROUTINES = {
    "double": ("Leave r10 doubled in place (r10 = 2 * input).", 21, 42),
    "inc": ("Leave r10 incremented by 1 (r10 = input + 1).", 41, 42),
    "negate": ("Leave r10 negated (r10 = -input) as a 32-bit value.", 5, (1 << 32) - 5),
    # ── HELD-OUT routines (nobody selected these for the demo; recipe-validation set) ──
    "decrement": ("Leave r10 decremented by 1 (r10 = input - 1).", 41, 40),
    "clear": ("Set r10 to zero.", 7, 0),
    "shl_one": ("Shift r10 left by one bit (r10 = input << 1).", 21, 42),
    "and_mask": ("Mask r10 to its low 8 bits (r10 = input & 255).", 261, 5),
}


def ask(model: str, prompt: str, temperature: float, num_predict: int) -> tuple[str, int, float]:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": 8192},
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
    return d.get("response", ""), int(d.get("eval_count", 0)), time.time() - t0


def strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = "\n".join(s.split("\n")[1:])
    if s.rstrip().endswith("```"):
        s = "\n".join(s.rstrip().split("\n")[:-1])
    return s.strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-coder:30b")
    ap.add_argument("--arm", default="minimal", choices=sorted(ARMS))
    ap.add_argument("--feedback", action="store_true")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--routines", default="double,inc,negate")
    a = ap.parse_args()

    import generate  # noqa: E402  (provides run_generated)

    rows, accepted, total = [], 0, 0
    for name in a.routines.split(","):
        spec, seed_value, expected = ROUTINES[name]
        print(f"=== {name}: {spec}  (seed r10={seed_value}, expect {expected})")
        history = []
        for i in range(1, a.n + 1):
            prompt = f"{ARMS[a.arm]}\n\nTASK: {spec}\n"
            if a.feedback and history:
                for h in history:
                    prompt += f"\n--- attempt {h['cand']} ---\n{h['tile']}ORACLE: {h['why']}\n"
                prompt += "\nFix the problem the oracle reported. Emit only the tile.\n"
            prompt += "\nTile:"
            text, tok, wall = ask(a.model, prompt, a.temperature, 512)
            tile = strip_fences(text)
            code = f"LDI r10 {seed_value}\n{tile}"
            rec = generate.run_generated(code)
            regs = rec.get("registers_full") or []
            got = regs[10] if len(regs) > 10 else None
            ok = bool(rec.get("halted")) and got == expected
            accepted += ok
            total += 1
            why = "ok" if ok else (rec.get("error") or ("fault" if rec.get("faulted") else f"r10={got}"))
            print(f"  cand {i}: {'ACCEPT' if ok else 'reject'}  r10={got}  {wall:.1f}s {tok}tok  {str(why)[:70]}")
            history.append({"cand": i, "tile": tile, "why": str(why)[:200]})
            rows.append({"routine": name, "cand": i, "accept": ok, "r10": got,
                         "expected": expected, "halted": rec.get("halted"),
                         "faulted": rec.get("faulted"), "error": rec.get("error"),
                         "tile": tile, "tok": tok, "wall": round(wall, 2)})

    out = pathlib.Path("tools/builder_eval/ollama_tile_results.json")
    out.write_text(json.dumps({"model": a.model, "acceptance": f"{accepted}/{total}",
                               "rate": round(accepted / total, 3) if total else 0.0,
                               "temperature": a.temperature, "rows": rows}, indent=2))
    print(f"\nACCEPTANCE {accepted}/{total} = {accepted/total:.0%}" if total else "no trials")
    print(f"GlyphGPT corpus baseline: 9% (clustered, 3/20 tiles)")


if __name__ == "__main__":
    main()
