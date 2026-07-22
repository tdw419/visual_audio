#!/usr/bin/env python3
"""
Test if WGSL shader compiles successfully.
"""

import wgpu
import wgpu.utils
from pathlib import Path

print("Testing WGSL shader compilation...")

device = wgpu.utils.get_default_device()
shader_path = Path(__file__).parent / 'tools' / 'RISCV_CPU_MMU.wgsl'
shader_code = shader_path.read_text()

try:
    compute_shader = device.create_shader_module(code=shader_code)
    print("✓ Shader compiled successfully")
    
    # Try to create a minimal pipeline
    bind_group_layout = device.create_bind_group_layout(entries=[
        {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'storage'}},
        {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'uniform'}},
        {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer': {'type': 'read-only-storage'}},
    ])
    
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[bind_group_layout])
    pipeline = device.create_compute_pipeline(
        layout=pipeline_layout,
        compute={'module': compute_shader, 'entry_point': 'main'},
    )
    
    print("✓ Pipeline created successfully")
    
except Exception as e:
    print(f"✗ Compilation failed: {e}")
    import traceback
    traceback.print_exc()