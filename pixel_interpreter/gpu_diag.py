#!/usr/bin/env python3
"""Diagnose GPU compute availability and test buffer creation."""

import sys
import subprocess

print("=== Testing wgpu backend options ===\n")

# Test with forced backend configurations
configs = [
    {"WGPU_BACKEND": "gl"},
    {"WGPU_BACKEND": "vk"},
    {"WGPU_BACKEND": "gl", "MESA_LOADER_DRIVER_OVERRIDE": "iris"},
    {"WGPU_BACKEND": "gl", "MESA_LOADER_DRIVER_OVERRIDE": "i915"},
    {},
]

import os

for i, env_vars in enumerate(configs):
    print(f"Config {i + 1}: {env_vars if env_vars else 'Default'}")
    
    # Clean env
    for key in ["WGPU_BACKEND", "MESA_LOADER_DRIVER_OVERRIDE"]:
        os.environ.pop(key, None)
    
    # Set config
    os.environ.update(env_vars)
    
    try:
        import wgpu
        
        # Try adapter request
        print("  Requesting adapter...")
        adapter = wgpu.gpu.request_adapter(power_preference="high-performance")
        print(f"  ✓ Adapter: {adapter}")
        
        # Try device request
        print("  Requesting device...")
        device = adapter.request_device(required_limits=wgpu.required_limits)
        print(f"  ✓ Device: {device}")
        
        # Try buffer creation (the choke point)
        print("  Creating buffer...")
        buf = device.create_buffer(
            size=1024,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST
        )
        print(f"  ✓ Buffer: {buf}")
        
        # Try texture creation
        print("  Creating texture...")
        tex = device.create_texture(
            size=(256, 256, 1),
            format=wgpu.TextureFormat.rgba32uint,
            usage=wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.COPY_DST
        )
        print(f"  ✓ Texture: {tex}")
        
        print("  → ALL STEPS PASS\n")
        
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}\n")
        continue

print("\n=== Checking Vulkan vs OpenGL availability ===")

# Check Vulkan ICD
if os.path.exists("/usr/share/vulkan/icd"):
    print("Vulkan ICDs found:")
    import subprocess
    result = subprocess.run(["ls", "/usr/share/vulkan/icd/*.json"], shell=True, capture_output=True)
    if result.returncode == 0:
        for line in result.stdout.decode().strip().split('\n'):
            print(f"  - {line}")
else:
    print("No Vulkan ICDs found")

# Check Mesa DRI
if os.path.exists("/usr/lib/x86_64-linux-gnu/dri"):
    print("\nMesa DRI drivers found:")
    result = subprocess.run(["ls", "/usr/lib/x86_64-linux-gnu/dri/*.so"], shell=True, capture_output=True)
    if result.returncode == 0:
        drivers = [line.split('/')[-1] for line in result.stdout.decode().strip().split('\n')]
        intel_drivers = [d for d in drivers if 'iris' in d.lower() or 'i915' in d.lower()]
        if intel_drivers:
            print("  Intel drivers:")
            for d in intel_drivers:
                print(f"    - {d}")

print("\n=== Testing wgpu-info ===")

try:
    import subprocess
    result = subprocess.run(["wgpu-info"], capture_output=True, timeout=10)
    print(result.stdout.decode())
except FileNotFoundError:
    print("wgpu-info not available (install with: pip install wgpu-native)")
except Exception as e:
    print(f"wgpu-info failed: {e}")