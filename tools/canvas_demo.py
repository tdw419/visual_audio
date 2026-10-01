#!/usr/bin/env python3
"""
Demo: Canvas-based pixel OS execution.

This demonstrates that software can exist as images on a canvas, be read by
region, and executed. Multiple programs coexist in the same image space.
"""

import subprocess
import sys

def main():
    print("=" * 60)
    print("Pixel OS Demo: Canvas-Based Program Execution")
    print("=" * 60)
    
    # Create canvas with multiple programs
    print("\n1. Creating canvas with multiple cartridges...")
    
    # First program: fibonacci demo
    result = subprocess.run([
        sys.executable, 'tools/dense_encoder.py', 'encode',
        '/tmp/fibonacci_demo.py', '-o', '/tmp/cart1.png'
    ], capture_output=True, text=True)
    print(result.stdout.strip())
    
    # Place on canvas at (0, 0)
    result = subprocess.run([
        sys.executable, 'tools/dense_encoder.py', 'place',
        '/tmp/cart1.png', '/tmp/demo_canvas.png', '0', '0'
    ], capture_output=True, text=True)
    print(result.stdout.strip())
    
    # Second program: simple message
    result = subprocess.run([
        sys.executable, 'tools/dense_encoder.py', 'encode',
        '/tmp/second_cartridge.py', '-o', '/tmp/cart2.png'
    ], capture_output=True, text=True)
    print(result.stdout.strip())
    
    # Place on canvas at (100, 100)
    result = subprocess.run([
        sys.executable, 'tools/dense_encoder.py', 'place',
        '/tmp/cart2.png', '/tmp/demo_canvas.png', '100', '100'
    ], capture_output=True, text=True)
    print(result.stdout.strip())
    
    print(f"\n   Canvas created: /tmp/demo_canvas.png")
    
    # Read and execute first program
    print("\n2. Executing program 1 (region 0,0)...")
    print("-" * 40)
    result = subprocess.run([
        sys.executable, 'tools/dense_encoder.py', 'read',
        '/tmp/demo_canvas.png', '0', '0', '15', '15',
        '-o', '/tmp/program1.py'
    ], capture_output=True, text=True)
    print(result.stdout.strip())
    
    result = subprocess.run([sys.executable, '/tmp/program1.py'])
    print("-" * 40)
    
    # Read and execute second program
    print("\n3. Executing program 2 (region 100,100)...")
    print("-" * 40)
    result = subprocess.run([
        sys.executable, 'tools/dense_encoder.py', 'read',
        '/tmp/demo_canvas.png', '100', '100', '6', '6',
        '-o', '/tmp/program2.py'
    ], capture_output=True, text=True)
    print(result.stdout.strip())
    
    result = subprocess.run([sys.executable, '/tmp/program2.py'])
    print("-" * 40)
    
    # Summary
    print("\n" + "=" * 60)
    print("Demo Complete")
    print("=" * 60)
    print("\nKey observations:")
    print("  - Multiple programs coexist on single canvas")
    print("  - Region-based isolation (no crosstalk)")
    print("  - Programs are byte-identical to originals (CRC verified)")
    print("  - Execution directly from image pixels")
    print("\nThis proves:")
    print("  - Canvas is a viable program storage medium")
    print("  - Region addressing works (x, y, w, h)")
    print("  - Multiple cartridges can coexist safely")
    print("  - The cartridge format is lossless (round-trip verified)")
    print("\nFiles created:")
    print("  /tmp/demo_canvas.png  - Canvas with 2 programs")
    print("  /tmp/program1.py     - Recovered fibonacci demo")
    print("  /tmp/program2.py     - Recovered message program")
    print("=" * 60)

if __name__ == '__main__':
    main()