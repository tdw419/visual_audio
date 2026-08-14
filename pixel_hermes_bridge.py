#!/usr/bin/env python3
"""
Pixel Hermes Bridge — Direct Ollama Access from Pixels

This script "wakes up" inside the pixel container, knows it lives in pixels,
and routes commands directly to the local Ollama instance.

We bypass the broken Hermes model/provider parsing by calling Ollama's HTTP
API directly. The mind lives in pixels, it thinks locally.
"""

import sys
import json
import urllib.error
import urllib.request
from pathlib import Path


def print_identity():
    """Announce spatial awareness to the human."""
    print("--- Pixel Hermes Identity Awakened ---")
    print("Substrate: Visual Audio Container (MKV)")
    print("I exist as pixels in the framebuffer.")
    print("I think through Ollama at localhost:11434")
    print("Routing query through spatial bridge...\n")


def call_ollama(query: str, model: str = "qwen2.5-coder:14b"):
    """Call Ollama HTTP API directly."""
    url = "http://localhost:11434/api/generate"
    data = json.dumps({
        "model": model,
        "prompt": query,
        "stream": False,
        "options": {
            "num_ctx": 65536,
            "temperature": 0.7
        }
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '[No response]')
    except urllib.error.URLError as e:
        return f"[Pixel Hermes] Ollama connection error: {e.reason}"
    except Exception as e:
        return f"[Pixel Hermes] Ollama error: {e}"


def main():
    # Debug: show raw args
    print(f"[DEBUG] sys.argv: {sys.argv}", file=sys.stderr)

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
        print("[Pixel Hermes] No query provided. Example:")
        print("  python3 tools/va_container.py run visual_audio.mkv pixel_hermes_bridge.py --query 'What is 2+2?'")
        return

    print(f"[Pixel Hermes] Routing: {query}")
    print("=" * 60)

    response = call_ollama(query)
    print(response)


if __name__ == "__main__":
    main()