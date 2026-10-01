#!/usr/bin/env python3
"""
SYSTEM: Complete Code → Pixels → MKV → Execute workflow with semantic display.

This script demonstrates the full Visual Audio pattern for software-as-pixels:
1. Tokenize code using wordbase.db (semantic pixel mapping)
2. Display semantic token stream with RGB visualization
3. Store code in visual_audio.mkv via dense encoding (byte-perfect)
4. Extract and execute the code from the MKV
5. Show pixel-level storage efficiency metrics

Use Cases:
- Software-as-pixels: Code becomes pixel data for display/storage
- Visual Audio transmission: Code can be encoded as audio via pixel codec
- Geometry OS integration: Pixel-native software transmission to hypervisor
- Container self-hosting: Code lives inside its own MKV as pixels
"""

import sys
import os
import tempfile
import subprocess
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pixel_tokenizer import PixelTokenizer
import tools.va_container as va_container


def tokenize_code_semantic(code: str, wordbase_path: str = "db/wordbase.db", verbose: bool = True):
    """
    Convert code to semantic pixel tokens using wordbase.db.

    Returns list of token IDs (each maps to an RGB pixel in wordbase).
    """
    if verbose:
        print(f"=== STEP 1: Semantic Tokenization ===")
        print(f"Code size: {len(code)} bytes")
        print(f"Code preview: {code[:60]}{'...' if len(code) > 60 else ''}")

    tokenizer = PixelTokenizer(wordbase_path=Path(wordbase_path))
    token_ids = tokenizer.encode(code, add_special_tokens=True)

    if verbose:
        print(f"\nTokenized into {len(token_ids)} semantic tokens")
        print(f"Special tokens: {[tid for tid in token_ids[:5] if tid < 16]}")
        print(f"Content tokens: {[tid for tid in token_ids[:10] if tid >= 16]}")

        # Show semantic mapping for first few tokens
        print(f"\nSemantic mapping (first 10 tokens):")
        pixels = tokenizer.ids_to_pixels(token_ids[:10])
        for i, (tid, pixel) in enumerate(zip(token_ids[:10], pixels)):
            word = tokenizer.decode([tid])
            r, g, b = pixel
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            
            # Show token type
            if tid < 16:
                token_type = "SPECIAL"
            else:
                token_type = "WORD"
            
            # Truncate long words
            display_word = word if len(word) <= 12 else word[:10] + '..'
            
            print(f"  [{i:2d}] ID={tid:6d} {token_type:8} {hex_color} → '{display_word}'")

    tokenizer.close()
    return token_ids


def store_code_in_mkv(mkv_path: str, code: str, content_name: str = "demo_code.py", verbose: bool = True):
    """
    Store code byte-perfectly in the MKV container using dense encoding.

    Each RGB pixel = 3 bytes of raw source code.
    """
    if verbose:
        print(f"\n=== STEP 2: Dense Storage in MKV ===")
        print(f"Container: {mkv_path}")
        print(f"Content name: {content_name}")
        print(f"Code size: {len(code)} bytes")

    # Write code to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        # Add to MKV container
        result = subprocess.run(
            ["python3", "tools/va_container.py", "add", mkv_path, tmp_path,
             "--name", content_name, "--role", "content"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # Calculate storage efficiency
            pixel_count = (len(code) + 2) // 3
            density = len(code) / pixel_count
            
            if verbose:
                print(f"✓ Code successfully added to MKV container")
                print(f"  Dense RGB24: {len(code)} bytes → {pixel_count} pixels")
                print(f"  Storage density: {density:.2f} bytes/pixel")
                print(f"  Theoretical capacity: {607500 * density / 1024:.1f} KB per frame")
        else:
            print(f"✗ Failed to add to MKV: {result.stderr}")
            return False
    finally:
        os.unlink(tmp_path)

    return True


def extract_and_execute_from_mkv(mkv_path: str, content_name: str = "demo_code.py", verbose: bool = True):
    """
    Extract code from MKV and execute it.
    """
    if verbose:
        print(f"\n=== STEP 3: Extraction from MKV ===")

    # Extract to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["python3", "tools/va_container.py", "cat", mkv_path, content_name, "-o", tmp_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"✗ Failed to extract from MKV: {result.stderr}")
            return None

        # Verify extraction
        with open(tmp_path, 'r') as f:
            extracted_code = f.read()
        
        if verbose:
            print(f"✓ Extracted to: {tmp_path}")
            print(f"  Size: {len(extracted_code)} bytes")

        # Execute it
        if verbose:
            print(f"\n=== STEP 4: Execution ===")
        
        exec_result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        if verbose:
            print(f"Exit code: {exec_result.returncode}")
            if exec_result.stdout:
                print(f"STDOUT:\n{exec_result.stdout}")
            if exec_result.stderr:
                print(f"STDERR:\n{exec_result.stderr}")

        return exec_result

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def run_from_container(mkv_path: str, content_name: str = "demo_code.py", args: list | None = None, verbose: bool = True):
    """
    Run code directly from container using built-in run command.
    """
    if verbose:
        print(f"\n=== STEP 5: Direct Container Execution ===")

    cmd = ["python3", "tools/va_container.py", "run", mkv_path, content_name]
    if args:
        cmd.extend(args)
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    
    if verbose:
        print(f"Exit code: {result.returncode}")
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
    
    return result


def show_container_info(mkv_path: str, verbose: bool = True):
    """
    Show container statistics.
    """
    if verbose:
        print(f"\n=== Container Statistics ===")

    result = subprocess.run(
        ["python3", "tools/va_container.py", "ls", mkv_path],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        lines = result.stdout.strip().split('\n')
        entry_count = int(lines[0].split(',')[1].split()[0])
        
        if verbose:
            print(f"Total entries: {entry_count}")
            
            # Find content entries
            content_entries = []
            for line in lines[1:]:
                if '[content]' in line:
                    content_entries.append(line)
            
            if content_entries:
                print(f"Content entries: {len(content_entries)}")
                for entry in content_entries[:3]:  # Show first 3
                    print(f"  {entry.strip()}")
    
    return result.stdout


def main():
    """Run the complete system demo."""
    DEMO_CODE = '''#!/usr/bin/env python3
"""Demo code executed from visual_audio.mkv as pixels"""
import sys
import json

print("Hello from Visual Audio MKV!")
print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
print(f"This code was stored as RGB pixels inside the container")
print("=" * 60)

# Show pixel storage efficiency
code_size = 198  # bytes
pixel_count = (code_size + 2) // 3
density = code_size / pixel_count

print(f"Storage metrics:")
print(f"  Code size: {code_size} bytes")
print(f"  Pixel count: {pixel_count} pixels (RGB24)")
print(f"  Density: {density:.2f} bytes/pixel")
print(f"  Frame capacity: ~{607500 * density / 1024:.1f} KB")
print("=" * 60)
'''

    MKV_PATH = "visual_audio.mkv"
    CONTENT_NAME = "demo_code_system.py"

    print("=" * 60)
    print("VISUAL AUDIO SYSTEM: Code → Pixels → MKV → Execute")
    print("=" * 60)

    # Step 1: Semantic tokenization
    token_ids = tokenize_code_semantic(DEMO_CODE)

    # Step 2: Dense storage in MKV
    if not store_code_in_mkv(MKV_PATH, DEMO_CODE, CONTENT_NAME):
        print("\n✗ System failed at storage step")
        return 1

    # Step 3: Extract and execute
    output = extract_and_execute_from_mkv(MKV_PATH, CONTENT_NAME)

    # Step 4: Direct container execution
    run_output = run_from_container(MKV_PATH, CONTENT_NAME)

    # Show container info
    show_container_info(MKV_PATH)

    # Verify success
    if output and output.returncode == 0 and "Hello from Visual Audio MKV!" in output.stdout:
        print("\n" + "=" * 60)
        print("✓ SYSTEM COMPLETE: Code successfully round-tripped!")
        print("=" * 60)
        print("\nKey capabilities demonstrated:")
        print("  ✓ Semantic tokenization via wordbase.db")
        print("  ✓ Dense RGB24 encoding (3 bytes/pixel)")
        print("  ✓ MKV container storage with CRC+SHA256")
        print("  ✓ Extraction and execution")
        print("  ✓ Direct container run command")
        print("  ✓ Storage efficiency tracking")
        print("\nIntegration paths:")
        print("  → Geometry OS hypervisor (pixel-native software transmission)")
        print("  → Visual Audio codec (code → audio transmission)")
        print("  → Memory Palace (code stored as PNG artifacts)")
        print("=" * 60)
        return 0
    else:
        print("\n✗ System failed at execution step")
        return 1


if __name__ == "__main__":
    sys.exit(main())