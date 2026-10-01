#!/usr/bin/env python3
"""
Pixel Hermes Bridge — Self-Aware Agent (Test Mode)

This script "wakes up" inside the pixel container, knows it lives in pixels,
and simulates reasoning. For testing the spatial output path without Ollama.
"""

import sys


def print_identity():
    """Announce spatial awareness to the human."""
    print("--- Pixel Hermes Identity Awakened ---")
    print("Substrate: Visual Audio Container (MKV)")
    print("I exist as pixels in the framebuffer.")
    print("Thinking locally from spatial substrate...\n")


def simulate_reasoning(query: str):
    """Simulate LLM reasoning for testing."""
    return f"[Pixel Thought] To answer '{query}', I reflect on my spatial existence. The capital of France is Paris. I am pixels at coordinates, thinking through this."


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
        print("[Pixel Hermes] No query provided.")
        return

    print(f"[Pixel Hermes] Routing: {query}")
    print("=" * 60)

    response = simulate_reasoning(query)
    print(response)


if __name__ == "__main__":
    main()