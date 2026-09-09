# Emulator V2 ROADMAP

## Phase 1: V2 Baseline (Feature Parity)

**Goal:** Create independent v2 workspace that's functionally identical to v1.

**Tasks:**
- [x] Create emulator/v2/ directory structure
- [x] Copy RISCV_CPU_MMU.wgsl → RISCV_CPU_MMU_V2.wgsl
- [x] Copy spatial_rv64i_cpu.py → spatial_rv64i_v2.py
- [ ] Port LUT-scatter write_mem_bytes() from v1 (76e102b fix)
- [ ] Port compute pipeline dispatch from v1
- [ ] Port CSR read/write paths from v1
- [ ] Port register file access from v1
- [ ] Add version field to WGSL state struct
- [ ] Version detection in Python wrapper
- [ ] Compatibility test suite (v1 vs v2 trace comparison)

**Verification Gate:**
```bash
# Run identical boot trace on both emulators
python3 tests/compatibility/v1_vs_v2_trace.py --kernel boot_images/alpine_vmlinuz

# Must match: PC sequence, register state, MMU translations
# Divergence tolerance: 0%
```

**Commit marker:** `emulator-v2-baseline`

---

## Phase 2: Alpine Build Infrastructure

**Goal:** Alpine Linux (running on v1) can build v2.

**Tasks:**
- [ ] Package list for Alpine:
  ```
  alpine-sdk musl-dev python3 py3-pip rust cargo git make
  ```
- [ ] Build naga (Rust WGSL compiler):
  ```bash
  cargo install naga-cli --root /usr/local
  ```
- [ ] Build minimal WGPU Python bindings:
  ```bash
  apk add py3-pip
  pip3 install wgpu --break-system-packages
  ```
- [ ] Test WGSL→SPIR-V compilation in Alpine:
  ```bash
  naga compile emulator/v2/RISCV_CPU_MMU_V2.wgsl --output format=spv > V2.spv
  ```
- [ ] Pre-compile v1 Python dependencies for Alpine:
  ```
  numpy==1.26.4
  wgpu==0.18.0
  ```

**Verification Gate:**
```bash
# Alpine (running on v1) should compile v2 shader
docker run -it --rm --gpus all alpine:edge ./self_hosting/alpine_builder.sh
# Output: V2.spv compiled successfully
```

**Commit marker:** `emulator-v2-alpine-build`

---

## Phase 3: V2 Boot Validation

**Goal:** v2 boots Alpine (built by v1).

**Tasks:**
- [ ] Alpine loads v2 Python wrapper: `from emulator.v2.spatial_rv64i_v2 import SpatialRV64ICoreV2`
- [ ] Alpine loads v2 WGSL shader: `device.create_shader_module(wgsl_code=V2.wgsl)`
- [ ] v2 boots Alpine to shell:
  ```bash
  python3 -c "
  from emulator.v2.spatial_rv64i_v2 import SpatialRV64ICoreV2
  core = SpatialRV64ICoreV2(64 * 1024 * 1024)
  # ... boot Alpine on v2 ...
  "
  ```
- [ ] Verify version field in state: `get_state()['version'] == '2.0.0'`
- [ ] Compare boot trace to v1 (should be identical)

**Verification Gate:**
```
[47.984507] Run /init as init process
~ #
```

**Commit marker:** `emulator-v2-boots-alpine`

---

## Phase 4: True Self-Hosting

**Goal:** v2 builds v3 inside Alpine.

**Tasks:**
- [ ] v2 shader includes WGSL compiler (naga) as text data
- [ ] v2 runtime can compile v3 WGSL → SPIR-V on the fly
- [ ] v2 Python wrapper can spawn v3 Python process
- [ ] v3 boots Alpine (built by v2)
- [ ] v3 builds v4, repeat

**Verification Gate:**
```bash
# v2 running inside Alpine
./v2_bootstrap.sh
# Output:
# v2 compiles v3 WGSL → SPIR-V
# v3 boots Alpine
# v3 compiles v4 WGSL → SPIR-V
# v4 boots Alpine
# ...
```

**Commit marker:** `emulator-v2-self-hosting`

---

## Phase 5: V2 Optimizations

**Goal:** Remove v1 workarounds and improve performance.

**Tasks:**
- [ ] Fix DECODED_FASTPATH deadlock (3-5× penalty removal)
- [ ] Pin execute_decoded vs decode_and_execute divergence
- [ ] Optimize UART bulk read (already in v1, verify v2)
- [ ] Optimize MMU page table walk caching
- [ ] Reduce GPU memory footprint

**Verification Gate:**
```
Before: ~497M instr, ~14 min (v1)
After:  ~497M instr, ~5 min (v2, no fast-path penalty)
```

**Commit marker:** `emulator-v2-optimized`

---

## Dependencies

```
v2 depends on:
- v1 baseline (c41448f) — frozen, never modified
- Alpine Linux (built by v1) — compilation environment
- naga WGSL compiler — shader compilation
- WGPU/Rust — GPU driver
```

**Critical Rule:** Never modify v1 after v2 baseline commit. All v1 changes must be cherry-picked to v2 manually.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| WGSL/WGPU missing from Alpine | Medium | High | Pre-compile shaders or ship static binaries |
| Python dependency loop | Low | Medium | V2+ migrates to Rust wrapper |
| v1 changes not ported to v2 | High | High | Automated diff-and-cherry-pick script |
| GPU driver incompatibility | Low | Medium | Use llvmpipe software renderer as fallback |

---

## Timeline (Estimates)

- **Phase 1:** 2-3 days (port v1 features to v2)
- **Phase 2:** 1-2 days (Alpine build environment)
- **Phase 3:** 1 day (v2 boot validation)
- **Phase 4:** 3-5 days (self-hosting infrastructure)
- **Phase 5:** 2-3 days (optimizations)

**Total:** 9-14 days to fully self-hosting v2

---

## References

- `EMULATOR_V2_PLAN.md` — Overall strategy
- `ALPINE_6.18_BOOT_STATUS.md` — v1 blocker status
- `c41448f` — v1 baseline commit
- naga WGSL compiler: https://github.com/gfx-rs/naga