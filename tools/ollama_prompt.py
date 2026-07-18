#!/usr/bin/env python3
"""
ollama_prompt.py — Prompt Ollama with content from Visual Audio container.

This tool enables the container to "think about itself" by:
1. Extracting content from container entries (ROADMAP.md, specs, tests)
2. Using that content as context for LLM prompts
3. Storing LLM responses back into the container

Usage (from container):
  python3 tools/va_container.py run visual_audio.mkv tools/ollama_prompt.py \
    --prompt "What should I work on next?" \
    --context spec/ROADMAP.md

Usage (from host with VA_CONTAINER env):
  VA_CONTAINER=visual_audio.mkv python3 tools/ollama_prompt.py \
    --prompt "Analyze project status" \
    --context spec/ROADMAP.md
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Default models (configurable via --model)
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
FALLBACK_MODELS = ["qwen2.5-coder:latest", "phi3:latest"]

# Total context budget across all entries; oversized entries are head-truncated
# with an explicit marker so the model never sees silently-clipped input.
MAX_CONTEXT_CHARS = 12000


def get_container_path():
    """Get container path from VA_CONTAINER env var."""
    container = os.environ.get("VA_CONTAINER")
    if not container:
        print("ERROR: VA_CONTAINER environment variable not set", file=sys.stderr)
        print("When using 'va_container.py run', this is set automatically.", file=sys.stderr)
        sys.exit(1)
    return container


def extract_entry(container, entry_name):
    """Extract an entry from the container to a temp file, return path."""
    import tempfile

    fd, temp_path = tempfile.mkstemp(suffix=f"_{entry_name.replace('/', '_')}")
    os.close(fd)

    # Try to extract using sibling va_container.py
    script_dir = Path(__file__).parent
    container_tool = script_dir / "va_container.py"

    if not container_tool.exists():
        # Fallback: assume tools/va_container.py is in PATH
        container_tool = "tools/va_container.py"

    result = subprocess.run(
        [sys.executable, str(container_tool), "cat", container, entry_name, "-o", temp_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"ERROR: Failed to extract {entry_name}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        os.unlink(temp_path)
        return None

    return temp_path


def read_content(path):
    """Read content from file, try JSON parse first."""
    try:
        with open(path, "r") as f:
            content = f.read()

        # Try JSON parse
        try:
            return json.dumps(json.loads(content), indent=2)
        except json.JSONDecodeError:
            return content
    except Exception as e:
        print(f"ERROR: Failed to read {path}: {e}", file=sys.stderr)
        return None


def call_ollama(prompt, context=None, model=DEFAULT_MODEL):
    """Call Ollama with prompt and optional context."""

    full_prompt = prompt

    if context:
        full_prompt = f"""CONTEXT:
{context}

USER REQUEST:
{prompt}

Respond based on the context above. Be specific and actionable."""

    result = subprocess.run(
        ["ollama", "run", model, full_prompt],
        capture_output=True,
        text=True,
        timeout=600,  # large models on CPU can be slow
    )

    if result.returncode != 0:
        if "model" in result.stderr.lower():
            print(f"ERROR: Model '{model}' not found or unavailable", file=sys.stderr)
            return None
        print(f"ERROR: Ollama call failed: {result.stderr}", file=sys.stderr)
        return None

    return result.stdout


def main():
    parser = argparse.ArgumentParser(
        description="Prompt Ollama with Visual Audio container content"
    )
    parser.add_argument("--prompt", help="Prompt to send to Ollama")
    parser.add_argument(
        "--context",
        action="append",
        help="Container entries to use as context (can specify multiple)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--output",
        help="Container entry to store response (e.g., analysis/ollama_response.md)",
    )
    parser.add_argument("--print", action="store_true", help="Print response to stdout")
    parser.add_argument(
        "--list-models", action="store_true", help="List available Ollama models"
    )

    args = parser.parse_args()

    # Handle --list-models (doesn't need --prompt)
    if args.list_models:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        print(result.stdout)
        return 0

    if not args.prompt:
        parser.error("--prompt is required (unless using --list-models)")

    # Get container path
    container = get_container_path()
    print(f"Container: {container}", file=sys.stderr)

    # Build context from container entries
    context_parts = []
    temp_files = []

    if args.context:
        per_entry = MAX_CONTEXT_CHARS // len(args.context)
        for entry_name in args.context:
            print(f"Extracting {entry_name}...", file=sys.stderr)
            temp_path = extract_entry(container, entry_name)
            if temp_path:
                content = read_content(temp_path)
                if content:
                    if len(content) > per_entry:
                        print(f"WARNING: {entry_name} truncated "
                              f"{len(content)} -> {per_entry} chars", file=sys.stderr)
                        content = (content[:per_entry]
                                   + f"\n[... TRUNCATED at {per_entry} of {len(content)} chars]")
                    context_parts.append(f"=== {entry_name} ===\n{content}\n")
                    temp_files.append(temp_path)
                else:
                    print(f"WARNING: Failed to read {entry_name}", file=sys.stderr)
            else:
                print(f"WARNING: Failed to extract {entry_name}", file=sys.stderr)

    # Clean up temp files
    for temp_path in temp_files:
        try:
            os.unlink(temp_path)
        except:
            pass

    context = "\n".join(context_parts) if context_parts else None

    if context:
        print(f"Using {len(args.context)} context entries ({len(context)} chars)", file=sys.stderr)

    # Call Ollama
    print(f"Prompting {args.model}...", file=sys.stderr)
    response = call_ollama(args.prompt, context, args.model)

    if not response:
        # Try fallback models
        for fallback in FALLBACK_MODELS:
            print(f"Retrying with fallback model: {fallback}", file=sys.stderr)
            response = call_ollama(args.prompt, context, fallback)
            if response:
                break

    if not response:
        print("ERROR: All Ollama calls failed", file=sys.stderr)
        return 1

    # Output response
    if args.print or not args.output:
        print(response)
        print()

    if args.output:
        # Write to temp file first
        import tempfile
        fd, temp_path = tempfile.mkstemp(suffix="_ollama_response.md")
        os.close(fd)

        header = (f"<!-- model: {args.model} | prompt: {args.prompt} | "
                  f"context: {', '.join(args.context or [])} | "
                  f"UNVERIFIED LLM OUTPUT: leads to investigate, not evidence -->\n\n")
        with open(temp_path, "w") as f:
            f.write(header + response)

        # Upsert into container: update if the entry exists, else add
        script_dir = Path(__file__).parent
        container_tool = script_dir / "va_container.py"
        note = f"LLM analysis ({args.model}, unverified): {args.prompt[:60]}"

        result = subprocess.run(
            [sys.executable, str(container_tool), "update", container, args.output,
             temp_path, "--note", note],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            result = subprocess.run(
                [sys.executable, str(container_tool), "add", container, temp_path,
                 "--name", args.output, "--role", "analysis", "--note", note],
                capture_output=True, text=True,
            )

        os.unlink(temp_path)

        if result.returncode != 0:
            print(f"ERROR: Failed to store response in container: {result.stderr}", file=sys.stderr)
            return 1

        print(f"Response stored in container: {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())