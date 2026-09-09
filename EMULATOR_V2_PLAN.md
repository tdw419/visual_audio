# Emulator V2 Plan — Self-Hosting Path

## Goal

Create v2 of the GPU RV64 emulator that can be built by Alpine Linux running on v1, enabling a self-hosting bootstrap loop without breaking the working v1.

## Current Architecture (v1)

```
glyph_dispatch/src/riscv/RISCV_CPU_MMU.wgsl  (3,623 lines)
  ↓ compiled by WGPU
GPU Shader (runs on RTX 5090)
  ↑
tools/spatial_rv64i_cpu.py (SpatialRV64ICore, 755 lines)
  ↓ Python runtime
Host System
```

**Status:** ✅ Boots Linux 6.18.35 to interactive shell on GPU RV64 core

## V2 Workspace Structure

```
emulator/
├── v1/                          # Working baseline (frozen)
│   ├── RISCV_CPU_MMU.wgsl       # Current shader (c41448f)
│   ├── spatial_rv64i_cpu.py      # Current Python wrapper
│   ├── SPATIAL_RV64I.wgsl        # Dispatch layer
│   └── tests/                    # v1 test suite
│
├── v2/                          # Development workspace
│   ├── RISCV_CPU_MMU_V2.wgsl    # New shader (independent)
│   ├── spatial_rv64i_v2.py       # New wrapper
│   ├── self_hosting.md          # This file
│   ├── ROADMAP.md               # V2 milestones
│   └── tests/
│       └── compatibility/       # V1→V2 migration tests
│
└── self_hosting/               # Alpine can build and run v2
    ├── alpine_builder.sh        # Alpine build script
    ├── minimal_wgsl_compiler.py # WGSL→SPIR-V inside Alpine
    └── bootstrap/
        ├── kernel_config        # Alpine kernel config
        └── userland/             # Busybox + build tools
```

## Self-Hosting Strategy

### Phase 1: V1 Stability (DONE)
- ✅ v1 boots Linux to shell
- ✅ 2579bde, bc4e316 fixes committed
- ✅ c41448f frozen as baseline

### Phase 2: V2 Isolation
```bash
# Create v2 workspace from v1
mkdir -p emulator/v2
cp -r emulator/v1/*.py emulator/v2/
cp emulator/v1/RISCV_CPU_MMU.wgsl emulator/v2/RISCV_CPU_MMU_V2.wgsl

# Update all imports in v2
find emulator/v2 -name "*.py" -exec sed -i 's/from spatial_rv64i_cpu import/from spatial_rv64i_v2 import/g' {} \;
```

### Phase 3: Alpine Build Tooling
**Challenge:** WGSL requires WGPU (Rust + Vulkan), Alpine needs to compile it.

**Solution:** Ship pre-compiled minimal WGSL toolchain or use naga (Rust WGSL compiler):
1. Build naga on host, ship static binary to Alpine
2. Alpine: `naga compile input.wgsl --output format=spv > output.spv`
3. Use WebGPU/ Vulkan loaders in Alpine

**Alternative:** Rust-hosted emulator (eliminates Python dependency entirely)

### Phase 4: Self-Hosting Loop
```
v1 (GPU) boots Alpine
  ↓
Alpine builds naga/WGPU toolchain (or uses pre-compiled)
  ↓
Alpine compiles v2 WGSL shader → SPIR-V
  ↓
v2 shader loaded → v2 boots Alpine
  ↓
v2 Alpine builds v3, repeat
```

## V2 Features (Incremental)

**V2.0 — Feature Parity**
- Copy v1 exactly, rename classes
- Add `version` field to state struct
- Pass compatibility tests

**V2.1 — Self-Hosting Infrastructure**
- Alpine build script that compiles WGSL
- Minimal WGPU/naga toolchain
- Bootstrap userland (Busybox + make + gcc)

**V2.2 — Optimizations**
- Fix DECODED_FASTPATH deadlock properly (no workaround)
- Pin execute_decoded vs decode_and_execute divergence
- Reduce 3-5× penalty

**V2.3 — True Self-Hosting**
- v2 compiles v3 inside Alpine
- v3 boots and compiles v4
- Escalating kernel builds

## Immediate Steps

1. **Create v2 workspace**
   ```bash
   mkdir -p emulator/v2 emulator/self_hosting/bootstrap
   cp emulator/v1/*.py emulator/v2/
   cp emulator/v1/RISCV_CPU_MMU.wgsl emulator/v2/RISCV_CPU_MMU_V2.wgsl
   ```

2. **Add version detection**
   - Insert `emulator_version: u32` at start of RiscvCPU struct in V2 WGSL
   - Return version in Python wrapper's `get_state()`

3. **Compatibility test suite**
   - Run identical trace on v1 and v2
   - Compare PC, register state, MMU translations
   - Fail if divergence > 1%

4. **Alpine minimal build env**
   - Package list: `git make gcc musl-dev python3 rust cargo`
   - Build naga: `cargo install naga-cli`
   - Test WGSL→SPIR-V compilation

## Verification Gates

- [ ] v2 passes all v1 tests (compatibility mode)
- [ ] Alpine can compile V2 WGSL → SPIR-V
- [ ] v2 boots Alpine (built by v1)
- [ ] Alpine-on-v2 can compile v3
- [ ] v3 boots Alpine (built by v2)

## Risks & Mitigations

**Risk:** WGSL/WGPU requires modern GPU drivers in Alpine
**Mitigation:** Use Vulkan software renderer (llvmpipe) or ship pre-compiled shaders

**Risk:** Build toolchain size (>100MB)
**Mitigation:** Incremental builds, cache compiled shaders

**Risk:** Python dependency loop
**Mitigation:** V2+ should migrate to Rust for true self-hosting

## References

- `RV64_MIGRATION.md` — Prior migration notes
- `ALPINE_6.18_BOOT_STATUS.md` — Current blocker status
- `c41448f` — v1 baseline commit