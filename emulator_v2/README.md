# emulator_v2 — the xv6 RISC-V emulator, moved into pixels

## What v1 is

- **Emulator logic:** `tools/RISCV_CPU_MMU.wgsl` — RV64I + SV39 MMU, RVC, trap/CSR.
  141 KB of WGSL text on disk. wgpu compiles it to native GPU code at load.
- **Driver:** `tools/boot_xv6_gpu.py` — loads that `.wgsl` from disk, sets up
  guest RAM / CPU-state buffers, dispatches the compute shader in a loop.
- **Status:** boots real xv6 to a shell on the GPU emulator; register-for-register
  lockstep vs QEMU across the captured boot trace (see `RV64_LOCKSTEP_HARNESS_RECEIPT.md`).

Note: xv6-riscv is **RV64**, not RV32 — the "32" in "32-bit emulator" refers to the
32-bit instruction word packed one-per-RGBA-pixel, not the register width.

## What v2 changes

v1 already keeps the *data* in pixels (guest RAM, CPU struct, MMU tables live in
pixel buffers). v2 makes the *emulator itself* pixel data too, so
`visual_audio.mkv` boots a whole OS with nothing external on disk.

Four rungs, cheapest first. v2 targets rungs 1 and 1.5; rung 2 is a separate proof.

### Level 1 — ship the shader as pixels (WGSL stays source of truth)  ← DONE ✓
Encode `RISCV_CPU_MMU.wgsl` bytes into a pixel frame (4 bytes/px, ~192×192),
with a header (magic, length, format id, SHA-256). Driver reads the frame,
decodes to text, hands it to `create_shader_module`. **Zero runtime cost** —
still compiled to native.

**Status:** Complete.
- `pack_shader.py` — packer/unpacker with SHA-256 verification
- `emulator_frame.png` — 188×188 px, 141,295 bytes, sha256 `6363a645...`
- Verification: unpack → diff → byte-identical vs original (PASS)
- `boot_xv6_gpu_v2.py` — boots xv6 with shader from pixel frame (ready to test)

To verify:
```bash
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'emulator_v2')
from pack_shader import unpack
import hashlib
import subprocess

shader_frame = Path('emulator_v2/emulator_frame.png')
original_shader = Path('tools/RISCV_CPU_MMU.wgsl')
unpacked_shader = Path('/tmp/RISCV_CPU_MMU_unpacked.wgsl')

unpack(shader_frame, unpacked_shader)
orig_hash = hashlib.sha256(original_shader.read_bytes()).hexdigest()
unpack_hash = hashlib.sha256(unpacked_shader.read_bytes()).hexdigest()
result = subprocess.run(['diff', '-q', str(original_shader), str(unpacked_shader)], capture_output=True)

print(f'SHA-256 match: {orig_hash == unpack_hash}')
print(f'diff result: {result.returncode == 0}')
"
```

To test a real boot (requires xv6 kernel):
```bash
python3 emulator_v2/boot_xv6_gpu_v2.py /path/to/xv6/kernel.elf --shader-frame emulator_v2/emulator_frame.png
```

### Level 1.5 — author the emulator as a pixel-encoded DSL, generate WGSL at load
Build on `tools/riscv_wgsl_dsl.py` + `WGSL_DSL_PROTOTYPE.md` /
`WGSL_DSL_INTEGRATION_PLAN.md`. Emulator described in a compact opcode DSL,
stored as pixels; generator expands it to WGSL on the host.

**Acceptance gate:** generator output must diff byte-for-byte against the current
`RISCV_CPU_MMU.wgsl`. Only then does the DSL form become canonical and the
`.wgsl` become a build artifact.

**Status:** Not started — DSL tooling exists in tools/ but needs integration work.

### Level 2 — true in-pixel execution (separate milestone, not in v2 scope)
One minimal fixed WGSL "pixel CPU" (SpaDSL / Pixel Interpreter direction) whose
program memory is a pixel buffer; it interprets the emulator's bytecode which
interprets RISC-V. 20–100× slowdown. Self-hosting proof, not a daily driver.

**Status:** Out of scope for v2.

## Rules carried over from the container work
- Payload is **source text or the DSL**, never SPIR-V / pipeline caches (not
  portable across drivers).
- Once the emulator is data, a bad frame write corrupts it: append-only +
  directory + flock discipline (as in `tools/va_container.py`), and **verify the
  SHA-256 before every `create_shader_module`**.
- Keep the native `tools/*.wgsl` path as the dev daily-driver; v2 is the
  self-contained distribution path.

## Files
- `pack_shader.py` — Level 1 packer/unpacker. `pack` encodes a `.wgsl` to a PNG
  frame with a verified header; `unpack` decodes and checks SHA-256.
- `emulator_frame.png` — Current RISCV_CPU_MMU.wgsl as pixels (188×188, verified).
- `boot_xv6_gpu_v2.py` — xv6 boot script that loads shader from pixel frame.
- `test_shader_frame.py` — Verification script (unpack → diff → SHA-256 check).
- `README.md` — This file.

## Next Steps
1. **Test a real xv6 boot** with `boot_xv6_gpu_v2.py` to confirm the pixel-sourced
   shader works identically to the original `boot_xv6_gpu.py`.
2. **Integrate with VAC1 container** — encode emulator_frame.png as a frame in
   `visual_audio.mkv`, modify va_container.py to extract it.
3. **Proceed to Level 1.5** — integrate the DSL tooling and get it to reproduce
   the shader byte-for-byte.