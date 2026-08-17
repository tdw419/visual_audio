#!/usr/bin/env python3
"""Verify pixel-interpreter execution against golden reference."""

from pathlib import Path
import argparse
import numpy as np
from PIL import Image

def load_state_row(img_path: Path) -> dict:
    """Load state row (y=0) from a state PNG and return as dict."""
    img = Image.open(img_path).convert("RGBA")
    arr = np.asarray(img, dtype=np.uint32)
    
    pc_state = arr[0, 0]
    acc_state = arr[0, 1]
    flag_state = arr[0, 2]
    
    return {
        "pc": (int(pc_state[0]), int(pc_state[1])),
        "pc_x": int(pc_state[0]),
        "pc_y": int(pc_state[1]),
        "halt_flag": int(pc_state[2]),
        "accumulator": int(acc_state[0]),
        "zero_flag": int(flag_state[0]),
    }

def verify_state(state: dict, expected: dict) -> bool:
    """Verify state matches expected values."""
    errors = []

    if "accumulator" in expected and state["accumulator"] != expected["accumulator"]:
        errors.append(f"Accumulator: {state['accumulator']} != {expected['accumulator']}")

    if "zero_flag" in expected and state["zero_flag"] != expected["zero_flag"]:
        errors.append(f"Zero Flag: {state['zero_flag']} != {expected['zero_flag']}")

    if "halt_flag" in expected and state["halt_flag"] != expected["halt_flag"]:
        errors.append(f"Halt Flag: {state['halt_flag']} != {expected['halt_flag']}")

    if "pc_x" in expected and state["pc_x"] != expected["pc_x"]:
        errors.append(f"PC X: {state['pc_x']} != {expected['pc_x']}")
    
    if "pc_y" in expected and state["pc_y"] != expected["pc_y"]:
        errors.append(f"PC Y: {state['pc_y']} != {expected['pc_y']}")
    
    if errors:
        for err in errors:
            print(f"✗ {err}")
        return False
    
    print("✓ All checks passed")
    return True

def main():
    parser = argparse.ArgumentParser(description="Verify pixel-interpreter state PNG")
    parser.add_argument("state_png", type=Path, help="State PNG to verify")
    parser.add_argument("--acc", type=int, help="Expected accumulator")
    parser.add_argument("--zf", type=int, help="Expected zero flag")
    parser.add_argument("--halt", type=int, help="Expected halt flag")
    parser.add_argument("--pcx", type=int, help="Expected PC X")
    parser.add_argument("--pcy", type=int, help="Expected PC Y")
    args = parser.parse_args()
    
    state = load_state_row(args.state_png)
    print(f"=== State from {args.state_png} ===")
    print(f"PC: ({state['pc_x']}, {state['pc_y']})")
    print(f"Accumulator: {state['accumulator']}")
    print(f"Zero Flag: {state['zero_flag']}")
    print(f"Halt Flag: {state['halt_flag']}")
    print()
    
    expected = {}
    if args.acc is not None:
        expected["accumulator"] = args.acc
    if args.zf is not None:
        expected["zero_flag"] = args.zf
    if args.halt is not None:
        expected["halt_flag"] = args.halt
    if args.pcx is not None:
        expected["pc_x"] = args.pcx
    if args.pcy is not None:
        expected["pc_y"] = args.pcy
    
    success = verify_state(state, expected)
    exit(0 if success else 1)

if __name__ == "__main__":
    main()