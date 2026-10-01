# V5 Roadmap: The Bare-Metal Geometric OS

**Status:** DRAFT (Planning Phase)

## The V1-V4 Trajectory
Looking at the evolution from V1 to V4, a clear trajectory emerges: **the progressive elimination of symbolic abstraction layers.**

- **V1/V2:** Eliminated traditional disk files by moving storage to visual pixels, but relied on a massive host-side daemon.
- **V3:** Eliminated the host-side daemon by moving decoding to the guest UEFI.
- **V4:** Eliminated traditional window managers by moving the spatial coordinator to the GPU (Glyph Assembly), but incubated it inside Ubuntu.

**The V5 Imperative:** Eliminate the Ubuntu host OS completely. The spatial logic must ride bare-metal.

---

## The V5 Architecture: Direct-to-GPU

In V5, the bootloader will no longer hand off to a monolithic Linux kernel running systemd and GNOME. Instead, it will boot an ultra-minimal kernel whose sole purpose is to initialize the GPU and hand over all control to the Spatial Program Coordinator.

### Key Milestones for V5

#### Phase 1: The Minimal GPU Substrate (Removing Ubuntu)
We must replace the 15GB Ubuntu rootfs with a minimal embedded kernel (e.g., Alpine Linux or a custom build) that contains only:
1. The Linux Kernel (for basic hardware support).
2. DRM/KMS drivers (Direct Rendering Manager / Kernel Mode Setting).
3. Vulkan drivers (Mesa/NVIDIA).
4. `evdev` (for raw mouse/keyboard input).

#### Phase 2: Direct Framebuffer Rendering (Removing `minifb`/X11)
**Status:** COMPLETE ✓
`geos_v5/examples/v5_kms.rs` renders the GPU Window Coordinator directly to the DRM/KMS framebuffer (`/dev/dri/card0`). The GPU shader (`glyph_render.wgsl`) drives the pixels on the screen with no X11/Wayland/minifb in the path.

Verification:
- V5 Phase 2 confirmed working end-to-end with screenshot
- Window System: 3 windows (RED at 50,50, GREEN at 100,100, BLUE at 20,20)
- Display: 800×600 render centered in 1280×800 mode with gray background
- Fixed: virtio-gpu shadow buffer sync via `dirty_framebuffer()`

#### Phase 3: Raw Input Handling
**Status:** COMPLETE ✓ (verified 2026-08-24, see PHASE3_INTERACTIVE_VERIFIED_RECEIPT.md)
Without an X11 window to capture mouse events, `geos_v5` reads directly from `/dev/input/event0` using the `evdev` crate. Raw input events are translated into spatial WCB updates (`WindowEvent::click`, `WindowEvent::drag`) and dispatched to the GPU interaction shader (`glyph_interact.wgsl`).

Implementation:
- `src/evdev_input.rs`: `EvdevReader` wraps `evdev::Device` for safe event processing
- Supports BTN_LEFT clicks and REL_X/REL_Y drag motion
- Supports ABS_X/ABS_Y absolute motion (QEMU vmmouse), scaled from device range to screen pixels
- Batch-delta accumulation: diagonal drag emits ONE WindowEvent with both deltas (fixes dropped-axis bug)
- Deferred click emission: click position reflects the full SYN_REPORT batch, not stale (0,0)
- `examples/v5_interactive.rs`: Interactive KMS render loop with real mouse input
- Environment variables: `V5_DRI_CARD` (default: `/dev/dri/card0`), `V5_INPUT_DEVICE` (default: `/dev/input/event0`)
- Verified end-to-end with QEMU-monitor-injected input: click→raise (z 1→3), drag→move (x,y shifts), screendump pixel proof

#### Phase 4: Self-Hosting File Execution
**Status:** COMPLETE ✓ (verified 2026-08-24, see PHASE4_SELF_HOSTING_RECEIPT.md)
The Spatial Program Coordinator reads new `.glyph` programs or visual assets directly from the V4 PDB (Pixel Database) using spatial memory coordinates, entirely bypassing standard file systems (ext4/fat).

Implementation:
- `src/wcb.rs`: WCB layout constants + canonical seed, std-only (shared by window + loader)
- `src/spatial_loader.rs`: `WindowDef` manifest, `glyph_program` + `windows` PDB tables, encode/decode to tiled PDB, `bootstrap_from_pdb()` seeds the WCB and places program bytes at `PROGRAM_BASE`
- `examples/v5_self_host.rs`: full loop — encode spatial_coordinator.glyph + window manifest → tiled PDB PNGs → decode back → bootstrap WCB → GPU render
- Verified: program byte-identical through PDB round-trip, WCB geometry matches canonical seed, framebuffer pixel-identical to seed render on RTX 5090 (Vulkan)

#### Phase 5: Glyph Program Execution on the WCB
**Status:** COMPLETE ✓ (verified 2026-08-24, see PHASE5_GLYPH_EXECUTION_RECEIPT.md)
The PDB-loaded `.glyph` program now *executes*: a Rust glyph interpreter runs
the spatial coordinator supervisor loop against the WCB `data_memory`,
CALLR-dispatching each active window's tick routine so windows drift on the
GPU display.

Implementation:
- `src/glyph.rs`: `GlyphProgram` assembler (labels → packed `(row<<16)|col`
  addresses) + `GlyphCpu` interpreter mirroring `tools/glyph_isa_v2.py`
  `GlyphCPUv2` semantics: LDI/ADD/SUB/AND/OR/XOR/SHL/SHR/CMP/LD/ST/PRT/
  PUSH/POP/CALL/RET/JMPR/CALLR/JMP/JZ/HALT, r31-descending program-space
  stack, LD/ST over WCB `data_memory` words
- `examples/v5_glyph_exec.rs`: full loop — assemble spatial_coordinator.glyph,
  build Phase-5 manifest (real tick_addr per window), encode → PDB → decode →
  bootstrap → execute → GPU render
- Verified: 67 instructions assembled; 20,000 steps executed; WCB0.X drifted
  50→214, WCB2.Y 20→184 (164 passes, counters in lockstep); 325,272 pixel
  bytes changed on the RTX 5090 render; RED-origin pixel (60,60) flipped
  RED→background

#### Phase 6: Minimal GPU Substrate (Removing Ubuntu)
Replace the 15GB Ubuntu rootfs with a minimal embedded kernel (Alpine Linux or
custom build) containing only: Linux kernel (basic hardware support), DRM/KMS
drivers, Vulkan drivers (Mesa/NVIDIA), and evdev (raw mouse/keyboard input).

**Not started.** As of 2026-08-24/25, this remains the only way to get
raw-KMS mode with zero DRM-master contention. In the meantime, `V5` keeps
its full Ubuntu desktop, and `pixel_linux_enter.sh`/`pixel_linux_exit.sh`
(see `V5_VM_DEV_ENVIRONMENT.md`) provide a reversible, opt-in toggle
between the desktop and raw-KMS `v5_interactive` — a deliberately smaller,
interim step, not a step toward or away from this phase.

---

## V5 Boot Sequence

1. **UEFI Firmware** executes `v4_bootloader_x86.efi`.
2. Bootloader decodes the PDB and extracts the **Minimal GPU Substrate** kernel into RAM.
3. Kernel boots in < 2 seconds, initializes Vulkan and KMS.
4. Kernel executes `geos_pixel_v5` as `init` (PID 1).
5. `geos_pixel_v5` allocates the spatial WCB rows on the GPU and dispatches the native `.glyph` window coordinator.
6. The GPU takes complete control of the screen.

## Next Actionable Steps
To begin V5, we need to prototype **Phase 2 (Direct Framebuffer Rendering)**. We can test this by stripping `wc008_gui.rs` of its `minifb` dependency and using a Rust KMS/DRM crate (like `drm-rs` or `gbm`) to render our `wgpu` buffer directly to a TTY without a display server.
