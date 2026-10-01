#!/usr/bin/env python3
"""Ollama-authored VA->Glyph loop: local LLM drafts glyph assembly, the Visual
Audio byte codec speaks it, the Glyph engine executes it, the oracle judges.

Pipeline (Jericho's prompt, ollama edition):
  ollama(qwen) -> assembly text -> normalize -> GlyphAssemblerV2 (validate)
  -> pixel image -> speak.encode WAV -> speak.decode -> identity check
  -> GlyphCPUv2 execute -> oracle vs expected output.
  Repair: attempt 2 re-drafts with the assembler error OR the oracle's
  got/want mismatch as feedback (max 2 generations per task).

Exit codes: 0 = all tasks PASS, 3 = any task FAIL/unassemblable.

RESULTS (2026-09-14 AM, qwen2.5-coder 7b + 14b, 2 tasks x 3 attempts each):
  Pipeline: fully closed — every generation normalized, assembled, spoken,
  decoded IDENTICAL, executed, judged. Transport never corrupted a draft.
  Drafting: assembler/normalize errors went 3/6 -> 0/6 after shape-gate +
  humanized feedback; registers-zeroed rule fixed the uninitialized-subtract
  failure mode. Oracle: 0/12 passes. Failure class is control flow — models
  emit loop-shaped straight-line code (missing back-edges, JZ placement),
  consistent with the known draftsman boundary (straight-line ALU strong,
  loops weak). Countdown reached [3,2,1,0]-then-underflow once (one guard
  short). Next rungs: qwen3-coder:30b, or more attempts at fixed temp.

RESULTS (2026-09-14 PM, same 2 tasks x 3 attempts x same 2 models, after
  label resolver + corrected countdown few-shot example):
  Changes: prompt teaches :label jumps; to_instructions() resolves
  ':name' -> absolute (col,row) two-pass (same scheme as
  tools/rv64i_to_glyph.py); assembler-error feedback no longer tells the
  model to emit raw numeric targets. Labels verified correct in isolation
  (row-boundary 0,1 case, longest-first disambiguation, undefined-label
  loud failure — the first cut SILENTLY DROPPED unresolved jumps, fixed:
  they now pass through to the assembler and fail the attempt loudly).
  Live outcome: 1/12 attempt-passes (14b countdown attempt 3, exact
  [3,2,1,0]) vs 0/12 baseline — n=2, not a rate, but the hard-0 wall
  broke once. Attribution is NOT labels: models used raw coordinates in
  10/12 attempts (labels in 2) and every raw jump landed on its intended
  target — coordinate arithmetic was NOT the dominant failure class in
  these runs. The active ingredient is most plausibly the corrected
  few-shot example (demonstrates print-check-subtract-loop with r2=1
  init). Remaining failure class is loop-carried counter invariants:
  never initializing/incrementing the counter (r2 frozen at 1 -> [3,3,3...]
  and [0,1,2,3...] infinite runs) and check-vs-print ordering ([3,2,1],
  missing the final 0). Next rungs: prompt the counter invariant
  explicitly (name a register, init 1, increment every pass), or
  Patch-and-Copy loop-spine templates so the model only drafts the body.
"""
import json
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, "tools")
sys.path.insert(0, ".")

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools import speak  # noqa: E402

W = 8  # instructions per row

TASKS = [
    {
        "name": "countdown",
        "prompt": ("Write a glyph assembly program that prints 3, 2, 1, 0 (one "
                   "value per PRT, in that order) then HALTs. Start r5 at 3, "
                   "print it, subtract 1, and loop until r5 has printed 0 and "
                   "the program ends."),
        "expected": [3, 2, 1, 0],
    },
    {
        "name": "sumsq",
        "prompt": ("Write a glyph assembly program that computes 1+2+3+4 using a "
                   "loop (r5 = running sum, r2 = counter 1..4, r1 = constant 4), "
                   "PRTs the final sum exactly once, then HALTs."),
        "expected": [10],
    },
]

ISA_RULES = """Glyph ISA v2 rules:
- One instruction per line. Exact syntax, whitespace-separated:
    ADD rd rs      (rd = rd + rs; same pattern for SUB MUL AND OR XOR SHL SHR)
    LDI rd <imm>   (rd = immediate number)
    CMP rs1 rs2    (sets flag for JZ; both must be REGISTERS, never numbers)
    JZ :label      (jump to a LABEL when the CMP flag is zero)
    JMP :label     (unconditional jump to a LABEL)
    LD rd rs / ST rs rd / PRT rs / HALT
- Registers are r1..r7. ALL REGISTERS START AT 0. Any constant you need
  (e.g. 1) must be loaded with LDI into a register before it is used.
- Labels: a line with ONLY ":name" marks a position. JZ/JMP take a label
  name, never a raw number - you do NOT need to count instructions or
  compute any position yourself. Use as many labels as you want.
- LOOP CHECKLIST - follow all 4 steps for ANY loop:
    1. Pick a counter register and LDI it to its starting value ONCE,
       BEFORE the loop starts.
    2. LDI a free register to 1 (the increment) ONCE, before the loop.
    3. Inside the loop body, change the counter EVERY pass (ADD/SUB it
       by the increment register) - a counter that never changes makes
       an infinite loop.
    4. CMP the counter against the limit register, then JZ :exit on match.
- Every program ends with HALT.

Example program (prints 5 4 3 2 1 then halts):
LDI r5 5
LDI r1 0
LDI r2 1
:loop
PRT r5
CMP r5 r1
JZ :done
SUB r5 r2
JMP :loop
:done
HALT

Output ONLY instructions and labels, one per line. No comments, no markdown."""

MNEMONICS = {"ADD", "SUB", "MUL", "AND", "OR", "XOR", "SHL", "SHR", "LDI",
             "CMP", "JZ", "JMP", "LD", "ST", "PRT", "HALT"}


LABEL_DEF = re.compile(r"^:\w+$")


def to_instructions(text, width_instrs=W):
    """Normalize a raw model response into assembler-ready instruction lines.

    Mostly syntactic (strips markdown fences/prose, re-splits packed lines at
    mnemonics, tightens jump-target commas), plus one semantic-adjacent step:
    a two-pass label resolver (same scheme as tools/rv64i_to_glyph.py's
    assemble_glyph_to_pixels) so the model writes 'JZ :done' / 'JMP :loop'
    instead of hand-computing absolute (col,row) - added 2026-09-14 after
    verifying the model's control-flow failures were largely 2D-coordinate
    arithmetic errors, not looping-logic errors. Final oracle judgment is
    still on the ENGINE's output, not on whether resolution "looks right".
    """
    lines = []
    for raw in text.splitlines():
        s = raw.strip().strip("`")
        if not s or s.startswith(("#", "```")) or s.lower() in ("plaintext", "asm"):
            continue
        if LABEL_DEF.match(s):
            lines.append(s)  # label definition - keep, resolved below
            continue
        first = s.split()[0].rstrip(":")
        if first not in MNEMONICS:
            toks = s.replace(",", " , ").split()
            if not any(t in MNEMONICS for t in toks):
                continue  # prose
            s = " ".join(toks)
        lines.append(s)
    # re-split packed lines at mnemonic boundaries (label-def lines pass through)
    out = []
    for line in lines:
        if LABEL_DEF.match(line):
            out.append(line)
            continue
        toks = line.replace(",", " , ").split()
        cur = []
        for t in toks:
            if t in MNEMONICS and cur:
                out.append(" ".join(cur))
                cur = [t]
            else:
                cur.append(t)
        if cur:
            out.append(" ".join(cur))

    # Pass 1: collect label -> instruction index (label-def lines are not
    # instructions and are removed here).
    labels = {}
    instrs = []
    for line in out:
        if LABEL_DEF.match(line):
            labels[line] = len(instrs)
        else:
            instrs.append(line)

    # Pass 2: resolve ':label' refs to 'col,row', longest-name-first so one
    # label name can't be mangled as a substring of another.
    resolved = []
    for line in instrs:
        for lbl, idx in sorted(labels.items(), key=lambda kv: -len(kv[0])):
            col, row = idx % width_instrs, idx // width_instrs
            line = re.sub(rf"(?<!\S){re.escape(lbl)}(?!\S)", f"{col},{row}", line)
        resolved.append(line)

    # jump targets: 'JZ 8, 0' / 'JMP -4 , 0' / 'JZ 7,' -> 'JMP x,0' canonical
    # (assembler packs imm from ONE comma arg; negative/relative targets are
    # left for the oracle-repair round to catch as wrong logic)
    fixed = []
    for l in resolved:
        m = re.match(r"((?:JZ|JMP)\s+)(-?\d*)\s*,\s*(\d*)$", l)
        if m and (m.group(2) or m.group(3)):
            l = f"{m.group(1)}{m.group(2) or '0'},{m.group(3) or '0'}"
        fixed.append(l)
    # shape gate: drop anything that isn't a well-formed instruction —
    # kills prose lines that merely mention a mnemonic (e.g. "Note: ... LDI ...")
    # UNDEFINED LABELS must fail LOUDLY: a JZ/JMP whose label never resolved is
    # kept as 'JZ :typo' (shape below) so the ASSEMBLER rejects it and the
    # attempt becomes an assembler-error retry. Dropping the line here instead
    # would silently delete a jump and change program semantics with no
    # feedback to the model (verified 2026-09-14: silent-drop bug in the first
    # cut of this resolver).
    shapes = [
        re.compile(r"^(?:ADD|SUB|MUL|AND|OR|XOR|SHL|SHR|LD|ST)\s+r[1-7]\s+r[1-7]$"),
        re.compile(r"^LDI\s+r[1-7]\s+-?\d+$"),
        re.compile(r"^CMP\s+r[1-7]\s+r[1-7]$"),
        re.compile(r"^(?:JZ|JMP)\s+-?\d+,\d+$"),
        re.compile(r"^(?:JZ|JMP)\s+:\w+$"),  # unresolved label -> assembler error (loud)
        re.compile(r"^PRT\s+r[1-7]$"),
        re.compile(r"^HALT$"),
    ]
    return [l for l in fixed if any(s.match(l) for s in shapes)]


def ollama(prompt: str, model: str) -> str:
    out = subprocess.run(
        ["curl", "-s", "--max-time", "120", "localhost:11434/api/generate",
         "-d", json.dumps({"model": model, "prompt": prompt, "stream": False})],
        capture_output=True, text=True, timeout=150)
    return json.loads(out.stdout).get("response", "")


def try_assemble(lines):
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    try:
        img = asm.assemble(lines, width_instrs=W)
        return om, img, None
    except Exception as e:
        om.close()
        return None, None, str(e)


def execute(img):
    om2 = OpcodeMapV2()
    cpu = GlyphCPUv2(om2, cols_instrs=W)
    cpu.run(np.ascontiguousarray(img, dtype=np.uint8), max_instructions=300)
    om2.close()
    return cpu


def transport(img, task, ecc=True):
    """Speak the image and decode it back. Returns (identical, cpu_or_None)."""
    raw = img.tobytes()
    wav = f"/tmp/va_ollama_{task['name']}.wav"
    speak.encode(raw, wav, use_ecc=ecc)
    back = speak.decode(wav, use_ecc=ecc)
    arr = np.frombuffer(back, dtype=np.uint8)
    identical = arr.size == img.size and bool((arr.reshape(img.shape) == img).all())
    return identical, (execute(arr.reshape(img.shape)) if identical else None)


def humanize_assembler_error(err: str | None) -> str:
    """Translate cryptic assembler crashes into ISA feedback the model can use."""
    if err and "invalid literal for int() with base 10: ''" in err:
        return ("An arithmetic/data-move instruction got an immediate where a "
                "REGISTER is required (e.g. 'ADD r2 1' is invalid — write "
                "'LDI r7 1' then 'ADD r2 r7'). Second operand of ADD SUB MUL "
                "AND OR XOR SHL SHR LD ST must be r1..r7; only LDI takes a "
                "raw number.")
    if err and "not enough values to unpack" in err:
        return ("A JZ/JMP target was not a valid position — almost always an "
                "UNDEFINED or misspelled label (e.g. 'JZ :dne' with no ':dne' "
                "line). Every ':name' used in a jump must be defined on its "
                "own line as ':name' before the end of the program.")
    if err and "out of bounds" in err and "target" in err:
        return ("A jump/call target pointed PAST the end of the program. "
                "Jump targets are absolute (col,row) instruction cells — "
                "the safest fix is to use a :label (define it on its own "
                "line where you want to land, then 'JZ :name' / 'JMP "
                ":name') instead of hand-computed coordinates. If you "
                "meant an off-by-one, recount: the last valid instruction "
                "is at index (count-1).")
    if err and "image-space syscall" in err:
        return ("That LD reads an address that was never written by ST — "
                "FILE_READ/AUDIO_IN/STORE_CODE write PIXEL/image space, "
                "which LD cannot read back. Move the data with ST to a "
                "RAM address first, then LD from there.")
    return err


def run_task(task, model, ecc=True):
    print(f"\n=== {task['name']} (model={model}, ecc={ecc})")
    prompt = f"{ISA_RULES}\n\nTask: {task['prompt']}"
    feedback = ""
    lines = []
    for attempt in (1, 2, 3):
        raw = ollama(prompt + feedback, model)
        lines = to_instructions(raw)
        om, img, err = try_assemble(lines)
        if img is None:
            herr = humanize_assembler_error(err)
            print(f"  attempt {attempt}: ASSEMBLE ERROR: {herr}")
            print(f"  normalized was: {lines}")
            feedback = (f"\n\nYour previous attempt failed to assemble with error:"
                        f"\n{herr}\nPrevious attempt:\n" + "\n".join(lines) +
                        "\nOutput a corrected program. Instructions and labels only. "
                        "Jump targets must be LABELS: 'JZ :done' / 'JMP :loop', "
                        "each defined on its own line as ':name'. Do not compute "
                        "numeric positions.")
            continue
        print(f"  attempt {attempt}: draft ok ({len(lines)} instrs)")
        for l in lines:
            print(f"    | {l}")
        identical, cpu = transport(img, task, ecc)
        if not identical or cpu is None:
            print("  TRANSPORT CORRUPT — refusing to execute")
            om.close()
            return False
        got, want = list(cpu.output)[:8], task["expected"]
        om.close()
        if got == want:
            print(f"  transport IDENTICAL · oracle got={got} want={want} -> PASS")
            return True
        print(f"  oracle FAIL: got={got} want={want}")
        feedback = (f"\n\nYour previous program assembled and ran but produced"
                    f"\n{got} instead of the required {want}.\nPrevious attempt:\n"
                    + "\n".join(lines) +
                    "\nFix the logic. Instructions and labels only.")
    return False


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-coder:7b"
    results = {}
    for task in TASKS:
        try:
            results[task["name"]] = run_task(task, model)
        except Exception as e:
            print(f"  ERROR: {e}")
            results[task["name"]] = False
    print(f"\nverdict: {sum(results.values())}/{len(results)} tasks PASS  {results}")
    sys.exit(0 if all(results.values()) else 3)


if __name__ == "__main__":
    main()
