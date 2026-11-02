#!/usr/bin/env python3
"""spatial_builder.py — prompt GlyphGPT to build verified spatial-OS routines.

This is the human/intent-facing front-end to the 4-pillar neural compiler.
You describe the OS task; it coordinates the pillars:

    1. Neural (GlyphGPT 838K)  -> caller coordination around the routine
    2. FSM (GlyphFSM)          -> grammar + caller axioms (CALL then HALT)
    3. RoutineAtlas            -> the verified tile IS the routine body
    4. GlyphCPUv2 oracle       -> execute; nothing ships without HALT + contract

The model is NOT prompted with English prose — it is prompted with the
structured caller prefix (entry trampoline + argument setup) that the
corpus taught it, conditioned on family "leaf_call:<tile>". The semantic
contract (what a0 / memory must contain afterwards) is checked against a
ground-truth computed in Python, independently of the model.

Usage:
  python3 spatial_builder.py double      --value 21
  python3 spatial_builder.py accumulate  --array 7,9,5
  python3 spatial_builder.py memcpy      --array 111,222,333 --dest 600
  python3 spatial_builder.py tile_clear  --dest 400 --words 4 --fill 57005
  python3 spatial_builder.py all         # run every contract

Exit code 0 only if every requested task assembled, executed, halted,
AND met its semantic contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from glyph_gpt.atlas import build_default_atlas            # noqa: E402
from glyph_gpt.generate import (                           # noqa: E402
    BOS,
    extract_to_halt,
    generate,
    run_generated,
)
from glyph_gpt.model import load_checkpoint                # noqa: E402
from glyph_gpt.tokenizer import GlyphTokenizer             # noqa: E402

M32 = 0xFFFFFFFF

# ---------------------------------------------------------------------------
# Task specs: prompt prefix (the "prompt" the model was trained on) + the
# semantic contract checked against Python-computed ground truth.
# Register conventions (fixed ABI, from the synth corpus):
#   double:      r10 = v                -> a0(r10) = 2*v
#   accumulate:  r11 = base, r12 = n    -> a0 = sum(mem[base..base+n))
#   memcpy:      r11 = src, r12 = dst, r13 = n -> mem[dst..dst+n) = mem[src..]
#   tile_clear:  r11 = base, r13 = n, r14 = fill -> mem[base..base+n) = fill
# ---------------------------------------------------------------------------


def _prefix_double(v: int) -> str:
    # The caller LDI carries a 16-bit immediate; a wider value would be
    # silently truncated here while the contract still checks 2*v, so
    # reject it up front rather than emit a routine that can't pass.
    if not 0 <= v <= 0xFFFF:
        raise SystemExit(f"double --value {v} out of range "
                         f"[0, 65535] (16-bit caller immediate)")
    return (":__entry\nLDI r31 4351\nJMP :main\n:main\n"
            f"LDI r10 {v}\nLDI r1 0x8\n")


def _prefix_accumulate(words: list[int]) -> str:
    lines = [":__entry\nLDI r31 4351\nJMP :main\n:main\n", "LDI r11 500\n"]
    for i, w in enumerate(words):
        lines.append(f"LDI r14 {w}\n")
        if i == 0:
            lines.append("ST r11 r14\n")
        else:
            lines.append(f"LDI r15 {500 + i}\nST r15 r14\n")
    lines.append(f"LDI r12 {len(words)}\nLDI r1 0x8\n")
    return "".join(lines)


def _prefix_memcpy(words: list[int], dst: int) -> str:
    lines = [":__entry\nLDI r31 4351\nJMP :main\n:main\n", "LDI r11 500\n"]
    for i, w in enumerate(words):
        lines.append(f"LDI r14 {w}\n")
        if i == 0:
            lines.append("ST r11 r14\n")
        else:
            lines.append(f"LDI r15 {500 + i}\nST r15 r14\n")
    lines.append(f"LDI r12 {dst}\nLDI r13 {len(words)}\nLDI r1 0x8\n")
    return "".join(lines)


def _prefix_tile_clear(dst: int, n: int, fill: int) -> str:
    return (":__entry\nLDI r31 4351\nJMP :main\n:main\n"
            f"LDI r11 {dst}\nLDI r14 {fill}\nLDI r13 {n}\nLDI r1 0x8\n")


# ---------------------------------------------------------------------------
# SB-1: tile composition — chained multi-CALL pipelines in one linked image.
# The builder typesets the caller (entry trampoline + per-stage argument
# loads + one CALL per stage + a single HALT); the model still emits each
# stage's CALL coordination (asserted to match). The composite contract is
# the byte-exact end state, folded stage-by-stage in Python.
# ---------------------------------------------------------------------------

MEM_WORDS = 1024  # default GlyphCPUv2 RAM; a stage touching >= this faults


def _entry() -> str:
    return ":__entry\nLDI r31 4351\nJMP :main\n:main\n"


def _stage_touched(tile: str, a: list[int]) -> tuple[int, int]:
    """Highest word index a stage's parameters will touch (for static OOB
    attribution — the oracle fault is still the ground truth)."""
    if tile == "seed":
        return a[0], a[0] + (len(a) - 1)              # addr, w0..
    if tile == "tile_clear":
        return a[0], a[0] + a[1]                      # base, n
    if tile == "memcpy":
        return min(a[0], a[1]), max(a[0], a[1]) + a[2]   # src, dst, n
    if tile == "accumulate":
        return a[0], a[0] + a[1]                      # base, n
    raise SystemExit(f"unknown pipeline stage '{tile}'")


def _stage_args_text(tile: str, a: list[int]) -> str:
    if tile == "seed":
        base, words = a[0], a[1:]
        return "".join(f"LDI r14 {w & 0xFFFF}\nLDI r15 {base + i}\nST r15 r14\n"
                       for i, w in enumerate(words))
    if tile == "tile_clear":
        return f"LDI r11 {a[0]}\nLDI r14 {a[2] & 0xFFFF}\nLDI r13 {a[1]}\n"
    if tile == "memcpy":
        return f"LDI r11 {a[0]}\nLDI r12 {a[1]}\nLDI r13 {a[2]}\n"
    if tile == "accumulate":
        return f"LDI r11 {a[0]}\nLDI r12 {a[1]}\n"
    raise SystemExit(f"unknown pipeline stage '{tile}'")


def parse_pipeline(spec: str) -> list[dict]:
    """'seed:500,3,1,4 clear:600,3,0 memcpy:500,600,3 accumulate:600,3'"""
    stages = []
    for tok_ in spec.split():
        name, _, rest = tok_.partition(":")
        nums = [int(x, 0) for x in rest.split(",")] if rest else []
        canon = {"clear": "tile_clear"}.get(name, name)
        stages.append({"tile": canon, "args": nums})
    return stages


def simulate_pipeline(stages: list[dict]) -> tuple[dict, int | None]:
    """Fold the stage sequence to the expected end state: {word: value} plus
    the expected a0 (r10) if an accumulate ran last-writing it."""
    mem: dict[int, int] = {}
    r10: int | None = None
    for s in stages:
        t, a = s["tile"], s["args"]
        if t == "seed":
            for i, w in enumerate(a[1:]):
                mem[a[0] + i] = w & M32
        elif t == "tile_clear":
            for i in range(a[1]):
                mem[a[0] + i] = a[2] & M32
        elif t == "memcpy":
            src, dst, n = a
            for i in range(n):
                mem[dst + i] = mem.get(src + i, 0)
        elif t == "accumulate":
            r10 = sum(mem.get(a[0] + i, 0) for i in range(a[1])) & M32
    return mem, r10


def run_pipeline(stages: list[dict], model, tok, atlas,
                 ldi_reg_vals: dict | None, seed: int) -> dict:
    all_names = list(atlas.tiles.keys())

    # static OOB attribution: first stage whose params leave the RAM
    oob_stage = next((i for i, s in enumerate(stages)
                      if _stage_touched(s["tile"], s["args"])[1] >= MEM_WORDS),
                     None)

    caller = _entry()
    model_calls = []
    for s in stages:
        caller += _stage_args_text(s["tile"], s["args"])
        if s["tile"] == "seed":
            continue
        call_line, model_ok = _gen_call_line(s["tile"], model, tok, atlas,
                                             ldi_reg_vals, seed)
        model_calls.append((s["tile"], call_line, model_ok))
        caller += call_line + "\n"
    caller += "HALT\n"

    linked = atlas.link(caller)
    receipt = run_generated(linked)
    mem_expect, r10_expect = simulate_pipeline(stages)

    faulted = bool(receipt.get("faulted"))
    halted = bool(receipt.get("halted"))
    mem = receipt.get("memory", [])
    model_bad = [t for t, _, ok in model_calls if not ok]

    if halted and not faulted:
        mem_ok = all(w < len(mem) and mem[w] == v for w, v in mem_expect.items())
        r10_ok = (r10_expect is None
                  or receipt.get("registers_full", [None] * 11)[10] == r10_expect)
        ok = mem_ok and r10_ok and not model_bad
        a0 = receipt.get("registers_full", [None] * 11)[10]
        detail = (f"end state mem_ok={mem_ok} r10_ok={r10_ok}"
                  + ("" if r10_expect is None
                     else f" (a0={a0} want={r10_expect})")
                  + (f" model_bad={model_bad}" if model_bad else ""))
    else:
        ok = False
        stage_name = (f"stage {oob_stage} ({stages[oob_stage]['tile']})"
                      if oob_stage is not None else "unknown stage")
        detail = (f"did not halt (faulted={faulted}); offending {stage_name}"
                  if faulted else "did not halt")

    return {"pipeline": " -> ".join(s["tile"] for s in stages),
            "caller": caller, "receipt": receipt, "model_calls": model_calls,
            "pass": bool(ok), "detail": detail,
            "fault_addr": receipt.get("fault_addr"),
            "oob_stage": oob_stage}


def build_task(tile: str, value: int, array: list[int], dest: int,
               words: int, fill: int) -> dict:
    """Everything needed to prompt, generate, and verify one task."""
    if tile == "double":
        prefix = _prefix_double(value)
        prompt_setup = f"LDI r10 {value}   (v)"

        def contract(receipt, model_text):
            want = (2 * value) & M32
            got = receipt.get("registers_full", [None] * 11)[10]
            return got == want, f"a0={got} want={want}"

    elif tile == "accumulate":
        prefix = _prefix_accumulate(array)
        prompt_setup = f"base=500 n={len(array)}"

        def contract(receipt, model_text):
            want = sum(array) & M32
            got = receipt.get("registers_full", [None] * 11)[10]
            return got == want, f"a0={got} want={want}"

    elif tile == "memcpy":
        prefix = _prefix_memcpy(array, dest)
        prompt_setup = f"src=500 dst={dest} n={len(array)}"

        def contract(receipt, model_text):
            got = receipt.get("memory", [])[dest:dest + len(array)]
            return got == [w & M32 for w in array], f"mem[{dest}..]={got}"

    elif tile == "tile_clear":
        prefix = _prefix_tile_clear(dest, words, fill)
        prompt_setup = f"base={dest} n={words} fill={fill}"

        def contract(receipt, model_text):
            got = receipt.get("memory", [])[dest:dest + words]
            return got == [fill & M32] * words, f"mem[{dest}..]={got}"

    else:
        raise SystemExit(f"unknown tile '{tile}' (known: double, accumulate, "
                         f"memcpy, tile_clear)")
    return {"tile": tile, "prefix": prefix, "setup": prompt_setup,
            "contract": contract}


def run_task(task: dict, model, tok, atlas, ldi_reg_vals: dict | None,
             temperature: float, seed: int) -> dict:
    all_names = list(atlas.tiles.keys())
    ids, vals = tok.encode(task["prefix"], family=f"leaf_call:{task['tile']}",
                           atlas_names=all_names)
    ctx = [i for i in ids if i != BOS]
    ctx_vals = vals[1:] if ids[0] == BOS else vals

    torch.manual_seed(seed)
    out_ids, out_vals = generate(ctx, ctx_vals, model, max_new_tokens=40,
                                 temperature=temperature, greedy=True,
                                 tok=tok, use_fsm=True,
                                 family=f"leaf_call:{task['tile']}",
                                 atlas_names=all_names,
                                 ldi_reg_vals=ldi_reg_vals)
    gen = extract_to_halt(out_ids[len(ctx):])
    gen_vals = out_vals[len(ctx):len(ctx) + len(gen)]
    caller_text = tok.decode(gen, gen_vals, resolve_labels=True,
                             atlas_names=all_names)
    linked = atlas.link(task["prefix"] + "\n" + caller_text)
    receipt = run_generated(linked)
    if receipt.get("halted"):
        ok, detail = task["contract"](receipt, caller_text)
    else:
        ok, detail = False, "did not halt"
    faulted = bool(receipt.get("faulted"))
    return {"tile": task["tile"], "setup": task["setup"],
            "caller": caller_text.strip(), "receipt": receipt,
            "pass": bool(ok) and not faulted, "detail": detail,
            "fault_addr": receipt.get("fault_addr")}


def _gen_call_line(tile: str, model, tok, atlas, ldi_reg_vals: dict | None,
                   seed: int) -> tuple[str, bool]:
    """Prompt the model for one stage's caller coordination (SB-0 style) and
    return its CALL line plus whether the model emitted the expected target.
    The FSM guarantees a well-formed CALL; this asserts the model didn't
    drift to the wrong tile."""
    all_names = list(atlas.tiles.keys())
    prefix = _entry() + "LDI r1 0x8\n"
    ids, vals = tok.encode(prefix, family=f"leaf_call:{tile}",
                           atlas_names=all_names)
    ctx = [i for i in ids if i != BOS]
    ctx_vals = vals[1:] if ids[0] == BOS else vals
    torch.manual_seed(seed)
    out_ids, out_vals = generate(ctx, ctx_vals, model, max_new_tokens=40,
                                 temperature=1.0, greedy=True, tok=tok,
                                 use_fsm=True, family=f"leaf_call:{tile}",
                                 atlas_names=all_names,
                                 ldi_reg_vals=ldi_reg_vals)
    gen = extract_to_halt(out_ids[len(ctx):])
    gen_vals = out_vals[len(ctx):len(ctx) + len(gen)]
    txt = tok.decode(gen, gen_vals, resolve_labels=True, atlas_names=all_names)
    want = f"CALL :atlas_{tile}"
    for line in txt.splitlines():
        if line.strip().startswith("CALL :atlas_"):
            return line.strip(), line.strip() == want
    return want, False  # model emitted no CALL; fall back, flag it


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prompt GlyphGPT to build verified spatial-OS routines")
    ap.add_argument("task", choices=["double", "accumulate", "memcpy",
                                     "tile_clear", "all"], default="all",
                    nargs="?")
    ap.add_argument("--value", type=lambda s: int(s, 0), default=21,
                    help="v for double")
    ap.add_argument("--array", default="7,9,5",
                    help="comma-separated words for accumulate/memcpy")
    ap.add_argument("--dest", type=lambda s: int(s, 0), default=600,
                    help="destination word address (memcpy / tile_clear)")
    ap.add_argument("--words", type=int, default=4,
                    help="word count (tile_clear)")
    ap.add_argument("--fill", type=lambda s: int(s, 0), default=0xDEAD,
                    help="fill value (tile_clear)")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pipeline", default=None,
                    help="SB-1: chained stages in one image, e.g. "
                         "'seed:500,3,1,4 clear:600,3,0 memcpy:500,600,3 "
                         "accumulate:600,3'")
    args = ap.parse_args()

    print("=" * 70)
    print("Loading pillars: checkpoint + tokenizer + RoutineAtlas")
    print("=" * 70)
    model = load_checkpoint(str(_HERE / "checkpoint.pt"))
    tok = GlyphTokenizer.load(str(_HERE / "tokenizer.json"))
    atlas = build_default_atlas()
    try:
        from glyph_gpt.synth import ldi_reg_value_sets
        ldi_reg_vals = ldi_reg_value_sets(_HERE / "synth_receipts.jsonl")
    except Exception:
        ldi_reg_vals = None
    print(f"  model: {sum(p.numel() for p in model.parameters()):,} params, "
          f"vocab {model.config.vocab_size}")
    print(f"  atlas tiles: {', '.join(atlas.tiles)}")

    if args.pipeline:
        stages = parse_pipeline(args.pipeline)
        print()
        print("=" * 70)
        print(f"PIPELINE: {' -> '.join(s['tile'] for s in stages)}")
        print("=" * 70)
        r = run_pipeline(stages, model, tok, atlas, ldi_reg_vals, args.seed)
        print("--- model-emitted stage coordination ---")
        for t, line, ok in r["model_calls"]:
            print(f"  {line}   {'ok' if ok else 'DRIFT'}")
        print(f"--- oracle: halted={r['receipt'].get('halted')} "
              f"steps={r['receipt'].get('steps')} "
              f"faulted={r['receipt'].get('faulted')} ---")
        tag = "PASS" if r["pass"] else "FAIL"
        print(f"[{tag}] pipeline: {r['detail']}")
        if r.get("fault_addr") is not None:
            print(f"       OOB fault at byte addr {r['fault_addr']:#x}")
        print()
        print("=" * 70)
        print(f"spatial_builder: {'1/1' if r['pass'] else '0/1'} pipeline "
              f"verified (neural + FSM + atlas + oracle)")
        return 0 if r["pass"] else 1

    tiles = (["double", "accumulate", "memcpy", "tile_clear"]
             if args.task == "all" else [args.task])
    array = [int(w, 0) for w in args.array.split(",")]

    results = []
    for t in tiles:
        task = build_task(t, args.value, array, args.dest, args.words,
                          args.fill)
        print()
        print("=" * 70)
        print(f"TASK: {t}   setup: {task['setup']}")
        print("=" * 70)
        r = run_task(task, model, tok, atlas, ldi_reg_vals,
                     args.temperature, args.seed)
        print("--- model-emitted caller coordination ---")
        print(r["caller"] or "(empty)")
        print(f"--- oracle: halted={r['receipt'].get('halted')} "
              f"steps={r['receipt'].get('steps')} "
              f"faulted={r['receipt'].get('faulted')} ---")
        if r["pass"]:
            print(f"[PASS] {t}: {r['detail']}")
        else:
            print(f"[FAIL] {t}: {r['detail']}")
            if r.get("fault_addr") is not None:
                print(f"       OOB fault at byte addr {r['fault_addr']:#x}")
        results.append(r)

    n_pass = sum(r["pass"] for r in results)
    print()
    print("=" * 70)
    print(f"spatial_builder: {n_pass}/{len(results)} tasks verified "
          f"(neural + FSM + atlas + oracle)")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
