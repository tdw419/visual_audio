#!/usr/bin/env python3
"""BK-102 R3: :do free-text → structured spatial command via LOCAL ollama qwen.

Advisory-only boundary (BK-92 discipline, binding):
  - The LLM proposes ONE structured command; it NEVER executes anything.
  - The deterministic dispatcher (run_spatial_command via IPC exec_command)
    is the ONLY executor.
  - Unparseable/unknown-verb output → loud failure (JSON with ok=false),
    never a silent no-op.

Design: the model translates natural language into one verb from the
compositor's EXISTING vocabulary (50+ dispatcher verbs), constrained to a
strict JSON schema. We validate against the live verb list derived from the
gate suite's known-good verbs + anything the compositor acks; unknown verbs
are rejected before IPC is attempted.

Usage:
  echo "make node_1 blue" | tools/map_intent.py
  tools/map_intent.py "tile the windows"          # one-shot
  tools/map_intent.py --dry-run "make it blue"    # translate only, no IPC
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from pathlib import Path

SOCKET_PATH = Path("/tmp/spatial_compositor.sock")
OLLAMA_MODEL = "qwen2.5-coder:7b"  # local, free; 14b fallback handled by caller
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_TIMEOUT_S = 30
IPC_TIMEOUT_S = 10

# Verbs accepted for direct exec_command dispatch. Kept conservative:
# these are the dispatcher verbs with known stable arity (verified in
# run_spatial_command). Color verbs are included for forward-compat with
# BK-102 R1; if R1 hasn't landed, the compositor itself errors loudly,
# which we surface — never swallow.
# R2: deterministic color resolution. Source of truth = CSS-148 table
# (tools/named_colors.py, byte-verified against PIL canonical). wordbase.db
# color_hex is FORBIDDEN as a color source (see BK-102 amendments 1-3:
# 86% singletons = hash signature, 13/32 color names correct, stored
# gold=maroon/violet=chartreuse). The LLM may propose a color word; we
# REPLACE it with the table value. Unknown color words are an error, not
# a model fallback — deterministic or nothing.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from tools.named_colors import NAMED_COLORS

KNOWN_VERBS = {
    # zero-arg toggles/views
    "hud", "minimap", "overlays", "grid", "snap", "clear",
    # layout
    "tile", "relax", "untangle",
    # selection
    "select", "deselect", "invert",
    # cluster color: :clustercolor <id> <r> <g> <b> [a]  (live-gated path)
    "clustercolor",
    # node color: :color <id> <r> <g> <b> [a]  (BK-102 R1 landed c7740e3d,
    # branch af3e-r1-node-color; wired into R3 2026-10-03 per lane pointer)
    "color",
    # camera
    "back", "next", "prev",
}

# Verbs whose LAST args are a color (r g b [a]) — the canonicalization pass
# and the unknown-color-word pre-check apply to these.
COLOR_VERBS = {"clustercolor", "color"}

VERB_ARITY = {
    "clustercolor": (4, 5),   # id r g b [a] — verb itself is parts[0]
    "color": (4, 5),          # id r g b [a] — same shape, node scope
}

SYSTEM_RULES = (
    "You translate a natural-language instruction into ONE spatial compositor "
    "command. Reply with ONLY a JSON object, no prose, no markdown:\n"
    '{"verb": "<one verb from the list>", "args": ["arg1", ...]}\n'
    "Valid verbs: " + ", ".join(sorted(KNOWN_VERBS)) + "\n"
    "Rules:\n"
    "- clustercolor args: cluster_id, then decimal r g b (0.0-1.0), optional a\n"
    "- color words map to RGB: blue=[0,0,1] red=[1,0,0] green=[0,1,0] "
    "purple=[0.6,0.2,1] yellow=[1,0.84,0] cyan=[0,0.8,1] orange=[1,0.5,0]\n"
    "- If the instruction is not achievable with one verb, reply "
    '{"error": "reason"}\n'
    "- Never invent verbs. Never add explanation."
)

_PROMPT_CACHE: dict = {}


def resolve_color(word: str) -> tuple[float, float, float, float] | None:
    """Deterministic named-color lookup. Returns None if not a known color."""
    return NAMED_COLORS.get(word.strip().lower().replace(" ", ""))


def translate_free_text(text: str) -> dict:
    """LLM leg: natural language → {"verb","args"} | {"error"}. Advisory only."""
    prompt = f"{SYSTEM_RULES}\n\nInstruction: {text}\nJSON:"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(OLLAMA_TIMEOUT_S),
             "-d", json.dumps({
                 "model": OLLAMA_MODEL,
                 "prompt": prompt,
                 "stream": False,
                 "format": "json",
                 "options": {"temperature": 0,
                             "num_predict": 120},
             }),
             OLLAMA_URL],
            capture_output=True, text=True, timeout=OLLAMA_TIMEOUT_S + 5,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ollama timeout", "stage": "llm"}
    if r.returncode != 0:
        return {"ok": False, "error": f"ollama unreachable: {r.stderr[:120]}",
                "stage": "llm"}
    try:
        body = json.loads(r.stdout)
        raw = body.get("response", "")
    except json.JSONDecodeError:
        return {"ok": False, "error": "ollama returned non-JSON",
                "stage": "llm", "raw": r.stdout[:200]}
    # strict extraction: one JSON object
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"ok": False, "error": "no JSON object in model output",
                "stage": "parse", "raw": raw[:200]}
    try:
        proposal = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"invalid JSON: {e}", "stage": "parse",
                "raw": m.group(0)[:200]}
    if "error" in proposal:
        return {"ok": False, "error": f"model refused: {proposal['error']}",
                "stage": "model"}
    verb = proposal.get("verb")
    raw_args = proposal.get("args", [])
    if not isinstance(raw_args, list):
        return {"ok": False, "error": "args must be a list",
                "stage": "validate", "raw": proposal}
    # Coerce numbers to strings: qwen emits [0, 0, 1] for RGB; the
    # dispatcher's command line is string-joined anyway. Non-numeric
    # non-strings stay rejected.
    args: list[str] = []
    for a in raw_args:
        if isinstance(a, bool) or not isinstance(a, (str, int, float)):
            return {"ok": False,
                    "error": f"arg not string/number: {a!r}",
                    "stage": "validate", "raw": proposal}
        args.append(str(a))
    if verb not in KNOWN_VERBS:
        return {"ok": False,
                "error": f"unknown verb '{verb}' (not in whitelist)",
                "stage": "validate", "raw": proposal}
    if verb in VERB_ARITY:
        lo, hi = VERB_ARITY[verb]
        # 2026-10-06: for COLOR_VERBS, a 2-arg shape (id, color-word) is
        # admissible when a NAMED color word appears in the instruction —
        # the R2 determinism pass below expands it via the CSS-148 table.
        # qwen at temp-0 drifts between the 5-arg RGBA shape and the
        # 2-arg named shape; rejecting the short shape at arity turned a
        # resolvable intent into a loud error (live finding, RED leg:
        # test_r2_two_arg_named_color_resolves). Unknown color words in
        # the short shape still fail LOUD at stage=color downstream.
        if verb in COLOR_VERBS and len(args) == 2:
            low = re.sub(r"[^a-z]", " ", text.lower())
            if any(re.search(rf"\b{re.escape(w)}\b", low)
                   for w in NAMED_COLORS):
                pass  # defer arity to the R2 pass, which appends RGBA
            else:
                # unknown/absent color word in the short shape: fail at
                # stage=color (same stage as the R2 pass's unknown-word
                # loud error) so the failure names the COLOR problem,
                # not an arity problem — the shape is fine, the word
                # isn't in the table and the model gave no decimals.
                return {"ok": False,
                        "error": (f"color word {args[1]!r} not in CSS-148 "
                                  f"table and no RGBA decimals provided"),
                        "stage": "color", "raw": proposal}
        elif not (lo <= len(args) <= hi):
            return {"ok": False,
                    "error": f"{verb} needs {lo}-{hi} args, got {len(args)}",
                    "stage": "validate", "raw": proposal}
    # R2 determinism pass (generalized 2026-10-03 to COLOR_VERBS = clustercolor
    # + color/R1): for a color verb, ALWAYS canonicalize the color through the
    # CSS-148 table when a color word appears in the INSTRUCTION text — even if
    # the model also emitted decimals, because model-chosen decimals are
    # exactly the nondeterministic guess this pass removes. No color word in
    # the instruction: model decimals pass through; model non-decimals are a
    # LOUD error (no silent fallthrough). An unknown color word ('ocean',
    # 'cerulean') is a stage=color error regardless of what the model guessed —
    # the model may pick a WHITELISTED verb for an UNKNOWN color, and letting
    # its decimals through was the wordbase-forbidden leak fixed this tick
    # (measured: 'cerulean' -> model guess [0,0.45,1] passed as ok before).
    # 2026-10-06: entry widened to len(args) >= 2 — the 2-arg (id, word)
    # shape admitted at arity (see VERB_ARITY comment) canonicalizes here.
    if verb in COLOR_VERBS and len(args) >= 2:
        def _is_dec(x: str) -> bool:
            try:
                float(x)
                return True
            except ValueError:
                return False
        # find a color word in the original instruction (longest match first)
        found = None
        low = re.sub(r"[^a-z]", " ", text.lower())
        for w in sorted(NAMED_COLORS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(w)}\b", low):
                found = w
                break
        if found is not None:
            resolved = resolve_color(found)
            args = [args[0]] + [f"{c:.10g}" for c in resolved[:3]]
            args.append(f"{resolved[3]:.10g}")  # alpha default 1.0
        else:
            # unknown color word: prefer the trailing word of the instruction
            # when it is a WORD (not a cluster id / decimal) and not a table
            # word — that is the natural-language color the user asked for.
            # A trailing cluster id (e.g. 'set cluster c1' with no color word
            # at all) means the MODEL invented decimals with no color word in
            # the instruction: those pass through untouched (decimal passthrough
            # contract). LOUD stage=color only fires when a non-decimal,
            # non-id word or non-decimal arg is actually present.
            words = low.split()
            tail_word = words[-1] if words else ""
            non_dec = "".join(x for x in args[-3:] if not _is_dec(x))
            if (tail_word and tail_word not in NAMED_COLORS
                    and tail_word != verb and not _is_dec(tail_word)
                    and len(tail_word) > 2):
                word = tail_word
            elif non_dec:
                word = non_dec
            else:
                return {"ok": True, "verb": verb, "args": args}
            return {"ok": False,
                    "error": f"unknown color word '{word}' "
                             "(not in CSS-148 table; wordbase forbidden)",
                    "stage": "color", "raw": proposal}
    return {"ok": True, "verb": verb, "args": args}


def command_line(verb: str, args: list[str]) -> str:
    """Build the command-bar string the dispatcher would see from ':'. """
    return " ".join([verb] + list(args))


def ipc_exec(cmd: str) -> dict:
    """Executor leg: deterministic dispatcher via IPC. The ONLY executor."""
    if not SOCKET_PATH.exists():
        return {"ok": False,
                "error": f"compositor socket missing: {SOCKET_PATH}",
                "stage": "ipc"}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(IPC_TIMEOUT_S)
    try:
        s.connect(str(SOCKET_PATH))
        s.sendall((json.dumps({
            "action": "exec_command",
            "command": cmd,
        }) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        if not buf:
            return {"ok": False, "error": "empty IPC response", "stage": "ipc"}
        resp = json.loads(buf.decode().splitlines()[0])
        return {"ok": resp.get("status") == "ok", "ipc": resp, "stage": "ipc"}
    except (socket.timeout, ConnectionError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e), "stage": "ipc"}
    finally:
        s.close()


def run(text: str, dry_run: bool = False) -> dict:
    t = translate_free_text(text)
    if not t.get("ok"):
        return t
    if dry_run:
        return {**t, "dry_run": True, "command": command_line(t["verb"], t["args"])}
    x = ipc_exec(command_line(t["verb"], t["args"]))
    return {**x, "verb": t["verb"], "args": t["args"],
            "command": command_line(t["verb"], t["args"])}


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    dry = "--dry-run" in argv
    text = " ".join(args) if args else sys.stdin.read().strip()
    if not text:
        print(json.dumps({"ok": False, "error": "no instruction given"}))
        return 2
    out = run(text, dry_run=dry)
    print(json.dumps(out, indent=1))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
