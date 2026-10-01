#!/usr/bin/env python3
"""
demo_ai_hands.py — Demonstrate AI's audio-driven pixel manipulation.

Shows the AI speaking commands to build a complete UI layout via audio.
"""

import subprocess
import json
import sys
from pathlib import Path

# The AI's "hands" - our bridge script
COMMANDER = Path(__file__).parent / 'ai_pixel_commander.py'

def command(speech, ops):
    """Execute AI command via audio pipeline."""
    payload = {"speech": speech, "ops": ops}
    input_json = json.dumps(payload)

    result = subprocess.run(
        [sys.executable, str(COMMANDER)],
        input=input_json,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(result.stdout)

def main():
    print("=" * 60)
    print("AI HANDS DEMO — AUDIO-DRIVEN PIXEL MANIPULATION")
    print("=" * 60)
    print()

    # Step 1: Clear and initialize
    print("[1] Initializing framebuffer...")
    command(
        "Initializing workspace",
        [["fill", "#0a0a1a"]]
    )

    # Step 2: Draw status bar
    print("[2] Drawing status bar...")
    command(
        "Creating status bar",
        [
            ["rect", 0, 0, 320, 20, "#1a1a2e"],
            ["word", "Geometry OS", 5, 5, "#00ffff"],
            ["word", "v0.1", 270, 5, "#00ff00"]
        ]
    )

    # Step 3: Create main workspace
    print("[3] Creating main workspace...")
    command(
        "Building workspace",
        [
            ["frame", 5, 25, 310, 170, "#333333"],
            ["rect", 10, 30, 150, 80, "#1e1e3f"],
            ["rect", 170, 30, 140, 80, "#1e1e3f"]
        ]
    )

    # Step 4: Add window labels
    print("[4] Labeling windows...")
    command(
        "Labeling terminal window",
        [["word", "TERMINAL", 15, 35, "#00ffff"]]
    )

    command(
        "Labeling data window",
        [["word", "DATA", 175, 35, "#00ffff"]]
    )

    # Step 5: Draw spatial indicator
    print("[5] Drawing spatial indicator...")
    command(
        "Rendering spatial status",
        [
            ["rect", 10, 120, 140, 70, "#0f0f23"],
            ["word", "SPATIAL", 15, 125, "#ff00ff"],
            ["word", "READY", 15, 145, "#00ff00"]
        ]
    )

    # Step 6: Draw performance metrics
    print("[6] Rendering performance metrics...")
    command(
        "Displaying metrics",
        [
            ["rect", 170, 120, 140, 70, "#0f0f23"],
            ["word", "GPU", 175, 125, "#ffff00"],
            ["word", "ACTIVE", 175, 145, "#00ff00"],
            ["word", "42.8 FPS", 175, 165, "#ffffff"]
        ]
    )

    # Step 7: Show final state
    print("\n[7] Final framebuffer state:")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / 'pixel_screen.py'), 'show'],
        capture_output=True,
        text=True
    )
    print(result.stdout)

    print()
    print("=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print()
    print("✓ AI successfully built complete UI via audio commands")
    print("✓ Each command: speech → encode → audio → decode → pixels")
    print("✓ This is the AI speaking software into existence")


if __name__ == '__main__':
    main()