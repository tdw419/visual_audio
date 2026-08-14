#!/usr/bin/env python3
"""
Pixel Mind REPL — Interactive shell for the spatial cognitive system.

This provides an interactive read-eval-print loop for the pixel substrate
memory. Each query routes through pixel_hermes_bridge_context.py, which
reads prior thoughts from pixel frames, reasons via Ollama, and writes
the new thought back to the spatial substrate.

Usage:
    python3 tools/pixel_mind_repl.py

Then just type queries. The mind remembers across turns.
"""

import re
import sys
import os
import json
import subprocess
from pathlib import Path

# Add tools/ to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container

CONTAINER = "visual_audio.mkv"
BRIDGE_SCRIPT = "pixel_hermes_bridge_context.py"


def _keywords(text: str) -> set:
    """Lowercase word set for cheap keyword-overlap scoring.

    Mirrors pixel_hermes_bridge_context.py's scorer (not imported directly —
    the REPL runs as a plain disk script, the bridge runs via
    `va_container.py run`, which extracts to a temp dir; keeping this
    self-contained avoids a cross-context import that only works by
    coincidence of cwd).
    """
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_relevance(query: str, text: str) -> int:
    return len(_keywords(query) & _keywords(text))


def print_banner():
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║         PIXEL MIND REPL — Spatial Cognitive Shell          ║
    ╠════════════════════════════════════════════════════════════╣
    ║  Substrate: Visual Audio Container (MKV)                  ║
    ║  Memory:   Pixel frames (persistent across sessions)      ║
    ║  Engine:   Ollama qwen2.5-coder:14b @ localhost:11434      ║
    ║                                                                  ║
    ║  The screen is the mind. Pixels remember.                  ║
    ╚════════════════════════════════════════════════════════════╝

    Type queries. The mind remembers your turns across sessions.
    Commands:
      /clear     — Clear all spatial memory (delete thought frames)
      /ls        — List current thought frames
      /cat N     — Read thought frame N (by index from /ls)
      /search Q  — Search all thoughts/summaries by topic keyword overlap
      /quit      — Exit REPL
""")


def list_thoughts():
    """List all thought frames in the container."""
    with Container(CONTAINER) as c:
        thoughts = c.list(filter_role="thought")
    return thoughts


def list_all_entries():
    """List both thought and summary frames (name, kind)."""
    with Container(CONTAINER) as c:
        thoughts = c.list(filter_role="thought")
        summaries = c.list(filter_role="summary")

    entries = []
    for e in thoughts:
        entries.append((e["name"], "thought"))
    for e in summaries:
        entries.append((e["name"], "summary"))

    return entries


def _entry_snippet(content: str) -> str:
    """Render a JSON thought/summary payload as a short one-line preview."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content[:120].replace("\n", " ")

    if "summary" in data:
        return f"[summary of {data.get('summarized_exchange_count', '?')} exchanges] {data['summary'][:100]}"
    q = data.get("query", "")
    r = data.get("response", "")
    return f"Q: {q[:60]}  A: {r[:60]}"


def search_thoughts(query, top_n=10):
    """Rank all thought/summary frames by keyword overlap with `query`.

    Reads every frame's content (no way around it — there's no index other
    than the container's own directory), scores it, and returns the top_n
    with score > 0, most relevant first.
    """
    entries = list_all_entries()
    if not entries:
        return []

    scored = []
    with Container(CONTAINER) as c:
        for name, kind in entries:
            try:
                content = c.read_text(name)
                score = score_relevance(query, content)
                if score > 0:
                    scored.append((score, name, kind, content))
            except KeyError:
                # Entry disappeared between list and read (unlikely)
                continue

    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:top_n]


def clear_memory():
    """Clear all spatial memory by removing thought frames."""
    thoughts = list_thoughts()

    if not thoughts:
        print("[Memory] No thought frames to clear.")
        return

    print(f"[Memory] Found {len(thoughts)} thought frames.")
    confirm = input("Delete ALL spatial memory? This cannot be undone. [yes/N]: ").strip().lower()

    if confirm != "yes":
        print("[Memory] Aborted.")
        return

    # For now, we can't delete entries from va_container.py (append-only design)
    # So we'll just warn the user about this limitation
    print("[Memory] WARNING: va_container.py is append-only by design.")
    print("[Memory] Thought frames cannot be deleted without rebuilding the container.")
    print("[Memory] Workaround: Create a new container with only the tools you need.")
    print("[Memory] Aborted (container remains intact).")


def read_thought(index_str):
    """Read a specific thought frame by index."""
    thoughts = list_thoughts()

    try:
        idx = int(index_str)
        if idx < 0 or idx >= len(thoughts):
            print(f"[Memory] Index {idx} out of range (0-{len(thoughts)-1})")
            return

        entry = thoughts[idx]
        name = entry["name"]

        with Container(CONTAINER) as c:
            content = c.read_text(name)

        print(f"\n{'='*60}")
        print(f"Thought Frame: {name}")
        print(f"{'='*60}")
        print(content)
        print(f"{'='*60}\n")

    except ValueError:
        print(f"[Memory] Invalid index: '{index_str}'")
    except Exception as e:
        print(f"[Memory] Error reading thought: {e}")


def query_pixel_mind(query):
    """Send a query through the spatial bridge.

    This still uses subprocess to run the bridge script inside the container,
    which is the correct approach — the bridge needs to execute in the
    container's temporary extraction environment.
    """
    cmd = ["python3", "tools/va_container.py", "run", CONTAINER, BRIDGE_SCRIPT, "--query", query]

    # Run with the environment so the bridge can find the container
    env = os.environ.copy()
    env["VA_CONTAINER"] = str(Path(CONTAINER).resolve())

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[Error] Bridge failed: {result.stderr}")
        return None

    return result.stdout


def repl():
    """Main REPL loop."""
    print_banner()

    turn = 0
    while True:
        try:
            user_input = input(f"\n[Pixel Mind] Turn {turn + 1} > ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input == "/quit":
                print("\n[Pixel Mind] Shutting down. Spatial memory preserved in container.")
                break

            elif user_input == "/ls":
                thoughts = list_thoughts()
                if not thoughts:
                    print("[Memory] No thought frames found.")
                else:
                    print(f"\n[Memory] {len(thoughts)} thought frames:")
                    for i, entry in enumerate(thoughts):
                        name = entry["name"]
                        frame_start = entry["frames"][0]
                        frame_count = entry["frames"][1]
                        length = entry["length"]
                        print(f"  [{i}] {name}  frames {frame_start}..{frame_start + frame_count - 1}  {length} bytes")
                continue

            elif user_input.startswith("/cat "):
                _, idx_str = user_input.split(maxsplit=1)
                read_thought(idx_str)
                continue

            elif user_input.startswith("/search"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2 or not parts[1].strip():
                    print("[Search] Usage: /search <topic keywords>")
                    continue
                search_query = parts[1].strip()
                print(f"\n[Search] Scanning all thought/summary frames for: '{search_query}'...")
                results = search_thoughts(search_query)
                if not results:
                    print("[Search] No matches found.")
                else:
                    print(f"[Search] {len(results)} match(es), most relevant first:\n")
                    for score, name, kind, content in results:
                        print(f"  [{score} match{'es' if score != 1 else ''}] ({kind}) {name}")
                        print(f"    {_entry_snippet(content)}")
                continue

            elif user_input == "/clear":
                clear_memory()
                continue

            # Regular query
            print(f"\n[Pixel Mind] Routing query through spatial substrate...")
            print(f"[Pixel Mind] Reading prior thoughts from pixel frames...\n")

            response = query_pixel_mind(user_input)

            if response:
                print(response)
                turn += 1
            else:
                print("[Error] No response from spatial bridge.")

        except KeyboardInterrupt:
            print("\n\n[Pixel Mind] Interrupt received. Spatial memory preserved.")
            break
        except EOFError:
            print("\n\n[Pixel Mind] EOF received. Shutting down.")
            break


if __name__ == "__main__":
    repl()