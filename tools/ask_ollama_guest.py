#!/usr/bin/env python3
"""ask-ollama: prompt local Ollama from inside the pixel-booted guest VM.

Slice 1 of the GPU-OS-to-agent prompt channel. Writes a request to
guest_prompt.json over the 9p-shared .hermes_guest_context/ directory,
polls for a matching guest_prompt_response.json written by the host-side
tools/ollama_guest_listener.py, prints the response content to stdout, and
cleans up after itself.

Wire contract: dedicated files guest_prompt.json / guest_prompt_response.json
-- distinct from guest_bridge.py's host_command.json / guest_response.json /
guest_state.json. No shared state, no collision.
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
DEFAULT_TIMEOUT = 60.0
POLL_INTERVAL = 0.2


def resolve_context_dir() -> Path:
    """In-guest the 9p mount lands at /host_zion/...; on the host (and in
    tests) the same physical directory is <repo_root>/.hermes_guest_context."""
    guest_path = Path("/host_zion/projects/visual_audio/.hermes_guest_context")
    if guest_path.exists():
        return guest_path
    return Path(__file__).resolve().parent.parent / ".hermes_guest_context"


def write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    os.rename(tmp, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prompt local Ollama from the guest VM.")
    parser.add_argument("prompt", nargs="?", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--raw", action="store_true",
                         help="print the full response JSON instead of just content")
    args = parser.parse_args(argv)

    prompt = args.prompt
    if prompt is None:
        if sys.stdin.isatty():
            parser.error("no prompt given and stdin is a tty")
        prompt = sys.stdin.read().strip()
    if not prompt:
        parser.error("empty prompt")

    context_dir = resolve_context_dir()
    context_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = context_dir / "guest_prompt.json"
    response_file = context_dir / "guest_prompt_response.json"

    req_id = f"req_{uuid.uuid4().hex[:12]}"
    request = {
        "id": req_id,
        "prompt": prompt,
        "model": args.model,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_atomic(prompt_file, request)

    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline:
            if response_file.exists():
                try:
                    payload = json.loads(response_file.read_text())
                except (json.JSONDecodeError, OSError):
                    time.sleep(POLL_INTERVAL)
                    continue
                if payload.get("id") != req_id:
                    # Not ours: a stale or unrelated response. Leave it
                    # alone and keep waiting for the real one (R2).
                    time.sleep(POLL_INTERVAL)
                    continue
                try:
                    response_file.unlink()
                except OSError:
                    pass
                if payload.get("status") != "ok":
                    print(f"ask-ollama: listener error: {payload.get('error', 'unknown error')}",
                          file=sys.stderr)
                    return 1
                if args.raw:
                    print(json.dumps(payload))
                else:
                    print(payload.get("content", ""))
                return 0
            time.sleep(POLL_INTERVAL)

        print(f"ask-ollama: timed out after {args.timeout}s waiting for the host listener",
              file=sys.stderr)
        return 1
    finally:
        # Never leave an orphaned request behind -- if nobody consumed it
        # (listener down, or we gave up waiting), clean up our own file,
        # but only if it's still OURS (a listener may have claimed and
        # deleted it already) (R4).
        if prompt_file.exists():
            try:
                existing = json.loads(prompt_file.read_text())
                if existing.get("id") == req_id:
                    prompt_file.unlink()
            except (json.JSONDecodeError, OSError):
                pass


if __name__ == "__main__":
    sys.exit(main())
