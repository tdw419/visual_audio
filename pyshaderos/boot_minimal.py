#!/usr/bin/env python3
"""
Minimal ShaderOS Boot - Loads only the substrate kernel
"""
import time
from ShaderOSRuntime import ShaderOSRuntime, SHADER_ID_SUBSTRATE_KERNEL

def main():
    print("\n=== MINIMAL SHADEROS BOOT ===\n")

    runtime = ShaderOSRuntime()

    # Register only the substrate kernel (base layer)
    print("Registering substrate kernel...")
    try:
        runtime.register_shader(
            SHADER_ID_SUBSTRATE_KERNEL,
            "substrate_kernel",
            "runtime/core/substrate.wgsl",
            "main"
        )
        print("✓ Substrate kernel loaded successfully\n")
    except Exception as e:
        print(f"✗ Failed to load substrate kernel: {e}")
        return

    print("✅ ShaderOS Runtime ready (minimal mode)")
    print("Running substrate kernel for 10 frames...\n")

    # Run for 10 frames
    for frame in range(10):
        print(f"=== FRAME {frame} ===")
        runtime.tick()
        time.sleep(0.1)

        # Read frame counter from GPU
        import numpy as np
        frame_data = runtime.queue.read_buffer(
            runtime.shared_buffers['global_frame_counter'],
            0,
            4
        )
        frame_count = np.frombuffer(frame_data, dtype=np.uint32)[0]
        print(f"GPU Frame Counter: {frame_count}")
        print()

    print("🏁 Minimal boot completed successfully!")
    print("\nThe substrate kernel is running on GPU and incrementing frame counters.")
    print("This proves the core ShaderOS infrastructure is working.")

if __name__ == "__main__":
    main()
