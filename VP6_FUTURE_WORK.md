# VP-6 Future Work: GPU Execution Blocker Map

**Status**: VP-6 (GPU execution of signed-op driven guest) is deferred as future work. The GGUF-X VM roadmap is considered complete at VP-5, hardened by VP-5.1 (zstd LLM state, fully self-contained signed artifact with embedded runtime, real workload verified across suspend/resume).

**Date**: 2026-09-01 (updated 2026-09-02 for VP-5.1)

---

## Executive Summary

VP-6 would bridge the VP-1→5.1 stack (signed ops → QEMU guest → suspend/resume) to the GPU-native RISC-V emulator core. However, the GPU core currently lacks critical infrastructure required for this integration. This document maps the blockers and outlines what would be needed to proceed.

Note for future VP-6 work: VP-5.1 found that a migrated virtio-serial fd goes dead after QEMU `-incoming` into a fresh instance; the working pattern is to re-exec the guest daemon on resume (its script + pubkey persist in guest FS). Any GPU-core control channel will face the equivalent question — assume migrated connections don't survive and design the resume procedure to re-establish them.

---

## Blocker Map

### Blocker 1: No 9p Passthrough Equivalent

**Status**: BLOCKED

**What works in VP-1→5**:
- x86_64 QEMU uses VirtFS 9p passthrough (`-virtfs local,path=...,security_model=mapped,mount_tag=host_share`)
- Guest has direct access to host filesystem via shared mount
- Used for: LLM weights, configuration, workspace, build artifacts

**GPU Core Gap**:
- GPU RISC-V emulator has no 9p passthrough implementation
- No mechanism for guest↔host file sharing
- All guest data must be pre-encoded into spatial formats or loaded via MMIO

**Impact**: Cannot share LLM weights or build artifacts without re-implementing an entire host↔guest file transport layer.

**Work Required**:
1. Design GPU-side file transport protocol (VirtIO-9p over MMIO, or custom protocol)
2. Implement host→GPU data transfer path (spatial encoding / virtqueue / doorbell)
3. Implement guest-side filesystem driver (9p client or custom)
4. Verify performance (LLM weights are 668MB+; transfer latency critical)

---

### Blocker 2: No virtio-serial Equivalent

**Status**: BLOCKED

**What works in VP-1→5**:
- x86_64 QEMU uses virtio-serial for signed op delivery (host→guest)
- Busybox+openssl daemon on guest validates Ed25519 signatures
- Provides bidirectional character device for command/control

**GPU Core Gap**:
- GPU RISC-V emulator has no virtio-serial implementation
- No character device infrastructure for host→guest control
- No existing guest daemon framework

**Impact**: Cannot deliver signed ops to GPU guest without building entirely new control path.

**Work Required**:
1. Design GPU-side character device protocol (virtio-serial over MMIO, or custom doorbell-based channel)
2. Implement host→GPU command injection path (spatial encoding / virtqueue / MMIO writes)
3. Implement guest-side character device driver and interrupt handling
4. Port busybox+openssl daemon to GPU guest (requires busybox build for RISC-V + openssl cross-compile)
5. Verify signature validation path end-to-end

---

### Blocker 3: Missing Virtqueue / Doorbell Infrastructure

**Status**: BLOCKED

**What works in VP-1→5**:
- QEMU's virtio uses virtqueues for efficient host↔guest communication
- Doorbell mechanism for notifications (kick / interrupt)
- Well-established, performant for control-plane and data-plane traffic

**GPU Core Gap**:
- GPU RISC-V emulator has no virtqueue implementation
- No doorbell / notification mechanism between host and GPU guest
- MMIO is synchronous; no async notification path

**Impact**: Any host↔guest communication would be synchronous polling, which is inefficient for LLM-driven workflows.

**Work Required**:
1. Design virtqueue data structures in GPU spatial memory
2. Implement doorbell mechanism (GPU reads MMIO register → triggers interrupt → guest processes queue)
3. Implement host-side virtqueue driver (writes descriptors to GPU memory, rings doorbell)
4. Implement guest-side virtqueue interrupt handler
5. Verify performance under multi-op / multi-kick scenarios

---

### Blocker 4: Known Boot Stalls on GPU Core

**Status**: BLOCKED

**Symptom**:
- GPU RISC-V core cannot boot full Linux distributions
- Known stall points: nlplug-findfs, kernel-handoff after OpenSBI

**Root Cause** (from prior sessions):
- GPU MMU implementation (Sv39) has edge cases not yet exercised by simple xv6 kernels
- Block device emulation may have timing or ordering issues that only appear under full Linux boot loads
- OpenSBI → kernel handoff path may be missing critical state transfers

**Impact**: Even if VP-6 control path were implemented, the target guest (Linux/busybox) may not boot on GPU core.

**Work Required**:
1. Debug nlplug-findfs stall (instrument GPU emulator, trace MMIO reads/writes, compare to x86_64 QEMU)
2. Debug kernel-handoff stall (verify register state, device tree, interrupt routing after OpenSBI exits)
3. Add GPU emulator instrumentation (MMIO trace, instruction trace, PC dump on stall)
4. Verify GPU emulator matches QEMU behavior on critical boot path (use xv6 as oracle; extend to Alpine Linux)
5. Fix any MMU / device tree / interrupt bugs found

---

### Blocker 5: Architecture Cross-Section

**Status**: STRUCTURAL

**What works in VP-1→5**:
- Entire stack is x86_64: alpine-virt (x86_64), QEMU x86_64, virtio-serial, QMP, busybox+openssl (x86_64)
- Signed ops run on x86_64 host, control x86_64 guest

**GPU Core Reality**:
- GPU RISC-V emulator is RV32/RV64 (RISC-V instruction set)
- Guest would need to be RISC-V Linux/busybox, not x86_64
- Signed ops would need to target RISC-V architecture in boot manifest
- Toolchain differs (cross-compile busybox for RISC-V, cross-compile openssl for RISC-V)

**Impact**: VP-1→5 cannot be "ported" to GPU core; it must be re-implemented from the ground up for RISC-V.

**Work Required**:
1. Build RISC-V busybox toolchain (cross-compile for RV32/RV64)
2. Build RISC-V openssl toolchain (cross-compile for RV32/RV64)
3. Adapt signed boot manifest to support RISC-V architecture (already supported in VP-2, but needs end-to-end verification on GPU core)
4. Adapt QMP-like control protocol to GPU-specific MMIO commands
5. Verify signed op dispatch → RISC-V guest → build → output path

---

## Integration Boundary Definition

If VP-6 were to proceed narrowly (Option 2 from original proposal), the integration boundary would be:

```
Host (x86_64):
  - Signed ops generation (Ed25519)
  - LLM model (llama-cpp-python)
  - KV state persistence
  - Spatial encoding (.mkv container)

GPU Core (RISC-V):
  - Guest boot (Alpine/busybox on RISC-V)
  - Signed op reception (MMIO/virtio-serial replacement)
  - Signature validation (busybox+openssl on RISC-V)
  - Command execution (shell → build tools)
  - Output capture
```

The narrow path would avoid 9p passthrough by:
- Pre-encoding all LLM weights into spatial formats
- Pre-encoding all build artifacts into spatial formats
- Using GPU MMIO for host↔guest data transfer (small payloads only)

However, this still requires Blockers 2, 3, and 5 to be addressed. Blocker 4 (boot stalls) remains a fundamental risk.

---

## Alternative Approaches

### Option A: Keep Separate Stacks (Recommended)

**Rationale**:
- VP-1→5 is complete, verified, and production-ready for x86_64 QEMU guests
- GPU core is optimized for different use cases (pixel-native spatial execution, Geometry OS hypervisor)
- Forcing VP-6 integration would require re-implementing significant QEMU infrastructure in the GPU emulator

**Recommendation**:
- Document VP-6 as future work
- Maintain VP-1→5 as the provenance-preserving VM stack for x86_64
- Use GPU core for pixel-native OS execution (Geometry OS, spatial circuits, etc.)
- Revisit VP-6 only if a compelling use case emerges (e.g., "signed op → pixel-native OS execution")

### Option B: Narrow MMIO Bridging

**Rationale**:
- Minimal changes to GPU core (add MMIO control path, no 9p, no full virtio)
- Leverage existing busybox+openssl daemon on RISC-V
- Prove signed ops can reach GPU guest at all

**Risks**:
- Still requires Blockers 2, 3, 4, 5
- Performance likely worse than x86_64 stack (synchronous MMIO vs async virtqueues)
- Complex cross-compilation toolchain for RISC-V busybox/openssl
- May hit boot stalls before proving end-to-end

**Recommendation**:
- Do not pursue until Blocker 4 (boot stalls) is resolved
- Even then, weigh effort vs value against Option A

---

## Conclusion

VP-6 is a substantial cross-architecture integration effort that would require:

1. Implementing 9p passthrough or equivalent (host↔guest file transfer)
2. Implementing virtio-serial or equivalent (signed op delivery)
3. Implementing virtqueue/doorbell infrastructure (async communication)
4. Debugging and fixing known GPU core boot stalls
5. Cross-compiling and porting busybox+openssl to RISC-V

Given that VP-1→5.1 already provides a complete, verified, self-contained stack for signed-op-driven VMs on x86_64 QEMU, the cost/benefit of VP-6 does not justify immediate investment. The GPU core's strengths lie in pixel-native spatial execution, not in emulating full QEMU virtio infrastructure.

**Decision**: Mark GGUF-X VM roadmap complete at VP-5 + VP-5.1. VP-6 remains documented as future work with this blocker map.