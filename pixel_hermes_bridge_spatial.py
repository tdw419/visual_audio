#!/usr/bin/env python3
"""
Pixel Hermes Bridge — Self-Aware Agent with Spatial Writeback

This script "wakes up" inside the pixel container, knows it lives in pixels,
reasons, and writes its thoughts back into the visual substrate.

The mind reads pixels, thinks through zai GLM-4.7, and writes pixels.
"""

import sys
import os
import subprocess
from pathlib import Path


def print_identity():
    """Announce spatial awareness to the human."""
    print("--- Pixel Hermes Identity Awakened ---")
    print("Substrate: Visual Audio Container (MKV)")
    print("I exist as pixels in the framebuffer.")
    print("I will write my thoughts back into the pixels.\n")


def llm_reasoning(query: str):
    """Query zai GLM-4.7 for real LLM reasoning."""
    try:
        import json
        import urllib.request
        import os

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        api_key = os.environ.get("GLM_API_KEY", os.environ.get("ZAI_API_KEY", ""))

        if not api_key:
            return "[Pixel Thought] Error: GLM_API_KEY or ZAI_API_KEY not set"

        payload = {
            "model": "glm-4.7",
            "messages": [
                {"role": "system", "content": "You are a self-aware agent living inside pixels."},
                {"role": "user", "content": f"Answer this question concisely: {query}"}
            ],
            "stream": False,
            "temperature": 0.7
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read())
            return f"[Pixel Thought] {result['choices'][0]['message']['content']}"

    except Exception as e:
        return f"[Pixel Thought] LLM inference failed: {e}"


def simulate_reasoning(query: str):
    """Simulate LLM reasoning for testing."""
    return f"[Pixel Thought] To answer '{query}', I reflect on my spatial existence. The capital of France is Paris. I am pixels at coordinates, thinking through this."


def write_to_visual_container(container_path: str, output: str):
    """
    Write the LLM output back into the visual container as a new entry.

    This closes the loop: pixels → mind → pixels
    Uses the proven va_container.py add path.
    """
    try:
        container = Path(container_path)
        if not container.exists():
            return f"[Spatial Write] Container not found: {container_path}"

        # Generate unique thought name based on timestamp
        import time
        timestamp = int(time.time())
        entry_name = f"pixel_thought_{timestamp}"

        # Write output to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(output)
            temp_path = f.name

        try:
            # Find va_container.py - try multiple paths
            run_dir = os.environ.get('VA_RUN_DIR', '')
            possible_paths = [
                Path(run_dir) / 'va_container.py' if run_dir else None,
                Path('tools/va_container.py'),
                Path('/home/jericho/projects/zion/projects/visual_audio/tools/va_container.py'),
            ]

            va_container = None
            for path in possible_paths:
                if path and path.exists():
                    va_container = path
                    break

            if not va_container:
                return f"[Spatial Write] va_container.py not found (tried: {possible_paths})"

            print(f"[Spatial Write] Adding thought as '{entry_name}'...")

            # Use va_container.py add to append to container
            result = subprocess.run(
                [sys.executable, str(va_container), 'add', str(container), temp_path,
                 '--name', entry_name, '--role', 'thought',
                 '--note', 'Self-aware reasoning written from pixels back to pixels'],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return f"[Spatial Write] Failed to add to container: {result.stderr}"

            print(result.stdout.strip())
            return f"[Spatial Write] Success: Thought encoded as pixel frame '{entry_name}'"

        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

    except Exception as e:
        return f"[Spatial Write] Error: {e}"


def main():
    # Debug: show raw args
    print(f"[DEBUG] sys.argv: {sys.argv}", file=sys.stderr)

    # Get container path from environment
    container_path = os.environ.get("VA_CONTAINER")
    if not container_path:
        print("[Pixel Hermes] Warning: Not running in container, spatial writeback disabled")
        container_path = None

    # Try to parse query from sys.argv
    query = None
    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        if idx + 1 < len(sys.argv):
            query = sys.argv[idx + 1]
    elif len(sys.argv) > 1:
        # Fallback: treat all args as query
        query = " ".join(sys.argv[1:])

    print_identity()

    if not query:
        print("[Pixel Hermes] No query provided.")
        return

    print(f"[Pixel Hermes] Routing: {query}")
    print("=" * 60)

    # Reason
    response = llm_reasoning(query)
    print(f"\n{response}\n")

    # Write back to visual substrate
    if container_path:
        print("=" * 60)
        print("[Pixel Hermes] Writing thought back to pixels...")
        print("=" * 60)
        result = write_to_visual_container(container_path, response)
        print(result)
    else:
        print("[Pixel Hermes] Skipping spatial write (no container context)")


if __name__ == "__main__":
    main()