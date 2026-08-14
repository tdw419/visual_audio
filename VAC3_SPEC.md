# VAC3 Specification - Visual Audio Container v3

**Status**: Draft
**Date**: 2026-08-14
**Philosophy**: Frames are not time, they are Z-axis slices in a 3D spatial tensor

## The Shift

**VAC1/VAC2**: Time-series video. Frame N = T=N seconds.
- Play in VLC to watch execution evolve
- Extract frame to get snapshot at T=N

**VAC3**: 3D Spatial Tensor. Frame N = Z=N layer in spatial substrate.
- Load into GPU as `texture_3d`
- Different shaders access different Z-layers simultaneously
- User sees Z=0, CPU reads Z=1, diagnostics write Z=2

## Frame Layout (Reserved Z-Indices)

```
Z=0:  DISPLAY FRAMEBUFFER (Human-readable)
       - Resolution: User-defined (e.g., 1920×1080, 1280×720)
       - Format: RGB24
       - Use case: What the user sees on screen
       - Consumer: PixiJS/WebGPU renderer (visual shell)

Z=1:  EXECUTION SUBSTRATE (RAM / Software)
       - Resolution: Hilbert-mapped (e.g., 1024×1024 = 1MB RGBA = 4MB RAM)
       - Format: RGB24 (or RGBA32 for direct byte mapping)
       - Use case: Where CPU instructions execute from
       - Consumer: WGSL compute shader (riscv_gpu_cpu.wgsl)

Z=2:  DIAGNOSTICS LAYER (Crash logs, failure states)
       - Resolution: Matches Z=1 (same pixel grid)
       - Format: RGB24
       - Use case: Compute shader writes failure codes here
       - Consumer: Debug tooling, AI inspection

Z=3+: APPLICATION DATA (Extension layers)
       - Reserved for future use
       - Audio tracks, peripheral state, network buffers, etc.
```

## GPU Memory Layout

When a VAC3 file is loaded, it becomes a `texture_3d` in GPU memory:

```
texture_3d<float, access::read_write> vac3_texture;
// Dimensions: [width][height][depth]
// Example: [1024][1024][4] = 1024×1024 pixels, 4 Z-layers

// Visual Shell (Display) - only ever renders Z=0
@fragment
fn render_display(@location(0) uv: vec2<f32>) -> vec4<f32> {
    let x = i32(uv.x * 1024.0);
    let y = i32(uv.y * 1024.0);
    let z = 0;  // ALWAYS Z=0 for display
    return vac3_texture[x][y][z];
}

// CPU Emulator (Execution) - reads from Z=1
@compute
fn execute_cpu(@builtin(global_invocation_id) id: vec3<u32>) {
    let pc = load_pc_from_z1(id.x, id.y);  // Read from Z=1
    // ... execute instruction ...
    store_crash_to_z2(failure_code);       // Write to Z=2
}
```

## Advantages

### 1. Non-Interrupting Debugging
- User continues seeing Z=0 (display)
- Compute shader writes failure to Z=2
- AI queries Z=2 without pausing execution

### 2. Spatial Coherence
- Z=1 (RAM) is laid out via Hilbert curve
- Contiguous memory = neighboring pixels
- C-structures = recognizable 2D patterns

### 3. Unified Storage
- One MKV file = Entire computing substrate
- Display + RAM + Diagnostics in one container
- Boot from container, run from container, debug from container

### 4. GPU-Native Execution
- No host-side copying
- All Z-layers live in GPU VRAM
- Compute shader and renderer share same texture

## File Format Requirements

### MKV Structure

```
alpine_boot_vac3.nut:
  Video Track:
    - Frame 0: Display framebuffer (1920×1080 RGB24)
    - Frame 1: RAM substrate (1024×1024 RGB24)
    - Frame 2: Diagnostics layer (1024×1024 RGB24)
    - Frame 3: (reserved)
    - ...
  
  Audio Track:
    - Optional: Console output via Visual Audio codec
  
  Attachment:
    - manifest.json (metadata, VAC3 version, layer specifications)
```

### Manifest Schema

```json
{
  "version": "VAC3",
  "layers": [
    {
      "z_index": 0,
      "name": "display",
      "width": 1920,
      "height": 1080,
      "format": "RGB24",
      "description": "Human-readable framebuffer"
    },
    {
      "z_index": 1,
      "name": "ram_substrate",
      "width": 1024,
      "height": 1024,
      "format": "RGB24",
      "hilbert_mapped": true,
      "description": "Execution substrate (RAM)"
    },
    {
      "z_index": 2,
      "name": "diagnostics",
      "width": 1024,
      "height": 1024,
      "format": "RGB24",
      "description": "Crash logs, failure states"
    }
  ],
  "entry_point": {
    "z_index": 1,
    "offset": 4096
  }
}
```

## Migration Path

### From VAC2 to VAC3

**Current (VAC2)**:
- Capture time-series of memory dumps
- Each frame = execution snapshot at T=N

**New (VAC3)**:
- Capture single boot into spatial layers
- Frame 0 = Final display state
- Frame 1 = Final RAM state
- Frame 2 = Execution trace / diagnostics

**Tool Changes**:

1. `qemu_to_mkv.py`: Add `--vac3-mode` flag
   ```python
   # VAC2 mode (default): Time-series capture
   python3 qemu_to_mkv.py disk.qcow2 --output boot_trace_vac2.mkv
   
   # VAC3 mode: Spatial tensor capture
   python3 qemu_to_mkv.py disk.qcow2 --output boot_bundle_vac3.mkv --vac3
   ```

2. `dense_encoder_video.py`: Support multi-layer manifests
   ```python
   encode_mkv(
       layers={
           0: framebuffer_bytes,
           1: ram_substrate_bytes,
           2: diagnostics_bytes
       },
       manifest=manifest_v3
   )
   ```

3. Geometry OS GPU compositor: Load as `texture_3d`
   ```rust
   let texture = device.create_texture(&TextureDescriptor {
       size: Extent3d {
           width: 1024,
           height: 1024,
           depth_or_array_layers: 4,  // 4 Z-layers
       },
       dimension: TextureDimension::D3,
       // ...
   });
   ```

## Example Usage

### 1. Capture Alpine Linux as VAC3 Bundle

```bash
python3 tools/qemu_to_mkv.py boot_images/alpine_riscv64.qcow2 \
    --arch riscv64 \
    --output alpine_boot_vac3.nut \
    --vac3 \
    --capture-z0-display \
    --capture-z1-ram \
    --capture-z2-diagnostics
```

### 2. Load into Geometry OS GPU Compositor

```rust
// Load VAC3 as 3D texture
let vac3_texture = load_vac3_as_texture("alpine_boot_vac3.nut");

// Render Z=0 to screen (user sees Alpine login)
renderer.set_z_layer(0);
renderer.draw_frame();

// Compute shader executes from Z=1
compute_executor.set_ram_layer(1);
compute_executor.run();

// Check Z=2 for crashes
let diagnostics = texture.read_layer(2);
if diagnostics.has_failure() {
    println!("Boot failed: {}", diagnostics.error_message());
}
```

### 3. Debugging with AI

```python
from vac3_loader import VAC3Bundle

bundle = VAC3Bundle("alpine_boot_vac3.nut")

# User sees display
display = bundle.get_layer(z=0)
display.show()  # Alpine login prompt

# AI inspects execution substrate
ram = bundle.get_layer(z=1)
entropy_analysis = ai.analyze_spatial_patterns(ram)

# AI reads diagnostics layer
diagnostics = bundle.get_layer(z=2)
if diagnostics.has_crash():
    print(f"Crash at PC={diagnostics.crash_pc}")
```

## Verification Requirements

Before labeling a container as VAC3-compliant, verify:

1. **Frame Count**: Must have at least 3 frames (Z=0, Z=1, Z=2)
2. **Manifest Validation**: `manifest.json` must declare VAC3 version
3. **Z-Layer Resolutions**: Z=1 and Z=2 must have identical dimensions
4. **Display Layer**: Z=0 must be human-readable (not raw RAM)
5. **Hilbert Mapping**: If `hilbert_mapped: true` in manifest, Z=1 must preserve spatial locality

## Future Extensions

- **Z=3**: Audio buffer state
- **Z=4**: Network packet buffers
- **Z=5**: Peripheral device state
- **Z=6**: Crypto keys / Secure enclave
- **Z=7**: AI model weights (spatial LLM)

## Philosophical Note

VAC3 completes "The Screen is the Mind" architecture:

- **VAC1**: "The Screen is the Hard Drive" (software as pixels)
- **VAC2**: "The Screen is the Time Machine" (execution as video frames)
- **VAC3**: "The Screen is the 3D Mind" (display + substrate + diagnostics in spatial tensor)

The OS boots from pixels, executes from pixels, and you debug it by reading pixels from a different Z-layer of the same file.

---

**Status**: ✅ Spec defined, ready for implementation
**Next**: Update `qemu_to_mkv.py` with `--vac3` mode, test Alpine capture