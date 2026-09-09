# Emulator V2 Status — Self-Hosting Bootstrap Path

## Phase 1: V2 Baseline (Feature Parity)

**Status:** 🟡 In Progress — Skeleton created, API stubs pending

**Completed:**
- [x] `emulator/v2/` directory structure
- [x] `RISCV_CPU_MMU_V2.wgsl` copied from v1
- [x] `spatial_rv64i_v2.py` skeleton with version detection
- [x] `emulator/v2/ROADMAP.md` — full phase breakdown
- [x] `emulator/self_hosting/alpine_builder.sh` — WGSL build script
- [x] `emulator/v2/tests/compatibility/v1_vs_v2_trace.py` — test harness

**Pending:**
- [ ] Port LUT-scatter `write_mem_bytes()` from v1 (76e102b fix)
- [ ] Port compute pipeline dispatch from v1
- [ ] Port CSR read/write paths from v1
- [ ] Port register file access from v1
- [ ] Add version field to WGSL state struct
- [ ] Compatibility test suite execution

**Blockers:** None — mechanical porting from v1

---

## Phase 2: Alpine Build Infrastructure

**Status:** 🔵 Not Started — Scripts written, needs Alpine environment

**Completed:**
- [x] `alpine_builder.sh` — installs Rust, Cargo, naga
- [x] Package list defined: `alpine-sdk musl-dev python3 py3-pip rust cargo`

**Pending:**
- [ ] Test `alpine_builder.sh` in real Alpine (on v1)
- [ ] Verify naga WGSL→SPIR-V compilation
- [ ] Build minimal WGPU Python bindings
- [ ] Test v2 Python wrapper loading in Alpine

**Blockers:** Need v1 Alpine shell access

---

## Phase 3: V2 Boot Validation

**Status:** 🔵 Blocked on Phase 2

---

## Phase 4: True Self-Hosting

**Status:** 🔵 Blocked on Phase 3

---

## Phase 5: V2 Optimizations

**Status:** 🔵 Blocked on Phase 4

---

## Current Focus

**Immediate next step:** Port LUT-scatter `write_mem_bytes()` from v1 to v2.

**Why:** This is the critical 76e102b fix that enables kernel image loading. Without it, v2 can't even boot OpenSBI.

**Reference:** `tools/spatial_rv64i_cpu.py:548-580` (lines 548-580 in current v1)

---

## Version Tracking

| Component | v1 Commit | v2 Status |
|-----------|-----------|-----------|
| WGSL Shader | `c41448f` (RISCV_CPU_MMU.wgsl) | 🟡 Copied as RISCV_CPU_MMU_V2.wgsl |
| Python Wrapper | `c41448f` (spatial_rv64i_cpu.py) | 🟡 Skeleton in spatial_rv64i_v2.py |
| Version Field | None | 🟡 Added to Python wrapper (not WGSL yet) |
| Alpine Build | N/A | 🔵 Scripted, untested |

---

## Risk Assessment

| Risk | Status | Mitigation |
|------|--------|------------|
| v1 changes not ported to v2 | 🟡 Medium | Mechanical porting, test suite |
| Alpine build fails | 🔵 Unknown | Use llvmpipe fallback if needed |
| WGSL/WGPU incompatibility | 🟡 Low | v2 is feature-parity copy |
| Performance regression | 🔵 Unknown | Optimizations in Phase 5 |

---

## References

- `EMULATOR_V2_PLAN.md` — Overall strategy
- `emulator/v2/ROADMAP.md` — Phase breakdown
- `c41448f` — v1 baseline commit
- `76e102b` — LUT-scatter write fix (critical for v2)

**Last Updated:** 2026-08-31 (Session: V2 baseline creation)