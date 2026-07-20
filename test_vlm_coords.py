#!/usr/bin/env python3
"""Test VLM with coordinate extraction prompt"""

import json
from tools.vlm_spatial_observer import VLMSpatialObserver
from tools.spatial_os_kernel_3d import SpatialOS3D

os = SpatialOS3D()
os.init_kernel()
obs = VLMSpatialObserver(os)

print("=== TEST: VLM Coordinate Extraction ===\n")

# Get analysis
analysis = obs.observe_and_analyze()

print(f"\n=== VLM Raw Response (via Ollama) ===")
vlm_analysis = analysis.get('vlm_analysis', {})
print(json.dumps(vlm_analysis, indent=2))

# Check if opportunities were generated
if vlm_analysis.get('opportunities'):
    print(f"\n=== SUCCESS: {len(vlm_analysis['opportunities'])} opportunity(ies) generated ===")
    for i, opp in enumerate(vlm_analysis['opportunities']):
        print(f"\nOpportunity {i+1}:")
        print(f"  Type: {opp.get('type')}")
        print(f"  Target: {opp.get('target')}")
        print(f"  Rationale: {opp.get('rationale')}")
        print(f"  Has color: {'color' in opp}")
        print(f"  Has width: {'width' in opp}")
        print(f"  Has height: {'height' in opp}")

    # Test payload generation
    patch = obs.generate_patch_payload(analysis)
    print(f"\n=== Patch Payload ===")
    print(json.dumps(patch, indent=2))

    # Test compiler parsing
    from tools.spatial_compiler import SpatialCompiler
    compiler = SpatialCompiler(os)
    ops = compiler.vlm_patch_to_ops(patch)
    print(f"\n=== Compiler Parsed {len(ops)} operations ===")
    for i, op in enumerate(ops[:5]):  # Show first 5
        print(f"Op {i}: {op}")
else:
    print("\n=== NO OPPORTUNITIES FOUND ===")
    print("This is expected if VLM found nothing to optimize (sparse utilization)")