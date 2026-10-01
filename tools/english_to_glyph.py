#!/usr/bin/env python3
"""
English → Glyph ISA Spatial Compiler

Parses plain English commands into GlyphISA v2 assembly for spatial execution.

This is the FRONT DOOR for the "voice" pipeline in Geometry OS:
  LLM speaks English → this compiler → .glyph assembly → PNG pixels → audio → execution

Unlike src/nlp/natural_language_compiler.py (which compiles to Python), this tool
compiles to Glyph ISA assembly for direct spatial execution on Geometry OS.

Pipeline:
    English text
        → parse_english_to_glyph()          (this file)
        → .glyph assembly file
        → GlyphAssemblerV2 (from glyph_isa_v2.py)
        → RGB pixels (.png)
        → [--speak] speak_glyph.py → dual-band WAV
        → pixel_os_listener.py (provenance-gated execution)

Usage:
    python3 tools/english_to_glyph.py "draw a red rectangle at 10,20 size 100x50"
    python3 tools/english_to_glyph.py "clear the screen" --speak
    python3 tools/english_to_glyph.py "boot linux in a window" -o boot.glyph --speak
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# Add tools/ (for direct glyph_isa_v2 import) and the project root
# (glyph_isa_v2 does `from tools.wordbase import ...`, which needs the root
# on sys.path even when this script itself runs as tools/english_to_glyph.py)
tools_path = Path(__file__).parent.absolute()
sys.path.insert(0, str(tools_path))
sys.path.insert(0, str(tools_path.parent))

try:
    from glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
    GLYPH_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: GlyphAssemblerV2 not found: {e}")
    GLYPH_AVAILABLE = False


# Semantic intent patterns for English → Glyph mapping
# Each intent maps to a Glyph macro
SEMANTIC_INTENTS = [
    {
        "patterns": [r"clear( the)? screen", r"clear pixels", r"reset screen"],
        "macro": "CLEAR_SCREEN",
        "handler": lambda m: {}
    },
    {
        "patterns": [r"draw (a )?(red|green|blue|white|black|yellow|cyan|magenta) rectangle at (\d+),\s*(\d+)(?: size (\d+)x(\d+))?"],
        "macro": "DRAW_RECT",
        "handler": lambda m: {
            "color": COLOR_MAP[m.group(2)],
            "x": int(m.group(3)) if m.group(3) else 0,
            "y": int(m.group(4)) if m.group(4) else 0,
            "w": int(m.group(5)) if m.group(5) else 100,
            "h": int(m.group(6)) if m.group(6) else 50,
        }
    },
    {
        "patterns": [r"draw (a )?(red|green|blue|white|black|yellow|cyan|magenta) pixel at (\d+),\s*(\d+)"],
        "macro": "DRAW_PIXEL",
        "handler": lambda m: {
            "color": COLOR_MAP[m.group(2)],
            "x": int(m.group(3)),
            "y": int(m.group(4)),
        }
    },
    {
        "patterns": [r"boot linux( in a window)?"],
        "macro": "BOOT_LINUX",
        "handler": lambda m: {
            "container_addr": 0x8000_0000,  # Default container address
            "flags": 0x05,  # 0x01 (graphical) | 0x04 (cognitive)
        }
    },
    {
        "patterns": [r"store code( at (0x[0-9a-fA-F]+|\d+)(?: to (0x[0-9a-fA-F]+|\d+))?(?: size (0x[0-9a-fA-F]+|\d+))?)?"],
        "macro": "STORE_CODE",
        "handler": lambda m: {
            "dest_addr": int(m.group(2), 16) if m.group(2) and m.group(2).startswith('0x') else (int(m.group(2)) if m.group(2) else 0x1000),
            "src_addr": int(m.group(3), 16) if m.group(3) and m.group(3).startswith('0x') else (int(m.group(3)) if m.group(3) else 0x2000),
            "length": int(m.group(4), 16) if m.group(4) and m.group(4).startswith('0x') else (int(m.group(4)) if m.group(4) else 256),
        }
    },
]


# Glyph ISA macros (templates)
GLYPH_MACROS = {
    "CLEAR_SCREEN": "LDI r1 0; LDI r2 0; LDI r3 0; HALT",
    "DRAW_RECT": "LDI r1 {x}; LDI r2 {y}; LDI r3 {w}; LDI r4 {h}; LDI r5 {color}; HALT",
    "DRAW_PIXEL": "LDI r1 {x}; LDI r2 {y}; LDI r3 {color}; HALT",
    # SYSCALL implementations with proper parameters
    "BOOT_LINUX": "LDI r1 {container_addr}; LDI r2 {flags}; SYSCALL r3 0x10; HALT",  # 0x10 = BOOT_LINUX
    "STORE_CODE": "LDI r1 {dest_addr}; LDI r2 {src_addr}; LDI r3 {length}; SYSCALL r4 0x11; HALT",  # 0x11 = STORE_CODE
}


# Color name to Glyph register value mapping
COLOR_MAP = {
    "red": 0xFF0000,
    "green": 0x00FF00,
    "blue": 0x0000FF,
    "white": 0xFFFFFF,
    "black": 0x000000,
    "yellow": 0xFFFF00,
    "cyan": 0x00FFFF,
    "magenta": 0xFF00FF,
    "gray": 0x808080,
    "orange": 0xFFA500,
}


def parse_english_to_glyph(text: str) -> Tuple[Optional[str], Optional[str], Dict]:
    """
    Parse a plain English sentence into Glyph ISA assembly.

    Args:
        text: Plain English command

    Returns:
        (assembly_text, macro_name, params)
    """
    text = text.lower().strip()

    for intent in SEMANTIC_INTENTS:
        for pattern in intent["patterns"]:
            match = re.search(pattern, text)
            if match:
                macro = intent["macro"]
                params = intent["handler"](match)

                template = GLYPH_MACROS.get(macro)
                if template:
                    assembly = template.format(**params)
                    return assembly, macro, params

    return None, None, {}


def write_glyph_source(assembly: str, glyph_path: Path) -> List[str]:
    """
    Write ';' joined assembly as .glyph source, one instruction per line.

    Args:
        assembly: Semicolon-joined assembly string
        glyph_path: Output .glyph file path

    Returns:
        List of instruction lines
    """
    lines = [line.strip() for line in assembly.replace(';', '\n').split('\n') if line.strip()]
    glyph_path.write_text('\n'.join(lines) + '\n')
    return lines


def assemble_to_pixels(lines: List[str], output_path: Optional[Path] = None) -> Optional[Path]:
    """
    Compile .glyph instruction lines to a pixel image via GlyphAssemblerV2.

    Args:
        lines: List of assembly instruction lines
        output_path: Output PNG path

    Returns:
        Path to saved PNG, or None if GlyphAssemblerV2 not available
    """
    if not GLYPH_AVAILABLE:
        print("[SIMULATED] GlyphAssemblerV2 not available - skipping pixel compilation")
        return None

    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)

    try:
        image = assembler.assemble(lines)
    finally:
        op_map.close()

    if output_path:
        from PIL import Image
        img = Image.fromarray(image.astype('uint8'), 'RGB')
        img.save(output_path)
        print(f"✓ Saved pixel program to: {output_path}")

    return output_path


def speak_program(glyph_path: Path, wav_path: Path, private_key: str, narration: str):
    """
    Encode the .glyph file as a signed dual-band WAV via speak_glyph.py's functions.

    Args:
        glyph_path: Path to .glyph source file
        wav_path: Output WAV path
        private_key: Path to Ed25519 private key
        narration: Spoken narration for the low band
    """
    if not GLYPH_AVAILABLE:
        print("[SIMULATED] speak_glyph integration not available")
        return

    from speak_glyph import encode_glyph, encode_ops_to_audio

    ops = encode_glyph(str(glyph_path))
    audio = encode_ops_to_audio(ops, private_key, narration, str(wav_path))

    duration = len(audio) / 44100  # speak_glyph uses 44100Hz
    print(f"✓ Saved signed voice program to: {wav_path} ({duration:.1f}s)")

    print(f"  Play with: aplay {wav_path}")
    print(f"  Execute via:")
    print(f"    python3 tools/pixel_os_listener.py --fb /tmp/framebuffer.png \\")
    print(f"      --provenance --enable-driver-ops --driver-output-dir /tmp/drivers \\")
    print(f"      --public-key keys/pixel_os_public.pem --queue --watch-dir ./")


def main():
    parser = argparse.ArgumentParser(
        description="Compile Plain English to Glyph ISA Spatial Programs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "command",
        help="Plain English command (e.g., 'draw a red rectangle at 10,20 size 100x50')"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        default="output_program.png",
        help="Output PNG path (default: output_program.png)"
    )

    parser.add_argument(
        "-g", "--glyph-output",
        type=str,
        default="output_program.glyph",
        help="Output .glyph source path (default: output_program.glyph)"
    )

    parser.add_argument(
        "--speak",
        action="store_true",
        help="Also encode the program as a signed dual-band WAV via speak_glyph.py"
    )

    parser.add_argument(
        "--wav-output",
        type=str,
        default="output_program.wav",
        help="WAV output path when --speak is used (default: output_program.wav)"
    )

    parser.add_argument(
        "--private-key",
        type=str,
        default="keys/pixel_os_private.pem",
        help="Ed25519 private key path for signing (default: keys/pixel_os_private.pem)"
    )

    parser.add_argument(
        "--narration",
        type=str,
        default=None,
        help="Spoken narration for the low band when --speak (default: derived from command)"
    )

    args = parser.parse_args()

    print(f"🎙️  Listening: {args.command}\n")

    # Parse English to Glyph assembly
    assembly, macro_name, params = parse_english_to_glyph(args.command)

    if not assembly:
        print("❌ Could not map spoken command to a spatial intent.")
        print("   Supported patterns:")
        for intent in SEMANTIC_INTENTS:
            print(f"     - {' / '.join(intent['patterns'][:2])}")
        return 1

    print(f"🧠 Intent Recognized: {macro_name}")
    if params:
        print(f"   Parameters: {params}")
    print(f"\n⚙️  Generated Spatial Assembly (GlyphISA v2):")
    print(f"   {assembly}\n")

    # Write .glyph source file
    glyph_path = Path(args.glyph_output)
    lines = write_glyph_source(assembly, glyph_path)
    print(f"✓ Saved .glyph source to: {glyph_path}")

    # Assemble to pixels
    output_path = Path(args.output)
    saved = assemble_to_pixels(lines, output_path)
    if not saved:
        print("\n❌ Pixel compilation was skipped (GlyphAssemblerV2 unavailable) — no PNG was written.",
              file=sys.stderr)
        return 1

    # Optional: Speak to WAV
    if args.speak:
        private_key = args.private_key
        if not Path(private_key).exists():
            # Not on cwd-relative disk -- check the container's extraction dir,
            # if we're running under `va_container.py run` (VA_RUN_DIR is set).
            run_dir = os.environ.get("VA_RUN_DIR")
            if run_dir and (Path(run_dir) / args.private_key).exists():
                private_key = str(Path(run_dir) / args.private_key)
            else:
                print(f"❌ --speak requires private key, not found: {args.private_key}", file=sys.stderr)
                return 1

        wav_path = Path(args.wav_output)
        narration = args.narration or f"Executing {macro_name} from {glyph_path.name}"
        speak_program(glyph_path, wav_path, private_key, narration)

    print(f"\n✅ Pixel spatial program successfully compiled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())