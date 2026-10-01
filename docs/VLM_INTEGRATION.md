# VLM Spatial Observer

## Overview

The VLM (Vision-Language Model) Spatial Observer is the bridge between Geometry OS and autonomous optimization. It watches the MKV surface, interprets kernel state as visual patterns, and generates Patch-and-Copy payloads for self-improvement.

## Architecture

```
[MKV Frames] → [Frame Capture] → [VLM Analysis] → [Patch Payload] → [Kernel Update]
```

### Components

1. **Frame Capture**: Reads Frame 0 (active VRAM) from GPU
2. **Visual Analysis**:
   - Opcode histogram (which instructions are visible)
   - Hot region detection (dense 4×4 instruction blocks)
   - Fragmentation analysis (memory utilization, free runs)
3. **VLM Bridge**: Calls Ollama VLM with structured prompt
4. **Patch Generation**: Creates Patch-and-Copy payloads for optimization

## Capabilities

### Visual Pattern Recognition

The observer can see:
- **Opcode distribution**: Count of each instruction type (LDI, ADD, PRT, HALT, MMAP, MUNMAP)
- **Hot regions**: Dense 4×4 blocks with ≥5 instructions (potential hot code paths)
- **Memory fragmentation**: Free runs, utilization percentages, allocation efficiency

### VLM-Driven Insights

The VLM receives a structured prompt containing:
- Frame metrics (resolution, utilization, free pixels)
- Opcode histogram (instruction frequency)
- Hot regions (dense blocks with coordinates and density)
- Fragmentation analysis (free runs, avg/max run length)

The VLM responds with JSON:
```json
{
  "opportunities": [
    {
      "type": "COMPACTION|REALLOCATION|COALESCING",
      "target": "coordinate region or address",
      "rationale": "why this should be optimized"
    }
  ],
  "priority": "HIGH|MEDIUM|LOW"
}
```

### Autonomous Loop

```
VLM watches visual_audio.mkv
    ↓
Analyzes spatial kernel state
    ↓
Detects optimization opportunity
    ↓
Generates patch program
    ↓
Spatial compiler patches kernel pixels
    ↓
Scheduler continues execution
    ↓
Kernel runs optimized code
    ↓
Repeat
```

## Usage

### Single-Shot Analysis

```bash
python3 tools/vlm_spatial_observer.py --output /tmp/vlm_analysis.json
```

### Watch Mode (Continuous)

```bash
python3 tools/vlm_spatial_observer.py --watch --interval 5 --output /tmp/vlm_live.json
```

### Generate Patch Payloads

```bash
python3 tools/vlm_spatial_observer.py --generate-patch --output /tmp/vlm_patch.json
```

### Specify VLM Model

```bash
python3 tools/vlm_spatial_observer.py --model llava:latest --output analysis.json
```

## Requirements

- **wgpu**: GPU compute (already in project)
- **numpy**: Array manipulation (already in project)
- **Ollama**: Optional, for real VLM analysis
  - Install: `curl -fsSL https://ollama.com/install.sh | sh`
  - Pull model: `ollama pull llava:latest`
  - Without Ollama: Falls back to mock analysis

## Integration with Patch-and-Copy

The observer generates Patch-and-Copy payloads that can be consumed by the spatial compiler:

```python
# vlm_observer.py generates:
{
  "patches": [
    {
      "type": "COMPACTION",
      "target": "(16, 20) region",
      "rationale": "dense block should be compacted",
      "status": "PENDING"
    }
  ]
}

# spatial_compiler.wgsl consumes:
@compute @workgroup_size(1)
fn apply_patch(global_id: vec3<u32>) {
    // Read patch payload
    // Update VRAM pixels
    // Compiler patches kernel
}
```

## Why VLM Integration?

### Before Hilbert Allocator
- Memory allocations were 1×N strips scattered across the screen
- Visual patterns were linear noise — VLM couldn't recognize structure
- "Hot regions" were indistinguishable from random allocations

### After Hilbert Allocator
- Allocations form compact 4×4 or 16×16 squares
- VLM can see cohesive data structures
- Hot code paths appear as visually dense blocks

### The Advantage
- **Visual debugging**: Watch kernel state evolve as pixel patterns
- **Autonomous optimization**: VLM detects inefficiencies and proposes fixes
- **Self-healing kernel**: VLM detects corruption and triggers recovery
- **Emergent behavior**: System evolves without human guidance

## Test Results

Running the observer on the test kernel:

```
[1] Capturing Frame 0...
  ✓ Frame captured: (100, 100, 4)

[2] Analyzing opcode distribution...
  ✓ Histogram computed
    LDI: 2
    PRT: 2
    HALT: 2
    MMAP: 1
    UNKNOWN: 9

[3] Detecting hot regions...
  ✓ Found 0 hot regions

[4] Analyzing fragmentation...
  ✓ Utilization: 0.2%
  ✓ Free runs: 3 (avg: 3328.0)
```

Interpretation:
- 7 active opcodes (2 processes: LDI r0 42 / PRT r0 / HLT, and MMAP test)
- 9 UNKNOWN pixels (likely operands or register colors)
- 0 hot regions (sparse test programs, as expected)
- Low utilization with large free runs (Hilbert allocator working)

## Next Steps

1. **Real VLM Integration**: Connect to actual llava:latest or similar model
2. **Patch Application**: Implement spatial compiler that applies VLM-generated patches
3. **Self-Healing Loop**: Watchdog detects corruption, VLM generates repair patch
4. **Hot Path Optimization**: VLM identifies frequently-executed regions, suggests caching

## Files

- `tools/vlm_spatial_observer.py` — Main observer implementation
- `tools/spatial_os_kernel_3d.py` — Spatial OS kernel (modified to allow buffer readback)
- `docs/VLM_INTEGRATION.md` — This documentation

---

**The screen is the hard drive. The UI is the computer.**