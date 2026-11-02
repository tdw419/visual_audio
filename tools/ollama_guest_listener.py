#!/usr/bin/env python3
"""ollama_guest_listener: host-side half of the guest-VM-to-Ollama prompt
channel (Slice 1). Watches guest_prompt.json, dispatches to local Ollama,
writes guest_prompt_response.json. Dedicated wire files -- does not touch
guest_bridge.py's host_command.json / guest_response.json / guest_state.json.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
POLL_INTERVAL = 0.3


def resolve_context_dir() -> Path:
    guest_path = Path("/host_zion/projects/visual_audio/.hermes_guest_context")
    if guest_path.exists():
        return guest_path
    return Path(__file__).resolve().parent.parent / ".hermes_guest_context"


def write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    os.rename(tmp, path)


def query_ollama(prompt: str, model: str, timeout: float = 55.0) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())
    return result.get("response", "")


def process_one(context_dir: Path) -> bool:
    """Claim and process exactly one pending guest prompt, if any exists.
    Returns True if a request was processed, False if there was nothing to
    do. Claims (deletes) the request file BEFORE dispatching to Ollama so a
    concurrent tick of our own loop can't double-process the same request."""
    prompt_file = context_dir / "guest_prompt.json"
    response_file = context_dir / "guest_prompt_response.json"

    if not prompt_file.exists():
        return False

    try:
        request = json.loads(prompt_file.read_text())
    except (json.JSONDecodeError, OSError):
        # Partial/corrupt write (write-then-rename on the CLI side should
        # prevent this, but never claim-and-destroy something we can't
        # parse) -- leave it for the next tick.
        return False

    try:
        prompt_file.unlink()
    except OSError:
        pass

    req_id = request.get("id")
    model = request.get("model") or DEFAULT_MODEL
    prompt = request.get("prompt", "")

    start = time.monotonic()
    try:
        content = query_ollama(prompt, model)
        response = {
            "id": req_id,
            "status": "ok",
            "content": content,
            "model": model,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        response = {
            "id": req_id,
            "status": "error",
            "error": str(exc),
            "model": model,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }

    write_atomic(response_file, response)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Host-side listener for the guest-VM Ollama prompt channel."
    )
    parser.add_argument("--daemon", action="store_true",
                         help=f"run continuously, polling every {POLL_INTERVAL}s")
    parser.add_argument("--once", action="store_true",
                         help="process at most one pending request, then exit")
    args = parser.parse_args(argv)

    if not args.daemon and not args.once:
        parser.error("specify --daemon or --once")

    context_dir = resolve_context_dir()
    context_dir.mkdir(parents=True, exist_ok=True)

    if args.once:
        process_one(context_dir)
        return 0

    try:
        while True:
            process_one(context_dir)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
