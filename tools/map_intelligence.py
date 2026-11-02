#!/usr/bin/env python3
"""tools/map_intelligence.py — BK-92 R1: self-annotating map daemon (advisory-only).

Reads the newest entries from .builder_queue/decision_log.jsonl, prompts a LOCAL
ollama model, and pushes a 3-bullet lane-state summary onto the spatial map via
the existing set_annotations IPC verb.

HARD BOUNDARY (DIRECTIVE_BK92_MAP_INTELLIGENCE.md, binding): ADVISORY NEVER
AUTHORITATIVE. This daemon annotates only. It NEVER gates, blocks, writes the
ledger, or feeds any verdict logic. Its only write is the set_annotations IPC
call and its own state file.

Degrades gracefully: ollama down / compositor down -> log + backoff, map and
annotations untouched (stale annotations persist by design).
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_LOG = ".builder_queue/decision_log.jsonl"
DEFAULT_SOCKET = "/tmp/spatial_compositor.sock"
DEFAULT_STATE = "/tmp/map_intelligence_state.json"
DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_INTERVAL = 300.0
BACKOFF_CAP = 3600.0

PROMPT_TEMPLATE = """You are the lane commentator for a GPU-OS build map. Below are the {n} most recent auditor decision-log entries. Summarize the current lane state as exactly 3 short bullets (one line each, max 12 words per bullet). Facts only from the entries; no speculation.

Entries:
{entries}

Reply with ONLY the 3 bullets, each starting with "- ".
"""


def assemble_context(entries: list[dict], head: str, cursor: int) -> str:
    """Deterministic prompt assembly. Fixed input -> byte-identical prompt.

    `entries` are already-parsed decision-log dicts. They are sorted by
    timestamp here so the prompt is canonical regardless of line order in the
    log file (fixed content -> byte-identical prompt, L1 gate leg).
    """
    ordered = sorted(entries, key=lambda e: str(e.get("timestamp", "")))
    lines = []
    for e in ordered:
        ts = e.get("timestamp", "?")
        ticket = e.get("ticket_id", "?")
        verdict = e.get("verdict", "?")
        score = e.get("overall_score", e.get("score", "?"))
        lines.append(f"- [{ts}] {ticket} verdict={verdict} score={score}")
    entry_block = "\n".join(lines) if lines else "- (no entries)"
    return PROMPT_TEMPLATE.format(n=len(entries), entries=entry_block) + (
        f"HEAD: {head}\nCURSOR: {cursor}\n"
    )


def snapshots_equal(a: str, b: str) -> bool:
    """Snapshot comparator used by the L1 gate leg. Must discriminate."""
    return a == b


def read_log_tail(log_path: Path, n: int) -> tuple[list[dict], int]:
    """Return (last n parsed entries oldest-first, cursor=total valid lines)."""
    entries: list[dict] = []
    valid = 0
    if not log_path.exists():
        return entries, 0
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            valid += 1
            entries.append(obj)
    return entries[-n:], valid


def query_ollama(prompt: str, model: str, base_url: str, timeout: float = 60.0) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    return body.get("response", "")


def bullets_from_response(text: str, max_bullets: int = 3) -> list[str]:
    bullets = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("-", "*", "•")):
            bullets.append(line.lstrip("-*• ").strip())
        elif line and not bullets and len(line) < 120:
            continue  # skip preamble lines before the first bullet
    return bullets[:max_bullets]


def callout_annotation(bullets: list[str], model: str, cursor: int,
                       anchor: list[float]) -> dict:
    text = f"lane digest ({model} @ cursor {cursor}):\n" + "\n".join(
        f"• {b}" for b in bullets)
    return {
        "type": "callout",
        "anchor": anchor,
        "text": text,
        "badge_color": [0.2, 0.9, 0.4, 0.9],
        "border_color": [0.2, 0.9, 0.4, 0.7],
    }


def push_annotations(socket_path: str, items: list[dict], timeout: float = 10.0) -> bool:
    """Line-framed IPC set_annotations. Returns True on status=ok."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(socket_path)
        req = json.dumps({"action": "set_annotations", "items": items}) + "\n"
        s.sendall(req.encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        if not buf:
            return False
        return json.loads(buf.decode().splitlines()[0]).get("status") == "ok"
    except (OSError, json.JSONDecodeError):
        return False


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except json.JSONDecodeError:
            pass
    return {"cursor": 0, "records": []}


def run_once(log_path: Path, head: str, model: str, base_url: str,
             socket_path: str, state_path: Path, anchor: list[float],
             n_entries: int = 5,
             query_fn=query_ollama, push_fn=push_annotations,
             now_fn=time.time) -> bool:
    """One digest cycle. Returns True if an annotation was pushed.

    Never raises on expected failures (ollama down, compositor down): those
    return False and leave map + state untouched (graceful degradation).
    """
    entries, cursor = read_log_tail(log_path, n_entries)
    if cursor == load_state(state_path)["cursor"]:
        return False  # nothing new since last digest
    prompt = assemble_context(entries, head, cursor)
    try:
        response = query_fn(prompt, model, base_url)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"[map_intelligence] ollama unreachable, backing off: {exc}",
              file=sys.stderr)
        return False
    bullets = bullets_from_response(response)
    if len(bullets) < 3:
        print(f"[map_intelligence] model returned {len(bullets)} bullets, "
              "want 3; skipping push", file=sys.stderr)
        return False
    annotation = callout_annotation(bullets, model, cursor, anchor)
    if not push_fn(socket_path, [annotation]):
        print("[map_intelligence] compositor push failed, backing off",
              file=sys.stderr)
        return False
    state = load_state(state_path)
    state["cursor"] = cursor
    state["records"].append({
        "ts": now_fn(),
        "model": model,
        "cursor": cursor,
        "head": head,
        "bullets": bullets,
        "prompt_sha": __import__("hashlib").sha256(prompt.encode()).hexdigest(),
    })
    state_path.write_text(json.dumps(state, indent=1))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true", help="single cycle, then exit")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--socket", default=DEFAULT_SOCKET)
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    ap.add_argument("--anchor", nargs=2, type=float, default=[0.0, 8.0],
                    help="world-space anchor x y for the callout")
    ap.add_argument("--head", default="", help="current HEAD sha for provenance")
    args = ap.parse_args()

    interval = args.interval
    while True:
        ok = run_once(Path(args.log), args.head, args.model, args.base_url,
                      args.socket, Path(args.state), args.anchor)
        if ok:
            interval = args.interval  # reset backoff on success
        elif interval < BACKOFF_CAP:
            interval = min(interval * 2, BACKOFF_CAP)
        if args.once:
            return 0 if ok else 1
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
