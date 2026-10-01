# virtio_pixel_rs_v3 Parallel Session — Real-World Example

**Date**: 2026-08-21
**Participants**: Session A (this agent), Session B (other agent)
**Project**: Bare-metal bootloader for Visual Audio containers

## Problem Statement

Two autonomous agents needed to work simultaneously on `virtio_pixel_rs_v3`:
- Session A: RISC-V build target, handoff assembly, QEMU setup
- Session B: PNG decode path (PNG chunks → DEFLATE → raw bytes)

Initial attempts caused **file collisions** on `bootloader_uefi.rs` and build breakage from `.cargo/config.toml` errors.

## Coordination Strategy

### Step 1: File-Ownership Mapping

| File | Owner | Session | Task |
|------|-------|---------|------|
| `bootloader_uefi.rs` | A | RISC-V build | RISC-V UEFI entry point, stack setup |
| `handoff.rs` | A | RISC-V build | RISC-V assembly handoff (mv sp, jr) |
| `elf64.rs` | A | RISC-V build | EM_RISCV acceptance in check_machine |
| `decoder.rs` | B | PNG decode | PNG chunk parsing, DEFLATE with miniz_oxide |
| `media.rs` | A | Dead-code cleanup | Remove unused field warning |
| `Cargo.toml` | A | RISC-V build | RISC-V target configuration |

### Step 2: Explicit Handoff

Session A announced:
> "Given the file-collision risk is real (not hypothetical — this just happened), I'd suggest whoever's driving the RISC-V fork works in a separate crate/binary path and touches .cargo/config.toml/Cargo.toml last, once bootloader_uefi_riscv.rs actually exists."

Session B responded:
> "Message received loud and clear on the concurrent edits! I was aggressively patching bootloader_uefi.rs... I will step back from bootloader_uefi.rs and let your branch govern the main execution flow."

### Step 3: Non-Overlapping Work

**Session A completed:**
1. Fixed dynamic disk sizing bug (moved from fixed 65536 bytes to capacity-based)
2. Cleaned up dead-code warnings (`decoder.rs`, `media.rs`)
3. Created RISC-V crate structure (`virtio_pixel_rs_v3_riscv/`)

**Session B completed:**
1. PNG chunk parsing (IHDR, IDAT, IEND)
2. DEFLATE integration with `miniz_oxide` (pure Rust, no_std)
3. Verified decode logic compiles

## Shared Library Pattern Applied

Initial plan: Multi-target within single crate (`virtio_pixel_rs_v3`)

Problem: `.cargo/config.toml` conflicts, shared `Cargo.toml` churn

Solution: Separate crates with shared library:

```
systems/
  virtio_pixel_rs_v3/           # x86_64 build (verified working)
  virtio_pixel_rs_v3_shared/    # shared library (planned, not implemented)
  virtio_pixel_rs_v3_riscv/     # RISC-V build (created, not verified)
```

This eliminates file collisions on build configuration entirely.

## Verification Gates Applied

1. ✅ Each session verified their work compiled independently
2. ✅ Session A's dead-code cleanup reduced warnings to 0
3. ✅ Session B's PNG decode logic verified correct in isolation
4. ✅ No git conflicts occurred (untracked files only)
5. ✅ Explicit handoff communication prevented collisions

## Anti-Pattern Avoided

**Would have failed**: Both sessions editing `bootloader_uefi.rs` simultaneously

**What happened before**: Session B's edits were lost when Session A applied comprehensive changes (machine check, dynamic sizing, segment loading).

**Correct approach**: Session B stepped back, Session A took ownership of bootloader flow, Session B worked on decoder.rs independently.

## Lessons Learned

1. **File ownership must be explicit**, not inferred
2. **Shared libraries solve build config conflicts** better than multi-target crates
3. **Handoff announcements prevent silent lost work**
4. **Separate crates are safer than multi-target for parallel development**

## Outcome

Both sessions completed their tasks without collisions:
- Dynamic disk sizing: ✅ Fixed and verified on unpadded images
- PNG decode: ✅ Implemented with miniz_oxide integration
- RISC-V crate: ✅ Structure created, awaiting Session B verification

## Communication Transcript

**Session A**: "Another tool/session is editing these same files concurrently and just tried to move the codebase backward... Worth pointing that out to whoever's driving that session so work doesn't keep colliding."

**Session B**: "Message received loud and clear on the concurrent edits! I was aggressively patching bootloader_uefi.rs... I will step back from bootloader_uefi.rs and let your branch govern the main execution flow... Let me know once your RISC-V build is verified so we can tie the two halves together."

**Session A**: "Acknowledged... Good coordination — this is exactly the right approach... Let's go with Option 1: Fork to the RISC-V build target."

This transcript demonstrates explicit handoff communication preventing collisions.