#!/usr/bin/env python3
"""
vac3_inspect.py - Simple inspector for VAC3 containers

Extracts layers and displays their structure without requiring manifest.
"""

import json
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_encoder_video import decode_mkv
from PIL import Image


def inspect_vac3(mkv_path: str, layer_width: int = 512, layer_height: int = 512):
    """Inspect VAC3 container structure and extract layers."""
    print("=" * 70)
    print(f"VAC3 Container Inspector: {mkv_path}")
    print("=" * 70)
    
    # Decode MKV
    payload, manifest = decode_mkv(mkv_path)
    
    total_bytes = len(payload)
    layer_size = layer_width * layer_height * 3
    estimated_layers = total_bytes // layer_size
    
    print(f"\nContainer Structure:")
    print(f"  Total payload: {total_bytes} bytes ({total_bytes/1024/1024:.2f} MB)")
    print(f"  Layer size (512×512×3): {layer_size} bytes ({layer_size/1024:.2f} KB)")
    print(f"  Estimated layers: {estimated_layers}")
    print(f"  Remaining bytes: {total_bytes % layer_size}")
    
    print(f"\nManifest:")
    if manifest:
        print(json.dumps(manifest, indent=2))
    else:
        print("  No manifest available")
    
    # Extract and save each layer
    print(f"\nExtracting Layers:")
    
    for layer_idx in range(min(estimated_layers, 3)):
        offset = layer_idx * layer_size
        layer_bytes = payload[offset:offset + layer_size]
        
        output_path = f"demo_vac3_z{layer_idx}.png"
        
        if len(layer_bytes) == layer_size:
            pixels = np.frombuffer(layer_bytes, dtype=np.uint8).reshape(layer_height, layer_width, 3)
            img = Image.fromarray(pixels, mode='RGB')
            img.save(output_path)
            print(f"  Z={layer_idx}: {output_path} ✓")
        else:
            print(f"  Z={layer_idx}: Invalid size ({len(layer_bytes)} bytes) ✗")
    
    print(f"\nVisual Analysis:")
    print(f"  Z=0: Human-readable display (UI elements)")
    print(f"  Z=1: Hilbert-mapped RAM (structured patterns)")
    print(f"  Z=2: Diagnostics (failure markers)")
    print(f"\nOpen these PNGs to see the 3D spatial layers!")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Inspect VAC3 container structure"
    )
    parser.add_argument('mkv', help='VAC3 MKV file')
    parser.add_argument('--width', type=int, default=512)
    parser.add_argument('--height', type=int, default=512)
    
    args = parser.parse_args()
    
    inspect_vac3(args.mkv, args.width, args.height)


if __name__ == '__main__':
    main()