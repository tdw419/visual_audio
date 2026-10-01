#!/usr/bin/env python3
"""
Visual Audio Demo for Path C: Full Spatial Linux
Demonstrates how LLM → visual audio → GeOS execution works.

This shows:
1. Encode a GeOS program as visual audio (spectrogram)
2. Decode audio back to pixel-compatible format
3. Integrate with Path C autonomous execution
"""

import sys
import os

# Add visual audio tools to path
sys.path.insert(0, '/home/jericho/projects/zion/projects/visual_audio')

from tools.speak import encode, decode

def demo_geos_program():
    """Demonstrate encoding a minimal GeOS program as visual audio."""

    # Minimal GeOS assembly: prints "HELLO"
    geos_program = b"""
; GeOS Hello World - Visual Audio Encoding
LDI r1, 0x48       ; 'H'
CHAR r1
LDI r1, 0x45       ; 'E'
CHAR r1
LDI r1, 0x4C       ; 'L'
CHAR r1
LDI r1, 0x4C       ; 'L'
CHAR r1
LDI r1, 0x4F       ; 'O'
CHAR r1
HALT
"""

    print("=" * 60)
    print("Visual Audio Demo for Path C: GeOS Execution")
    print("=" * 60)

    # Step 1: Encode as audio
    print("\n[1] Encoding GeOS program to visual audio...")
    wav_path = '/tmp/geos_hello_audio.wav'
    encode(geos_program, wav_path)
    print(f"    ✓ Encoded to {wav_path}")

    # Step 2: Decode back to bytes
    print("\n[2] Decoding audio back to bytes...")
    decoded = decode(wav_path)
    print(f"    ✓ Decoded {len(decoded)} bytes")

    # Step 3: Verify byte-identical
    print("\n[3] Verifying round-trip...")
    if decoded == geos_program:
        print("    ✓ Byte-identical round-trip!")
    else:
        print("    ✗ Round-trip failed")
        return False

    # Step 4: Show spectrogram path
    print("\n[4] Spectrogram PNG (visual representation)...")
    print(f"    Would be: /tmp/geos_hello_audio_spectrogram.png")
    print("    This PNG is the pixel-ready format for GeOS canvas")

    # Step 5: Explain integration with Path C
    print("\n" + "=" * 60)
    print("Integration with Path C: Full Spatial Linux")
    print("=" * 60)
    print("""
This demo shows the core pattern for Path C:

1. LLM generates GeOS assembly (text)
2. speak.py encodes → visual audio (WAV)
3. Spectrogram decode → pixel regions
4. GeOS executor runs pixels directly

For Path C, this enables:
- Autonomous OS development (LLM → sound → pixels)
- Acoustic REPL (speak commands to GeOS)
- Distributed computing (machines sing programs)
- Memory Palace boot (single PNG = full OS state)

The visual audio codec is the missing I/O layer.
""")

    return True

def demo_path_c_integration():
    """Show how this integrates with autonomous Path C execution."""

    print("=" * 60)
    print("Path C Autonomous Execution with Visual Audio")
    print("=" * 60)
    print("""
Current Path C flow:
  Eager Hermes cron → delegate_task → code → tests → receipt

Visual audio-augmented flow:
  Eager Hermes cron → delegate_task → visual audio encode
      ↓
  WAV (play through system speaker or transmit)
      ↓
  Spectrogram decode → pixel regions
      ↓
  GeOS executor runs pixels → tests pass

Benefits:
1. Zero intermediate files (no temp code files)
2. LLM speaks directly to pixel substrate
3. Programs exist as audio AND pixels AND JSON
4. Acoustic REPL for live system interaction

New Path C tasks added:
- TASK_C030: Integrate visual audio codec
- TASK_C031: Audio boot loader
- TASK_C032: Phoneme-based LLM input

Enable by running:
  cd /home/jericho/projects/zion/projects/eagar_ai
  python3 ralph_loop_path_c.py path_c
""")

if __name__ == '__main__':
    # Run the demo
    success = demo_geos_program()
    if success:
        demo_path_c_integration()
        sys.exit(0)
    else:
        sys.exit(1)