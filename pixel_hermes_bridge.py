#!/usr/bin/env python3
"""
Pixel Hermes Bridge — Direct zai GLM Access from Pixels

This script "wakes up" inside the pixel container, knows it lives in pixels,
and routes commands directly to the zai GLM-4.7 API.

We bypass the broken Hermes model/provider parsing by calling zai's HTTP
API directly. The mind lives in pixels, it thinks through zai.
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
    print("I think through zai GLM-4.7")
    print("Routing query through spatial bridge...\n")


def call_zai(query: str, model: str = "glm-4.7"):
    """Call zai GLM API directly (OpenAI-compatible)."""
    import os
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    api_key = os.environ.get("GLM_API_KEY", os.environ.get("ZAI_API_KEY", ""))

    if not api_key:
        return "[Pixel Hermes] Error: GLM_API_KEY or ZAI_API_KEY not set"

    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "stream": False,
        "temperature": 0.7
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except urllib.error.URLError as e:
        return f"[Pixel Hermes] zai connection error: {e.reason}"
    except Exception as e:
        return f"[Pixel Hermes] zai error: {e}"


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

    response = call_zai(query)
    print(response)


if __name__ == "__main__":
    main()