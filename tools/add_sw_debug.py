#!/usr/bin/env python3
"""
Add debug instrumentation to RISCV_CPU_MMU.wgsl for SW debugging.
We'll write debug info to a specific memory address.
"""

import sys
from pathlib import Path

shader_path = Path('/home/jericho/projects/zion/projects/visual_audio/tools/RISCV_CPU_MMU.wgsl')
shader = shader_path.read_text()

# Add a debug buffer to the struct and instrumentation
# DEBUG: We'll write to offset 0xF0000 as a debug region

# Find write_phys_word and add instrumentation
old_write = """fn write_phys_word(pa: vec2<u32>, val: u32) {
    // Handle physical memory at 0x80000000+ (xv6 M-mode boot)
    let pa_base = select(0u, PHYS_BASE, pa.x >= PHYS_BASE);
    let pa_offset = pa.x - pa_base;
    let word_addr = (pa_offset / 4u);
    if (word_addr >= arrayLength(&memory)) {
        return;
    }
    var px = memory[word_addr];
    let new_word = val;
    px.r = new_word & 0xFFu;
    px.g = (new_word >> 8u) & 0xFFu;
    px.b = (new_word >> 16u) & 0xFFu;
    px.a = (new_word >> 24u) & 0xFFu;
    memory[word_addr] = px;
}"""

new_write = """fn write_phys_word(pa: vec2<u32>, val: u32) {
    // DEBUG: Write to debug buffer at 0x800F0000
    let debug_base: u32 = 0x800F0000u;
    if (pa.x >= debug_base && pa.x < debug_base + 256u) {
        let debug_word_addr = (pa.x - debug_base) / 4u;
        if (debug_word_addr < 64u) {
            debug_output[debug_word_addr] = val;
        }
        return;
    }
    
    // Handle physical memory at 0x80000000+ (xv6 M-mode boot)
    let pa_base = select(0u, PHYS_BASE, pa.x >= PHYS_BASE);
    let pa_offset = pa.x - pa_base;
    let word_addr = (pa_offset / 4u);
    if (word_addr >= arrayLength(&memory)) {
        return;
    }
    var px = memory[word_addr];
    let new_word = val;
    px.r = new_word & 0xFFu;
    px.g = (new_word >> 8u) & 0xFFu;
    px.b = (new_word >> 16u) & 0xFFu;
    px.a = (new_word >> 24u) & 0xFFu;
    memory[word_addr] = px;
}"""

if old_write in shader:
    shader = shader.replace(old_write, new_write)
    print("✓ Added debug instrumentation to write_phys_word")
    
    # Now add the debug_output array to the global declarations
    # Find where memory is declared and add debug_output nearby
    
    memory_pos = shader.find('@group(0) @binding(0) var<storage, read_write> memory: array<InstructionPixel>;')
    if memory_pos >= 0:
        # Add debug_output right after memory
        debug_decl = '\n@group(0) @binding(0) var<storage, read_write> debug_output: array<u32, 64>;  // DEBUG: For SW debugging\n'
        insert_pos = memory_pos + len('@group(0) @binding(0) var<storage, read_write> memory: array<InstructionPixel>;')
        shader = shader[:insert_pos] + debug_decl + shader[insert_pos:]
        print("✓ Added debug_output array")
        
        # Save the modified shader
        shader_path.write_text(shader)
        print(f"✓ Saved modified shader to {shader_path}")
    else:
        print("✗ Could not find memory declaration")
else:
    print("✗ Could not find write_phys_word function")
    print("Searching for 'write_phys_word'...")
    if 'fn write_phys_word' in shader:
        pos = shader.find('fn write_phys_word')
        print(f"Found at position {pos}")
        print(shader[pos:pos+100])