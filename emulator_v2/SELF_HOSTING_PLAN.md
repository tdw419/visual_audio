# SELF_HOSTING_PLAN.md

## Goal

Boot xv6 from **pixel-encoded data only** - no files on disk except a tiny Python loader (~200 lines).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ visual_audio.mkv (VAC1 Container)                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Frame 0: emulator_frame.png (141KB WGSL shader)    │    │
│  │ Frame 1: kernel_frame.png (xv6 ELF binary)          │    │
│  │ Frame 2: fsimg_frame.png (filesystem image)         │    │
│  │ Frame 3: dtb_frame.png (device tree, if needed)     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ v2_boot.py unpacks & verifies
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ GPU Memory                                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Emulator Shader (WGSL) → Compiled to native code    │    │
│  │ Guest RAM (72MB) → Kernel + fs.img + MMU tables     │    │
│  │ CPU State (528 bytes) → Registers + CSRs            │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ WGSL compute shader executes
                            ▼
                    xv6 shell prompt ($)
```

## Current Status

### Level 1: Shader as Pixels ✅ COMPLETE

**What's done:**
- `emulator_v2/pack_shader.py` - Pack/unpack WGSL with SHA-256 verification
- `emulator_v2/emulator_frame.png` - 141KB shader encoded as 188×188 PNG
- `emulator_v2/test_shader_frame.py` - Byte-identical verification (PASS)
- `emulator_v2/boot_xv6_gpu_v2_simple.py` - Boots xv6 from pixel-sourced shader (PASS)

**What's verified:**
```
✓ Shader frame unpacks to byte-identical WGSL
✓ xv6 boots from pixel-sourced shader
✓ UART output: "xv6 kernel is booting"
✓ v1 (original shader) untouched on master
```

**What's not yet in pixels:**
- Kernel ELF binary
- Filesystem image (fs.img)
- Device tree (DTB)

### Level 2: Full Boot Chain (NEXT TARGET)

**Goal:** Single `visual_audio.mkv` container contains everything needed to boot xv6.

**Tasks:**
1. Extend `pack_shader.py` to handle arbitrary binaries (not just WGSL)
2. Pack kernel, fs.img, and DTB as pixel frames
3. Create container loader that reads all frames from VAC1 container
4. Boot from container with zero disk dependencies

**Estimated cost:** 1-2 days

## Technical Details

### Frame Format (Level 1)

```
Header (44 bytes):
  0-3:   MAGIC "EMV2"
  4-5:   Version (2)
  6-7:   Format ID (1 = WGSL text, 2 = raw binary)
  8-11:  Payload length (uint32)
  12-43: SHA-256 of payload

Payload (variable):
  Raw bytes, RGBA-encoded as pixels (4 bytes/pixel, row-major)
```

### Container Format (VAC1)

```
visual_audio.mkv (MKV container):
  Frame 0: EMV2 header + emulator shader payload
  Frame 1: EMV2 header + kernel ELF payload
  Frame 2: EMV2 header + fs.img payload
  Frame 3: EMV2 header + DTB payload (optional)
```

### Loader Entry Point

```python
# emulator_v2/boot_from_container.py (single file, ~200 lines)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'emulator_v2'))
sys.path.insert(0, str(Path(__file__).parent / 'tools'))

from pack_shader import unpack_from_memory
from va_container import VAC1Container

def boot_from_container(container_path: Path):
    """Boot xv6 from pixel-encoded container."""
    # 1. Load container
    container = VAC1Container(container_path)

    # 2. Extract frames with SHA-256 verification
    emulator_data = container.unpack_frame('emulator', verify=True)
    kernel_data = container.unpack_frame('kernel', verify=True)
    fsimg_data = container.unpack_frame('fs.img', verify=True)
    dtb_data = container.unpack_frame('dtb', verify=True) if container.has_frame('dtb') else None

    # 3. Compile shader from memory
    shader_code = emulator_data.decode('utf-8')

    # 4. Setup GPU buffers
    device = wgpu.utils.get_default_device()
    shader_module = device.create_shader_module(code=shader_code)
    # ... (same as v1, but data comes from memory not disk)

    # 5. Boot
    # ... (same execution loop as v1)

if __name__ == '__main__':
    boot_from_container(Path(sys.argv[1]))
```

## Implementation Plan

### Phase 1: Extend Packer (2 hours)
```python
# emulator_v2/pack_shader.py

FORMAT_WGSL_TEXT = 1      # WGSL source code
FORMAT_RAW_BINARY = 2     # Arbitrary binary (kernel, fs.img, etc.)

def pack_binary(src: Path, out: Path, format_id: int = FORMAT_RAW_BINARY) -> None:
    """Pack any binary as a pixel frame with SHA-256 verification."""
    # Same as pack() but with format_id=2 for raw binary
    pass

def unpack_to_memory(frame: Path) -> bytes:
    """Unpack frame to bytes without writing to disk."""
    img = Image.open(frame).convert("RGBA")
    raw = img.tobytes()
    magic, version, format_id, length, digest = HEADER.unpack(raw[:HEADER_LEN])
    payload = raw[HEADER_LEN:HEADER_LEN + length]
    actual = hashlib.sha256(payload).digest()
    if actual != digest:
        raise ValueError("SHA-256 mismatch")
    return payload
```

### Phase 2: Pack Boot Artifacts (30 minutes)
```bash
# Pack kernel
python3 -c "
from emulator_v2.pack_shader import pack_binary
from pathlib import Path
pack_binary(Path('/tmp/xv6-riscv/kernel/kernel'), Path('emulator_v2/kernel_frame.png'))
"

# Pack fs.img
python3 -c "
from emulator_v2.pack_shader import pack_binary
from pathlib import Path
pack_binary(Path('/tmp/xv6-riscv/fs.img'), Path('emulator_v2/fsimg_frame.png'))
"

# Pack DTB (if needed)
# python3 -c "from emulator_v2.pack_shader import pack_binary; ..."
```

### Phase 3: Create Container Loader (4 hours)
```python
# emulator_v2/boot_from_container.py

class FrameLoader:
    """Load pixel frames from VAC1 container."""

    def __init__(self, container_path: Path):
        self.container = VAC1Container(container_path)

    def get_frame_data(self, frame_name: str) -> bytes:
        """Extract and verify frame by name."""
        frame_path = self.container.extract_frame(frame_name)
        return unpack_to_memory(frame_path)

def boot_from_container(container_path: Path):
    """Boot xv6 from pixel-encoded container."""
    loader = FrameLoader(container_path)

    # Extract all frames
    shader_code = loader.get_frame_data('emulator').decode('utf-8')
    kernel_bytes = loader.get_frame_data('kernel')
    fsimg_bytes = loader.get_frame_data('fs.img')

    # Load ELF from bytes
    kernel_data = io.BytesIO(kernel_bytes)
    loader_elf = ELF64Loader.from_bytes(kernel_data)

    # Setup memory (kernel + fs.img)
    memory = setup_memory(loader_elf, fsimg_bytes)

    # Setup CPU state
    cpu_state = make_cpu_state(loader_elf.entry_point)

    # Boot with shader from memory
    harness = create_gpu_hardware_from_memory(shader_code, memory, cpu_state)
    # ... (dispatch loop)
```

### Phase 4: Verify Full Chain (1 hour)
```bash
# 1. Create container
python3 tools/va_container.py create \
  --name visual_audio.mkv \
  --frame emulator_frame.png \
  --frame kernel_frame.png \
  --frame fsimg_frame.png

# 2. Boot from container
python3 emulator_v2/boot_from_container.py visual_audio.mkv

# 3. Verify output
# Expected: "xv6 kernel is booting" → "$ " shell prompt
```

## Risk Assessment

### Low Risk
- Level 1 already verified (shader from pixels works)
- Boot artifacts are static binaries (kernel, fs.img)
- SHA-256 verification catches any corruption

### Medium Risk
- VAC1 container format stability needs verification
- Container loader error handling needs testing

### High Risk
- None (we're NOT pursuing DSL-generated shader)

## Success Criteria

### Level 2 Complete When:
✅ Kernel packed as pixel frame with SHA-256 verification
✅ fs.img packed as pixel frame with SHA-256 verification
✅ Container loader extracts all frames from VAC1 container
✅ xv6 boots from container to shell prompt
✅ Single command: `python3 emulator_v2/boot_from_container.py visual_audio.mkv`
✅ No disk dependencies (kernel, fs.img, shader all from container)

### Self-Hosting Complete When:
✅ visual_audio.mkv contains emulator + kernel + fs.img + DTB
✅ `python3 emulator_v2/boot_from_container.py visual_audio.mkv` boots xv6 to shell
✅ Loader is ~200 lines (no monolithic dependencies)
✅ v1 shader remains source of truth on master

## Decision Points

### Now (Level 2 or Stop?)
- **Option A:** Proceed to Level 2 (1-2 days) → full pixel boot chain
- **Option B:** Stop at Level 1 → shader verified, kernel/fs.img still on disk

### After Level 2
- **Option A:** Pursue Level 1.5 (DSL-generated shader) → known false-green risk
- **Option B:** Skip Level 1.5 → keep v1 shader as source of truth

### After Self-Hosting
- **Option A:** Integrate with VAC2 (spatial PDB) → more complex
- **Option B:** Stay with VAC1 → simpler, proven format

## Recommendation

**Proceed to Level 2 now.** Rationale:
1. Level 1 is complete and verified
2. Level 2 is low-risk (packing static binaries)
3. Self-hosting goal is within reach (1-2 days)
4. v1 remains untouched (no shader changes)
5. DSL-generated shader (Level 1.5) is a known pitfall - skip it

## Questions for User

1. **Should I proceed to Level 2 (full pixel boot chain)?**
   - Yes: I'll implement Phase 1-4 above
   - No: Level 1 is a safe checkpoint

2. **After Level 2, should we attempt Level 1.5 (DSL-generated shader)?**
   - Yes: I'll proceed with DSL tooling (risk of false-green)
   - No: Keep v1 shader as source of truth (safer)

3. **Container format preference?**
   - VAC1 (current, simpler): visual_audio.mkv
   - VAC2 (spatial PDB): More complex, better for larger payloads

Let me know which path you want to take, and I'll implement accordingly.