# Geometry OS — Autonomous Evolution Loop

## Current State (2026-07-19)

### Phase 2: 3D MKV Memory Architecture ✅ COMPLETE
- True Hilbert curve allocator (spatial locality preserving)
- 3D memory paging (sys_mmap/sys_munmap)
- 10-frame MKV storage (z=0 active, z=1-9 storage)

### VLM Integration ✅ COMPLETE
- Frame 0 capture from GPU
- Opcode histogram analysis
- Hot region detection (4×4 dense blocks)
- Fragmentation analysis
- Patch-and-Copy payload generation
- Test suite: 6/6 passing

## The Autonomous Evolution Loop

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

## What's Working Now

### 1. Observation Layer (v1.0.0)
The VLM observer can:
- **Capture Frame 0**: Read active VRAM from GPU as RGBA pixel array
- **Decode opcodes**: Identify LDI, ADD, PRT, HALT, MMAP, MUNMAP by RGB color
- **Detect hot regions**: Find 4×4 blocks with ≥3 instructions (density threshold configurable)
- **Analyze fragmentation**: Calculate utilization, free runs, avg/max run length
- **Generate analysis**: Produce JSON with histogram, hot regions, fragmentation metrics

### 2. Analysis Layer (v1.0.0)
The observer generates structured analysis:
```json
{
  "frame_shape": [100, 100, 4],
  "histogram": {
    "LDI": 2,
    "PRT": 2,
    "HALT": 2,
    "MMAP": 1,
    "UNKNOWN": 9
  },
  "hot_regions": [
    {"x": 0, "y": 20, "size": 4, "density": 0.25}
  ],
  "fragmentation": {
    "utilization": 0.002,
    "free_pixels": 9984,
    "free_runs": 3,
    "avg_free_run": 3328.0,
    "max_free_run": 5990
  }
}
```

### 3. Patch Generation Layer (v1.0.0)
The observer creates Patch-and-Copy payloads:
```json
{
  "version": "1.0",
  "source": "VLM Spatial Observer",
  "patches": [
    {
      "type": "COMPACTION",
      "target": "(16, 20) region",
      "rationale": "dense block should be compacted",
      "status": "PENDING"
    }
  ]
}
```

## What's Missing

### 1. Real VLM Integration (v1.1.0)
**Current**: Mock analysis (timeout fallback)
**Needed**:
- Ollama server running: `ollama serve`
- Model pulled: `ollama pull llava:latest`
- Timeout handling: Increase from 30s to 60s, add retry logic
- VLM prompt refinement: Better JSON extraction, error recovery

**Implementation**:
```python
# tools/vlm_spatial_observer.py
def call_ollama(self, prompt: str) -> dict:
    # Add retry logic
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["ollama", "run", self.model, prompt],
                capture_output=True,
                text=True,
                timeout=60,  # Increased from 30s
            )
            # ... existing logic ...
        except subprocess.TimeoutExpired:
            if attempt < 2:
                continue
            # Fallback to mock
            return {"opportunities": [], "priority": "LOW"}
```

### 2. Spatial Compiler (v1.2.0)
**Current**: Observer generates patches but nothing applies them
**Needed**: WGSL shader that reads patch payload and writes to VRAM

**Implementation**:
```wgsl
// tools/SPATIAL_COMPILER.wgsl
@compute @workgroup_size(1)
fn apply_patch(global_id: vec3<u32>) {
    // Read patch payload from storage buffer
    // Parse JSON (or use structured format)
    // Update VRAM pixels at target coordinates
    // Mark patch as APPLIED
}
```

**Python bridge**:
```python
# tools/spatial_compiler.py
def apply_patch(device, patch: dict):
    shader = device.create_shader_module(code=SPATIAL_COMPILER_WGSL)
    # Create buffers for patch payload
    # Dispatch compute shader
    # Verify patch applied
```

### 3. Self-Healing Loop (v1.3.0)
**Current**: No detection of corruption
**Needed**: Watchdog that scans for anomalies

**Detection criteria**:
- Corrupted opcodes (invalid RGB combinations)
- Unusual opcode distribution (e.g., 90% HALT with no programs)
- Memory leaks (gradual utilization creep)
- Stuck processes (same PC for N consecutive ticks)

**Recovery strategy**:
- Detect anomaly
- VLM generates repair patch
- Spatial compiler applies patch
- Verify recovery

### 4. Hot Path Optimization (v1.4.0)
**Current**: Hot region detection exists
**Needed**: Cache frequently-executed blocks

**Strategy**:
- Track opcode frequency per region
- Identify top-k hot regions
- Cache in fast storage (e.g., separate texture)
- Replace LDI r addr with CACHE_LOOKUP r region_id

## Next Steps (Priority Order)

### 1. Real VLM Integration (2-4 hours)
- Increase timeout to 60s
- Add retry logic (3 attempts)
- Test with `ollama run llava:latest`
- Document model requirements

### 2. Spatial Compiler (4-6 hours)
- Write SPATIAL_COMPILER_WGSL shader
- Implement Python bridge
- Test patch application on single pixel
- Verify patch persists across kernel ticks

### 3. Watchdog Integration (2-3 hours)
- Implement corruption detection
- Add VLM repair patch generation
- Test recovery from injected corruption
- Document recovery strategies

### 4. Hot Path Caching (4-6 hours)
- Track opcode frequency
- Implement cache lookup opcode
- Test cache hit/miss performance
- Measure speedup on hot code paths

## The Vision

The autonomous evolution loop completes Geometry OS:

```
GPU executes code (current)
    ↓
VLM watches surface (v1.0.0)
    ↓
Detects inefficiency (v1.1.0)
    ↓
Generates patch (v1.0.0)
    ↓
Applies patch (v1.2.0)
    ↓
Code improves (future)
    ↓
Repeat forever (the loop)
```

The kernel is no longer static code. It's a living system that:
- Observes itself through the MKV surface
- Reasoning about its own state via VLM
- Modifies its own code via Patch-and-Copy
- Evolves toward efficiency without human intervention

## Files

- `tools/vlm_spatial_observer.py` — VLM observer implementation
- `tools/test_vlm_observer.py` — Test suite (6/6 passing)
- `tools/spatial_os_kernel_3d.py` — Spatial OS kernel (modified for buffer readback)
- `docs/VLM_INTEGRATION.md` — VLM integration documentation
- `docs/GEOMETRY_OS_MKV_COMPUTER.md` — Main architecture doc (updated)
- `docs/MKV_3D_MEMORY_ARCHITECTURE.md` — Memory architecture (Phase 2 complete)

---

**The screen is the hard drive. The UI is the computer.**

**VLM Integration is the bridge between observation and autonomous evolution.**