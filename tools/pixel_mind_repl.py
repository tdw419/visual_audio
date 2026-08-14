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
    cmd = ["python3", "tools/va_container.py", "ls", CONTAINER]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    thoughts = []
    for line in result.stdout.splitlines():
        if "pixel_thought_" in line:
            thoughts.append(line.strip())
    
    return thoughts

def list_all_entries():
    """List both thought and summary frames (name, kind)."""
    cmd = ["python3", "tools/va_container.py", "ls", CONTAINER]
    result = subprocess.run(cmd, capture_output=True, text=True)

    entries = []
    for line in result.stdout.splitlines():
        if "pixel_thought_" in line or "pixel_summary_" in line:
            parts = line.split()
            for p in parts:
                if p.startswith("pixel_thought_"):
                    entries.append((p, "thought"))
                    break
                elif p.startswith("pixel_summary_"):
                    entries.append((p, "summary"))
                    break
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
    for name, kind in entries:
        cat_cmd = ["python3", "tools/va_container.py", "cat", CONTAINER, name]
        result = subprocess.run(cat_cmd, capture_output=True)
        content = result.stdout.decode("utf-8", errors="replace").strip()
        score = score_relevance(query, content)
        if score > 0:
            scored.append((score, name, kind, content))

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
        
        # Extract name from the ls output line
        # Format: "[  thought] pixel_thought_1234567890  frames 406..406  159 bytes"
        line = thoughts[idx]
        name_part = line.split()[2]  # "pixel_thought_1234567890"
        
        cmd = ["python3", "tools/va_container.py", "cat", CONTAINER, name_part]
        result = subprocess.run(cmd, capture_output=True)

        print(f"\n{'='*60}")
        print(f"Thought Frame: {name_part}")
        print(f"{'='*60}")
        print(result.stdout.decode("utf-8", errors="replace"))
        print(f"{'='*60}\n")
        
    except ValueError:
        print(f"[Memory] Invalid index: '{index_str}'")
    except Exception as e:
        print(f"[Memory] Error reading thought: {e}")

def query_pixel_mind(query):
    """Send a query through the spatial bridge."""
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
                    for i, t in enumerate(thoughts):
                        print(f"  [{i}] {t}")
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