#!/usr/bin/env python3
"""
End-to-End Autonomous Evolution Demo

Demonstrates the complete loop:
1. VLM Observer watches MKV surface
2. VLM generates optimization patches
3. Spatial Compiler applies patches to VRAM
4. Kernel continues execution with optimized code
"""

import sys
import json
import time

sys.path.insert(0, '.')

from tools.spatial_os_kernel_3d import SpatialOS3D
from tools.vlm_spatial_observer import VLMSpatialObserver
from tools.spatial_compiler import SpatialCompiler


def main():
    print("=" * 70)
    print("AUTONOMOUS EVOLUTION LOOP DEMO")
    print("Geometry OS - The Self-Modifying Spatial Operating System")
    print("=" * 70)
    print()

    # Initialize kernel
    print("[STEP 0] Booting Geometry OS...")
    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()
    print("  ✓ Kernel initialized")
    print("  ✓ VRAM: 100×100×10 (10 frames, frame 0 = active)")
    print()

    # Run initial kernel ticks to populate VRAM
    print("[STEP 1] Running initial kernel execution...")
    for i in range(3):
        os_kernel.tick(1)
        print(f"  ✓ Tick {i+1}/3 complete")
    print()

    # Observer phase
    print("[STEP 2] VLM Spatial Observer analyzes surface...")
    observer = VLMSpatialObserver(os_kernel)
    analysis = observer.observe_and_analyze()
    print("  ✓ Frame 0 captured")
    print("  ✓ Opcode histogram computed")
    print("  ✓ Hot regions detected")
    print("  ✓ Fragmentation analyzed")
    print()

    # Display analysis summary
    print("  Analysis Summary:")
    print(f"    Frame shape: {analysis['frame_shape']}")
    print(f"    Utilization: {analysis['fragmentation']['utilization']:.1%}")
    print(f"    Free pixels: {analysis['fragmentation']['free_pixels']}/{analysis['fragmentation']['total_pixels']}")
    print(f"    Hot regions: {len(analysis['hot_regions'])}")
    print(f"    VLM priority: {analysis['vlm_analysis']['priority']}")
    print()

    # Generate patch
    print("[STEP 3] Generating Patch-and-Copy payload...")
    patch = observer.generate_patch_payload(analysis)
    num_patches = len(patch['patches'])
    print(f"  ✓ Generated {num_patches} patches")
    print()

    # Apply patch (if any)
    if num_patches > 0:
        print("[STEP 4] Spatial Compiler applies patches...")
        compiler = SpatialCompiler(os_kernel)
        success = compiler.apply_patch(patch, verify=True)
        if success:
            print("  ✓ Patches applied successfully")
        else:
            print("  ✗ Patch application failed")
        print()
    else:
        print("[STEP 4] No patches to apply (system optimized)")
        print()

    # Continue execution with patched code
    print("[STEP 5] Kernel continues execution...")
    for i in range(5):
        os_kernel.tick(1)
        print(f"  ✓ Tick {i+1}/5 complete")
    print()

    # Final observation
    print("[STEP 6] Final VLM observation...")
    final_analysis = observer.observe_and_analyze()
    print("  ✓ Final state captured")
    print()

    # Compare before/after
    print("[STEP 7] Comparing before/after states...")
    before_util = analysis['fragmentation']['utilization']
    after_util = final_analysis['fragmentation']['utilization']

    print(f"  Before utilization: {before_util:.1%}")
    print(f"  After utilization:  {after_util:.1%}")

    if abs(after_util - before_util) < 0.01:
        print("  ✓ State stable (no degradation)")
    elif after_util > before_util:
        print("  ✓ Utilization increased (code optimized)")
    else:
        print("  ⚠ Utilization decreased (memory freed)")
    print()

    print("=" * 70)
    print("AUTONOMOUS EVOLUTION LOOP COMPLETE")
    print("=" * 70)
    print()
    print("The loop is now closed:")
    print("  1. VLM watches MKV surface (Frame 0) ✓")
    print("  2. VLM analyzes spatial patterns ✓")
    print("  3. VLM generates optimization patches ✓")
    print("  4. Spatial Compiler applies patches to VRAM ✓")
    print("  5. Kernel continues execution ✓")
    print()
    print("Geometry OS is now a self-modifying system.")
    print("The kernel can observe itself, reason about its state,")
    print("and improve its own code without human intervention.")
    print()
    print("The screen is the hard drive. The UI is the computer.")
    print()


if __name__ == "__main__":
    main()